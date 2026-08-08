"""
main.py
=======
Single entry point that runs the entire pipeline in order:

  1. generate_dataset.py    -> builds ../data/upi_transactions.db from scratch
  2. subscription_detector  -> populates detected_subscriptions table
  3. fraud_detector         -> populates fraud_flags table
  4. credit_score           -> populates credit_scores table

Run this once to set up a fully working demo database. Re-run any time
to regenerate everything fresh (all modules are idempotent — they clear
their own output tables before re-inserting).

Usage:
    python main.py
"""

import sqlite3
import subprocess
import sys

import subscription_detector
import fraud_detector
import credit_score

DB_PATH = "../data/upi_transactions.db"


def main():
    print("=" * 60)
    print("UPI TRANSACTION INTELLIGENCE PLATFORM — Pipeline Run")
    print("=" * 60)

    print("\n[1/4] Generating synthetic dataset...")
    subprocess.run([sys.executable, "generate_dataset.py"], check=True)

    conn = sqlite3.connect(DB_PATH)

    print("\n[2/4] Running subscription detection...")
    subscription_detector.run(conn)

    print("\n[3/4] Running fraud detection...")
    fraud_detector.run(conn)

    print("\n[4/4] Running credit scoring...")
    credit_score.run(conn)

    conn.close()

    print("\n" + "=" * 60)
    print("✅ Pipeline complete. Database ready at:", DB_PATH)
    print("   Next: build Streamlit dashboard / Groq chat layer on top of this DB.")
    print("=" * 60)


if __name__ == "__main__":
    main()
