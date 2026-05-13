# Compliance Rules for Credit Card Fraud Detection

## PCI DSS (Payment Card Industry Data Security Standard)

### Relevant Requirements for Fraud Detection Systems:
- **Requirement 6.4:** Protect all systems and networks from malicious software. All AI/ML models must be scanned.
- **Requirement 8.2:** Unique IDs for all users including system accounts accessing fraud detection models.
- **Requirement 10.2:** Implement audit trails for all fraud detection decisions.
- **Requirement 10.3:** Retain audit log history for at least 12 months.
- **Requirement 12.3.2:** Targeted risk analysis for every technology in use including AI systems.

### PCI DSS Data Classification:
- **Sensitive Authentication Data (SAD):** CVV, PIN, full track data — NEVER store post-authorization.
- **Primary Account Number (PAN):** Must be masked; only last 4 digits displayed.
- **Cardholder Data (CHD):** Name, expiration date — protect with encryption.

---

## BSA/AML (Bank Secrecy Act / Anti-Money Laundering)

### Currency Transaction Reports (CTR):
- File CTR for cash transactions **exceeding $10,000** in a single business day.
- Structuring (intentionally keeping transactions below $10,000) is ILLEGAL.
- AI system must flag: multiple transactions totaling >$10,000 in 24h from same customer.

### Suspicious Activity Reports (SAR):
- File SAR within **30 days** of detecting suspicious activity.
- Suspicious patterns requiring SAR:
  - Transactions with no apparent lawful purpose.
  - Rapid movement of funds (in/out same day).
  - Transactions inconsistent with customer profile.
  - Any transaction involving $5,000+ suspected of illegal activity.

### Know Your Customer (KYC):
- Verify identity of all customers.
- Risk-rate customers: Low / Medium / High.
- Enhanced Due Diligence (EDD) for High-risk customers.
- Beneficial ownership for business accounts >25% ownership.

---

## GDPR (General Data Protection Regulation)

### Automated Decision Making (Article 22):
- Individuals have the right NOT to be subject to solely automated decisions with significant effects.
- Fraud detection decisions affecting customer accounts **require human review** unless:
  - Necessary for contract performance.
  - Authorized by law.
  - Based on explicit consent.
- Customers must be informed if automated fraud detection is in use.

### Data Minimization:
- Collect only data necessary for fraud detection purposes.
- Do not retain raw transaction data beyond the defined retention period (90 days default).
- Anonymize or pseudonymize data used for model training.

### Right to Explanation:
- Customers can request explanation of why a transaction was flagged.
- AI system must support explainability — log key features driving each decision.

---

## SOX (Sarbanes-Oxley Act)

### Internal Controls:
- All fraud detection systems must be part of internal control documentation.
- Changes to fraud detection models require approval workflow.
- Quarterly review of model performance metrics.
- Annual audit of fraud detection system access logs.

### Financial Reporting:
- Material fraud losses must be disclosed.
- Fraud reserves must be accurately estimated using model data.

---

## Fraud Reporting Thresholds Summary

| Threshold | Action Required | Timeframe |
|-----------|----------------|-----------|
| >$10,000 single cash transaction | File CTR | Same business day |
| >$5,000 suspected illegal activity | File SAR | Within 30 days |
| Structuring pattern detected | File SAR | Within 30 days |
| Risk score > 0.95 | Auto-block + alert | Real-time |
| Risk score 0.70-0.95 | Human review queue | Within 4 hours |
| Risk score 0.50-0.70 | Monitoring + soft alert | Within 24 hours |
| Risk score < 0.50 | Log and monitor | Standard review |

---

## AI Governance Compliance Requirements

1. **Model Documentation:** Every model version must have a model card documenting training data, performance metrics, known biases, and intended use.
2. **Bias Auditing:** Quarterly analysis to ensure fraud detection does not disproportionately impact protected classes.
3. **Explainability Logging:** Every fraud decision must log the top-3 contributing features.
4. **Human Override:** Any automated block must be overridable by a qualified human reviewer.
5. **Model Versioning:** Immutable versioning of all deployed models with rollback capability.
6. **Drift Monitoring:** Alert when model performance degrades >5% from baseline metrics.
