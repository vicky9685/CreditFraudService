# Credit Card Fraud Patterns Reference Guide

## 1. Card-Not-Present (CNP) Fraud
Card-Not-Present fraud occurs when a stolen card number is used for online or phone transactions where the physical card is not required.

**Key Indicators:**
- Multiple small test charges followed by large purchases
- Shipping address differs from billing address
- Orders placed from high-risk IP geographies
- Multiple orders within short time window
- Use of prepaid or VoIP phone numbers
- Failed CVV validation attempts before success

**Risk Level:** HIGH — Accounts for 65-70% of all card fraud losses.

**Detection Signals:**
- IP geolocation mismatch with card billing country
- Device fingerprint not seen in cardholder's history
- Email address created within 24h of transaction
- Velocity: >3 CNP transactions per hour on same card

---

## 2. Account Takeover (ATO)
An attacker gains unauthorized access to a legitimate account, changes credentials, and makes fraudulent purchases.

**Key Indicators:**
- Login from new device or unusual location
- Password change followed immediately by large transaction
- Change of email/phone before transaction
- Multiple failed login attempts (brute force)
- Sudden change in spending patterns

**Risk Level:** CRITICAL — Average loss per ATO incident: $1,200+.

**Detection Signals:**
- New device fingerprint after credential change
- IP address in HIGH_RISK_COUNTRIES list
- Session anomaly: browser/OS never seen for this account
- Transactions in categories never used by this customer

---

## 3. Identity Theft / Synthetic Identity
Fraudsters create new accounts using stolen or fabricated personal information (synthetic identity = mix of real and fake data).

**Key Indicators:**
- New account with no transaction history
- Address is a mail drop or virtual address
- Multiple applications with slight name variations
- SSN belongs to deceased or minor
- Immediately maxing out credit limit

**Risk Level:** HIGH — Synthetic identity fraud is the fastest-growing financial crime.

**Detection Signals:**
- Address mismatch with credit bureau data
- Authorized user added within days of account opening
- First purchase >$500 within 48h of account opening

---

## 4. Velocity Attacks
Rapid sequential transactions designed to maximize theft before the card is blocked.

**Key Indicators:**
- >5 transactions per hour on same card
- Transactions at different merchant locations geographically impossible to visit in sequence
- Transactions precisely under reporting thresholds (structuring)
- Multiple small ATM withdrawals in rapid succession

**Risk Level:** HIGH — Can drain account within minutes.

**Detection Signals:**
- velocity_1h > 5 is HIGH alert
- velocity_1h > 10 is CRITICAL — auto-block recommended
- Amount just below $10,000 (BSA reporting threshold) → structuring
- Transaction amounts: $9,999, $9,997, $9,995 = structuring pattern

---

## 5. Geographic Anomaly Fraud
Transactions occurring in physically impossible locations relative to recent card activity.

**Key Indicators:**
- Card used in New York and London within 2 hours
- IP address country differs from POS terminal country
- Distance from home >1,000 km for domestic card
- Transaction in high-risk country when customer is domestic-only

**Risk Level:** MEDIUM-HIGH

**Detection Signals:**
- distance_from_home_km > 500 = elevated risk
- distance_from_home_km > 2000 = HIGH risk
- ip_country differs from merchant_country = review
- ip_country in HIGH_RISK set (NG, RO, UA, BR) = escalate

---

## 6. BIN (Bank Identification Number) Attack
Criminals test thousands of card numbers with the same BIN prefix to find valid cards.

**Key Indicators:**
- Hundreds of small transactions ($1–$5) from same IP
- Same merchant hit repeatedly with different card numbers sharing BIN prefix
- High decline rate from single IP or device
- Bot-like request timing (regular intervals)

**Risk Level:** HIGH — Can compromise thousands of cards rapidly.

**Detection Signals:**
- >50 failed transactions with same BIN from one IP
- Transaction timing variance < 100ms (automated)
- Merchant experiencing >10x normal decline rate

---

## 7. Card Skimming
Physical device captures magnetic stripe data at ATMs or POS terminals.

**Key Indicators:**
- Multiple cards compromised at same ATM/POS in same time window
- Cloned cards used in different geographic region than original
- Transactions at ATMs in high-risk tourist areas
- Magnetic stripe transaction when chip is available

**Risk Level:** MEDIUM — Physical infrastructure attack.

**Detection Signals:**
- Magnetic stripe read when card has EMV chip
- ATM location appears in skimmer database
- Card used far from home immediately after ATM usage

---

## 8. Social Engineering / Phishing
Fraudsters trick cardholders into revealing credentials or authorizing fraudulent transfers.

**Key Indicators:**
- Customer calls report being contacted by "bank" or "IRS"
- Unusual authorization for wire transfer
- Customer approving transaction they don't recognize
- Account accessed from legitimate device but by attacker

**Risk Level:** VARIES — Can lead to very large single losses.
