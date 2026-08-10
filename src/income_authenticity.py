"""
income_authenticity.py
======================
Detection module for Institutional View to analyze:
1. Circular Transactions: Counterparties appearing as both credit source and debit destination
   for the same user, with similar amounts (within 15%) and close timing (within 7 days),
   repeating across 2+ distinct months.
2. Shared Risky Counterparties: Counterparties appearing in fraud_flags for 3+ different users.
"""

import sys
import sqlite3
import uuid
from datetime import datetime
from collections import defaultdict

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass


def detect_circular_transactions(user_id: str, conn: sqlite3.Connection) -> list[dict]:
    # Query debits
    debits = conn.execute(
        """
        SELECT txn_id, timestamp, amount, counterparty_vpa, counterparty_name
        FROM transactions
        WHERE user_id = ? AND direction = 'debit'
        """,
        (user_id,)
    ).fetchall()
    
    # Query credits
    credits = conn.execute(
        """
        SELECT txn_id, timestamp, amount, counterparty_vpa, counterparty_name
        FROM transactions
        WHERE user_id = ? AND direction = 'credit'
        """,
        (user_id,)
    ).fetchall()

    debits_by_vpa = defaultdict(list)
    for r in debits:
        debits_by_vpa[r[3]].append({
            "txn_id": r[0],
            "timestamp": datetime.strptime(r[1], "%Y-%m-%d %H:%M:%S"),
            "amount": r[2],
            "counterparty_name": r[4]
        })
        
    credits_by_vpa = defaultdict(list)
    for r in credits:
        credits_by_vpa[r[3]].append({
            "txn_id": r[0],
            "timestamp": datetime.strptime(r[1], "%Y-%m-%d %H:%M:%S"),
            "amount": r[2],
            "counterparty_name": r[4]
        })

    circular_pairs = []
    
    for vpa in set(debits_by_vpa.keys()).intersection(credits_by_vpa.keys()):
        vpa_debits = debits_by_vpa[vpa]
        vpa_credits = credits_by_vpa[vpa]
        
        matches = []
        for deb in vpa_debits:
            for cred in vpa_credits:
                # Check timing within 7 days
                time_diff = abs((deb["timestamp"] - cred["timestamp"]).days)
                if time_diff <= 7:
                    # Check amount within 15%
                    max_amt = max(deb["amount"], cred["amount"])
                    amt_diff_pct = abs(deb["amount"] - cred["amount"]) / max_amt if max_amt > 0 else 0
                    if amt_diff_pct <= 0.15:
                        matches.append((deb, cred))
        
        # Check if matched pairs repeat across 2+ distinct months (based on debit timestamp month)
        months = set(pair[0]["timestamp"].strftime("%Y-%m") for pair in matches)
        if len(months) >= 2:
            for deb, cred in matches:
                circular_pairs.append({
                    "user_id": user_id,
                    "counterparty_vpa": vpa,
                    "counterparty_name": deb["counterparty_name"] or cred["counterparty_name"] or vpa,
                    "debit_txn_id": deb["txn_id"],
                    "debit_timestamp": deb["timestamp"].strftime("%Y-%m-%d %H:%M:%S"),
                    "debit_amount": deb["amount"],
                    "credit_txn_id": cred["txn_id"],
                    "credit_timestamp": cred["timestamp"].strftime("%Y-%m-%d %H:%M:%S"),
                    "credit_amount": cred["amount"]
                })
                
    return circular_pairs


def detect_shared_risky_counterparties(conn: sqlite3.Connection) -> list[dict]:
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT
            t.counterparty_vpa,
            t.counterparty_name,
            COUNT(DISTINCT ff.user_id) AS unique_user_count,
            COUNT(ff.flag_id) AS total_flag_count
        FROM fraud_flags ff
        JOIN transactions t ON ff.txn_id = t.txn_id
        GROUP BY t.counterparty_vpa
        HAVING unique_user_count >= 3
        """
    )
    rows = cursor.fetchall()
    results = []
    for r in rows:
        results.append({
            "counterparty_vpa": r[0],
            "counterparty_name": r[1],
            "unique_user_count": r[2],
            "total_flag_count": r[3]
        })
    return results


def run(conn: sqlite3.Connection):
    cur = conn.cursor()
    
    # 1. Clear old entries (make run idempotent)
    cur.execute("DELETE FROM income_authenticity_flags")
    cur.execute("DELETE FROM shared_risk_counterparties")
    
    # 2. Compute and save shared risky counterparties
    shared_risky = detect_shared_risky_counterparties(conn)
    for sr in shared_risky:
        cur.execute(
            """
            INSERT OR REPLACE INTO shared_risk_counterparties (counterparty_vpa, counterparty_name, unique_user_count, total_flag_count)
            VALUES (?, ?, ?, ?)
            """,
            (sr["counterparty_vpa"], sr["counterparty_name"], sr["unique_user_count"], sr["total_flag_count"])
        )
        
    # 3. Compute and save circular transaction flags for all users
    cur.execute("SELECT user_id FROM users")
    user_ids = [r[0] for r in cur.fetchall()]
    
    total_flags = 0
    for u_id in user_ids:
        flags = detect_circular_transactions(u_id, conn)
        for f in flags:
            flag_id = str(uuid.uuid4())
            cur.execute(
                """
                INSERT INTO income_authenticity_flags (
                    flag_id, user_id, counterparty_vpa, counterparty_name,
                    debit_txn_id, debit_timestamp, debit_amount,
                    credit_txn_id, credit_timestamp, credit_amount
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    flag_id, u_id, f["counterparty_vpa"], f["counterparty_name"],
                    f["debit_txn_id"], f["debit_timestamp"], f["debit_amount"],
                    f["credit_txn_id"], f["credit_timestamp"], f["credit_amount"]
                )
            )
            total_flags += 1
            
    conn.commit()
    print(f"✅ Income authenticity detection complete: {total_flags} circular transaction flags, {len(shared_risky)} shared risk counterparties.")


if __name__ == "__main__":
    import os
    DB_PATH = "../data/upi_transactions.db"
    if os.path.exists(DB_PATH):
        conn = sqlite3.connect(DB_PATH)
        run(conn)
        conn.close()
    else:
        print("Database not found. Run main.py first.")
