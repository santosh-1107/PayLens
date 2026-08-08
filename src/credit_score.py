"""
credit_score.py
================
Computes an alternate credit-worthiness score (300-900 range, mirrors
familiar CIBIL-style scoring) purely from UPI transaction cash-flow
patterns — no formal credit history required. This is the module that
serves gig/informal workers who are credit-invisible to traditional
bureaus.

DESIGN CHOICE: rule-based weighted formula, not a trained ML model.
Honest reasoning: training a real classifier needs labeled outcome data
(who actually defaulted), which we don't have and can't fabricate
credibly in 3 days. A transparent formula is more defensible in a demo
than a black-box model trained on fake labels. This is explicitly
scoped as "v1 heuristic — ML model with real repayment-outcome labels
is future work" (see README).

THREE COMPONENTS (each 0-1, then blended into final 300-900 score):

1. income_regularity: how consistent are credit (income) transactions
   in timing and amount? Regular salaried income scores high; highly
   sporadic gig income scores lower — but the point of this whole
   module is that even irregular income still gets a fair score,
   unlike a bank that just says "no formal payslip = no score".

2. expense_ratio: ratio of total debits to total credits. Someone who
   consistently spends within their means (spends less than they earn)
   scores higher than someone who is cash-flow negative.

3. volatility: how much does the account balance/cash flow swing month
   to month? Lower volatility (stable financial behavior) scores higher.
"""

import sqlite3
import uuid
import statistics
from datetime import datetime
from collections import defaultdict

DB_PATH = "../data/upi_transactions.db"


def compute_income_regularity(credits):
    """Returns 0-1. High = regular intervals + consistent amounts (formal salary-like).
    Lower = sporadic gig-style income, but still rewarded for frequency/consistency
    of ANY kind — this is the core equity fix vs traditional scoring."""
    if len(credits) < 2:
        return 0.0

    dates = sorted([datetime.strptime(c["timestamp"], "%Y-%m-%d %H:%M:%S") for c in credits])
    gaps = [(dates[i+1] - dates[i]).days for i in range(len(dates) - 1)]
    if not gaps:
        return 0.0

    avg_gap = statistics.mean(gaps)
    gap_stdev = statistics.stdev(gaps) if len(gaps) > 1 else 0

    # Coefficient of variation (lower = more regular timing)
    cv = gap_stdev / avg_gap if avg_gap > 0 else 1

    amounts = [c["amount"] for c in credits]
    amt_mean = statistics.mean(amounts)
    amt_stdev = statistics.stdev(amounts) if len(amounts) > 1 else 0
    amt_cv = amt_stdev / amt_mean if amt_mean > 0 else 1

    # Combine: lower variation = higher regularity score. Also reward higher
    # frequency of credits overall (more data points = more trustworthy signal).
    regularity = max(0, 1 - (cv * 0.5 + amt_cv * 0.5))
    frequency_bonus = min(1.0, len(credits) / 12) * 0.15  # up to 12 credits over 6mo = "regular enough"

    return round(min(1.0, regularity * 0.85 + frequency_bonus), 3)


def compute_expense_ratio_score(credits, debits):
    """Returns 0-1. Compares total spend to total income. Spending well
    within income = high score. Spending more than income = low score."""
    total_credit = sum(c["amount"] for c in credits)
    total_debit = sum(d["amount"] for d in debits)

    if total_credit == 0:
        return 0.0

    ratio = total_debit / total_credit  # >1 means spending more than earning

    if ratio <= 0.5:
        score = 1.0
    elif ratio <= 0.8:
        score = 0.8
    elif ratio <= 1.0:
        score = 0.6
    elif ratio <= 1.2:
        score = 0.3
    else:
        score = 0.1

    return score


def compute_volatility_score(credits, debits):
    """Returns 0-1. Looks at month-to-month net cash flow (credits - debits)
    and penalizes high swings. Stable cash flow = high score."""
    all_txns = credits + debits
    if len(all_txns) < 2:
        return 0.0

    monthly_net = defaultdict(float)
    for c in credits:
        month_key = c["timestamp"][:7]  # YYYY-MM
        monthly_net[month_key] += c["amount"]
    for d in debits:
        month_key = d["timestamp"][:7]
        monthly_net[month_key] -= d["amount"]

    values = list(monthly_net.values())
    if len(values) < 2:
        return 0.5  # not enough months of data to judge volatility fairly

    mean_val = statistics.mean(values)
    stdev_val = statistics.stdev(values)

    if mean_val == 0:
        return 0.0

    cv = abs(stdev_val / mean_val)
    # Lower coefficient of variation = more stable = higher score
    score = max(0, 1 - min(cv, 2) / 2)
    return round(score, 3)


def compute_score_for_user(transactions):
    credits = [t for t in transactions if t["direction"] == "credit"]
    debits = [t for t in transactions if t["direction"] == "debit"]

    income_reg = compute_income_regularity(credits)
    expense_score = compute_expense_ratio_score(credits, debits)
    volatility_score = compute_volatility_score(credits, debits)

    # Weighted blend: income regularity weighted highest since it's the
    # key differentiator for credit-invisible users
    blended = (income_reg * 0.45) + (expense_score * 0.30) + (volatility_score * 0.25)

    # Map 0-1 blended score to familiar 300-900 range
    final_score = round(300 + blended * 600)

    return {
        "score": final_score,
        "income_regularity_component": income_reg,
        "expense_ratio_component": expense_score,
        "volatility_component": volatility_score,
    }


def run(conn):
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM users")
    user_ids = [r[0] for r in cur.fetchall()]

    cur.execute("DELETE FROM credit_scores")  # idempotent re-runs

    for user_id in user_ids:
        cur.execute(
            "SELECT timestamp, amount, direction FROM transactions WHERE user_id = ?",
            (user_id,),
        )
        rows = cur.fetchall()
        transactions = [{"timestamp": r[0], "amount": r[1], "direction": r[2]} for r in rows]

        result = compute_score_for_user(transactions)
        cur.execute(
            """INSERT INTO credit_scores
               (score_id, user_id, score, income_regularity_component,
                expense_ratio_component, volatility_component)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                str(uuid.uuid4()), user_id, result["score"],
                result["income_regularity_component"], result["expense_ratio_component"],
                result["volatility_component"],
            ),
        )

    conn.commit()
    print(f"✅ Credit scoring complete: scores computed for {len(user_ids)} users")

    # Show a quick summary
    cur.execute("""
        SELECT u.name, u.monthly_income_estimate, c.score
        FROM credit_scores c JOIN users u ON c.user_id = u.user_id
        ORDER BY c.score DESC
    """)
    print("   Sample scores (name, declared income, computed score):")
    for row in cur.fetchall()[:5]:
        print(f"   - {row[0]}: ₹{row[1]}/mo -> score {row[2]}")


if __name__ == "__main__":
    conn = sqlite3.connect(DB_PATH)
    run(conn)
    conn.close()
