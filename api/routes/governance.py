"""Enterprise AI governance endpoints."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Response

from governance.audit import get_audit_logger
from governance.monitor import get_metrics
from governance.policy import get_policy_enforcer

router = APIRouter(prefix="/governance", tags=["AI Governance"])


@router.get("/audit/events", summary="Recent audit events")
def recent_audit_events(limit: int = 50) -> list[dict[str, Any]]:
    """
    Retrieve recent audit log events.
    Events are PII-masked before storage.
    """
    return get_audit_logger().get_recent_events(limit=limit)


@router.get("/audit/stats", summary="Audit log statistics")
def audit_stats() -> dict[str, Any]:
    """Summary statistics from the audit log."""
    return get_audit_logger().get_stats()


@router.get("/metrics/summary", summary="Model performance metrics")
def metrics_summary() -> dict[str, Any]:
    """Current model performance metrics with drift alerts."""
    return get_metrics().get_summary()


@router.get("/metrics/prometheus", summary="Prometheus metrics")
def prometheus_metrics() -> Response:
    """Prometheus text format metrics for scraping."""
    data = get_metrics().prometheus_metrics()
    return Response(content=data, media_type="text/plain; charset=utf-8")


@router.get("/policy/summary", summary="Active governance policies")
def policy_summary() -> dict[str, Any]:
    """List all active governance policies and their thresholds."""
    return get_policy_enforcer().get_summary()


@router.get("/health", summary="Governance system health")
def governance_health() -> dict[str, Any]:
    """Health check for all governance subsystems."""
    audit = get_audit_logger()
    metrics = get_metrics()
    policy = get_policy_enforcer()
    return {
        "audit_logging": "healthy",
        "audit_event_count": len(audit.get_recent_events(1000)),
        "policy_engine": "healthy",
        "active_policies": len(policy.get_summary()["active_policies"]),
        "metrics_collector": "healthy",
        "drift_alerts": metrics.check_drift(),
    }


@router.post("/feedback", summary="Submit prediction feedback")
def submit_feedback(body: dict[str, Any]) -> dict[str, Any]:
    """
    Submit labeled feedback for model retraining.

    Body fields:
      - transaction_id: str
      - outcome: 'confirmed_fraud' | 'false_positive' | 'true_negative' | 'inconclusive'
      - investigator_id: str
      - notes: str (optional)
    """
    from governance.audit import get_audit_logger
    audit = get_audit_logger()
    audit.log_policy_check(
        policy_name="FEEDBACK_RECEIVED",
        passed=True,
        details=body,
    )
    return {
        "status": "accepted",
        "transaction_id": body.get("transaction_id"),
        "outcome": body.get("outcome"),
        "message": "Feedback logged for model retraining pipeline.",
    }
