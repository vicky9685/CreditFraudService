"""
FastAPI application factory for CreditFraudService.

Startup sequence:
  1. Load config
  2. Generate & load synthetic transaction data
  3. Index knowledge base into ChromaDB (if not already indexed)
  4. Initialise LLM provider
  5. Start HTTP server

All routes are mounted under /api/v1/.
"""
from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config.settings import get_settings
from api.routes import fraud, rag, governance, agent

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown logic."""
    cfg = get_settings()
    logger.info("=== %s v%s starting ===", cfg.app_name, cfg.app_version)

    # Load synthetic transaction data
    try:
        from data.generator import generate_sample_dataset
        from tools.transaction_tools import store_transactions
        df = generate_sample_dataset(n=500)
        records = df.to_dict(orient="records")
        count = store_transactions(records)
        logger.info("Loaded %d synthetic transactions", count)
    except Exception as exc:
        logger.error("Failed to load sample data: %s", exc)

    # Index knowledge base into ChromaDB
    try:
        from rag.retriever import FraudKnowledgeRetriever
        retriever = FraudKnowledgeRetriever()
        if not retriever.is_indexed():
            n = retriever.index_knowledge_base()
            logger.info("Knowledge base indexed: %d chunks", n)
        else:
            stats = retriever.collection_stats()
            logger.info("Knowledge base already indexed: %d docs", stats["document_count"])
    except Exception as exc:
        logger.error("Failed to index knowledge base: %s", exc)

    # Warm up LLM
    try:
        from llm.provider import get_llm_client
        llm = get_llm_client()
        logger.info("LLM backend: %s", llm.backend)
    except Exception as exc:
        logger.warning("LLM warmup failed: %s", exc)

    logger.info("=== Startup complete ===")
    yield
    logger.info("=== %s shutting down ===", cfg.app_name)


def create_app() -> FastAPI:
    cfg = get_settings()

    app = FastAPI(
        title=cfg.app_name,
        description=(
            "Enterprise Credit Card Fraud Detection Service with RAG, "
            "ChromaDB, Qwen3/Ollama, Google ADK agents, MCP server, "
            "and enterprise AI governance."
        ),
        version=cfg.app_version,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # ── CORS ──────────────────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if not cfg.is_production else [],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Request logging + rate limiting middleware ─────────────────────────────
    @app.middleware("http")
    async def request_middleware(request: Request, call_next):
        from governance.policy import get_policy_enforcer
        enforcer = get_policy_enforcer()

        client_ip = request.client.host if request.client else "unknown"
        if not enforcer.check_rate_limit(client_ip):
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Try again in 60 seconds."},
            )

        start = time.perf_counter()
        response: Response = await call_next(request)
        latency_ms = (time.perf_counter() - start) * 1000
        response.headers["X-Response-Time-Ms"] = f"{latency_ms:.2f}"
        response.headers["X-Service-Version"] = cfg.app_version
        return response

    # ── Exception handler ─────────────────────────────────────────────────────
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.exception("Unhandled error on %s", request.url)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error", "type": type(exc).__name__},
        )

    # ── Routers ───────────────────────────────────────────────────────────────
    prefix = "/api/v1"
    app.include_router(fraud.router, prefix=prefix)
    app.include_router(rag.router, prefix=prefix)
    app.include_router(governance.router, prefix=prefix)
    app.include_router(agent.router, prefix=prefix)

    # ── Health check ──────────────────────────────────────────────────────────
    @app.get("/health", tags=["Health"], summary="Service health check")
    def health() -> dict[str, Any]:
        from vectorstore.chroma_store import get_vector_store
        from llm.provider import get_llm_client

        store_health = get_vector_store().health()
        llm_health = get_llm_client().health()
        return {
            "status": "healthy",
            "service": cfg.app_name,
            "version": cfg.app_version,
            "environment": cfg.app_env,
            "vector_store": store_health,
            "llm": llm_health,
        }

    # ── Root redirect ─────────────────────────────────────────────────────────
    @app.get("/", include_in_schema=False)
    def root():
        return {"message": f"Welcome to {cfg.app_name}", "docs": "/docs"}

    return app
