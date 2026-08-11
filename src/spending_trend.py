"""
spending_trend.py
=================
Detection module to calculate month-over-month trends for income and spending,
and flag profiles where spending growth rate meaningfully exceeds income growth rate.
"""

import sys
import sqlite3
import uuid
from datetime import datetime

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass


def calculate_slope_pct(values: list[float]) -> float:
    n = len(values)
    if n < 2:
        return 0.0
    mean_val = sum(values) / n
    if mean_val == 0:
        return 0.0
    
    x = list(range(n))
    mean_x = sum(x) / n
    
    numerator = sum((x[i] - mean_x) * (values[i] - mean_val) for i in range(n))
    denominator = sum((x[i] - mean_x) ** 2 for i in range(n))
    
    if denominator == 0:
        return 0.0
    
    slope = numerator / denominator
    # Normalize by mean to get a percentage trend relative to the user's average volume
    return (slope / mean_val) * 100.0


def detect_spending_income_divergence(user_id: str, conn: sqlite3.Connection) -> dict:
    current_month = datetime.now().strftime("%Y-%m")
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT substr(timestamp, 1, 7) AS month,
               SUM(CASE WHEN direction = 'credit' THEN amount ELSE 0 END) AS total_credit,
               SUM(CASE
                   WHEN direction = 'debit'
                        AND NOT EXISTS (
                            SELECT 1 FROM fraud_flags ff WHERE ff.txn_id = transactions.txn_id
                        )
                   THEN amount
                   ELSE 0
               END) AS total_debit
        FROM transactions
        WHERE user_id = ? AND substr(timestamp, 1, 7) != ?
        GROUP BY month
        ORDER BY month ASC
        """,
        (user_id, current_month)
    )
    rows = cursor.fetchall()
    
    if len(rows) < 2:
        return {
            "user_id": user_id,
            "income_trend": 0.0,
            "spending_trend": 0.0,
            "is_flagged": False,
            "description": "Insufficient data to compute monthly trends (requires at least 2 months)."
        }
        
    credits = [r[1] for r in rows]
    debits = [r[2] for r in rows]
    
    income_trend = calculate_slope_pct(credits)
    spending_trend = calculate_slope_pct(debits)
    
    # Flag if spending trend is higher than income trend by more than 2.0%
    is_flagged = spending_trend > (income_trend + 2.0)
    
    if is_flagged:
        description = (
            f"Spending growth trend (+{spending_trend:.1f}% MoM) exceeds "
            f"income growth trend ({'+' if income_trend >= 0 else ''}{income_trend:.1f}% MoM) "
            f"by more than the 2% threshold, indicating potential financial stress."
        )
    else:
        description = (
            f"Spending growth trend ({'+' if spending_trend >= 0 else ''}{spending_trend:.1f}% MoM) "
            f"is sustainable relative to income growth trend ({'+' if income_trend >= 0 else ''}{income_trend:.1f}% MoM)."
        )
        
    return {
        "user_id": user_id,
        "income_trend": round(income_trend, 2),
        "spending_trend": round(spending_trend, 2),
        "is_flagged": is_flagged,
        "description": description
    }


def run(conn: sqlite3.Connection):
    cur = conn.cursor()
    
    # 1. Clear old records
    cur.execute("DELETE FROM spending_trends")
    
    # 2. Query all users
    cur.execute("SELECT user_id FROM users")
    user_ids = [r[0] for r in cur.fetchall()]
    
    flagged_count = 0
    for u_id in user_ids:
        res = detect_spending_income_divergence(u_id, conn)
        trend_id = str(uuid.uuid4())
        cur.execute(
            """
            INSERT INTO spending_trends (trend_id, user_id, income_trend_pct, spending_trend_pct, is_flagged)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                trend_id,
                u_id,
                res["income_trend"],
                res["spending_trend"],
                1 if res["is_flagged"] else 0
            )
        )
        if res["is_flagged"]:
            flagged_count += 1
            
    conn.commit()
    print(f"✅ Spending trend detection complete: {flagged_count} profiles flagged where spending outpaces income.")


if __name__ == "__main__":
    import os
    DB_PATH = "../data/upi_transactions.db"
    if os.path.exists(DB_PATH):
        conn = sqlite3.connect(DB_PATH)
        run(conn)
        conn.close()
    else:
        print("Database not found. Run main.py first.")
