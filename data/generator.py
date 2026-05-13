"""Synthetic credit card fraud dataset generator."""
from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd

# Seed for reproducibility
_RNG = np.random.default_rng(42)
random.seed(42)

# ── Realistic merchant categories ─────────────────────────────────────────────
MERCHANT_CATEGORIES = {
    "grocery": {"avg_amount": 85, "std": 40, "fraud_multiplier": 0.5},
    "gas_station": {"avg_amount": 55, "std": 20, "fraud_multiplier": 0.8},
    "restaurant": {"avg_amount": 45, "std": 25, "fraud_multiplier": 0.6},
    "online_retail": {"avg_amount": 120, "std": 90, "fraud_multiplier": 3.5},
    "electronics": {"avg_amount": 350, "std": 200, "fraud_multiplier": 5.0},
    "travel": {"avg_amount": 800, "std": 500, "fraud_multiplier": 4.0},
    "pharmacy": {"avg_amount": 40, "std": 30, "fraud_multiplier": 1.5},
    "entertainment": {"avg_amount": 60, "std": 40, "fraud_multiplier": 2.0},
    "jewelry": {"avg_amount": 500, "std": 400, "fraud_multiplier": 6.0},
    "atm_withdrawal": {"avg_amount": 200, "std": 100, "fraud_multiplier": 7.0},
}

COUNTRIES = ["US", "CA", "GB", "DE", "FR", "AU", "JP", "BR", "MX", "NG", "RO", "UA"]
HIGH_RISK_COUNTRIES = {"NG", "RO", "UA", "BR"}

FRAUD_PATTERNS = [
    "card_not_present",
    "account_takeover",
    "identity_theft",
    "velocity_attack",
    "geographic_anomaly",
    "bin_attack",
    "social_engineering",
    "skimming",
]


@dataclass
class Transaction:
    transaction_id: str
    card_last4: str
    masked_card: str
    amount: float
    merchant_category: str
    merchant_name: str
    merchant_country: str
    timestamp: datetime
    is_international: bool
    channel: str          # online | pos | atm
    device_fingerprint: str
    ip_country: str
    velocity_1h: int      # transactions in past hour from this card
    velocity_24h: int     # transactions in past 24h
    distance_from_home_km: float
    is_fraud: bool
    fraud_pattern: str | None
    risk_score: float
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "transaction_id": self.transaction_id,
            "card_last4": self.card_last4,
            "masked_card": self.masked_card,
            "amount": round(self.amount, 2),
            "merchant_category": self.merchant_category,
            "merchant_name": self.merchant_name,
            "merchant_country": self.merchant_country,
            "timestamp": self.timestamp.isoformat(),
            "is_international": self.is_international,
            "channel": self.channel,
            "device_fingerprint": self.device_fingerprint,
            "ip_country": self.ip_country,
            "velocity_1h": self.velocity_1h,
            "velocity_24h": self.velocity_24h,
            "distance_from_home_km": round(self.distance_from_home_km, 1),
            "is_fraud": self.is_fraud,
            "fraud_pattern": self.fraud_pattern,
            "risk_score": round(self.risk_score, 4),
            "metadata": self.metadata,
        }


