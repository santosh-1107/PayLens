"""
subscription_detector.py
=========================
Detects recurring/subscription-style payments from raw transaction history.

LOGIC (deliberately rule-based, not ML — this is the right tool for the
job): group transactions by counterparty, then check if the payments
repeat at a roughly-consistent interval with a roughly-consistent amount.
Real recurring payments (Autopay/e-mandates) aren't perfectly punctual —
so we allow tolerance on both interval and amount rather than requiring
exact matches.

IMPORTANT: this module does NOT use the `is_synthetic_anomaly` or
"subscription" category labels from the generator. It re-discovers
patterns purely from timestamp + amount + counterparty — the same way
it would have to work on real, unlabeled Account Aggregator data.
"""

import sqlite3
import uuid
from datetime import datetime, timedelta
from collections import defaultdict

DB_PATH = "../data/upi_transactions.db"

MIN_OCCURRENCES = 3          # need at least 3 repeats to call it a "subscription"
INTERVAL_TOLERANCE_DAYS = 4  # allow +/- 4 days of jitter around detected interval
AMOUNT_TOLERANCE_PCT = 0.05  # allow +/- 5% amount variation


def detect_subscriptions_for_user(transactions):
    """transactions: list of dicts with keys timestamp, amount, counterparty_vpa,
    counterparty_name, direction. Returns list of detected subscription dicts."""

    # Only debit transactions can be subscriptions
    debits = [t for t in transactions if t["direction"] == "debit"]

    # Group by counterparty
    by_counterparty = defaultdict(list)
    for t in debits:
        by_counterparty[t["counterparty_vpa"]].append(t)

    detected = []
    for vpa, txns in by_counterparty.items():
        if len(txns) < MIN_OCCURRENCES:
            continue

        txns = sorted(txns, key=lambda t: t["timestamp"])
        dates = [datetime.strptime(t["timestamp"], "%Y-%m-%d %H:%M:%S") for t in txns]
        amounts = [t["amount"] for t in txns]

        # Compute gaps between consecutive payments
        gaps = [(dates[i+1] - dates[i]).days for i in range(len(dates) - 1)]
        avg_gap = sum(gaps) / len(gaps)

        # Check consistency: are most gaps close to the average?
        consistent_gaps = [g for g in gaps if abs(g - avg_gap) <= INTERVAL_TOLERANCE_DAYS]
        gap_consistency_ratio = len(consistent_gaps) / len(gaps)

        # Check amount consistency
        avg_amount = sum(amounts) / len(amounts)
        consistent_amounts = [
            a for a in amounts if abs(a - avg_amount) <= AMOUNT_TOLERANCE_PCT * avg_amount
        ]
        amount_consistency_ratio = len(consistent_amounts) / len(amounts)

        # Only flag as subscription if BOTH interval and amount are consistent enough,
        # and the interval looks like a real recurring cadence (roughly weekly to roughly quarterly)
        if (
            gap_consistency_ratio >= 0.7
            and amount_consistency_ratio >= 0.7
            and 5 <= avg_gap <= 100
        ):
            confidence = round((gap_consistency_ratio + amount_consistency_ratio) / 2, 2)
            last_date = dates[-1]
            next_expected = last_date + timedelta(days=round(avg_gap))

            detected.append({
                "subscription_id": str(uuid.uuid4()),
                "counterparty_vpa": vpa,
                "counterparty_name": txns[-1]["counterparty_name"],
                "avg_amount": round(avg_amount, 2),
                "interval_days": round(avg_gap),
                "last_txn_date": last_date.strftime("%Y-%m-%d"),
                "next_expected_date": next_expected.strftime("%Y-%m-%d"),
                "occurrence_count": len(txns),
                "confidence_score": confidence,
            })

    return detected


def run(conn):
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM users")
    user_ids = [r[0] for r in cur.fetchall()]

    cur.execute("DELETE FROM detected_subscriptions")  # idempotent re-runs

    total_detected = 0
    for user_id in user_ids:
        cur.execute(
            """SELECT timestamp, amount, counterparty_vpa, counterparty_name, direction
               FROM transactions WHERE user_id = ?""",
            (user_id,),
        )
        rows = cur.fetchall()
        transactions = [
            {
                "timestamp": r[0], "amount": r[1], "counterparty_vpa": r[2],
                "counterparty_name": r[3], "direction": r[4],
            }
            for r in rows
        ]

        subs = detect_subscriptions_for_user(transactions)
        for s in subs:
            cur.execute(
                """INSERT INTO detected_subscriptions
                   (subscription_id, user_id, counterparty_vpa, counterparty_name,
                    avg_amount, interval_days, last_txn_date, next_expected_date,
                    occurrence_count, confidence_score)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    s["subscription_id"], user_id, s["counterparty_vpa"], s["counterparty_name"],
                    s["avg_amount"], s["interval_days"], s["last_txn_date"], s["next_expected_date"],
                    s["occurrence_count"], s["confidence_score"],
                ),
            )
        total_detected += len(subs)

    conn.commit()
    print(f"✅ Subscription detection complete: {total_detected} subscriptions found across {len(user_ids)} users")


if __name__ == "__main__":
    conn = sqlite3.connect(DB_PATH)
    run(conn)
    conn.close()
