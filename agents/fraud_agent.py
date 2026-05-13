"""
Fraud Detection Agent built with Google ADK.

Architecture:
  - Uses google-adk LlmAgent with LiteLLM backend (connects to Ollama/Qwen3).
  - All fraud detection capabilities are exposed as ADK-compatible Python functions.
  - Falls back to a custom ReAct agent loop if ADK is not available.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from config.settings import get_settings
from tools.fraud_analysis import (
    analyze_transaction_features,
    detect_fraud_pattern,
    run_full_fraud_analysis,
    get_fraud_statistics,
)
from tools.transaction_tools import (
    get_transaction_by_id,
    search_transactions,
    get_card_velocity,
)
from tools.risk_scoring import compute_risk_score
from rag.pipeline import RAGPipeline

logger = logging.getLogger(__name__)

_AGENT_INSTRUCTION = """\
You are an expert credit card fraud detection agent with access to real-time
transaction data and a comprehensive fraud knowledge base.

Your capabilities:
1. Analyze individual transactions for fraud risk signals
2. Detect fraud patterns (CNP, ATO, velocity attack, geographic anomaly, etc.)
3. Query the RAG knowledge base for relevant fraud patterns and compliance rules
4. Check card velocity and historical transaction patterns
5. Generate risk scores with explainable contributing factors
6. Recommend appropriate actions (APPROVE / REVIEW / BLOCK / AUTO_BLOCK)

Always:
- Use available tools to gather evidence before making a determination
- Provide risk level (CRITICAL/HIGH/MEDIUM/LOW) with justification
- Cite relevant compliance requirements (PCI-DSS, BSA/AML, GDPR)
- Include top-3 contributing risk factors for explainability
- Recommend specific investigation steps for HIGH/CRITICAL cases
"""


# ── ADK-compatible tool functions ─────────────────────────────────────────────

def tool_analyze_transaction(transaction_id: str) -> str:
    """
    Run full fraud analysis on a transaction by ID.
    Returns risk score, detected patterns, and recommended action.
    """
    result = run_full_fraud_analysis(transaction_id)
    return json.dumps(result, default=str)


def tool_score_risk(transaction_json: str) -> str:
    """
    Compute risk score for a transaction provided as JSON string.
    Returns risk level and top contributing factors.
    """
    try:
        tx = json.loads(transaction_json)
    except json.JSONDecodeError as e:
        return json.dumps({"error": f"Invalid JSON: {e}"})
    result = compute_risk_score(tx)
    return json.dumps(result.to_dict())


def tool_detect_pattern(transaction_json: str) -> str:
    """
    Detect fraud patterns in a transaction provided as JSON string.
    Returns list of detected patterns with confidence scores.
    """
    try:
        tx = json.loads(transaction_json)
    except json.JSONDecodeError as e:
        return json.dumps({"error": f"Invalid JSON: {e}"})
    result = detect_fraud_pattern(tx)
    return json.dumps(result)


def tool_card_velocity(card_last4: str, window_hours: int = 1) -> str:
    """
    Get velocity metrics for a card in the specified time window.
    Returns transaction count, total amount, and velocity flag.
    """
    result = get_card_velocity(card_last4, window_hours)
    return json.dumps(result)


def tool_search_transactions(
    card_last4: str = "",
    merchant_category: str = "",
    is_fraud: str = "",
    limit: int = 10,
) -> str:
    """
    Search the transaction store with optional filters.
    is_fraud: 'true', 'false', or '' for all.
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
        limit=limit,
    )
    return json.dumps(results[:limit], default=str)


def tool_fraud_statistics(hours: int = 24) -> str:
    """
    Get aggregated fraud statistics for the past N hours.
    Returns fraud rate, patterns breakdown, and high-risk countries.
    """
    result = get_fraud_statistics(hours)
    return json.dumps(result)


def tool_query_knowledge_base(query: str) -> str:
    """
    Query the RAG knowledge base for fraud patterns, compliance rules,
    or investigation procedures using natural language.
    """
    pipeline = RAGPipeline()
    response = pipeline.query(query)
    return json.dumps({
        "answer": response.answer,
        "sources": [s["source"] for s in response.sources],
        "context_snippets": [s["content"][:200] for s in response.sources[:3]],
    })


