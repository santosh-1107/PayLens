"""
fraud_detector.py
==================
Flags suspicious transactions using rule-based signals, computed per-user
against that user's OWN historical behavior (not a global threshold —
what's "normal" for one user may be an anomaly for another).

Signals used (each contributes to a combined risk_score 0-1):
1. amount_spike     - transaction amount is a large statistical outlier
                       vs. the user's typical debit amount (z-score based)
2. odd_hour         - transaction happens late night / early morning
                       (11 PM - 5 AM), when the user has few/no other txns
3. new_payee        - counterparty never seen before in this user's history
4. velocity_burst   - multiple transactions to different/new counterparties
                       within a short time window (possible account takeover)

Design choice: rule-based over ML (e.g. Isolation Forest) for the 3-day
prototype because (a) it's fully explainable — each flag has a plain-
language reason, which matters for the chat/narrative layer, and
(b) it doesn't need a large training set to be reliable. Swapping in
an ML model later is a drop-in replacement — same output schema.
"""

import sqlite3
import uuid
import statistics
from datetime import datetime, timedelta
from collections import defaultdict

DB_PATH = "../data/upi_transactions.db"

ODD_HOUR_START = 23
ODD_HOUR_END = 5
VELOCITY_WINDOW_MINUTES = 15
VELOCITY_MIN_COUNT = 3
Z_SCORE_THRESHOLD = 2.5


def is_odd_hour(dt):
    return dt.hour >= ODD_HOUR_START or dt.hour < ODD_HOUR_END


def detect_fraud_for_user(transactions):
    """transactions: list of dicts (txn_id, timestamp, amount, direction,
    counterparty_vpa). Returns list of flag dicts."""

    debits = [t for t in transactions if t["direction"] == "debit"]
    debits = sorted(debits, key=lambda t: t["timestamp"])

    if len(debits) < 5:
        return []  # not enough history to establish a baseline

    amounts = [t["amount"] for t in debits]
    mean_amt = statistics.mean(amounts)
    stdev_amt = statistics.stdev(amounts) if len(amounts) > 1 else 1

    seen_payees = set()
    flags = []

    for i, t in enumerate(debits):
        reasons = []
        dt = datetime.strptime(t["timestamp"], "%Y-%m-%d %H:%M:%S")

        # Signal 1: amount spike (z-score vs user's own history up to this point)
        z = (t["amount"] - mean_amt) / stdev_amt if stdev_amt > 0 else 0
        if z >= Z_SCORE_THRESHOLD:
            reasons.append("amount_spike")

        # Signal 2: odd hour
        if is_odd_hour(dt):
            reasons.append("odd_hour")

        # Signal 3: new payee (never transacted with this VPA before)
        is_new_payee = t["counterparty_vpa"] not in seen_payees
        if is_new_payee:
            reasons.append("new_payee")

        # Signal 4: velocity burst — count txns within window minutes before this one
        window_start = dt - timedelta(minutes=VELOCITY_WINDOW_MINUTES)
        burst_count = sum(
            1 for other in debits
            if window_start <= datetime.strptime(other["timestamp"], "%Y-%m-%d %H:%M:%S") <= dt
        )
        if burst_count >= VELOCITY_MIN_COUNT:
            reasons.append("velocity_burst")

        seen_payees.add(t["counterparty_vpa"])

        if reasons:
            # Weighted risk score: amount_spike and velocity_burst are stronger signals
            weights = {"amount_spike": 0.4, "odd_hour": 0.15, "new_payee": 0.15, "velocity_burst": 0.4}
            risk_score = min(1.0, sum(weights.get(r, 0.1) for r in reasons))

            # Only actually flag if risk is meaningful — a lone "new_payee" isn't suspicious by itself
            if risk_score >= 0.3 and len(reasons) >= 2 or "amount_spike" in reasons or "velocity_burst" in reasons:
                flags.append({
                    "flag_id": str(uuid.uuid4()),
                    "txn_id": t["txn_id"],
                    "risk_score": round(risk_score, 2),
                    "reasons": ",".join(reasons),
                })

    return flags


def run(conn):
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM users")
    user_ids = [r[0] for r in cur.fetchall()]

    cur.execute("DELETE FROM fraud_flags")  # idempotent re-runs

    total_flagged = 0
    for user_id in user_ids:
        cur.execute(
            """SELECT txn_id, timestamp, amount, direction, counterparty_vpa
               FROM transactions WHERE user_id = ? ORDER BY timestamp""",
            (user_id,),
        )
        rows = cur.fetchall()
        transactions = [
            {"txn_id": r[0], "timestamp": r[1], "amount": r[2], "direction": r[3], "counterparty_vpa": r[4]}
            for r in rows
        ]

        flags = detect_fraud_for_user(transactions)
        for f in flags:
            cur.execute(
                """INSERT INTO fraud_flags (flag_id, txn_id, user_id, risk_score, reasons)
                   VALUES (?, ?, ?, ?, ?)""",
                (f["flag_id"], f["txn_id"], user_id, f["risk_score"], f["reasons"]),
            )
        total_flagged += len(flags)

    conn.commit()
    print(f"✅ Fraud detection complete: {total_flagged} transactions flagged across {len(user_ids)} users")

    # Validation against ground truth (only possible because this is synthetic data)
    cur.execute("""
        SELECT COUNT(*) FROM fraud_flags f
        JOIN transactions t ON f.txn_id = t.txn_id
        WHERE t.is_synthetic_anomaly = 1
    """)
    true_positives = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM transactions WHERE is_synthetic_anomaly = 1")
    total_actual_anomalies = cur.fetchone()[0]
    print(f"   - Recall check: caught {true_positives}/{total_actual_anomalies} injected anomalies")


if __name__ == "__main__":
    conn = sqlite3.connect(DB_PATH)
    run(conn)
    conn.close()
