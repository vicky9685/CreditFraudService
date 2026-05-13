"""
In-memory transaction store (mimics a real DB layer).
Supports get/search/velocity queries — loaded from the synthetic generator at startup.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)

# Module-level in-memory store: {transaction_id: transaction_dict}
_TRANSACTION_STORE: dict[str, dict[str, Any]] = {}


def store_transactions(transactions: list[dict[str, Any]]) -> int:
    """Bulk-load transactions into the in-memory store."""
    for tx in transactions:
        _TRANSACTION_STORE[tx["transaction_id"]] = tx
    logger.info("Stored %d transactions (%d total)", len(transactions), len(_TRANSACTION_STORE))
    return len(_TRANSACTION_STORE)


def get_transaction_by_id(transaction_id: str) -> dict[str, Any] | None:
    """Retrieve a single transaction by its ID."""
    tx = _TRANSACTION_STORE.get(transaction_id)
    if tx is None:
        logger.debug("Transaction '%s' not found", transaction_id)
    return tx


def search_transactions(
    card_last4: str | None = None,
    merchant_category: str | None = None,
    min_amount: float | None = None,
    max_amount: float | None = None,
    is_fraud: bool | None = None,
    channel: str | None = None,
    ip_country: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Filter transactions by one or more criteria."""
    results = list(_TRANSACTION_STORE.values())

    if card_last4:
        results = [t for t in results if t.get("card_last4") == card_last4]
    if merchant_category:
        results = [t for t in results if t.get("merchant_category") == merchant_category]
    if min_amount is not None:
        results = [t for t in results if float(t.get("amount", 0)) >= min_amount]
    if max_amount is not None:
        results = [t for t in results if float(t.get("amount", 0)) <= max_amount]
    if is_fraud is not None:
        results = [t for t in results if t.get("is_fraud") == is_fraud]
    if channel:
        results = [t for t in results if t.get("channel") == channel]
    if ip_country:
        results = [t for t in results if t.get("ip_country") == ip_country]

    # Sort by timestamp descending
    results.sort(key=lambda t: t.get("timestamp", ""), reverse=True)
    return results[:limit]


def get_card_velocity(card_last4: str, window_hours: int = 1) -> dict[str, Any]:
    """Return velocity metrics for a card within a rolling time window."""
    cutoff = datetime.now() - timedelta(hours=window_hours)
    card_txs = [
        t for t in _TRANSACTION_STORE.values()
        if t.get("card_last4") == card_last4
        and datetime.fromisoformat(t.get("timestamp", "2000-01-01")) >= cutoff
    ]

    total_amount = sum(float(t.get("amount", 0)) for t in card_txs)
    fraud_txs = [t for t in card_txs if t.get("is_fraud")]
    countries = list({t.get("ip_country") for t in card_txs})
    categories = list({t.get("merchant_category") for t in card_txs})

    return {
        "card_last4": card_last4,
        "window_hours": window_hours,
        "transaction_count": len(card_txs),
        "total_amount": round(total_amount, 2),
        "fraud_count": len(fraud_txs),
        "unique_countries": countries,
        "unique_categories": categories,
        "velocity_flag": len(card_txs) > 5,
    }


def get_fraud_summary(hours: int = 24) -> dict[str, Any]:
    """Aggregated fraud summary for the past N hours."""
    cutoff = datetime.now() - timedelta(hours=hours)
    recent = [
        t for t in _TRANSACTION_STORE.values()
        if datetime.fromisoformat(t.get("timestamp", "2000-01-01")) >= cutoff
    ]
    fraud = [t for t in recent if t.get("is_fraud")]

    if not recent:
        return {"period_hours": hours, "total": 0, "fraud": 0, "fraud_rate": 0.0}

    fraud_by_pattern: dict[str, int] = {}
    for t in fraud:
        pattern = t.get("fraud_pattern", "unknown") or "unknown"
        fraud_by_pattern[pattern] = fraud_by_pattern.get(pattern, 0) + 1

    return {
        "period_hours": hours,
        "total_transactions": len(recent),
        "fraud_transactions": len(fraud),
        "fraud_rate": round(len(fraud) / len(recent), 4),
        "total_fraud_amount": round(sum(float(t.get("amount", 0)) for t in fraud), 2),
        "fraud_by_pattern": fraud_by_pattern,
        "high_risk_countries": list(
            {t.get("ip_country") for t in fraud if t.get("ip_country")}
        ),
    }
