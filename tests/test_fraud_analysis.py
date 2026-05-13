"""Tests for fraud analysis tools."""
import pytest
from tools.fraud_analysis import analyze_transaction_features, detect_fraud_pattern
from tools.transaction_tools import store_transactions, get_transaction_by_id, search_transactions


@pytest.fixture(autouse=True)
def load_sample_data():
    """Load sample transactions for tests that need the store."""
    from data.generator import generate_sample_dataset
    df = generate_sample_dataset(n=100)
    store_transactions(df.to_dict(orient="records"))


def test_analyze_high_risk_transaction():
    tx = {
        "transaction_id": "HITEST01",
        "amount": 2500.00,
        "merchant_category": "electronics",
        "is_international": True,
        "ip_country": "NG",
        "velocity_1h": 8,
        "velocity_24h": 22,
        "distance_from_home_km": 3000.0,
        "channel": "online",
    }
    result = analyze_transaction_features(tx)
    assert result["risk_score"] >= 0.70
    assert result["risk_level"] in ("HIGH", "CRITICAL")
    assert len(result["fraud_signals"]) > 0


def test_analyze_low_risk_transaction():
    tx = {
        "transaction_id": "LOWTEST01",
        "amount": 30.00,
        "merchant_category": "grocery",
        "is_international": False,
        "ip_country": "US",
        "velocity_1h": 0,
        "velocity_24h": 2,
        "distance_from_home_km": 2.0,
        "channel": "pos",
    }
    result = analyze_transaction_features(tx)
    assert result["risk_score"] < 0.50


def test_detect_velocity_attack():
    tx = {
        "amount": 100,
        "merchant_category": "online_retail",
        "is_international": False,
        "ip_country": "US",
        "velocity_1h": 15,
        "velocity_24h": 40,
        "distance_from_home_km": 10,
        "channel": "online",
    }
    result = detect_fraud_pattern(tx)
    assert "velocity_attack" in result["detected_patterns"]
    assert result["confidence_scores"]["velocity_attack"] >= 0.70


def test_detect_geographic_anomaly():
    tx = {
        "amount": 500,
        "merchant_category": "travel",
        "is_international": True,
        "ip_country": "UA",
        "velocity_1h": 1,
        "velocity_24h": 3,
        "distance_from_home_km": 6000.0,
        "channel": "online",
    }
    result = detect_fraud_pattern(tx)
    assert "geographic_anomaly" in result["detected_patterns"]


def test_structuring_signal():
    tx = {
        "transaction_id": "STRUCT01",
        "amount": 9450.00,
        "merchant_category": "atm_withdrawal",
        "is_international": False,
        "ip_country": "US",
        "velocity_1h": 2,
        "velocity_24h": 5,
        "distance_from_home_km": 5.0,
        "channel": "atm",
    }
    result = analyze_transaction_features(tx)
    signal_names = [s["signal"] for s in result["fraud_signals"]]
    assert "STRUCTURING" in signal_names


def test_transaction_store_search():
    results = search_transactions(is_fraud=True, limit=10)
    assert isinstance(results, list)
    for tx in results:
        assert tx["is_fraud"] is True


def test_get_nonexistent_transaction():
    tx = get_transaction_by_id("NONEXISTENT000")
    assert tx is None
