# Fraud Investigation Procedures Guide

## Investigation Priority Matrix

| Risk Score | Category | SLA | Investigator Level |
|------------|----------|-----|-------------------|
| 0.95 – 1.0 | CRITICAL | Immediate auto-block | L2 + Supervisor |
| 0.80 – 0.95 | HIGH | 4 hours | L2 Investigator |
| 0.70 – 0.80 | ELEVATED | 8 hours | L1 or L2 |
| 0.50 – 0.70 | MEDIUM | 24 hours | L1 Investigator |
| < 0.50 | LOW | Standard review | Automated |

---

## Step-by-Step Investigation Process

### Step 1: Initial Triage (0–5 minutes)
1. Retrieve full transaction details including merchant, amount, timestamp.
2. Pull cardholder's 90-day transaction history.
3. Check if card is reported lost/stolen.
4. Review velocity metrics: transactions in last 1h and 24h.
5. Check IP geolocation against cardholder's home country.
6. Assign preliminary risk score from automated system.

### Step 2: Pattern Analysis (5–15 minutes)
1. Compare transaction to cardholder's spending profile (typical categories, amounts, merchants).
2. Check for velocity pattern: multiple transactions in short window.
3. Verify geographic consistency: is it possible to be at both locations?
4. Cross-reference device fingerprint: new device = elevated risk.
5. Look for structuring patterns: amounts just below $10,000.
6. Check merchant for previous fraud association.

### Step 3: Customer Contact (if score 0.70–0.95)
1. Attempt outreach via registered phone/email.
2. Identity verification before discussing account details.
3. Document customer response: confirm or deny transaction.
4. If unable to reach within 2 hours: escalate to provisional hold.

### Step 4: Decision and Action
- **Confirmed Fraud:** Block card, initiate chargeback, file SAR if required.
- **Confirmed Legitimate:** Clear flag, document false positive for model retraining.
- **Inconclusive:** Apply temporary hold, escalate to L2, require customer to verify in branch or via video call.

### Step 5: Documentation
1. Record all investigation steps in case management system.
2. Log reason for decision with top-3 contributing factors.
3. If SAR required: complete and file within 30-day window.
4. Tag case for model retraining dataset if it was a difficult judgment call.

---

## High-Risk Country Protocols

For transactions where ip_country or merchant_country is in the HIGH_RISK set (NG, RO, UA, BR):

1. **Automatic elevation** to HIGH risk regardless of other factors.
2. Require cardholder confirmation before processing.
3. Apply enhanced monitoring for 72h following any confirmed legitimate transaction.
4. If fraud confirmed: escalate to cross-border fraud team and notify relevant law enforcement (FBI IC3 for US cases).

---

## Chargeback Investigation

### Reason Code Categories:
- **10.x — Fraud:** Unauthorized use. No signature required if CNP.
- **11.x — Authorization:** Transaction processed without valid authorization.
- **12.x — Processing Errors:** Incorrect amount, duplicate processing.
- **13.x — Consumer Disputes:** Not as described, cancelled merchandise.

### Compelling Evidence for Disputes:
- Cardholder IP matches billing address geolocation.
- Device fingerprint matches previous authenticated sessions.
- Delivery confirmation to billing address.
- Signed receipt from POS terminal.
- Previous successful transactions with same merchant.

---

## SAR Filing Checklist

Required elements for a complete SAR:
- [ ] Subject information (cardholder details, masked PAN)
- [ ] Transaction details (date, amount, merchant, account)
- [ ] Nature of suspicious activity (from FRAUD_PATTERNS classification)
- [ ] Narrative explaining why activity is suspicious
- [ ] AI/model risk score and top contributing features
- [ ] Date suspicious activity was detected
- [ ] Financial institution information
- [ ] Contact person at institution

**Important:** Do NOT notify the subject that a SAR has been filed. This is a legal requirement (31 U.S.C. § 5318(g)(2)).

---

## Model Feedback Loop

After each investigation:
1. Label outcome: `confirmed_fraud | false_positive | true_negative | inconclusive`
2. Submit to feedback endpoint: `POST /api/v1/feedback`
3. Record top features that led to correct/incorrect decision.
4. Cases labeled `false_positive` are priority for model retraining.
5. Monthly retraining cycle reviews all labeled cases from the prior period.
