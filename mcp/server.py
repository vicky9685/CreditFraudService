"""
Model Context Protocol (MCP) server for Credit Fraud Detection.

Exposes fraud detection capabilities as MCP tools so any MCP-compatible
client (Claude Desktop, other agents) can use them.

Usage:
  python -m mcp.server          # stdio transport (default)
  python -m mcp.server --sse    # SSE transport

Tools exposed:
  - analyze_transaction        Analyze a stored transaction by ID
  - score_transaction_risk     Compute risk score from transaction JSON
  - detect_fraud_patterns      Classify fraud patterns in a transaction
  - check_card_velocity        Get card velocity metrics
  - search_fraud_transactions  Search the transaction store
  - get_fraud_statistics       Aggregated fraud stats
  - query_fraud_knowledge      RAG query on the knowledge base
  - run_full_investigation     End-to-end fraud investigation
"""
from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


def create_mcp_server():
    """Factory that builds and returns a configured FastMCP server instance."""
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as e:
        raise ImportError(
            "mcp package not installed. Run: pip install mcp>=1.3.0"
        ) from e

    from config.settings import get_settings
    from tools.fraud_analysis import (
        analyze_transaction_features,
        detect_fraud_pattern,
        run_full_fraud_analysis,
        get_fraud_statistics,
    )
    from tools.risk_scoring import compute_risk_score
    from tools.transaction_tools import (
        get_transaction_by_id,
        search_transactions,
        get_card_velocity,
    )

    cfg = get_settings()
    mcp = FastMCP(cfg.mcp_server_name)

    # ── Tool: analyze_transaction ──────────────────────────────────────────────

    @mcp.tool()
    def analyze_transaction(transaction_id: str) -> str:
        """
        Run a complete fraud analysis on a stored transaction.

        Args:
            transaction_id: The 16-character hex transaction ID.

        Returns:
            JSON with risk score, fraud signals, patterns, and recommended action.
        """
        tx = get_transaction_by_id(transaction_id)
        if tx is None:
            return json.dumps({"error": f"Transaction '{transaction_id}' not found"})
        features = analyze_transaction_features(tx)
        patterns = detect_fraud_pattern(tx)
        return json.dumps({
            "transaction_id": transaction_id,
            "features": features,
            "patterns": patterns,
        }, default=str)

    # ── Tool: score_transaction_risk ──────────────────────────────────────────

    @mcp.tool()
    def score_transaction_risk(transaction_json: str) -> str:
        """
        Compute a risk score for a transaction provided as a JSON string.

        Args:
            transaction_json: JSON string with fields: amount, merchant_category,
                is_international, ip_country, velocity_1h, velocity_24h,
                distance_from_home_km, channel.

        Returns:
            JSON with risk_score (0-1), risk_level, contributing_factors,
            and recommended_action.
        """
        try:
            tx = json.loads(transaction_json)
        except json.JSONDecodeError as e:
            return json.dumps({"error": f"Invalid JSON: {e}"})
        result = compute_risk_score(tx)
        return json.dumps(result.to_dict())

    # ── Tool: detect_fraud_patterns ───────────────────────────────────────────

    @mcp.tool()
    def detect_fraud_patterns(transaction_json: str) -> str:
        """
        Classify which fraud patterns a transaction matches.

        Args:
            transaction_json: JSON string with transaction fields.

        Returns:
            JSON with detected_patterns list, primary_pattern, and
            confidence_scores for each pattern type.
        """
        try:
            tx = json.loads(transaction_json)
        except json.JSONDecodeError as e:
            return json.dumps({"error": f"Invalid JSON: {e}"})
        return json.dumps(detect_fraud_pattern(tx))

    # ── Tool: check_card_velocity ─────────────────────────────────────────────

    @mcp.tool()
    def check_card_velocity(card_last4: str, window_hours: int = 1) -> str:
        """
        Retrieve velocity metrics for a card in a rolling time window.

        Args:
            card_last4: Last 4 digits of the card number.
            window_hours: Look-back window in hours (default: 1).

        Returns:
            JSON with transaction_count, total_amount, unique_countries,
            unique_categories, and velocity_flag.
        """
        result = get_card_velocity(card_last4, window_hours)
        return json.dumps(result)

    # ── Tool: search_fraud_transactions ───────────────────────────────────────

    @mcp.tool()
    def search_fraud_transactions(
        card_last4: str = "",
        merchant_category: str = "",
        is_fraud: str = "",
        channel: str = "",
        limit: int = 20,
    ) -> str:
        """
        Search stored transactions with optional filters.

        Args:
            card_last4: Filter by last 4 card digits (optional).
            merchant_category: Filter by category e.g. 'electronics' (optional).
            is_fraud: 'true' | 'false' | '' for all (optional).
            channel: Filter by channel: 'online' | 'pos' | 'atm' (optional).
            limit: Maximum results to return (default: 20).

        Returns:
            JSON array of matching transactions.
        """
        fraud_filter: bool | None = None
        if is_fraud.lower() == "true":
            fraud_filter = True
        elif is_fraud.lower() == "false":
            fraud_filter = False

        results = search_transactions(
            card_last4=card_last4 or None,
            merchant_category=merchant_category or None,
            is_fraud=fraud_filter,
            channel=channel or None,
            limit=limit,
        )
        return json.dumps(results, default=str)

    # ── Tool: get_fraud_statistics ────────────────────────────────────────────

    @mcp.tool()
    def get_fraud_stats(hours: int = 24) -> str:
        """
        Get aggregated fraud statistics for a time window.

        Args:
            hours: Look-back period in hours (default: 24).

        Returns:
            JSON with total_transactions, fraud_rate, fraud_by_pattern,
            total_fraud_amount, and high_risk_countries.
        """
        return json.dumps(get_fraud_statistics(hours))

    # ── Tool: query_fraud_knowledge ───────────────────────────────────────────

    @mcp.tool()
    def query_fraud_knowledge(question: str, source_filter: str = "") -> str:
        """
        Query the RAG knowledge base with a natural language question.

        Args:
            question: Natural language question about fraud detection.
            source_filter: Limit to a specific knowledge base file
                e.g. 'fraud_patterns.md' | 'compliance_rules.md' |
                'investigation_guide.md' | 'risk_indicators.md' (optional).

        Returns:
            JSON with LLM answer, source documents, and context snippets.
        """
        from rag.pipeline import RAGPipeline
        pipeline = RAGPipeline()
        response = pipeline.query(
            question,
            source_filter=source_filter or None,
        )
        return json.dumps({
            "answer": response.answer,
            "sources": [s["source"] for s in response.sources],
            "model": response.model,
        })

    # ── Tool: run_full_investigation ──────────────────────────────────────────

    @mcp.tool()
    def run_full_investigation(transaction_id: str) -> str:
        """
        Run a comprehensive end-to-end fraud investigation for a transaction.
        Combines feature analysis, pattern detection, velocity checks,
        and RAG-augmented compliance guidance.

        Args:
            transaction_id: The 16-character hex transaction ID.

        Returns:
            JSON with complete investigation report including risk score,
            patterns, compliance requirements, and recommended action.
        """
        # Base analysis
        base = run_full_fraud_analysis(transaction_id)
        if "error" in base:
            return json.dumps(base)

        # RAG augmentation
        tx = get_transaction_by_id(transaction_id)
        rag_question = (
            f"What fraud patterns and compliance requirements apply to a "
            f"${tx.get('amount',0):.2f} {tx.get('merchant_category','unknown')} "
            f"transaction from {tx.get('ip_country','unknown')} "
            f"with velocity_1h={tx.get('velocity_1h',0)} "
            f"and risk_score={tx.get('risk_score',0):.2f}?"
        )
        from rag.pipeline import RAGPipeline
        pipeline = RAGPipeline()
        rag_resp = pipeline.query(rag_question, extra_context=json.dumps(tx, default=str))

        return json.dumps({
            **base,
            "rag_analysis": rag_resp.answer,
            "rag_sources": [s["source"] for s in rag_resp.sources],
        }, default=str)

    logger.info("MCP server '%s' configured with %d tools", cfg.mcp_server_name, 7)
    return mcp


def run_stdio_server() -> None:
    """Entry point for running the MCP server over stdio."""
    import asyncio
    server = create_mcp_server()
    asyncio.run(server.run_stdio_async())


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_stdio_server()
