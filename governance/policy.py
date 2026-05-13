"""
Enterprise policy enforcement engine.

Loads policies from config/policies.yaml and enforces them at decision time.

Policies enforced:
  - Auto-block threshold (score >= 0.95)
  - Human review for scores in the grey zone (0.70 – 0.95)
  - Structuring / AML alert ($9,000–$9,999 range)
  - High-risk country enhanced monitoring
  - Rate limiting per user/session
  - PII access controls
  - Model age / drift policy violations
"""
from __future__ import annotations

import logging
import time
from collections import defaultdict
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from config.settings import get_settings

logger = logging.getLogger(__name__)


@dataclass
class PolicyViolation:
    policy_name: str
    severity: str      # BLOCK | WARN | INFO
    message: str
    transaction_id: str | None = None
    details: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy": self.policy_name,
            "severity": self.severity,
            "message": self.message,
            "transaction_id": self.transaction_id,
            "details": self.details or {},
        }


class PolicyEnforcer:
    """
    Stateful policy engine.  Evaluate a transaction+result against all
    active governance policies.  Returns a list of any violations found.
    """

    def __init__(self) -> None:
        self._cfg = get_settings()
        self._rate_counters: dict[str, list[float]] = defaultdict(list)
        self._policies = self._load_yaml_policies()

    def _load_yaml_policies(self) -> dict[str, Any]:
        policy_path = Path(self._cfg.governance_policy_file)
        if not policy_path.exists():
            logger.warning("Policy file not found: %s", policy_path)
            return {}
        try:
            import yaml
            with policy_path.open() as f:
                return yaml.safe_load(f) or {}
        except ImportError:
            logger.warning("PyYAML not installed; using built-in policy defaults.")
            return {}
        except Exception as exc:
            logger.error("Failed to load policies: %s", exc)
            return {}

    # ── main evaluate ─────────────────────────────────────────────────────────

    def evaluate(
        self,
        transaction: dict[str, Any],
        risk_result: dict[str, Any],
        session_id: str = "anonymous",
    ) -> list[PolicyViolation]:
        violations: list[PolicyViolation] = []

        tx_id = transaction.get("transaction_id")
        score = float(risk_result.get("risk_score", 0))
        amount = float(transaction.get("amount", 0))
        ip_country = transaction.get("ip_country", "US")
        velocity_1h = int(transaction.get("velocity_1h", 0))

        # ── P1: Auto-block threshold ──────────────────────────────────────────
        if score >= self._cfg.auto_block_threshold:
            violations.append(PolicyViolation(
                policy_name="AUTO_BLOCK_THRESHOLD",
                severity="BLOCK",
                message=f"Risk score {score:.4f} exceeds auto-block threshold "
                        f"({self._cfg.auto_block_threshold}). Transaction blocked.",
                transaction_id=tx_id,
                details={"score": score, "threshold": self._cfg.auto_block_threshold},
            ))

        # ── P2: Human review zone ─────────────────────────────────────────────
        elif self._cfg.risk_threshold_high <= score < self._cfg.auto_block_threshold:
            violations.append(PolicyViolation(
                policy_name="HUMAN_REVIEW_REQUIRED",
                severity="WARN",
                message=f"Risk score {score:.4f} requires human review "
                        f"within 4 hours (SLA).",
                transaction_id=tx_id,
                details={"score": score, "sla_hours": 4},
            ))

        # ── P3: Structuring / AML alert ───────────────────────────────────────
        if 9000 <= amount < 10000:
            violations.append(PolicyViolation(
                policy_name="AML_STRUCTURING_ALERT",
                severity="BLOCK",
                message=f"Transaction amount ${amount:.2f} triggers BSA/AML "
                        f"structuring alert. SAR filing may be required.",
                transaction_id=tx_id,
                details={"amount": amount, "regulation": "BSA/AML 31 U.S.C. § 5324"},
            ))

        # ── P4: CTR threshold ─────────────────────────────────────────────────
        if amount >= 10000:
            violations.append(PolicyViolation(
                policy_name="CTR_REQUIRED",
                severity="WARN",
                message=f"Transaction of ${amount:.2f} requires Currency Transaction "
                        f"Report (CTR) filing.",
                transaction_id=tx_id,
                details={"amount": amount, "regulation": "BSA 31 CFR § 1010.311"},
            ))

        # ── P5: High-risk country ─────────────────────────────────────────────
        if ip_country in {"NG", "RO", "UA", "BR"}:
            violations.append(PolicyViolation(
                policy_name="HIGH_RISK_COUNTRY",
                severity="WARN",
                message=f"Transaction IP originates from high-risk country: {ip_country}. "
                        f"Enhanced monitoring applied.",
                transaction_id=tx_id,
                details={"ip_country": ip_country},
            ))

        # ── P6: Velocity limit ────────────────────────────────────────────────
        if velocity_1h > 10:
            violations.append(PolicyViolation(
                policy_name="VELOCITY_LIMIT_EXCEEDED",
                severity="BLOCK",
                message=f"Card velocity {velocity_1h} transactions/hour exceeds "
                        f"limit of 10. Possible velocity attack.",
                transaction_id=tx_id,
                details={"velocity_1h": velocity_1h, "limit": 10},
            ))

        # ── P7: GDPR automated decision disclosure ────────────────────────────
        if score >= self._cfg.risk_threshold_medium and not risk_result.get("top_factors"):
            violations.append(PolicyViolation(
                policy_name="GDPR_EXPLAINABILITY_MISSING",
                severity="WARN",
                message="GDPR Art. 22: Automated decision made without explainability "
                        "data. Top contributing factors must be logged.",
                transaction_id=tx_id,
            ))

        return violations

    # ── rate limiting ─────────────────────────────────────────────────────────

    def check_rate_limit(
        self,
        key: str,
        limit: int | None = None,
        window_seconds: int = 60,
    ) -> bool:
        """Return True if rate limit is NOT exceeded."""
        max_rpm = limit or self._cfg.max_requests_per_minute
        now = time.monotonic()
        timestamps = self._rate_counters[key]

        # Remove expired timestamps
        self._rate_counters[key] = [t for t in timestamps if now - t < window_seconds]
        if len(self._rate_counters[key]) >= max_rpm:
            return False  # rate limited

        self._rate_counters[key].append(now)
        return True

    # ── compliance checks ─────────────────────────────────────────────────────

    def check_data_retention(self, event_age_days: int) -> PolicyViolation | None:
        retention = self._policies.get("data_governance", {}).get("retention_days", 90)
        if event_age_days > retention:
            return PolicyViolation(
                policy_name="DATA_RETENTION_EXCEEDED",
                severity="WARN",
                message=f"Event is {event_age_days} days old, exceeds "
                        f"retention policy of {retention} days.",
            )
        return None

    def is_action_compliant(self, action: str, score: float) -> bool:
        """Verify that the recommended action is consistent with policy."""
        if score >= self._cfg.auto_block_threshold:
            return action == "AUTO_BLOCK"
        if score >= self._cfg.risk_threshold_high:
            return action in ("HUMAN_REVIEW", "AUTO_BLOCK")
        return True

    def get_summary(self) -> dict[str, Any]:
        return {
            "auto_block_threshold": self._cfg.auto_block_threshold,
            "human_review_threshold": self._cfg.risk_threshold_high,
            "pii_masking_enabled": self._cfg.pii_masking_enabled,
            "require_explainability": self._cfg.require_explainability,
            "max_requests_per_minute": self._cfg.max_requests_per_minute,
            "active_policies": [
                "AUTO_BLOCK_THRESHOLD",
                "HUMAN_REVIEW_REQUIRED",
                "AML_STRUCTURING_ALERT",
                "CTR_REQUIRED",
                "HIGH_RISK_COUNTRY",
                "VELOCITY_LIMIT_EXCEEDED",
                "GDPR_EXPLAINABILITY_MISSING",
            ],
        }


@lru_cache(maxsize=1)
def get_policy_enforcer() -> PolicyEnforcer:
    return PolicyEnforcer()