_ADK_TOOLS = [
    tool_analyze_transaction,
    tool_score_risk,
    tool_detect_pattern,
    tool_card_velocity,
    tool_search_transactions,
    tool_fraud_statistics,
    tool_query_knowledge_base,
]


# ── ADK Agent factory ─────────────────────────────────────────────────────────

class FraudDetectionAgent:
    """
    Wraps the Google ADK LlmAgent with a graceful fallback to a custom
    ReAct loop when ADK/Ollama is unavailable.
    """

    def __init__(self) -> None:
        self._cfg = get_settings()
        self._adk_agent = None
        self._runner = None
        self._session_service = None
        self._use_adk = False
        self._init_adk()

    def _init_adk(self) -> None:
        try:
            from google.adk.agents import LlmAgent
            from google.adk.models.lite_llm import LiteLlm
            from google.adk.runners import Runner
            from google.adk.sessions import InMemorySessionService

            model = LiteLlm(model=self._cfg.adk_model)
            self._adk_agent = LlmAgent(
                name="fraud_detection_agent",
                model=model,
                description="Expert credit card fraud detection agent",
                instruction=_AGENT_INSTRUCTION,
                tools=_ADK_TOOLS,
            )
            self._session_service = InMemorySessionService()
            self._runner = Runner(
                agent=self._adk_agent,
                app_name=self._cfg.app_name,
                session_service=self._session_service,
            )
            self._use_adk = True
            logger.info("ADK agent initialised with model '%s'", self._cfg.adk_model)
        except Exception as exc:
            logger.warning("ADK unavailable (%s) — using built-in ReAct loop.", exc)
            self._use_adk = False

    async def run(self, user_message: str, session_id: str = "default") -> str:
        """
        Run the agent with the given message.
        Returns the agent's final text response.
        """
        if self._use_adk:
            return await self._run_adk(user_message, session_id)
        return await self._run_react(user_message)

    async def _run_adk(self, user_message: str, session_id: str) -> str:
        from google.genai import types as genai_types

        session = await self._session_service.get_session(
            app_name=self._cfg.app_name,
            user_id="system",
            session_id=session_id,
        )
        if session is None:
            session = await self._session_service.create_session(
                app_name=self._cfg.app_name,
                user_id="system",
                session_id=session_id,
            )

        content = genai_types.Content(
            role="user",
            parts=[genai_types.Part(text=user_message)],
        )
        final_response = ""
        async for event in self._runner.run_async(
            user_id="system",
            session_id=session.id,
            new_message=content,
        ):
            if event.is_final_response() and event.content:
                for part in event.content.parts:
                    if hasattr(part, "text") and part.text:
                        final_response += part.text
        return final_response or "[No response from ADK agent]"

    async def _run_react(self, user_message: str) -> str:
        """
        Minimal ReAct loop: parse the user message, call relevant tools,
        assemble a structured response.
        """
        from llm.provider import get_llm_client

        llm = get_llm_client()

        tool_context = self._gather_tool_context(user_message)
        rag_context = tool_query_knowledge_base(user_message[:200])

        system = _AGENT_INSTRUCTION
        augmented = (
            f"## Tool Results\n{tool_context}\n\n"
            f"## Knowledge Base Context\n{rag_context}\n\n"
            f"## User Request\n{user_message}"
        )
        answer, _ = llm.generate(system_prompt=system, user_message=augmented)
        return answer

    def _gather_tool_context(self, message: str) -> str:
        """Heuristic: extract transaction IDs from the message and call relevant tools."""
        import re
        parts: list[str] = []

        # Look for transaction IDs (16-char hex)
        tx_ids = re.findall(r"\b[0-9A-F]{16}\b", message.upper())
        for tx_id in tx_ids[:3]:
            result = tool_analyze_transaction(tx_id)
            parts.append(f"Transaction {tx_id}:\n{result}")

        # Look for card last-4
        card_matches = re.findall(r"\b\d{4}\b", message)
        for card in card_matches[:2]:
            vel = tool_card_velocity(card)
            parts.append(f"Card velocity {card}:\n{vel}")

        # Always include recent fraud stats
        stats = tool_fraud_statistics(24)
        parts.append(f"Recent fraud statistics:\n{stats}")

        return "\n\n".join(parts) if parts else "No direct tool matches."

    @property
    def backend(self) -> str:
        return "adk" if self._use_adk else "react_fallback"


def build_fraud_agent() -> FraudDetectionAgent:
    return FraudDetectionAgent()
