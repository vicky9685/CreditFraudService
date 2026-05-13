"""
RAG pipeline: retrieves relevant knowledge base context, then sends an
augmented prompt to the configured LLM (Ollama/Qwen3).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from config.settings import get_settings
from rag.retriever import FraudKnowledgeRetriever

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are an expert credit card fraud detection analyst with deep knowledge of:
- Fraud patterns (CNP, ATO, identity theft, velocity attacks, geographic anomalies)
- Compliance requirements (PCI-DSS, BSA/AML, GDPR, SOX)
- Investigation procedures and risk scoring
- Financial crime typologies

Use the provided context from the knowledge base to give accurate, actionable answers.
Always cite which knowledge base source supports your answer.
When assessing risk, always provide:
1. Risk Level (CRITICAL/HIGH/MEDIUM/LOW)
2. Key indicators observed
3. Recommended action
4. Relevant compliance requirements
"""


@dataclass
class RAGResponse:
    answer: str
    sources: list[dict[str, Any]] = field(default_factory=list)
    context_used: str = ""
    query: str = ""
    model: str = ""
    tokens_used: int = 0


class RAGPipeline:
    """
    Full RAG pipeline:
      1. Retrieve relevant chunks from ChromaDB via FraudKnowledgeRetriever.
      2. Augment the user query with retrieved context.
      3. Send to Ollama/Qwen3 and return structured response.
    """

    def __init__(
        self,
        retriever: FraudKnowledgeRetriever | None = None,
        llm_client: Any | None = None,
    ) -> None:
        self._cfg = get_settings()
        self._retriever = retriever or FraudKnowledgeRetriever()
        self._llm = llm_client  # injected at startup; lazy-init if None

    def _get_llm(self) -> Any:
        """Lazy-initialise Ollama client."""
        if self._llm is None:
            from llm.provider import get_llm_client
            self._llm = get_llm_client()
        return self._llm

    def query(
        self,
        question: str,
        top_k: int | None = None,
        source_filter: str | None = None,
        extra_context: str | None = None,
    ) -> RAGResponse:
        """
        Retrieve relevant knowledge, build augmented prompt, call LLM.
        """
        # 1 — Retrieve
        retrieved = self._retriever.retrieve(question, top_k=top_k, source_filter=source_filter)
        context_parts = []
        if retrieved:
            for item in retrieved:
                context_parts.append(
                    f"[{item['source']} | sim={item['similarity']}]\n{item['content']}"
                )
        if extra_context:
            context_parts.insert(0, f"[Transaction Context]\n{extra_context}")

        context_str = "\n\n---\n\n".join(context_parts) if context_parts else "No context available."

        # 2 — Build augmented prompt
        user_message = (
            f"## Relevant Knowledge Base Context\n\n{context_str}\n\n"
            f"## Question\n\n{question}"
        )

        # 3 — Call LLM
        llm = self._get_llm()
        answer, tokens = llm.generate(
            system_prompt=_SYSTEM_PROMPT,
            user_message=user_message,
        )

        return RAGResponse(
            answer=answer,
            sources=retrieved,
            context_used=context_str,
            query=question,
            model=self._cfg.ollama_model,
            tokens_used=tokens,
        )

    def query_fraud_case(
        self,
        transaction: dict[str, Any],
        include_investigation_steps: bool = True,
    ) -> RAGResponse:
        """
        Specialised RAG query that analyses a specific transaction dict.
        Builds a rich question from transaction features and retrieves
        relevant fraud patterns and compliance rules.
        """
        amount = transaction.get("amount", 0)
        category = transaction.get("merchant_category", "unknown")
        is_intl = transaction.get("is_international", False)
        ip_country = transaction.get("ip_country", "US")
        velocity_1h = transaction.get("velocity_1h", 0)
        velocity_24h = transaction.get("velocity_24h", 0)
        distance = transaction.get("distance_from_home_km", 0)
        channel = transaction.get("channel", "unknown")
        risk_score = transaction.get("risk_score", 0)

        question = (
            f"Analyze this transaction for fraud risk:\n"
            f"- Amount: ${amount:.2f}\n"
            f"- Merchant category: {category}\n"
            f"- International transaction: {is_intl}\n"
            f"- IP country: {ip_country}\n"
            f"- Transactions in last 1h: {velocity_1h}\n"
            f"- Transactions in last 24h: {velocity_24h}\n"
            f"- Distance from cardholder home: {distance:.1f} km\n"
            f"- Channel: {channel}\n"
            f"- Pre-computed risk score: {risk_score:.4f}\n\n"
        )

        if include_investigation_steps:
            question += (
                "Please provide:\n"
                "1. Fraud pattern assessment (which patterns match?)\n"
                "2. Risk level and justification\n"
                "3. Applicable compliance requirements\n"
                "4. Recommended investigation steps\n"
                "5. Disposition recommendation (approve/review/block)\n"
            )

        return self.query(question, extra_context=str(transaction))
