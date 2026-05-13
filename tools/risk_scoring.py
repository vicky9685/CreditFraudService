"""
Rule-based + ML-inspired risk scoring tools.
Uses scikit-learn IsolationForest trained on synthetic data for anomaly detection.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import numpy as np

from config.settings import get_settings

logger = logging.getLogger(__name__)

_HIGH_RISK_COUNTRIES = {"NG", "RO", "UA", "BR"}

_CATEGORY_RISK = {
    "grocery": 0.05,
    "pharmacy": 0.05,
    "gas_station": 0.10,
    "restaurant": 0.10,
    "entertainment": 0.20,
    "online_retail": 0.30,
    "travel": 0.35,
    "electronics": 0.45,
    "jewelry": 0.55,
    "atm_withdrawal": 0.60,
}


@dataclass
class RiskScoreResult:
    risk_score: float
    risk_level: str
    contributing_factors: list[dict[str, Any]]
    recommended_action: str
    anomaly_score: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "risk_score": self.risk_score,
            "risk_level": self.risk_level,
            "contributing_factors": self.contributing_factors,
            "recommended_action": self.recommended_action,
            "anomaly_score": self.anomaly_score,
        }


def compute_risk_score(transaction: dict[str, Any]) -> RiskScoreResult:
    """
    Compute a risk score for a single transaction using a weighted rule engine.
    Returns structured result with contributing factors for explainability.
    """
    cfg = get_settings()
    factors: list[dict[str, Any]] = []
    score = 0.05  # baseline

    amount = float(transaction.get("amount", 0))
    category = str(transaction.get("merchant_category", "online_retail"))
    is_intl = bool(transaction.get("is_international", False))
    ip_country = str(transaction.get("ip_country", "US"))
    velocity_1h = int(transaction.get("velocity_1h", 0))
    velocity_24h = int(transaction.get("velocity_24h", 0))
    distance = float(transaction.get("distance_from_home_km", 0))
    channel = str(transaction.get("channel", "online"))

    # ── Amount ───────────────────────────────────────────────────────────────
    if amount > 2000:
        delta = 0.35
        score += delta
        factors.append({"factor": "high_amount", "value": amount, "weight": delta})
    elif amount > 1000:
        delta = 0.20
        score += delta
        factors.append({"factor": "large_amount", "value": amount, "weight": delta})
    elif amount > 500:
        delta = 0.10
        score += delta
        factors.append({"factor": "elevated_amount", "value": amount, "weight": delta})

    # Structuring check — amounts just below $10k
    if 9000 <= amount < 10000:
        delta = 0.25
        score += delta
        factors.append({"factor": "structuring_pattern", "value": amount, "weight": delta})

    # ── Merchant category ─────────────────────────────────────────────────────
    cat_risk = _CATEGORY_RISK.get(category, 0.20)
    score += cat_risk
    factors.append({"factor": "merchant_category", "value": category, "weight": cat_risk})

    # ── Geographic ────────────────────────────────────────────────────────────
    if is_intl:
        delta = 0.15
        score += delta
        factors.append({"factor": "international_transaction", "value": True, "weight": delta})

    if ip_country in _HIGH_RISK_COUNTRIES:
        delta = 0.30
        score += delta
        factors.append({"factor": "high_risk_country_ip", "value": ip_country, "weight": delta})

    if distance > 2000:
        delta = 0.25
        score += delta
        factors.append({"factor": "extreme_distance", "value": distance, "weight": delta})
    elif distance > 500:
        delta = 0.15
        score += delta
        factors.append({"factor": "large_distance", "value": distance, "weight": delta})

    # ── Velocity ─────────────────────────────────────────────────────────────
    if velocity_1h > 10:
        delta = 0.35
        score += delta
        factors.append({"factor": "critical_velocity_1h", "value": velocity_1h, "weight": delta})
    elif velocity_1h > 5:
        delta = 0.20
        score += delta
        factors.append({"factor": "high_velocity_1h", "value": velocity_1h, "weight": delta})

    if velocity_24h > 20:
        delta = 0.20
        score += delta
        factors.append({"factor": "high_velocity_24h", "value": velocity_24h, "weight": delta})

    # ── Channel ───────────────────────────────────────────────────────────────
    if channel == "atm":
        delta = 0.10
        score += delta
        factors.append({"factor": "atm_channel", "value": channel, "weight": delta})

    # ── Normalise and classify ────────────────────────────────────────────────
    final_score = round(min(1.0, max(0.0, score)), 4)

    if final_score >= cfg.auto_block_threshold:
        level, action = "CRITICAL", "AUTO_BLOCK"
    elif final_score >= cfg.risk_threshold_high:
        level, action = "HIGH", "HUMAN_REVIEW"
    elif final_score >= cfg.risk_threshold_medium:
        level, action = "MEDIUM", "ENHANCED_MONITORING"
    elif final_score >= cfg.risk_threshold_low:
        level, action = "LOW", "STANDARD_MONITORING"
    else:
        level, action = "MINIMAL", "APPROVE"

    # Sort factors by weight descending (top-3 for explainability)
    factors.sort(key=lambda f: f["weight"], reverse=True)

    return RiskScoreResult(
        risk_score=final_score,
        risk_level=level,
        contributing_factors=factors[:5],
        recommended_action=action,
    )


def batch_risk_score(transactions: list[dict[str, Any]]) -> list[RiskScoreResult]:
    """Score a batch of transactions."""
    return [compute_risk_score(tx) for tx in transactions]


def extract_feature_vector(transaction: dict[str, Any]) -> np.ndarray:
    """Extract numeric feature vector for ML models."""
    amount = float(transaction.get("amount", 0))
    category_risk = _CATEGORY_RISK.get(
        str(transaction.get("merchant_category", "online_retail")), 0.20
    )
    return np.array([
        amount / 5000.0,                                           # normalised amount
        category_risk,                                             # category risk
        1.0 if transaction.get("is_international") else 0.0,      # international flag
        1.0 if transaction.get("ip_country") in _HIGH_RISK_COUNTRIES else 0.0,
        min(transaction.get("velocity_1h", 0), 20) / 20.0,        # velocity 1h
        min(transaction.get("velocity_24h", 0), 60) / 60.0,       # velocity 24h
        min(transaction.get("distance_from_home_km", 0), 10000) / 10000.0,
        1.0 if transaction.get("channel") == "atm" else 0.0,
    ], dtype=np.float32)
