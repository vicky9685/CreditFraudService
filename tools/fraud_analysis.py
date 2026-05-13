"""
High-level fraud analysis functions — callable as ADK tools and MCP tools.
Each function returns JSON-serialisable dicts for easy transport.
"""
from __future__ import annotations

import logging
from typing import Any

from tools.risk_scoring import compute_risk_score, RiskScoreResult
from tools.transaction_tools import (
    get_transaction_by_id,
    get_card_velocity,
    search_transactions,
    get_fraud_summary,
)

logger = logging.getLogger(__name__)

_HIGH_RISK_COUNTRIES = {"NG", "RO", "UA", "BR"}


def analyze_transaction_features(transaction: dict[str, Any]) -> dict[str, Any]:
    """
    Comprehensive feature analysis of a transaction.
    Detects all applicable fraud signals and returns a structured report.
    """
    signals: list[dict[str, Any]] = []

    amount = float(transaction.get("amount", 0))
    category = transaction.get("merchant_category", "unknown")
    is_intl = transaction.get("is_international", False)
    ip_country = transaction.get("ip_country", "US")
    velocity_1h = int(transaction.get("velocity_1h", 0))
    velocity_24h = int(transaction.get("velocity_24h", 0))
    distance = float(transaction.get("distance_from_home_km", 0))
    channel = transaction.get("channel", "unknown")

    # Velocity signals
    if velocity_1h >= 10:
        signals.append({
            "signal": "CRITICAL_VELOCITY",
            "severity": "CRITICAL",
            "detail": f"{velocity_1h} transactions in last hour (threshold: 10)",
        })
    elif velocity_1h >= 5:
        signals.append({
            "signal": "HIGH_VELOCITY",
            "severity": "HIGH",
            "detail": f"{velocity_1h} transactions in last hour (threshold: 5)",
        })

    # Geographic signals
    if ip_country in _HIGH_RISK_COUNTRIES:
        signals.append({
            "signal": "HIGH_RISK_COUNTRY",
            "severity": "HIGH",
            "detail": f"IP originates from high-risk country: {ip_country}",
        })
    if distance > 2000:
        signals.append({
            "signal": "EXTREME_GEOGRAPHIC_ANOMALY",
            "severity": "HIGH",
            "detail": f"Transaction {distance:.0f} km from cardholder home",
        })
    elif distance > 500:
        signals.append({
            "signal": "GEOGRAPHIC_ANOMALY",
            "severity": "MEDIUM",
            "detail": f"Transaction {distance:.0f} km from cardholder home",
        })

    # Amount signals
    if amount > 2000:
        signals.append({
            "signal": "LARGE_AMOUNT",
            "severity": "HIGH",
            "detail": f"Transaction amount ${amount:.2f} exceeds $2000",
        })
    if 9000 <= amount < 10000:
        signals.append({
            "signal": "STRUCTURING",
            "severity": "CRITICAL",
            "detail": f"Amount ${amount:.2f} may be structured to avoid CTR",
            "compliance": "BSA/AML — file SAR",
        })

    # Channel signals
    if channel == "atm" and amount > 500:
        signals.append({
            "signal": "LARGE_ATM_WITHDRAWAL",
            "severity": "MEDIUM",
            "detail": f"ATM withdrawal of ${amount:.2f}",
        })

    # International + high-value
    if is_intl and amount > 1000:
        signals.append({
            "signal": "INTERNATIONAL_HIGH_VALUE",
            "severity": "MEDIUM",
            "detail": f"International transaction of ${amount:.2f}",
        })

    risk_result = compute_risk_score(transaction)

    return {
        "transaction_id": transaction.get("transaction_id", "N/A"),
        "fraud_signals": signals,
        "signal_count": len(signals),
        "risk_score": risk_result.risk_score,
        "risk_level": risk_result.risk_level,
        "recommended_action": risk_result.recommended_action,
        "top_factors": risk_result.contributing_factors[:3],
    }


