"""Tests for risk scoring engine."""
import pytest
from tools.risk_scoring import compute_risk_score, batch_risk_score


@pytest.fixture
def low_risk_tx():
    return {
        "amount": 25.00,
        "merchant_category": "grocery",
        "is_international": False,
        "ip_country": "US",
        "velocity_1h": 1,
        "velocity_24h": 3,
        "distance_from_home_km": 5.0,
        "channel": "pos",
    }


@pytest.fixture
def high_risk_tx():
    return {
        "amount": 3500.00,
        "merchant_category": "jewelry",
        "is_international": True,
        "ip_country": "NG",
        "velocity_1h": 12,
        "velocity_24h": 35,
        "distance_from_home_km": 5000.0,
        "channel": "online",
    }


def test_low_risk_transaction_score(low_risk_tx):
    result = compute_risk_score(low_risk_tx)
    assert result.risk_score < 0.50
    assert result.risk_level in ("MINIMAL", "LOW")
    assert result.recommended_action in ("APPROVE", "STANDARD_MONITORING")


def test_high_risk_transaction_score(high_risk_tx):
    result = compute_risk_score(high_risk_tx)
    assert result.risk_score >= 0.75
    assert result.risk_level in ("HIGH", "CRITICAL")
    assert result.recommended_action in ("HUMAN_REVIEW", "AUTO_BLOCK")


def test_structuring_detection():
    tx = {
        "amount": 9750.00,
        "merchant_category": "atm_withdrawal",
        "is_international": False,
        "ip_country": "US",
        "velocity_1h": 1,
        "velocity_24h": 2,
        "distance_from_home_km": 10.0,
        "channel": "atm",
    }
    result = compute_risk_score(tx)
    factor_names = [f["factor"] for f in result.contributing_factors]
    assert "structuring_pattern" in factor_names


def test_result_has_top_factors(high_risk_tx):
    result = compute_risk_score(high_risk_tx)
    assert len(result.contributing_factors) > 0
    for factor in result.contributing_factors:
        assert "factor" in factor
        assert "weight" in factor


def test_score_bounded():
    for amount in [0.01, 100, 1000, 50000]:
        tx = {
            "amount": amount,
            "merchant_category": "electronics",
            "is_international": True,
            "ip_country": "UA",
            "velocity_1h": 15,
            "velocity_24h": 40,
            "distance_from_home_km": 8000,
            "channel": "online",
        }
        result = compute_risk_score(tx)
        assert 0.0 <= result.risk_score <= 1.0


def test_batch_scoring():
    txs = [
        {"amount": 50, "merchant_category": "restaurant", "is_international": False,
         "ip_country": "US", "velocity_1h": 0, "velocity_24h": 2, "distance_from_home_km": 3, "channel": "pos"},
        {"amount": 5000, "merchant_category": "electronics", "is_international": True,
         "ip_country": "RO", "velocity_1h": 8, "velocity_24h": 25, "distance_from_home_km": 3000, "channel": "online"},
    ]
    results = batch_risk_score(txs)
    assert len(results) == 2
    assert results[1].risk_score > results[0].risk_score