class FraudDataGenerator:
    """Generates realistic synthetic credit card transactions with fraud labels."""

    def __init__(self, seed: int = 42) -> None:
        self._rng = np.random.default_rng(seed)
        random.seed(seed)
        self._card_pool = [self._gen_card() for _ in range(200)]
        self._merchant_pool = self._build_merchants()

    # ── private helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _gen_card() -> dict[str, str]:
        last4 = f"{random.randint(1000, 9999)}"
        full = f"4{''.join([str(random.randint(0,9)) for _ in range(11)])}{last4}"
        masked = f"****-****-****-{last4}"
        home_country = random.choices(
            COUNTRIES, weights=[40, 10, 10, 8, 8, 6, 4, 4, 4, 2, 2, 2]
        )[0]
        return {"last4": last4, "masked": masked, "home_country": home_country}

    @staticmethod
    def _build_merchants() -> list[dict[str, Any]]:
        merchants = []
        for category, params in MERCHANT_CATEGORIES.items():
            for i in range(10):
                merchants.append({
                    "category": category,
                    "name": f"{category.replace('_', ' ').title()} Store {i+1}",
                    "country": random.choices(
                        COUNTRIES, weights=[50, 8, 8, 6, 6, 5, 4, 3, 3, 2, 2, 3]
                    )[0],
                    **params,
                })
        return merchants

    def _gen_amount(self, category: str, is_fraud: bool) -> float:
        params = MERCHANT_CATEGORIES[category]
        if is_fraud:
            # Fraudsters often transact near round numbers or at limits
            if random.random() < 0.3:
                return round(float(self._rng.choice([99.99, 199.99, 499.99, 999.99])), 2)
            base = params["avg_amount"] * params["fraud_multiplier"]
        else:
            base = params["avg_amount"]
        amount = float(self._rng.normal(base, params["std"]))
        return max(1.0, round(amount, 2))

    def _gen_transaction(
        self,
        base_time: datetime,
        card: dict,
        velocity_1h: int,
        velocity_24h: int,
        fraud_rate: float = 0.05,
    ) -> Transaction:
        merchant = random.choice(self._merchant_pool)
        is_fraud = self._rng.random() < fraud_rate

        # Escalate fraud probability for high-risk factors
        if merchant["category"] in ("electronics", "jewelry", "atm_withdrawal"):
            is_fraud = is_fraud or (self._rng.random() < 0.08)

        fraud_pattern: str | None = None
        if is_fraud:
            fraud_pattern = random.choice(FRAUD_PATTERNS)

        amount = self._gen_amount(merchant["category"], is_fraud)

        # Channel: fraudsters prefer online / atm
        if is_fraud:
            channel = random.choices(["online", "pos", "atm"], weights=[55, 25, 20])[0]
        else:
            channel = random.choices(["online", "pos", "atm"], weights=[35, 55, 10])[0]

        ip_country = card["home_country"]
        if is_fraud and fraud_pattern in ("geographic_anomaly", "account_takeover"):
            ip_country = random.choice(list(HIGH_RISK_COUNTRIES))

        is_international = merchant["country"] != card["home_country"]
        if is_fraud and fraud_pattern == "geographic_anomaly":
            is_international = True

        distance = float(self._rng.exponential(20))
        if is_fraud and is_international:
            distance = float(self._rng.uniform(500, 10000))

        # Velocity abuse
        if is_fraud and fraud_pattern == "velocity_attack":
            velocity_1h = int(self._rng.integers(8, 25))
            velocity_24h = int(self._rng.integers(20, 60))

        risk_score = self._compute_heuristic_risk(
            amount=amount,
            category=merchant["category"],
            is_international=is_international,
            ip_country=ip_country,
            velocity_1h=velocity_1h,
            velocity_24h=velocity_24h,
            distance=distance,
            channel=channel,
            is_fraud=is_fraud,
        )

        tx_id = hashlib.sha256(
            f"{card['last4']}{base_time.isoformat()}{amount}".encode()
        ).hexdigest()[:16].upper()

        return Transaction(
            transaction_id=tx_id,
            card_last4=card["last4"],
            masked_card=card["masked"],
            amount=amount,
            merchant_category=merchant["category"],
            merchant_name=merchant["name"],
            merchant_country=merchant["country"],
            timestamp=base_time,
            is_international=is_international,
            channel=channel,
            device_fingerprint=hashlib.md5(
                f"{card['last4']}{channel}".encode()
            ).hexdigest()[:12],
            ip_country=ip_country,
            velocity_1h=velocity_1h,
            velocity_24h=velocity_24h,
            distance_from_home_km=distance,
            is_fraud=is_fraud,
            fraud_pattern=fraud_pattern,
            risk_score=risk_score,
            metadata={
                "card_home_country": card["home_country"],
                "processing_time_ms": int(self._rng.integers(50, 3000)),
            },
        )

    @staticmethod
    def _compute_heuristic_risk(
        amount: float,
        category: str,
        is_international: bool,
        ip_country: str,
        velocity_1h: int,
        velocity_24h: int,
        distance: float,
        channel: str,
        is_fraud: bool,
    ) -> float:
        score = 0.05  # base
        if amount > 500:
            score += 0.15
        if amount > 1000:
            score += 0.20
        if category in ("electronics", "jewelry", "atm_withdrawal"):
            score += 0.10
        if is_international:
            score += 0.15
        if ip_country in HIGH_RISK_COUNTRIES:
            score += 0.25
        if velocity_1h > 5:
            score += 0.20
        if velocity_24h > 15:
            score += 0.15
        if distance > 500:
            score += 0.20
        if channel == "atm":
            score += 0.05
        # Add noise
        noise = random.gauss(0, 0.05)
        if is_fraud:
            score += 0.20 + noise
        else:
            score += noise
        return round(max(0.0, min(1.0, score)), 4)

    # ── public API ────────────────────────────────────────────────────────────

    def generate(self, n: int = 1000) -> list[Transaction]:
        transactions: list[Transaction] = []
        base_time = datetime.now() - timedelta(days=30)

        for i in range(n):
            card = random.choice(self._card_pool)
            offset_minutes = int(i * (30 * 24 * 60) / n)
            ts = base_time + timedelta(minutes=offset_minutes)
            # Simple velocity approximation
            v1h = max(0, int(self._rng.poisson(0.5)))
            v24h = max(0, int(self._rng.poisson(3)))
            fraud_rate = 0.08 if card["home_country"] in HIGH_RISK_COUNTRIES else 0.05
            tx = self._gen_transaction(ts, card, v1h, v24h, fraud_rate)
            transactions.append(tx)

        return transactions

    def to_dataframe(self, n: int = 1000) -> pd.DataFrame:
        txs = self.generate(n)
        return pd.DataFrame([t.to_dict() for t in txs])


def generate_sample_dataset(n: int = 1000) -> pd.DataFrame:
    return FraudDataGenerator().to_dataframe(n)
