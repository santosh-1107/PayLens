# Technical Blueprint — UPI Transaction Intelligence Platform

This doc is written to be pasted directly into Cursor / Claude Code /
Antigravity as a build brief. It describes what's already built (don't
rebuild it) and what needs to be built next.

## Already built (do not rebuild — extend/import instead)

- `src/schema.sql` — SQLite schema, 5 tables: `users`, `transactions`,
  `detected_subscriptions`, `fraud_flags`, `credit_scores`.
- `src/generate_dataset.py` — synthetic data generator, produces
  `data/upi_transactions.db`.
- `src/subscription_detector.py` — exposes `run(conn)`, populates
  `detected_subscriptions`.
- `src/fraud_detector.py` — exposes `run(conn)`, populates `fraud_flags`.
- `src/credit_score.py` — exposes `run(conn)`, populates `credit_scores`.
- `src/main.py` — orchestrator, runs all of the above in sequence.

All modules are idempotent (safe to re-run) and already validated against
ground-truth labels in the synthetic data. **Do not modify the detection
logic unless explicitly asked** — it's tuned and tested.

## What to build next (in order)

### Layer 1: Groq chat/voice narrative layer

**Goal:** an LLM-powered explainer that turns structured rows from
`fraud_flags`, `detected_subscriptions`, and `credit_scores` into
plain-language answers to user questions.

**Critical design constraint:** the LLM must NOT reason freely over raw
transaction data or invent financial advice. It only *narrates* what the
rule engine already computed. This keeps it safe, accurate, and cheap
(small context per call).

**File to create:** `src/chat_layer.py`

**Function signature:**
```python
def explain(user_id: str, user_question: str, conn) -> str:
    """
    1. Pull relevant structured data for this user from the DB
       (recent fraud_flags, detected_subscriptions, latest credit_scores row).
    2. Build a system prompt that:
       - States the assistant's role: "You explain this user's financial
         data. You do not give financial/investment advice. You do not
         discuss anything outside this user's transaction data."
       - Includes the structured data as context (NOT raw unfiltered
         transaction dumps — pass the already-computed summaries).
       - Instructs: if asked something out of scope, politely decline
         and redirect to what you CAN explain.
    3. Call Groq API (model: llama-3.3-70b-versatile or similar fast model).
    4. Run output through a simple guardrail filter (see below) before returning.
    """
```

**Guardrails to implement (as a separate function `apply_guardrails(text: str) -> str`):**
- Block/strip responses containing financial advice language: "you should invest",
  "guaranteed returns", "buy", "sell" + stock-like tickers, "I recommend investing"
- Cap response length (set `max_tokens` in the Groq call, e.g. 300)
- If Groq API call fails/times out, fall back to a template string like:
  `f"I found {n} things to flag for you, but I'm having trouble generating
  a detailed explanation right now. Here's the raw summary: {summary}"`
- Rate limit: cache identical (user_id, question) pairs for the session to avoid
  redundant calls during a live demo

**Environment:** read `GROQ_API_KEY` from a `.env` file (use `python-dotenv`,
already in requirements.txt). Never hardcode the key.

**Voice (optional stretch, only if time allows):**
- STT: Groq's hosted `whisper-large-v3` endpoint
- TTS: `gTTS` (already in requirements.txt) for output narration,
  especially for the fraud-alert-before-you-confirm use case

### Layer 2: Streamlit dashboard

**Goal:** single-page app that ties everything together as one narrative
feed, not three separate siloed panels.

**File to create:** `src/dashboard.py`

**Structure:**
1. User selector dropdown (pull from `users` table)
2. A unified "Financial Events" timeline/feed combining:
   - Fraud flags (sorted by risk_score, most recent/highest risk first)
   - Detected subscriptions (with next_expected_date)
   - Latest credit score with the 3 component breakdown shown as a simple
     bar/gauge
3. A chat input box at the bottom wired to `chat_layer.explain()` — user
   can click "Why was this flagged?" next to any fraud flag, or type a
   free-form question
4. Keep styling simple — `st.metric()`, `st.dataframe()`, `st.chat_message()`
   are enough. Don't over-engineer custom CSS for a 3-day prototype.

**Run command:** `streamlit run dashboard.py` (run from inside `src/`)

## Data contracts (for reference when building Layer 1 & 2)

### `detected_subscriptions` row shape
```
subscription_id, user_id, counterparty_vpa, counterparty_name,
avg_amount, interval_days, last_txn_date, next_expected_date,
occurrence_count, confidence_score
```

### `fraud_flags` row shape
```
flag_id, txn_id, user_id, risk_score (0-1), reasons (comma-separated
string, e.g. "amount_spike,new_payee"), flagged_at
```
To get the actual transaction details for a flag, JOIN to `transactions`
on `txn_id`.

### `credit_scores` row shape
```
score_id, user_id, score (300-900), income_regularity_component (0-1),
expense_ratio_component (0-1), volatility_component (0-1), computed_at
```

## Known limitations to state honestly in any demo/report

- Fraud detector recall is ~59% on synthetic test anomalies — rule-based
  v1, not tuned to production accuracy. Document this, don't hide it.
- Credit score is a heuristic formula, not a trained model — no real
  labeled default/repayment data exists to train against.
- No real Account Aggregator integration — synthetic data only.
- No cross-bank/NPCI dispute resolution tracking — requires institutional
  access not available to this project.

These limitations are intentional, documented scope decisions for a 3-day
build — not oversights. Frame them as "future work requiring real data
access / institutional partnership" in any presentation.
