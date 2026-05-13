# Fraud Risk Indicators Reference

## Numeric Risk Features

### Transaction Amount Features
| Feature | Low Risk | Medium Risk | High Risk | Critical |
|---------|----------|-------------|-----------|---------|
| Amount | <$100 | $100–$500 | $500–$2000 | >$2000 |
| Round amount (%.00) | Normal | Slight flag | Flag | Strong flag |
| Amount = $9,999.xx | Normal | — | — | Structuring alert |
| Amount matches card limit | Normal | — | Flag | Block |

### Velocity Features
| Feature | Low Risk | Medium Risk | High Risk | Critical |
|---------|----------|-------------|-----------|---------|
| velocity_1h | 0–2 | 3–5 | 6–10 | >10 |
| velocity_24h | 0–5 | 6–10 | 11–20 | >20 |
| Failed attempts in 1h | 0 | 1–2 | 3–5 | >5 |

### Geographic Features
| Feature | Low Risk | Medium Risk | High Risk | Critical |
|---------|----------|-------------|-----------|---------|
| distance_from_home_km | <50 | 50–500 | 500–2000 | >2000 |
| ip_country = home_country | Safe | — | — | — |
| ip_country in HIGH_RISK set | — | — | Elevate | — |
| Impossible travel speed | — | — | — | Block |

---

## Categorical Risk Indicators

### Merchant Category Risk Weights
| Category | Base Risk | Notes |
|----------|-----------|-------|
| grocery | Very Low | Normal daily spending |
| pharmacy | Very Low | Normal daily spending |
| gas_station | Low | Common legitimate use |
| restaurant | Low | Common legitimate use |
| entertainment | Medium | CNP exposure |
| online_retail | Medium-High | High CNP fraud vector |
| travel | High | Large amounts + international |
| electronics | High | High-value resale items |
| jewelry | Very High | Cash equivalent, easy to fence |
| atm_withdrawal | Very High | Direct cash access |

### Channel Risk Weights
| Channel | Risk Level | Notes |
|---------|-----------|-------|
| POS (chip) | Lowest | EMV reduces counterfeit fraud |
| POS (swipe) | Low-Medium | Magnetic stripe risk |
| Online | Medium-High | CNP fraud vector |
| ATM | High | Cash withdrawal, skimming risk |
| Phone order | High | No physical verification |

### Device/Network Signals
| Signal | Risk Impact |
|--------|------------|
| Known device fingerprint | -20% risk |
| New device + large amount | +25% risk |
| Tor/VPN IP detected | +35% risk |
| IP in high-risk country | +30% risk |
| Hosting provider IP | +20% risk |
| Mobile carrier IP (expected) | Neutral |

---

## Composite Risk Score Formula (Heuristic)

```
risk_score = base(0.05)
  + amount_factor          [0.00 – 0.35]
  + velocity_factor        [0.00 – 0.35]
  + geographic_factor      [0.00 – 0.40]
  + channel_factor         [0.00 – 0.10]
  + merchant_category      [0.00 – 0.15]
  + device_factor          [0.00 – 0.25]
  + noise(μ=0, σ=0.03)
```

Final score clamped to [0.0, 1.0].

---

## Common False Positive Triggers

Understanding false positives helps reduce customer friction:

1. **Cardholder traveling** — Legitimate international use flagged as geographic anomaly.
   - Mitigation: Pre-travel notifications reduce false positives by 40%.

2. **Large one-time purchase** — Wedding rings, appliances, car down payment.
   - Mitigation: Check for prior communication about large purchase intent.

3. **New merchant category** — First time using card at electronics store.
   - Mitigation: Single new category with no other flags = low weight.

4. **Multiple family members on account** — Appears as velocity attack.
   - Mitigation: Device fingerprint diversity check (multiple known devices = family).

5. **Online gaming/streaming subscriptions** — Multiple small charges look like BIN attack.
   - Mitigation: Recurring merchant identifier reduces false positive.

---

## Model Performance Benchmarks

Target metrics for production fraud detection model:

| Metric | Minimum | Target | Best-in-Class |
|--------|---------|--------|---------------|
| Precision | 85% | 92% | 97% |
| Recall | 75% | 88% | 94% |
| F1 Score | 0.80 | 0.90 | 0.95 |
| False Positive Rate | <5% | <2% | <0.5% |
| AUC-ROC | >0.92 | >0.97 | >0.99 |
| Latency p99 | <500ms | <200ms | <50ms |

Drift alert: If F1 drops >5% from baseline, trigger retraining pipeline.
