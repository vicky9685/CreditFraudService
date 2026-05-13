"""
CreditFraudService — main entry point.

Modes:
  python main.py              → start FastAPI HTTP server
  python main.py --demo       → run CLI demo (no server)
  python main.py --mcp        → start MCP stdio server
  python main.py --index      → index knowledge base and exit
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

# ── Logging setup ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))


def run_api_server() -> None:
    """Start the FastAPI server with uvicorn."""
    import uvicorn
    from config.settings import get_settings
    from api.app import create_app

    cfg = get_settings()
    app = create_app()
    # PORT env var used by HF Spaces, Render, Fly.io, Railway
    port = int(os.environ.get("PORT", cfg.api_port))
    host = os.environ.get("HOST", cfg.api_host)
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level=cfg.log_level.lower(),
        reload=not cfg.is_production,
    )


def run_demo() -> None:
    """CLI demonstration of the full fraud detection pipeline."""
    print("\n" + "=" * 70)
    print("  CREDIT FRAUD DETECTION SERVICE — DEMO")
    print("=" * 70 + "\n")

    # Step 1: Generate sample data
    print("📊 Step 1: Generating synthetic transaction data...")
    from data.generator import generate_sample_dataset
    from tools.transaction_tools import store_transactions
    df = generate_sample_dataset(n=200)
    count = store_transactions(df.to_dict(orient="records"))
    fraud_count = df["is_fraud"].sum()
    print(f"   ✓ {count} transactions loaded ({fraud_count} fraudulent, {count-fraud_count} legitimate)")

    # Step 2: Index knowledge base
    print("\n📚 Step 2: Indexing knowledge base into ChromaDB...")
    from rag.retriever import FraudKnowledgeRetriever
    retriever = FraudKnowledgeRetriever()
    if not retriever.is_indexed():
        n_chunks = retriever.index_knowledge_base()
        print(f"   ✓ Indexed {n_chunks} knowledge base chunks")
    else:
        stats = retriever.collection_stats()
        print(f"   ✓ Already indexed: {stats['document_count']} chunks")

    # Step 3: Analyze sample transactions
    print("\n🔍 Step 3: Analyzing sample transactions...")
    fraud_txs = df[df["is_fraud"] == True].head(3)
    legit_txs = df[df["is_fraud"] == False].head(2)
    sample_txs = list(fraud_txs.to_dict(orient="records")) + list(legit_txs.to_dict(orient="records"))

    from tools.fraud_analysis import analyze_transaction_features, detect_fraud_pattern
    from agents.orchestrator import AgentOrchestrator
    orchestrator = AgentOrchestrator()

    for tx in sample_txs:
        result = orchestrator.run_pipeline(tx)
        fraud_label = "🚨 FRAUD" if tx["is_fraud"] else "✅ LEGIT"
        print(f"\n   Transaction {tx['transaction_id']} [{fraud_label}]")
        print(f"   Amount: ${tx['amount']:.2f} | Category: {tx['merchant_category']}")
        print(f"   Risk Score: {result.final_risk_score:.4f} | Level: {result.final_risk_level}")
        print(f"   Action: {result.recommended_action} | Pattern: {result.primary_pattern}")
        if result.errors:
            print(f"   Errors: {result.errors}")

    # Step 4: RAG Knowledge Query
    print("\n\n🧠 Step 4: RAG Knowledge Base Query...")
    query = "What are the key indicators of a velocity attack and what action should I take?"
    print(f"   Query: {query}")

    context = retriever.retrieve_as_context(query, top_k=3)
    print(f"   Retrieved {len(retriever.retrieve(query))} relevant chunks")
    print("   Top chunk preview:")
    top = retriever.retrieve(query, top_k=1)
    if top:
        print(f"   [{top[0]['source']} | sim={top[0]['similarity']}]")
        print(f"   {top[0]['content'][:300]}...")

    # Step 5: Governance check
    print("\n\n🏛️  Step 5: Policy & Governance Check...")
    from governance.policy import get_policy_enforcer
    enforcer = get_policy_enforcer()

    test_tx = {
        "transaction_id": "TEST0001",
        "amount": 9500.00,
        "ip_country": "NG",
        "velocity_1h": 12,
        "is_international": True,
    }
    test_risk = {"risk_score": 0.97, "risk_level": "CRITICAL", "top_factors": []}
    violations = enforcer.evaluate(test_tx, test_risk)
    print(f"   Test transaction (amount=$9500, ip=NG, velocity=12):")
    for v in violations:
        print(f"   ⚠️  [{v.severity}] {v.policy_name}: {v.message}")

    # Step 6: Audit log
    print("\n\n📋 Step 6: Audit Log Sample...")
    from governance.audit import get_audit_logger
    audit = get_audit_logger()
    audit.log_fraud_decision(
        transaction_id="TEST0001",
        action="AUTO_BLOCK",
        risk_score=0.97,
        risk_level="CRITICAL",
        top_factors=[{"factor": "high_risk_country", "weight": 0.30}],
        rag_sources=["fraud_patterns.md"],
        latency_ms=125.5,
    )
    recent = audit.get_recent_events(limit=1)
    if recent:
        print(f"   Last audit event: {json.dumps(recent[0], indent=2)[:400]}...")

    print("\n" + "=" * 70)
    print("  DEMO COMPLETE")
    print("  Run `python main.py` to start the API server")
    print("  API docs: http://localhost:8000/docs")
    print("=" * 70 + "\n")


def run_mcp_server() -> None:
    """Start the MCP stdio server."""
    print("Starting MCP server (stdio transport)...")
    # Load data first
    from data.generator import generate_sample_dataset
    from tools.transaction_tools import store_transactions
    df = generate_sample_dataset(n=200)
    store_transactions(df.to_dict(orient="records"))

    from rag.retriever import FraudKnowledgeRetriever
    r = FraudKnowledgeRetriever()
    if not r.is_indexed():
        r.index_knowledge_base()

    from mcp.server import run_stdio_server
    run_stdio_server()


def run_index() -> None:
    """Index the knowledge base and exit."""
    print("Indexing knowledge base...")
    from rag.retriever import FraudKnowledgeRetriever
    retriever = FraudKnowledgeRetriever()
    n = retriever.index_knowledge_base()
    stats = retriever.collection_stats()
    print(f"Indexed {n} chunks. Stats: {json.dumps(stats, indent=2)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="CreditFraudService")
    parser.add_argument("--demo", action="store_true", help="Run CLI demo")
    parser.add_argument("--mcp", action="store_true", help="Start MCP stdio server")
    parser.add_argument("--index", action="store_true", help="Index knowledge base and exit")
    args = parser.parse_args()

    if args.demo:
        run_demo()
    elif args.mcp:
        run_mcp_server()
    elif args.index:
        run_index()
    else:
        run_api_server()


if __name__ == "__main__":
    main()
