"""Tests for governance layer: audit, policy, monitoring."""
import pytest
from governance.audit import AuditLogger, _mask_pii
from governance.policy import PolicyEnforcer
from governance.monitor import MetricsCollector


# ── PII masking ───────────────────────────────────────────────────────────────

def test_mask_credit_card():
    text = "Card number: 4111111111111111"
    assert "4111111111111111" not in _mask_pii(text)
    assert "****" in _mask_pii(text)


def test_mask_email():
    text = "Contact: user@example.com for details"
    assert "user@example.com" not in _mask_pii(text)
    assert "[email_redacted]" in _mask_pii(text)


def test_mask_ip():
    text = "Request from 192.168.1.100"
    masked = _mask_pii(text)
    assert "192.168.1.100" not in masked
    assert "192.168" in masked  # first two octets retained


# ── AuditLogger ───────────────────────────────────────────────────────────────

def test_audit_logger_writes_event(tmp_path):
    import os
    log_file = tmp_path / "audit.jsonl"
    os.environ["AUDIT_LOG_FILE"] = str(log_file)

    logger = AuditLogger()
    logger._log_path = log_file
    logger._pii_masking = False

    event = logger.log_fraud_decision(
        transaction_id="TEST001",
        action="AUTO_BLOCK",
        risk_score=0.97,
        risk_level="CRITICAL",
        top_factors=[{"factor": "high_risk_country", "weight": 0.30}],
        latency_ms=100.0,
    )
    assert event.action == "AUTO_BLOCK"
    assert log_file.exists()
    lines = log_file.read_text().strip().splitlines()
    assert len(lines) == 1

    import json
    data = json.loads(lines[0])
    assert data["event_type"] == "FRAUD_DECISION"
    assert data["risk_score"] == 0.97


def test_audit_event_integrity_hash():
    import uuid
    from governance.audit import AuditEvent
    event = AuditEvent(
        event_id=str(uuid.uuid4()),
        event_type="FRAUD_DECISION",
        timestamp="2025-01-01T00:00:00+00:00",
        session_id="s1",
        user_id="u1",
        transaction_id="TX001",
        action="APPROVE",
        risk_score=0.10,
        risk_level="LOW",
        top_factors=[],
        model_version="1.0.0",
        rag_sources=[],
        decision_latency_ms=50.0,
    )
    h1 = event.compute_hash()
    h2 = event.compute_hash()
    assert h1 == h2  # deterministic


# ── PolicyEnforcer ────────────────────────────────────────────────────────────

@pytest.fixture
def policy():
    return PolicyEnforcer()


def test_auto_block_triggers(policy):
    tx = {"transaction_id": "T1", "amount": 100, "ip_country": "US",
          "velocity_1h": 1, "velocity_24h": 2}
    risk = {"risk_score": 0.97, "risk_level": "CRITICAL", "top_factors": [{"f": 1}]}
    violations = policy.evaluate(tx, risk)
    names = [v.policy_name for v in violations]
    assert "AUTO_BLOCK_THRESHOLD" in names
    assert any(v.severity == "BLOCK" for v in violations)


def test_structuring_alert(policy):
    tx = {"transaction_id": "T2", "amount": 9500.00, "ip_country": "US",
          "velocity_1h": 0, "velocity_24h": 1}
    risk = {"risk_score": 0.40, "risk_level": "MEDIUM", "top_factors": []}
    violations = policy.evaluate(tx, risk)
    names = [v.policy_name for v in violations]
    assert "AML_STRUCTURING_ALERT" in names


def test_high_risk_country_flagged(policy):
    tx = {"transaction_id": "T3", "amount": 200, "ip_country": "NG",
          "velocity_1h": 1, "velocity_24h": 2}
    risk = {"risk_score": 0.50, "risk_level": "MEDIUM", "top_factors": []}
    violations = policy.evaluate(tx, risk)
    names = [v.policy_name for v in violations]
    assert "HIGH_RISK_COUNTRY" in names


def test_rate_limiting(policy):
    # Default limit is 60 requests per minute
    key = "test_client_rl"
    for _ in range(60):
        allowed = policy.check_rate_limit(key, limit=5, window_seconds=60)
        if not allowed:
            break
    # 6th request should be blocked
    assert not policy.check_rate_limit(key, limit=5, window_seconds=60)


# ── MetricsCollector ──────────────────────────────────────────────────────────

def test_metrics_records_prediction():
    m = MetricsCollector()
    m.record_prediction(0.75, "HIGH", "HUMAN_REVIEW", 150.0, is_fraud=True)
    summary = m.get_summary()
    assert summary["window_size"] >= 1
    assert summary["fraud_rate"] > 0


def test_drift_detection():
    m = MetricsCollector()
    m.set_drift_baseline({"mean_risk_score": 0.30, "fraud_rate": 0.05})
    # Record anomalous predictions
    for _ in range(50):
        m.record_prediction(0.85, "HIGH", "HUMAN_REVIEW", 100.0, is_fraud=True)
    alerts = m.check_drift()
    assert len(alerts) > 0
    assert any(a["metric"] == "fraud_rate" for a in alerts)
