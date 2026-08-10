-- ============================================================
-- UPI Transaction Intelligence Platform — Database Schema
-- ============================================================
-- Design principle: ONE shared transactions table feeds THREE
-- independent rule modules (subscriptions, fraud, credit score).
-- This mirrors the real architecture: in production, this table
-- would be populated by Account Aggregator (AA) data instead of
-- the synthetic generator.
-- ============================================================

-- Users table: represents each account holder in the system
CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    monthly_income_estimate REAL,     -- ground-truth label, used only to validate credit score logic
    created_at TEXT DEFAULT (datetime('now'))
);

-- Core transactions table: this is the "shared pipeline" data source
CREATE TABLE IF NOT EXISTS transactions (
    txn_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,          -- ISO format: YYYY-MM-DD HH:MM:SS
    amount REAL NOT NULL,
    direction TEXT NOT NULL,          -- 'debit' or 'credit'
    counterparty_vpa TEXT NOT NULL,   -- e.g. 'netflix@upi', 'ramesh@okhdfcbank'
    counterparty_name TEXT,
    category TEXT,                    -- e.g. 'subscription', 'p2p', 'grocery', 'utility', 'salary'
    txn_type TEXT NOT NULL,           -- 'P2P' or 'P2M' (person-to-person / person-to-merchant)
    narration TEXT,                   -- raw UPI-style narration text
    is_synthetic_anomaly INTEGER DEFAULT 0,  -- ground-truth label: 1 if generator deliberately injected this as fraud (for testing/validation only, NOT used by the detector itself)
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

-- Output of subscription detection module
CREATE TABLE IF NOT EXISTS detected_subscriptions (
    subscription_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    counterparty_vpa TEXT NOT NULL,
    counterparty_name TEXT,
    avg_amount REAL,
    interval_days INTEGER,            -- detected recurrence interval
    last_txn_date TEXT,
    next_expected_date TEXT,
    occurrence_count INTEGER,
    confidence_score REAL,            -- 0-1, how confident the rule engine is this is a real subscription
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

-- Output of fraud detection module
CREATE TABLE IF NOT EXISTS fraud_flags (
    flag_id TEXT PRIMARY KEY,
    txn_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    risk_score REAL,                  -- 0-1, higher = more suspicious
    reasons TEXT,                     -- comma-separated human-readable reasons, e.g. "new_payee,odd_hour,amount_spike"
    flagged_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (txn_id) REFERENCES transactions(txn_id),
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

-- Output of credit scoring module
CREATE TABLE IF NOT EXISTS credit_scores (
    score_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    score REAL,                       -- normalized 300-900 (mimics familiar CIBIL-style range)
    income_regularity_component REAL,
    expense_ratio_component REAL,
    volatility_component REAL,
    computed_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

-- Output of complaint filing module (demo)
CREATE TABLE IF NOT EXISTS complaints (
    complaint_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    txn_id TEXT NOT NULL,
    reason TEXT NOT NULL,
    details TEXT,
    status TEXT NOT NULL,
    filed_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (user_id) REFERENCES users(user_id),
    FOREIGN KEY (txn_id) REFERENCES transactions(txn_id)
);

-- Output of subscription cancellation actions (demo)
CREATE TABLE IF NOT EXISTS subscription_actions (
    action_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    subscription_id TEXT NOT NULL,
    action_type TEXT NOT NULL,
    requested_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (user_id) REFERENCES users(user_id),
    FOREIGN KEY (subscription_id) REFERENCES detected_subscriptions(subscription_id)
);

-- Income authenticity detection output (circular transactions)
CREATE TABLE IF NOT EXISTS income_authenticity_flags (
    flag_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    counterparty_vpa TEXT NOT NULL,
    counterparty_name TEXT,
    debit_txn_id TEXT NOT NULL,
    debit_timestamp TEXT NOT NULL,
    debit_amount REAL NOT NULL,
    credit_txn_id TEXT NOT NULL,
    credit_timestamp TEXT NOT NULL,
    credit_amount REAL NOT NULL,
    detected_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (user_id) REFERENCES users(user_id),
    FOREIGN KEY (debit_txn_id) REFERENCES transactions(txn_id),
    FOREIGN KEY (credit_txn_id) REFERENCES transactions(txn_id)
);

-- Shared risky counterparties output
CREATE TABLE IF NOT EXISTS shared_risk_counterparties (
    counterparty_vpa TEXT PRIMARY KEY,
    counterparty_name TEXT,
    unique_user_count INTEGER NOT NULL,
    total_flag_count INTEGER NOT NULL,
    detected_at TEXT DEFAULT (datetime('now'))
);

-- Spending vs income trend output
CREATE TABLE IF NOT EXISTS spending_trends (
    trend_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    income_trend_pct REAL NOT NULL,
    spending_trend_pct REAL NOT NULL,
    is_flagged INTEGER NOT NULL,
    computed_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);


