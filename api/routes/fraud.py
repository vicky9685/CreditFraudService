"""Fraud detection REST endpoints."""
from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from agents.orchestrator import AgentOrchestrator
from governance.audit import get_audit_logger
from governance.monitor import get_metrics
from governance.policy import get_policy_enforcer
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

router = APIRouter(prefix="/fraud", tags=["Fraud Detection"])


# ── Request / Response models ─────────────────────────────────────────────────

class TransactionRequest(BaseModel):
    amount: float = Field(..., gt=0, description="Transaction amount in USD")
    merchant_category: str = Field(..., description="Merchant category code")
    merchant_country: str = Field(default="US")
    is_international: bool = Field(default=False)
    ip_country: str = Field(default="US")
    velocity_1h: int = Field(default=0, ge=0)
    velocity_24h: int = Field(default=0, ge=0)
    distance_from_home_km: float = Field(default=0.0, ge=0)
    channel: str = Field(default="online")
    card_last4: str = Field(default="0000")
    transaction_id: str | None = None


class RiskScoreResponse(BaseModel):
    transaction_id: str | None
    risk_score: float
    risk_level: str
    recommended_action: str
    contributing_factors: list[dict[str, Any]]
    policy_violations: list[dict[str, Any]]
    latency_ms: float


class FraudAnalysisResponse(BaseModel):
    transaction_id: str
    risk_score: float
    risk_level: str
    recommended_action: str
    fraud_signals: list[dict[str, Any]]
    detected_patterns: list[str]
    primary_pattern: str
    card_velocity: dict[str, Any]
    policy_violations: list[dict[str, Any]]
    latency_ms: float


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/score", response_model=RiskScoreResponse, summary="Compute risk score")
def score_transaction(body: TransactionRequest) -> RiskScoreResponse:
    """
    Compute a risk score for a transaction using the rule-based engine.
    Returns risk level, contributing factors, and policy violations.
    """
    start = time.perf_counter()
    tx = body.model_dump()

    risk = compute_risk_score(tx)
    enforcer = get_policy_enforcer()
    violations = enforcer.evaluate(tx, risk.to_dict())

    latency_ms = (time.perf_counter() - start) * 1000
    audit = get_audit_logger()
    audit.log_fraud_decision(
        transaction_id=body.transaction_id or "inline",
        action=risk.recommended_action,
        risk_score=risk.risk_score,
        risk_level=risk.risk_level,
        top_factors=risk.contributing_factors[:3],
        latency_ms=latency_ms,
    )
    metrics = get_metrics()
    metrics.record_prediction(
        risk_score=risk.risk_score,
        risk_level=risk.risk_level,
        action=risk.recommended_action,
        latency_ms=latency_ms,
    )

    return RiskScoreResponse(
        transaction_id=body.transaction_id,
        risk_score=risk.risk_score,
        risk_level=risk.risk_level,
        recommended_action=risk.recommended_action,
        contributing_factors=risk.contributing_factors,
        policy_violations=[v.to_dict() for v in violations],
        latency_ms=round(latency_ms, 2),
    )


@router.post("/analyze", response_model=FraudAnalysisResponse, summary="Full fraud analysis")
def analyze_transaction(body: TransactionRequest) -> FraudAnalysisResponse:
    """
    Comprehensive fraud analysis including feature signals, pattern detection,
    velocity check, and policy evaluation.
    """
    start = time.perf_counter()
    tx = body.model_dump()
    if body.transaction_id:
        tx["transaction_id"] = body.transaction_id
    else:
        import uuid
        tx["transaction_id"] = uuid.uuid4().hex[:16].upper()

    features = analyze_transaction_features(tx)
    patterns = detect_fraud_pattern(tx)
    velocity = get_card_velocity(body.card_last4, window_hours=1)
    enforcer = get_policy_enforcer()
    violations = enforcer.evaluate(tx, features)

    latency_ms = (time.perf_counter() - start) * 1000
    get_audit_logger().log_fraud_decision(
        transaction_id=tx["transaction_id"],
        action=features["recommended_action"],
        risk_score=features["risk_score"],
        risk_level=features["risk_level"],
        top_factors=features["top_factors"],
        latency_ms=latency_ms,
    )
    get_metrics().record_prediction(
        risk_score=features["risk_score"],
        risk_level=features["risk_level"],
        action=features["recommended_action"],
        latency_ms=latency_ms,
    )

    return FraudAnalysisResponse(
        transaction_id=tx["transaction_id"],
        risk_score=features["risk_score"],
        risk_level=features["risk_level"],
        recommended_action=features["recommended_action"],
        fraud_signals=features["fraud_signals"],
        detected_patterns=patterns["detected_patterns"],
        primary_pattern=patterns["primary_pattern"],
        card_velocity=velocity,
        policy_violations=[v.to_dict() for v in violations],
        latency_ms=round(latency_ms, 2),
    )


@router.get("/transaction/{transaction_id}", summary="Get transaction analysis")
def get_transaction_analysis(transaction_id: str) -> dict[str, Any]:
    """Run full fraud analysis on a stored transaction by ID."""
    result = run_full_fraud_analysis(transaction_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.get("/transactions", summary="Search transactions")
def list_transactions(
    card_last4: str | None = Query(default=None),
    merchant_category: str | None = Query(default=None),
    is_fraud: bool | None = Query(default=None),
    channel: str | None = Query(default=None),
    limit: int = Query(default=20, le=100),
) -> list[dict[str, Any]]:
    """Search stored transactions with optional filters."""
    return search_transactions(
        card_last4=card_last4,
        merchant_category=merchant_category,
        is_fraud=is_fraud,
        channel=channel,
        limit=limit,
    )


@router.get("/velocity/{card_last4}", summary="Card velocity check")
def card_velocity(
    card_last4: str,
    window_hours: int = Query(default=1, ge=1, le=168),
) -> dict[str, Any]:
    """Get velocity metrics for a card in a time window."""
    return get_card_velocity(card_last4, window_hours)


@router.get("/statistics", summary="Fraud statistics")
def fraud_statistics(
    hours: int = Query(default=24, ge=1, le=720),
) -> dict[str, Any]:
    """Aggregated fraud statistics for the specified time window."""
    return get_fraud_statistics(hours)


@router.post("/investigate/{transaction_id}", summary="Full investigation pipeline")
def full_investigation(transaction_id: str) -> dict[str, Any]:
    """
    Run the complete orchestration pipeline including:
    feature analysis, pattern detection, velocity check,
    policy evaluation, and deep analysis for high-risk cases.
    """
    tx = get_transaction_by_id(transaction_id)
    if tx is None:
        raise HTTPException(status_code=404, detail=f"Transaction '{transaction_id}' not found")

    orchestrator = AgentOrchestrator()
    result = orchestrator.run_pipeline(tx)
    return result.to_dict()
