"""
Multi-tool orchestrator for fraud detection pipelines.

Supports:
  - Sequential pipeline (enrich → score → classify → decide)
  - Parallel tool fan-out for batch analysis
  - Conditional branching based on risk thresholds
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from config.settings import get_settings
from tools.fraud_analysis import (
    analyze_transaction_features,
    detect_fraud_pattern,
    run_full_fraud_analysis,
)
from tools.risk_scoring import compute_risk_score
from tools.transaction_tools import get_card_velocity

logger = logging.getLogger(__name__)


@dataclass
class PipelineStep:
    name: str
    fn: Callable[..., Any]
    args: tuple = field(default_factory=tuple)
    kwargs: dict = field(default_factory=dict)
    condition: Callable[[dict], bool] | None = None  # only run if True


@dataclass
class OrchestrationResult:
    transaction_id: str
    pipeline_steps: list[str]
    step_outputs: dict[str, Any]
    final_risk_score: float
    final_risk_level: str
    recommended_action: str
    primary_pattern: str
    duration_ms: float
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "transaction_id": self.transaction_id,
            "pipeline_steps": self.pipeline_steps,
            "final_risk_score": self.final_risk_score,
            "final_risk_level": self.final_risk_level,
            "recommended_action": self.recommended_action,
            "primary_pattern": self.primary_pattern,
            "duration_ms": round(self.duration_ms, 2),
            "errors": self.errors,
            "step_outputs": self.step_outputs,
        }


class AgentOrchestrator:
    """
    Orchestrates the full fraud detection pipeline for a transaction.

    Pipeline stages:
      1. Feature extraction & risk scoring
      2. Pattern detection (parallel with velocity check)
      3. Conditional: if HIGH/CRITICAL → deep RAG analysis
      4. Final disposition decision
    """

    def __init__(self) -> None:
        self._cfg = get_settings()

    # ── synchronous pipeline ──────────────────────────────────────────────────

    def run_pipeline(self, transaction: dict[str, Any]) -> OrchestrationResult:
        """Full sequential + conditional orchestration pipeline."""
        start = time.perf_counter()
        tx_id = transaction.get("transaction_id", "UNKNOWN")
        steps_run: list[str] = []
        outputs: dict[str, Any] = {}
        errors: list[str] = []

        # Stage 1 — Risk scoring
        try:
            steps_run.append("risk_scoring")
            risk = compute_risk_score(transaction)
            outputs["risk_scoring"] = risk.to_dict()
        except Exception as exc:
            errors.append(f"risk_scoring: {exc}")
            risk = None

        # Stage 2a — Feature analysis
        try:
            steps_run.append("feature_analysis")
            outputs["feature_analysis"] = analyze_transaction_features(transaction)
        except Exception as exc:
            errors.append(f"feature_analysis: {exc}")

        # Stage 2b — Pattern detection
        try:
            steps_run.append("pattern_detection")
            outputs["pattern_detection"] = detect_fraud_pattern(transaction)
        except Exception as exc:
            errors.append(f"pattern_detection: {exc}")

        # Stage 2c — Velocity check
        try:
            steps_run.append("velocity_check")
            card_last4 = transaction.get("card_last4", "")
            outputs["velocity_check"] = get_card_velocity(card_last4, window_hours=1)
        except Exception as exc:
            errors.append(f"velocity_check: {exc}")

        # Stage 3 — Conditional: deep analysis for HIGH/CRITICAL
        final_score = risk.risk_score if risk else 0.0
        final_level = risk.risk_level if risk else "UNKNOWN"
        if risk and risk.risk_score >= self._cfg.risk_threshold_medium:
            try:
                steps_run.append("deep_analysis")
                deep = run_full_fraud_analysis(tx_id)
                outputs["deep_analysis"] = deep
                # Use deep analysis score if available
                if "final_risk_score" in deep:
                    final_score = deep["final_risk_score"]
                    final_level = deep["final_risk_level"]
            except Exception as exc:
                errors.append(f"deep_analysis: {exc}")

        # Stage 4 — Disposition
        steps_run.append("disposition")
        action = self._determine_action(final_score)
        primary_pattern = (
            outputs.get("pattern_detection", {}).get("primary_pattern", "unknown")
        )

        duration_ms = (time.perf_counter() - start) * 1000
        return OrchestrationResult(
            transaction_id=tx_id,
            pipeline_steps=steps_run,
            step_outputs=outputs,
            final_risk_score=final_score,
            final_risk_level=final_level,
            recommended_action=action,
            primary_pattern=primary_pattern,
            duration_ms=duration_ms,
            errors=errors,
        )

    def _determine_action(self, score: float) -> str:
        cfg = self._cfg
        if score >= cfg.auto_block_threshold:
            return "AUTO_BLOCK"
        if score >= cfg.risk_threshold_high:
            return "HUMAN_REVIEW"
        if score >= cfg.risk_threshold_medium:
            return "ENHANCED_MONITORING"
        if score >= cfg.risk_threshold_low:
            return "STANDARD_MONITORING"
        return "APPROVE"

    # ── async batch pipeline ──────────────────────────────────────────────────

    async def run_batch_async(
        self,
        transactions: list[dict[str, Any]],
        max_concurrency: int = 10,
    ) -> list[OrchestrationResult]:
        """Process a batch of transactions concurrently."""
        semaphore = asyncio.Semaphore(max_concurrency)

        async def _run_one(tx: dict[str, Any]) -> OrchestrationResult:
            async with semaphore:
                loop = asyncio.get_event_loop()
                return await loop.run_in_executor(None, self.run_pipeline, tx)

        tasks = [_run_one(tx) for tx in transactions]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        processed = []
        for r in results:
            if isinstance(r, Exception):
                logger.error("Batch item failed: %s", r)
            else:
                processed.append(r)
        return processed

    def run_batch(
        self,
        transactions: list[dict[str, Any]],
    ) -> list[OrchestrationResult]:
        """Synchronous batch processing."""
        return [self.run_pipeline(tx) for tx in transactions]
