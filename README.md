# UPI Transaction Intelligence Platform (PayLens)

**Status: Core pipeline, chat layer, dashboard, and institutional report complete ✅**

## What is this?

A smart assistant that reads a user's UPI transaction history and turns
raw transaction data into useful insight — for end users and, separately,
for authorized financial institutions reviewing credit risk.

End-user facing capabilities:

1. **Subscription tracking** — automatically finds recurring payments
   (subscriptions, EMIs, memberships) hiding in your transaction history.
2. **Fraud detection** — flags suspicious transactions (unusual amounts,
   odd hours, brand-new payees, rapid-fire payments) that look different
   from your normal spending behavior.
3. **Alternate credit scoring** — computes a credit-worthiness score from
   cash-flow patterns alone, for people without a traditional credit history
   (gig workers, informal-sector earners).
4. **Plain-language explanations** — Groq-powered chat that narrates what
   the rule engines found, in English, Hindi, or Tamil.
5. **Voice alerts** — spoken fraud and subscription alerts via gTTS, also
   multilingual.
6. **Complaint filing (demo)** — file a complaint against a flagged
   transaction; logged locally only (not a real bank/NPCI integration).
7. **Subscription cancellation intent (demo)** — mark a subscription for
   cancellation; logs intent only (does not cancel any real UPI mandate).

Institution-only capabilities (separate, password-gated report — not part
of the user-facing dashboard flow):

- Income/spending volatility analysis for gig-worker credit assessment
- Circular transaction detection ("salary washing" / self-funding loops)
- Shared risky counterparty detection (cross-user systemic risk)
- Spending-vs-income trend divergence (flags when spending growth outpaces
  income growth, excluding already-fraud-flagged transactions to avoid
  double-counting)

The key architectural idea: **most insights come from the same underlying
transaction data**, processed through one shared pipeline — not separate
silos.

In plain terms: *"It's like having a smart financial friend who reads
your transaction history, warns you about wasted subscriptions, catches
suspicious payments, helps you get a fair credit score — and gives
lenders a separate, confidential view of deeper risk signals when
authorized."*

---

## Current features (implemented and tested)

### 1. Core pipeline

Synthetic dataset generation and three rule-based detection modules, plus
two institutional analysis modules:

| Component | What it does |
|---|---|
| `generate_dataset.py` | Builds synthetic UPI data: **40 users**, **~3,600 transactions**, **6 months** of history |
| `subscription_detector.py` | Recurring payment detection (interval/amount matching) |
| `fraud_detector.py` | Rule-based fraud flagging (amount spike, odd hour, new payee, velocity burst). **~51% recall** on injected test anomalies — documented honestly, not overtuned to synthetic data |
| `credit_score.py` | Heuristic credit score (300–900) from three components: income regularity, expense ratio, volatility |
| `income_authenticity.py` | Circular transaction / "salary washing" pattern detection |
| `spending_trend.py` | Month-over-month spending vs income trend divergence; debit totals **exclude transactions already in `fraud_flags`** |

Orchestrated by `main.py` as a **6-step pipeline** (see Architecture below).

### 2. Groq-powered chat layer (`chat_layer.py`)

- Explains fraud flags, subscriptions, and credit scores in plain language
- Guardrailed against investment advice, prompt injection, and cross-user
  data leakage
- Falls back to a template response if the Groq API fails or times out
- Requires `GROQ_API_KEY` in a project-root `.env` file

### 3. Multilingual support

Chat responses and voice alerts work in **English**, **Hindi**, and **Tamil**
(selectable from the dashboard). gTTS handles voice synthesis; the chat
layer instructs Groq to respond in the selected language.

### 4. Streamlit dashboard (`dashboard.py`)

User-facing UI branded **PayLens**:

- User and language selector
- Fraud flags with risk badges, transaction details, and plain-text reasons
- Detected subscriptions with next expected charge dates
- Credit score breakdown with component progress bars
- Voice alerts (gTTS) for fraud flags and subscriptions
- Integrated chat wired to `chat_layer.explain()`
- Complaint filing form (local SQLite log, duplicate prevention per transaction)
- Subscription cancellation intent logging (local SQLite log)

### 5. Complaint filing (concept demo)

Users can file a complaint against a flagged transaction from the dashboard.
**This is not a real bank or NPCI integration** — complaints are stored in
a local `complaints` table only. Duplicate complaints for the same
transaction are blocked.

### 6. Subscription management (concept demo)

Users can mark a subscription "for cancellation." **This does not cancel
any real UPI mandate** — bank API access required for that is out of scope.
Intent is logged locally in `subscription_actions`.

### 7. Institution-only report (`pages/institution_report.py`)

Password-gated Streamlit page (`INSTITUTION_ACCESS_CODE` in `.env`,
defaults to `admin123`). **Not linked from the user-facing dashboard UI.**
Displays a **"CONFIDENTIAL — INSTITUTIONAL USE ONLY"** banner.

Includes:

- Income/spending volatility analysis for gig-worker credit assessment
- Circular transaction flags from `income_authenticity_flags`
- Shared risky counterparty profiles from `shared_risk_counterparties`
- Spending-vs-income trend divergence from `spending_trends`

Findings are flagged for human review — not automated credit/fraud decisions.

---

## Architecture

`main.py` runs the full pipeline in order:

