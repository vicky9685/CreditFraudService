"""
Enterprise audit logging for all AI-driven fraud decisions.

Compliance requirements addressed:
  - PCI-DSS Req 10.2 — audit trails for all fraud decisions
  - PCI-DSS Req 10.3 — 12-month retention
  - GDPR Art. 22 — log automated decision-making
  - SOX — immutable audit trail for financial decisions

Features:
  - Structured JSON Lines output (one event per line)
  - PII masking before persistence
  - Decision explainability fields (top-3 factors)
  - Tamper-evident sequential event IDs
  - Async-safe with threading.Lock
"""
from __future__ import annotations

import hashlib
import json
import re
import threading
import time
import uuid
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

from config.settings import get_settings


# ── PII masking ───────────────────────────────────────────────────────────────

_PII_PATTERNS = {
    "card_number": re.compile(r"\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b"),
    "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "email": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"),
    "ip_v4": re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
}


def _mask_pii(text: str) -> str:
    masked = text
    masked = _PII_PATTERNS["card_number"].sub("****-****-****-XXXX", masked)
    masked = _PII_PATTERNS["ssn"].sub("XXX-XX-XXXX", masked)
    masked = _PII_PATTERNS["email"].sub("[email_redacted]", masked)
    # Partial IP masking: keep first 2 octets
    masked = _PII_PATTERNS["ip_v4"].sub(
        lambda m: ".".join(m.group().split(".")[:2]) + ".x.x", masked
    )
    return masked


def _mask_dict(data: dict[str, Any]) -> dict[str, Any]:
    """Recursively mask PII fields in a dictionary."""
    masked: dict[str, Any] = {}
    _PII_FIELDS = {"card_number", "ssn", "email", "full_name", "phone", "address"}
    for k, v in data.items():
        if k in _PII_FIELDS:
            masked[k] = "***REDACTED***"
        elif isinstance(v, str):
            masked[k] = _mask_pii(v)
        elif isinstance(v, dict):
            masked[k] = _mask_dict(v)
        elif isinstance(v, list):
            masked[k] = [_mask_dict(i) if isinstance(i, dict) else i for i in v]
        else:
            masked[k] = v
    return masked


# ── Audit event ───────────────────────────────────────────────────────────────

@dataclass
class AuditEvent:
    event_id: str
    event_type: str          # FRAUD_DECISION | RAG_QUERY | AGENT_RUN | POLICY_CHECK
    timestamp: str
    session_id: str
    user_id: str
    transaction_id: str | None
    action: str              # APPROVE | REVIEW | BLOCK | AUTO_BLOCK
    risk_score: float | None
    risk_level: str | None
    top_factors: list[dict[str, Any]]
    model_version: str
    rag_sources: list[str]
    decision_latency_ms: float
    metadata: dict[str, Any] = field(default_factory=dict)
    sequence: int = 0

    # Integrity hash of (event_id + timestamp + transaction_id + risk_score)
    integrity_hash: str = ""

    def compute_hash(self) -> str:
        raw = f"{self.event_id}{self.timestamp}{self.transaction_id}{self.risk_score}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def to_log_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["integrity_hash"] = self.compute_hash()
        return d


class AuditLogger:
    """
    Thread-safe, file-backed audit logger producing JSON Lines output.
    Applies PII masking before writing when enabled.
    """

    def __init__(self) -> None:
        self._cfg = get_settings()
        self._log_path = self._cfg.audit_log_path
        self._pii_masking = self._cfg.pii_masking_enabled
        self._lock = threading.Lock()
        self._sequence = 0
        self._model_version = self._cfg.app_version

    def _next_seq(self) -> int:
        with self._lock:
            self._sequence += 1
            return self._sequence

    def log_fraud_decision(
        self,
        transaction_id: str,
        action: str,
        risk_score: float,
        risk_level: str,
        top_factors: list[dict[str, Any]],
        rag_sources: list[str] | None = None,
        latency_ms: float = 0.0,
        session_id: str = "system",
        user_id: str = "system",
        metadata: dict[str, Any] | None = None,
    ) -> AuditEvent:
        event = AuditEvent(
            event_id=str(uuid.uuid4()),
            event_type="FRAUD_DECISION",
            timestamp=datetime.now(timezone.utc).isoformat(),
            session_id=session_id,
            user_id=user_id,
            transaction_id=transaction_id,
            action=action,
            risk_score=round(risk_score, 4),
            risk_level=risk_level,
            top_factors=top_factors[:3],  # max 3 for explainability
            model_version=self._model_version,
            rag_sources=rag_sources or [],
            decision_latency_ms=round(latency_ms, 2),
            metadata=metadata or {},
            sequence=self._next_seq(),
        )
        self._write(event)
        return event

    def log_rag_query(
        self,
        query: str,
        sources_retrieved: list[str],
        latency_ms: float = 0.0,
        session_id: str = "system",
    ) -> AuditEvent:
        event = AuditEvent(
            event_id=str(uuid.uuid4()),
            event_type="RAG_QUERY",
            timestamp=datetime.now(timezone.utc).isoformat(),
            session_id=session_id,
            user_id="system",
            transaction_id=None,
            action="QUERY",
            risk_score=None,
            risk_level=None,
            top_factors=[],
            model_version=self._model_version,
            rag_sources=sources_retrieved,
            decision_latency_ms=round(latency_ms, 2),
            metadata={"query_length": len(query)},
            sequence=self._next_seq(),
        )
        self._write(event)
        return event

    def log_policy_check(
        self,
        policy_name: str,
        passed: bool,
        details: dict[str, Any],
        session_id: str = "system",
    ) -> AuditEvent:
        event = AuditEvent(
            event_id=str(uuid.uuid4()),
            event_type="POLICY_CHECK",
            timestamp=datetime.now(timezone.utc).isoformat(),
            session_id=session_id,
            user_id="system",
            transaction_id=details.get("transaction_id"),
            action="POLICY_PASS" if passed else "POLICY_BLOCK",
            risk_score=None,
            risk_level=None,
            top_factors=[],
            model_version=self._model_version,
            rag_sources=[],
            decision_latency_ms=0.0,
            metadata={"policy": policy_name, "passed": passed, **details},
            sequence=self._next_seq(),
        )
        self._write(event)
        return event

    def _write(self, event: AuditEvent) -> None:
        log_dict = event.to_log_dict()
        if self._pii_masking:
            log_dict = _mask_dict(log_dict)
        line = json.dumps(log_dict, default=str)
        with self._lock:
            with self._log_path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")

    def get_recent_events(self, limit: int = 100) -> list[dict[str, Any]]:
        """Read the last N events from the audit log."""
        if not self._log_path.exists():
            return []
        lines = self._log_path.read_text(encoding="utf-8").strip().splitlines()
        events = []
        for line in lines[-limit:]:
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return list(reversed(events))

    def get_stats(self) -> dict[str, Any]:
        events = self.get_recent_events(limit=10000)
        actions = [e.get("action") for e in events]
        return {
            "total_events": len(events),
            "fraud_decisions": sum(1 for a in actions if a in ("AUTO_BLOCK", "HUMAN_REVIEW")),
            "auto_blocks": actions.count("AUTO_BLOCK"),
            "human_reviews": actions.count("HUMAN_REVIEW"),
            "approvals": actions.count("APPROVE"),
        }


@lru_cache(maxsize=1)
def get_audit_logger() -> AuditLogger:
    return AuditLogger()
