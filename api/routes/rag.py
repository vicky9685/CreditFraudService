"""RAG query endpoints."""
from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from governance.audit import get_audit_logger
from governance.monitor import get_metrics
from rag.pipeline import RAGPipeline
from rag.retriever import FraudKnowledgeRetriever
from tools.transaction_tools import get_transaction_by_id

router = APIRouter(prefix="/rag", tags=["RAG Knowledge Base"])


class RAGQueryRequest(BaseModel):
    question: str = Field(..., min_length=5, description="Natural language question")
    top_k: int = Field(default=5, ge=1, le=20)
    source_filter: str | None = Field(
        default=None,
        description="Limit to specific file: fraud_patterns.md | compliance_rules.md | "
                    "investigation_guide.md | risk_indicators.md",
    )


class RAGQueryResponse(BaseModel):
    answer: str
    sources: list[dict[str, Any]]
    model: str
    tokens_used: int
    latency_ms: float
    query: str


@router.post("/query", response_model=RAGQueryResponse, summary="Query knowledge base")
def query_knowledge_base(body: RAGQueryRequest) -> RAGQueryResponse:
    """
    Query the fraud detection knowledge base using RAG.
    Retrieves relevant chunks from ChromaDB, augments with Qwen3/Ollama.
    """
    start = time.perf_counter()
    pipeline = RAGPipeline()
    response = pipeline.query(
        question=body.question,
        top_k=body.top_k,
        source_filter=body.source_filter,
    )
    latency_ms = (time.perf_counter() - start) * 1000

    audit = get_audit_logger()
    audit.log_rag_query(
        query=body.question,
        sources_retrieved=[s["source"] for s in response.sources],
        latency_ms=latency_ms,
    )
    metrics = get_metrics()
    if response.sources:
        avg_sim = sum(s["similarity"] for s in response.sources) / len(response.sources)
        metrics.record_rag_score(avg_sim)

    return RAGQueryResponse(
        answer=response.answer,
        sources=response.sources,
        model=response.model,
        tokens_used=response.tokens_used,
        latency_ms=round(latency_ms, 2),
        query=body.question,
    )


@router.post("/analyze-transaction/{transaction_id}", summary="RAG analysis of transaction")
def rag_analyze_transaction(transaction_id: str) -> dict[str, Any]:
    """
    Run RAG-augmented analysis on a stored transaction.
    Combines transaction features with relevant knowledge base context.
    """
    tx = get_transaction_by_id(transaction_id)
    if tx is None:
        raise HTTPException(status_code=404, detail=f"Transaction '{transaction_id}' not found")

    pipeline = RAGPipeline()
    response = pipeline.query_fraud_case(tx)
    return {
        "transaction_id": transaction_id,
        "analysis": response.answer,
        "sources": [s["source"] for s in response.sources],
        "model": response.model,
        "tokens_used": response.tokens_used,
    }


@router.post("/index", summary="Index knowledge base")
def index_knowledge_base() -> dict[str, Any]:
    """
    Trigger re-indexing of the knowledge base markdown files into ChromaDB.
    Idempotent — existing embeddings are upserted.
    """
    retriever = FraudKnowledgeRetriever()
    count = retriever.index_knowledge_base()
    return {
        "status": "indexed",
        "chunks_indexed": count,
        "stats": retriever.collection_stats(),
    }


@router.get("/stats", summary="Knowledge base statistics")
def kb_stats() -> dict[str, Any]:
    """Get statistics about the indexed knowledge base."""
    retriever = FraudKnowledgeRetriever()
    return retriever.collection_stats()


@router.get("/retrieve", summary="Retrieve relevant chunks")
def retrieve_chunks(
    q: str = Query(..., description="Search query"),
    top_k: int = Query(default=5, ge=1, le=20),
    source: str | None = Query(default=None),
) -> list[dict[str, Any]]:
    """Retrieve the most relevant knowledge base chunks without LLM generation."""
    retriever = FraudKnowledgeRetriever()
    return retriever.retrieve(q, top_k=top_k, source_filter=source)
