"""
Model performance monitoring and Prometheus metrics.

Tracks:
  - Prediction latency (histogram)
  - Risk score distribution (histogram)
  - Fraud rate over time (counter/gauge)
  - Policy violations (counter by type)
  - RAG retrieval quality (gauge)
  - Model drift alerts
"""
from __future__ import annotations

import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from functools import lru_cache
from threading import Lock
from typing import Any

logger = logging.getLogger(__name__)

try:
    from prometheus_client import Counter, Histogram, Gauge, CollectorRegistry

    _REGISTRY = CollectorRegistry()

    _PREDICTIONS_TOTAL = Counter(
        "fraud_predictions_total",
        "Total number of fraud predictions",
        ["risk_level", "action"],
        registry=_REGISTRY,
    )
    _PREDICTION_LATENCY = Histogram(
        "fraud_prediction_latency_seconds",
        "Prediction pipeline latency",
        buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
        registry=_REGISTRY,
    )
    _RISK_SCORE = Histogram(
        "fraud_risk_score",
        "Distribution of risk scores",
        buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
        registry=_REGISTRY,
    )
    _FRAUD_RATE = Gauge(
        "fraud_detection_rate",
        "Current rolling fraud detection rate (0-1)",
        registry=_REGISTRY,
    )
    _POLICY_VIOLATIONS = Counter(
        "policy_violations_total",
        "Policy violations by type",
        ["policy_name", "severity"],
        registry=_REGISTRY,
    )
    _RAG_RETRIEVAL_SCORE = Gauge(
        "rag_avg_similarity_score",
        "Average RAG retrieval similarity score",
        registry=_REGISTRY,
    )
    _PROMETHEUS_AVAILABLE = True
except ImportError:
    _PROMETHEUS_AVAILABLE = False
    logger.warning("prometheus_client not installed; metrics disabled.")


# ── In-memory rolling window metrics ─────────────────────────────────────────

@dataclass
class PredictionRecord:
    timestamp: float
    risk_score: float
    risk_level: str
    action: str
    latency_ms: float
    is_fraud: bool


class MetricsCollector:
    """
    Collects model performance metrics.
    Thread-safe rolling-window statistics + Prometheus export.
    """

    def __init__(self, window_size: int = 1000) -> None:
        self._window: deque[PredictionRecord] = deque(maxlen=window_size)
        self._policy_counts: dict[str, int] = defaultdict(int)
        self._rag_scores: deque[float] = deque(maxlen=200)
        self._lock = Lock()
        self._drift_baseline: dict[str, float] | None = None

    def record_prediction(
        self,
        risk_score: float,
        risk_level: str,
        action: str,
        latency_ms: float,
        is_fraud: bool = False,
    ) -> None:
        record = PredictionRecord(
            timestamp=time.time(),
            risk_score=risk_score,
            risk_level=risk_level,
            action=action,
            latency_ms=latency_ms,
            is_fraud=is_fraud,
        )
        with self._lock:
            self._window.append(record)

        if _PROMETHEUS_AVAILABLE:
            _PREDICTIONS_TOTAL.labels(risk_level=risk_level, action=action).inc()
            _PREDICTION_LATENCY.observe(latency_ms / 1000.0)
            _RISK_SCORE.observe(risk_score)
            self._update_fraud_rate_gauge()

    def record_policy_violation(self, policy_name: str, severity: str) -> None:
        with self._lock:
            self._policy_counts[policy_name] += 1
        if _PROMETHEUS_AVAILABLE:
            _POLICY_VIOLATIONS.labels(policy_name=policy_name, severity=severity).inc()

    def record_rag_score(self, avg_similarity: float) -> None:
        with self._lock:
            self._rag_scores.append(avg_similarity)
        if _PROMETHEUS_AVAILABLE:
            avg = sum(self._rag_scores) / len(self._rag_scores)
            _RAG_RETRIEVAL_SCORE.set(avg)

    def _update_fraud_rate_gauge(self) -> None:
        if not _PROMETHEUS_AVAILABLE or not self._window:
            return
        recent = list(self._window)[-100:]
        rate = sum(1 for r in recent if r.is_fraud) / len(recent)
        _FRAUD_RATE.set(rate)

    def set_drift_baseline(self, metrics: dict[str, float]) -> None:
        """Capture baseline metrics for drift detection."""
        with self._lock:
            self._drift_baseline = metrics.copy()

    def check_drift(self) -> list[dict[str, Any]]:
        """Compare current metrics to baseline; return alerts if drift > 5%."""
        if not self._drift_baseline or not self._window:
            return []

        current = self._compute_current_metrics()
        alerts = []
        for metric, baseline_val in self._drift_baseline.items():
            current_val = current.get(metric, baseline_val)
            if baseline_val > 0:
                drift_pct = abs(current_val - baseline_val) / baseline_val * 100
                if drift_pct > 5:
                    alerts.append({
                        "metric": metric,
                        "baseline": round(baseline_val, 4),
                        "current": round(current_val, 4),
                        "drift_pct": round(drift_pct, 2),
                        "severity": "CRITICAL" if drift_pct > 15 else "WARN",
                    })
        return alerts

    def _compute_current_metrics(self) -> dict[str, float]:
        records = list(self._window)
        if not records:
            return {}
        scores = [r.risk_score for r in records]
        latencies = [r.latency_ms for r in records]
        fraud_flags = [r.is_fraud for r in records]
        return {
            "mean_risk_score": sum(scores) / len(scores),
            "fraud_rate": sum(fraud_flags) / len(fraud_flags),
            "p95_latency_ms": sorted(latencies)[int(0.95 * len(latencies))],
            "high_risk_rate": sum(1 for r in records if r.risk_level in ("HIGH", "CRITICAL")) / len(records),
        }

    def get_summary(self) -> dict[str, Any]:
        with self._lock:
            records = list(self._window)

        if not records:
            return {"status": "no_data", "window_size": 0}

        scores = [r.risk_score for r in records]
        latencies = [r.latency_ms for r in records]
        action_counts: dict[str, int] = defaultdict(int)
        for r in records:
            action_counts[r.action] += 1

        sorted_lat = sorted(latencies)
        p95_idx = int(0.95 * len(sorted_lat))

        return {
            "window_size": len(records),
            "mean_risk_score": round(sum(scores) / len(scores), 4),
            "fraud_rate": round(sum(1 for r in records if r.is_fraud) / len(records), 4),
            "action_distribution": dict(action_counts),
            "latency_p50_ms": round(sorted_lat[len(sorted_lat) // 2], 2),
            "latency_p95_ms": round(sorted_lat[p95_idx], 2),
            "policy_violations": dict(self._policy_counts),
            "drift_alerts": self.check_drift(),
            "prometheus_enabled": _PROMETHEUS_AVAILABLE,
        }

    def prometheus_metrics(self) -> bytes:
        """Return Prometheus text format metrics."""
        if not _PROMETHEUS_AVAILABLE:
            return b"# Prometheus not available\n"
        from prometheus_client import generate_latest
        return generate_latest(_REGISTRY)


@lru_cache(maxsize=1)
def get_metrics() -> MetricsCollector:
    return MetricsCollector()