```
1. generate_dataset.py     → data/upi_transactions.db
2. subscription_detector   → detected_subscriptions
3. fraud_detector          → fraud_flags
4. credit_score            → credit_scores
5. income_authenticity     → income_authenticity_flags, shared_risk_counterparties
6. spending_trend          → spending_trends
```

All modules are idempotent — each clears its own output tables before
re-inserting. Safe to re-run any time.

The dashboard and chat layer **read** from this database; they do not
modify detection logic.

---

## Known limitations (documented scope boundaries)

This is a time-limited prototype. These are intentional boundaries, not
oversights:

| Limitation | Detail |
|---|---|
| Synthetic data only | No real Account Aggregator (AA) integration |
| Fraud recall ~51% | Rule-based v1, not production-tuned |
| Credit score | Transparent heuristic, not a trained ML model — no real labeled default/repayment data available |
| Complaints / refunds / cancellation | Log intent locally as concept demos — no real bank/NPCI integration |
| Pre-transaction fraud warning | Not built — detection is post-transaction only |
| Institution report | Confidential lender-facing view; not shown to end users |

Future work requiring real data access or institutional partnership:
Account Aggregator integration, production-grade fraud models, trained
credit classifiers, and live NPCI/bank grievance routing.

---

## Project structure

```
upi-intel-platform/
├── requirements.txt              # pinned dependencies
├── README.md                     # this file
├── .env                          # GROQ_API_KEY, INSTITUTION_ACCESS_CODE (not committed)
├── docs/
│   └── BLUEPRINT.md              # technical spec / architecture brief
├── data/
│   └── upi_transactions.db       # SQLite DB (generated by running the pipeline)
└── src/
    ├── schema.sql                # shared database schema
    ├── generate_dataset.py       # synthetic UPI transaction generator
    ├── subscription_detector.py  # recurring payment detection
    ├── fraud_detector.py         # rule-based anomaly flagging
    ├── credit_score.py           # alternate credit scoring (heuristic)
    ├── income_authenticity.py    # circular transaction + shared risk counterparty detection
    ├── spending_trend.py         # spending vs income trend divergence
    ├── chat_layer.py             # Groq-powered narrative layer (multilingual)
    ├── dashboard.py              # user-facing Streamlit dashboard (PayLens)
    ├── main.py                   # 6-step pipeline orchestrator
    └── pages/
        └── institution_report.py # password-gated institutional risk report
```

---

## How to run it

### 1. Install dependencies

```bash
cd src
pip install -r ../requirements.txt
```

> **Note:** On some Windows setups, `numpy` in `requirements.txt` may fail
> to build from source. Core pipeline modules use the standard library +
> SQLite; for the dashboard and chat layer, install at minimum:
> `streamlit`, `pandas`, `groq`, `python-dotenv`, `gTTS`, and `faker`.

### 2. Configure environment

Create a `.env` file at the project root:

```
GROQ_API_KEY=your_groq_api_key_here
INSTITUTION_ACCESS_CODE=your_institutional_password
```

`GROQ_API_KEY` powers live chat responses (falls back to template text if
missing). `INSTITUTION_ACCESS_CODE` gates the institutional report page.

### 3. Run the pipeline

```bash
cd src
python main.py
```

This will:

1. Generate a fresh synthetic dataset (~3,600 transactions, 40 users, 6 months)
2. Run subscription detection → `detected_subscriptions`
3. Run fraud detection → `fraud_flags`
4. Run credit scoring → `credit_scores`
5. Run income authenticity detection → `income_authenticity_flags`, `shared_risk_counterparties`
6. Run spending trend analysis → `spending_trends`

Safe to re-run any time — every step wipes and regenerates its own output.

### 4. Launch the user dashboard

```bash
cd src
python -m streamlit run dashboard.py
```

Open the URL shown in the terminal (typically `http://localhost:8501`).

### 5. Launch the institutional report (separate page)

With the Streamlit app running, select **Institution Report** from the
Streamlit sidebar pages menu, or run directly:

```bash
cd src
python -m streamlit run pages/institution_report.py
```

Enter the institutional access code to view confidential reports.

### Inspect the database directly

```bash
sqlite3 ../data/upi_transactions.db
sqlite> SELECT * FROM detected_subscriptions LIMIT 5;
sqlite> SELECT * FROM fraud_flags LIMIT 5;
sqlite> SELECT * FROM credit_scores LIMIT 5;
sqlite> SELECT * FROM spending_trends WHERE is_flagged = 1;
sqlite> SELECT * FROM complaints;
```

---

## Verified results (last pipeline run)

Approximate figures from a full `python main.py` run on the current dataset:

- **~3,685** synthetic transactions across **40 users**
- **~91** subscriptions detected
- **~187** fraud flags raised (**~51% recall** on **~314** injected test anomalies)
- Credit scores computed for all 40 users
- **~31** circular transaction flags, shared-risk counterparty profiles populated
- **~21** profiles flagged where spending growth outpaces income growth

---

## Tech stack

Python · SQLite · Streamlit · Groq API (`llama-3.3-70b-versatile`) · gTTS ·
python-dotenv · Faker · pandas · scikit-learn (reserved for future ML upgrade)

---
*Last updated: after full platform build — 6-step pipeline, PayLens dashboard, multilingual chat/voice, complaint/cancellation demos, and institutional report.*
