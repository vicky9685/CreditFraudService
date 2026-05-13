"""Tests for synthetic fraud data generator."""
import pytest
import pandas as pd
from data.generator import FraudDataGenerator, generate_sample_dataset


def test_generator_produces_expected_count():
    gen = FraudDataGenerator(seed=42)
    txs = gen.generate(100)
    assert len(txs) == 100


def test_fraud_rate_within_bounds():
    df = generate_sample_dataset(500)
    fraud_rate = df["is_fraud"].mean()
    # Expect roughly 5-15% fraud rate
    assert 0.02 < fraud_rate < 0.20, f"Unexpected fraud rate: {fraud_rate:.2%}"


def test_transaction_has_required_fields():
    gen = FraudDataGenerator(seed=1)
    txs = gen.generate(10)
    required = {
        "transaction_id", "card_last4", "amount", "merchant_category",
        "is_fraud", "risk_score", "channel", "velocity_1h", "velocity_24h",
    }
    for tx in txs:
        d = tx.to_dict()
        missing = required - d.keys()
        assert not missing, f"Missing fields: {missing}"


def test_risk_score_bounded():
    gen = FraudDataGenerator(seed=99)
    txs = gen.generate(200)
    for tx in txs:
        assert 0.0 <= tx.risk_score <= 1.0, f"risk_score={tx.risk_score} out of bounds"


def test_amounts_are_positive():
    gen = FraudDataGenerator(seed=7)
    txs = gen.generate(100)
    for tx in txs:
        assert tx.amount > 0, f"Non-positive amount: {tx.amount}"


def test_fraud_txs_have_pattern():
    gen = FraudDataGenerator(seed=42)
    txs = gen.generate(500)
    fraud_txs = [t for t in txs if t.is_fraud]
    for tx in fraud_txs:
        assert tx.fraud_pattern is not None, "Fraud transaction missing pattern"


def test_to_dataframe():
    gen = FraudDataGenerator(seed=42)
    df = gen.to_dataframe(50)
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 50
    assert "is_fraud" in df.columns
