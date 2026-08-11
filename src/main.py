"""
main.py
=======
Single entry point that runs the entire pipeline in order:

  1. generate_dataset.py    -> builds ../data/upi_transactions.db from scratch
  2. subscription_detector  -> populates detected_subscriptions table
  3. fraud_detector         -> populates fraud_flags table
  4. credit_score           -> populates credit_scores table
  5. income_authenticity    -> populates income_authenticity_flags / shared_risk_counterparties tables
  6. spending_trend         -> populates spending_trends table

Run this once to set up a fully working demo database. Re-run any time
to regenerate everything fresh (all modules are idempotent — they clear
their own output tables before re-inserting).

Usage:
    python main.py
"""

import os
import sqlite3
import subprocess
import sys
sys.stdout.reconfigure(encoding='utf-8')

import subscription_detector
import fraud_detector
import credit_score
import income_authenticity
import spending_trend

DB_PATH = "../data/upi_transactions.db"


def main():
    os.environ["PYTHONIOENCODING"] = "utf-8"
    print("=" * 60)
    print("UPI TRANSACTION INTELLIGENCE PLATFORM — Pipeline Run")
    print("=" * 60)

    print("\n[1/6] Generating synthetic dataset...")
    subprocess.run([sys.executable, "generate_dataset.py"], check=True)

    conn = sqlite3.connect(DB_PATH)

    print("\n[2/6] Running subscription detection...")
    subscription_detector.run(conn)

    print("\n[3/6] Running fraud detection...")
    fraud_detector.run(conn)

    print("\n[4/6] Running credit scoring...")
    credit_score.run(conn)

    print("\n[5/6] Running income authenticity detection...")
    income_authenticity.run(conn)

    print("\n[6/6] Running spending vs income trend analysis...")
    spending_trend.run(conn)

    conn.close()

    print("\n" + "=" * 60)
    print("✅ Pipeline complete (6 steps). Database ready at:", DB_PATH)
    print("   Next: build Streamlit dashboard / Groq chat layer on top of this DB.")
    print("=" * 60)


if __name__ == "__main__":
    main()