def detect_fraud_pattern(transaction: dict[str, Any]) -> dict[str, Any]:
    """
    Classify which fraud pattern(s) the transaction most closely matches.
    """
    patterns: list[str] = []
    confidence_scores: dict[str, float] = {}

    amount = float(transaction.get("amount", 0))
    ip_country = transaction.get("ip_country", "US")
    velocity_1h = int(transaction.get("velocity_1h", 0))
    velocity_24h = int(transaction.get("velocity_24h", 0))
    distance = float(transaction.get("distance_from_home_km", 0))
    channel = transaction.get("channel", "online")
    is_intl = transaction.get("is_international", False)
    category = transaction.get("merchant_category", "unknown")

    # Card Not Present
    cnp_score = 0.0
    if channel == "online":
        cnp_score += 0.40
    if amount > 200:
        cnp_score += 0.20
    if ip_country in _HIGH_RISK_COUNTRIES:
        cnp_score += 0.30
    confidence_scores["card_not_present"] = round(min(cnp_score, 1.0), 2)

    # Velocity Attack
    vel_score = 0.0
    if velocity_1h >= 5:
        vel_score = min(0.40 + velocity_1h * 0.06, 1.0)
    elif velocity_24h >= 15:
        vel_score = min(0.30 + velocity_24h * 0.02, 1.0)
    confidence_scores["velocity_attack"] = round(vel_score, 2)

    # Geographic Anomaly
    geo_score = 0.0
    if distance > 2000:
        geo_score = 0.85
    elif distance > 500:
        geo_score = 0.55
    if is_intl and ip_country in _HIGH_RISK_COUNTRIES:
        geo_score = min(geo_score + 0.20, 1.0)
    confidence_scores["geographic_anomaly"] = round(geo_score, 2)

    # Structuring / AML
    struct_score = 0.0
    if 9000 <= amount < 10000:
        struct_score = 0.90
    elif 4500 <= amount < 5000:
        struct_score = 0.55
    confidence_scores["structuring"] = round(struct_score, 2)

    # Card Skimming
    skim_score = 0.0
    if channel == "atm":
        skim_score += 0.30
    if distance > 100 and not is_intl:
        skim_score += 0.25
    confidence_scores["card_skimming"] = round(min(skim_score, 1.0), 2)

    # Account Takeover
    ato_score = 0.0
    if ip_country in _HIGH_RISK_COUNTRIES and channel == "online":
        ato_score += 0.40
    if category in ("electronics", "jewelry"):
        ato_score += 0.25
    confidence_scores["account_takeover"] = round(min(ato_score, 1.0), 2)

    # Collect patterns above threshold
    THRESHOLD = 0.40
    patterns = [k for k, v in confidence_scores.items() if v >= THRESHOLD]
    primary = max(confidence_scores, key=lambda k: confidence_scores[k]) if confidence_scores else "unknown"

    return {
        "detected_patterns": patterns,
        "primary_pattern": primary,
        "confidence_scores": confidence_scores,
        "pattern_count": len(patterns),
    }


def run_full_fraud_analysis(transaction_id: str) -> dict[str, Any]:
    """
    End-to-end fraud analysis pipeline for a stored transaction.
    Combines feature analysis, pattern detection, velocity, and risk scoring.
    """
    tx = get_transaction_by_id(transaction_id)
    if tx is None:
        return {"error": f"Transaction '{transaction_id}' not found", "status": "not_found"}

    feature_report = analyze_transaction_features(tx)
    pattern_report = detect_fraud_pattern(tx)
    velocity = get_card_velocity(tx["card_last4"], window_hours=1)

    return {
        "transaction_id": transaction_id,
        "status": "analyzed",
        "feature_analysis": feature_report,
        "pattern_detection": pattern_report,
        "card_velocity": velocity,
        "final_risk_score": feature_report["risk_score"],
        "final_risk_level": feature_report["risk_level"],
        "recommended_action": feature_report["recommended_action"],
        "primary_fraud_pattern": pattern_report["primary_pattern"],
    }


def get_fraud_statistics(hours: int = 24) -> dict[str, Any]:
    """Return aggregated fraud statistics for the specified time window."""
    return get_fraud_summary(hours)
