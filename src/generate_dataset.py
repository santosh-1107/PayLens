"""
generate_dataset.py
====================
Generates a synthetic UPI transaction dataset and loads it into SQLite.

WHY THIS MATTERS: this is the foundation of the whole demo. Since we
don't have real Account Aggregator access (out of scope for a 3-day
prototype), we simulate what AA data would look like — but we
deliberately EMBED patterns (recurring subscriptions, anomalies) so
that the rule engine modules have something real to detect. Without
this, the fraud/subscription detectors would have nothing to catch
and the demo would fall flat.

Ground-truth labels (is_synthetic_anomaly, and subscription membership
via counterparty_vpa naming) are stored ONLY for our own validation —
the detection modules do NOT read these labels. They must "discover"
the patterns using the same logic that would apply to real data.

Usage:
    python generate_dataset.py
Output:
    ../data/upi_transactions.db   (SQLite database)
"""

import sqlite3
import random
import uuid
import os
from datetime import datetime, timedelta
from faker import Faker

fake = Faker("en_IN")
random.seed(42)  # reproducible dataset across demo runs

DB_PATH = "../data/upi_transactions.db"
SCHEMA_PATH = "schema.sql"

NUM_USERS = 40
SIMULATION_DAYS = 180  # 6 months of history — enough for subscription intervals to repeat 4-6 times

# Known "subscription-style" merchants — recurring, fixed-ish amount
SUBSCRIPTION_MERCHANTS = [
    ("netflix@upi", "Netflix", 199, 649, 30),
    ("gym.fitclub@upi", "FitClub Gym", 999, 999, 30),
    ("lic.insurance@upi", "LIC Premium", 2500, 2500, 30),
    ("spotify@upi", "Spotify", 119, 119, 30),
    ("broadband.act@upi", "ACT Broadband", 799, 799, 30),
]

# Regular (non-recurring) merchant categories for normal spending noise
REGULAR_MERCHANTS = [
    ("zomato@upi", "Zomato", "food"),
    ("swiggy@upi", "Swiggy", "food"),
    ("bigbasket@upi", "BigBasket", "grocery"),
    ("bescom@upi", "BESCOM Electricity", "utility"),
    ("localgrocer@upi", "Local Grocer", "grocery"),
    ("petrolpump@upi", "HP Petrol Pump", "fuel"),
    ("apollo.pharmacy@upi", "Apollo Pharmacy", "health"),
]


def create_schema(conn):
    with open(SCHEMA_PATH, "r") as f:
        conn.executescript(f.read())
    conn.commit()


def create_users(conn):
    users = []
    for i in range(NUM_USERS):
        user_id = f"user_{i+1:03d}"
        name = fake.name()
        # Some users have regular salary income, some (gig workers) have irregular income
        income_estimate = random.choice(
            [12000, 15000, 18000, 22000, 28000, 35000, 45000, 55000, 70000, 90000]
        )
        users.append((user_id, name, income_estimate))

    conn.executemany(
        "INSERT INTO users (user_id, name, monthly_income_estimate) VALUES (?, ?, ?)",
        users,
    )
    conn.commit()
    return [u[0] for u in users]


def random_timestamp(day_offset, business_hours=True):
    base_date = datetime.now() - timedelta(days=SIMULATION_DAYS - day_offset)
    if business_hours:
        hour = random.randint(7, 22)
    else:
        hour = random.randint(0, 23)
    minute = random.randint(0, 59)
    return base_date.replace(hour=hour, minute=minute, second=0, microsecond=0)


def generate_subscriptions_for_user(user_id, txns):
    """Each user subscribes to 1-3 recurring services, paid roughly every
    ~30 days with small jitter (real UPI Autopay isn't perfectly punctual)."""
    n_subs = random.randint(1, 3)
    chosen = random.sample(SUBSCRIPTION_MERCHANTS, n_subs)

    for vpa, name, min_amt, max_amt, interval in chosen:
        amount = random.choice([min_amt, max_amt])
        day = random.randint(1, 10)  # first payment happens early in the window
        while day < SIMULATION_DAYS:
            jitter = random.randint(-2, 2)  # real recurring payments aren't exact to the day
            ts = random_timestamp(min(day + jitter, SIMULATION_DAYS - 1))
            txns.append({
                "txn_id": str(uuid.uuid4()),
                "user_id": user_id,
                "timestamp": ts.strftime("%Y-%m-%d %H:%M:%S"),
                "amount": amount,
                "direction": "debit",
                "counterparty_vpa": vpa,
                "counterparty_name": name,
                "category": "subscription",
                "txn_type": "P2M",
                "narration": f"UPI/{name}/Recurring/Autopay",
                "is_synthetic_anomaly": 0,
            })
            day += interval


def generate_regular_spending(user_id, txns):
    """Normal day-to-day noise: groceries, food delivery, utilities, fuel."""
    n_txns = random.randint(40, 80)
    for _ in range(n_txns):
        vpa, name, category = random.choice(REGULAR_MERCHANTS)
        amount = round(random.uniform(50, 1500), 2)
        day = random.randint(0, SIMULATION_DAYS - 1)
        ts = random_timestamp(day)
        txns.append({
            "txn_id": str(uuid.uuid4()),
            "user_id": user_id,
            "timestamp": ts.strftime("%Y-%m-%d %H:%M:%S"),
            "amount": amount,
            "direction": "debit",
            "counterparty_vpa": vpa,
            "counterparty_name": name,
            "category": category,
            "txn_type": "P2M",
            "narration": f"UPI/{name}/Payment",
            "is_synthetic_anomaly": 0,
        })


def generate_income(user_id, monthly_income, txns):
    """Simulate income: some users get regular monthly salary (formal),
    others get irregular smaller credits (gig/informal work) — this
    directly feeds the credit-scoring module's 'income regularity' feature."""
    is_regular = random.random() > 0.4  # 60% regular salaried, 40% gig-style irregular

    if is_regular:
        for month in range(SIMULATION_DAYS // 30):
            day = month * 30 + random.randint(1, 3)
            if day >= SIMULATION_DAYS:
                continue
            ts = random_timestamp(day)
            txns.append({
                "txn_id": str(uuid.uuid4()),
                "user_id": user_id,
                "timestamp": ts.strftime("%Y-%m-%d %H:%M:%S"),
                "amount": monthly_income,
                "direction": "credit",
                "counterparty_vpa": "employer.payroll@upi",
                "counterparty_name": "Employer Payroll",
                "category": "salary",
                "txn_type": "P2P",
                "narration": "UPI/Salary/Credit",
                "is_synthetic_anomaly": 0,
            })
    else:
        # irregular smaller credits scattered through the period, summing to roughly similar total
        n_credits = random.randint(10, 20)
        per_credit = (monthly_income * (SIMULATION_DAYS / 30)) / n_credits
        for _ in range(n_credits):
            day = random.randint(0, SIMULATION_DAYS - 1)
            ts = random_timestamp(day)
            amount = round(per_credit * random.uniform(0.5, 1.5), 2)
            txns.append({
                "txn_id": str(uuid.uuid4()),
                "user_id": user_id,
                "timestamp": ts.strftime("%Y-%m-%d %H:%M:%S"),
                "amount": amount,
                "direction": "credit",
                "counterparty_vpa": f"client{random.randint(1,9)}@upi",
                "counterparty_name": "Client Payment",
                "category": "gig_income",
                "txn_type": "P2P",
                "narration": "UPI/Payment Received",
                "is_synthetic_anomaly": 0,
            })


def _anomaly_amount() -> float:
    """Vary spike sizes so risk scores spread across low and high tiers."""
    if random.random() < 0.45:
        return round(random.uniform(5000, 10000), 2)
    return round(random.uniform(15000, 40000), 2)


def inject_fraud_anomalies(user_id, txns):
    """Deliberately inject 3-7 suspicious transactions per user so the
    fraud detection module has real signal to catch. Types:
    1. Odd-hour large payment to a brand-new counterparty
    2. Sudden amount spike vs user's normal spending
    3. High-velocity burst (multiple payments in a short window)
    """
    n_anomalies = random.randint(3, 7)
    for i in range(n_anomalies):
        anomaly_type = random.choice(["odd_hour_new_payee", "amount_spike", "velocity_burst"])
        day = random.randint(0, SIMULATION_DAYS - 1)

        if anomaly_type in ("odd_hour_new_payee", "amount_spike"):
            ts = random_timestamp(day, business_hours=False)
            amount = _anomaly_amount()
            fake_vpa = f"unknown{random.randint(1000,9999)}@okaxis"
            txns.append({
                "txn_id": str(uuid.uuid4()),
                "user_id": user_id,
                "timestamp": ts.strftime("%Y-%m-%d %H:%M:%S"),
                "amount": amount,
                "direction": "debit",
                "counterparty_vpa": fake_vpa,
                "counterparty_name": "Unknown",
                "category": "p2p",
                "txn_type": "P2P",
                "narration": "UPI/Payment/New Payee",
                "is_synthetic_anomaly": 1,
            })
        else:  # velocity_burst: 3 rapid payments within ~10 minutes
            base_ts = random_timestamp(day)
            burst_amount = _anomaly_amount() / 3
            for j in range(3):
                ts = base_ts + timedelta(minutes=j * 3)
                txns.append({
                    "txn_id": str(uuid.uuid4()),
                    "user_id": user_id,
                    "timestamp": ts.strftime("%Y-%m-%d %H:%M:%S"),
                    "amount": round(burst_amount * random.uniform(0.85, 1.15), 2),
                    "direction": "debit",
                    "counterparty_vpa": f"burst{random.randint(100,999)}@okicici",
                    "counterparty_name": "Unknown",
                    "category": "p2p",
                    "txn_type": "P2P",
                    "narration": "UPI/Payment/Rapid",
                    "is_synthetic_anomaly": 1,
                })


def generate_circular_transactions(user_id, txns):
    """Simulates circular transaction patterns ('salary washing') for about 15% of users.
    Returns True if injected, False otherwise."""
    if random.random() >= 0.15:
        return False

    circle_id = random.randint(100, 999)
    counterparty_vpa = f"circle{circle_id}@upi"
    counterparty_name = f"Circle Partner {circle_id}"

    n_months = random.randint(3, 4)
    max_start_month = (SIMULATION_DAYS // 30) - n_months
    if max_start_month < 0:
        max_start_month = 0
    start_month = random.randint(0, max_start_month)

    amount = round(random.uniform(15000, 30000), 2)

    for m in range(start_month, start_month + n_months):
        day_credit = m * 30 + random.randint(1, 10)
        ts_credit = random_timestamp(day_credit)
        txns.append({
            "txn_id": str(uuid.uuid4()),
            "user_id": user_id,
            "timestamp": ts_credit.strftime("%Y-%m-%d %H:%M:%S"),
            "amount": amount,
            "direction": "credit",
            "counterparty_vpa": counterparty_vpa,
            "counterparty_name": counterparty_name,
            "category": "salary",
            "txn_type": "P2P",
            "narration": "UPI/Salary/Credit",
            "is_synthetic_anomaly": 0,
        })

        day_debit = day_credit + random.randint(2, 5)
        if day_debit >= SIMULATION_DAYS:
            day_debit = SIMULATION_DAYS - 1

        ts_debit = random_timestamp(day_debit)
        debit_amount = round(amount * random.uniform(0.86, 0.95), 2)

        txns.append({
            "txn_id": str(uuid.uuid4()),
            "user_id": user_id,
            "timestamp": ts_debit.strftime("%Y-%m-%d %H:%M:%S"),
            "amount": debit_amount,
            "direction": "debit",
            "counterparty_vpa": counterparty_vpa,
            "counterparty_name": counterparty_name,
            "category": "p2p",
            "txn_type": "P2P",
            "narration": "UPI/Payment/Transfer",
            "is_synthetic_anomaly": 0,
        })

    return True


def main():
    # Idempotent re-runs: wipe any existing database file first so this
    # script can be run repeatedly (e.g. via main.py) without unique-
    # constraint errors from leftover data.
    if os.path.exists(DB_PATH):
        try:
            os.remove(DB_PATH)
        except PermissionError:
            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()
            cur.execute("PRAGMA foreign_keys = OFF;")
            cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = [r[0] for r in cur.fetchall() if r[0] != 'sqlite_sequence']
            for table in tables:
                cur.execute(f"DELETE FROM {table};")
            cur.execute("PRAGMA foreign_keys = ON;")
            conn.commit()
            conn.close()

    conn = sqlite3.connect(DB_PATH)
    create_schema(conn)

    user_ids_incomes = []
    cur = conn.cursor()
    users = create_users(conn)

    cur.execute("SELECT user_id, monthly_income_estimate FROM users")
    user_income_map = dict(cur.fetchall())

    all_txns = []
    circular_users_count = 0
    for user_id in users:
        generate_subscriptions_for_user(user_id, all_txns)
        generate_regular_spending(user_id, all_txns)
        generate_income(user_id, user_income_map[user_id], all_txns)
        inject_fraud_anomalies(user_id, all_txns)
        if generate_circular_transactions(user_id, all_txns):
            circular_users_count += 1

    # Sort by timestamp for realism (not required, but nice for eyeballing the data)
    all_txns.sort(key=lambda t: t["timestamp"])

    cur.executemany(
        """INSERT INTO transactions
           (txn_id, user_id, timestamp, amount, direction, counterparty_vpa,
            counterparty_name, category, txn_type, narration, is_synthetic_anomaly)
           VALUES (:txn_id, :user_id, :timestamp, :amount, :direction, :counterparty_vpa,
                   :counterparty_name, :category, :txn_type, :narration, :is_synthetic_anomaly)""",
        all_txns,
    )
    conn.commit()

    print(f"✅ Generated {len(all_txns)} transactions for {len(users)} users")
    print(f"✅ Database written to {DB_PATH}")

    # Quick sanity summary
    cur.execute("SELECT COUNT(*) FROM transactions WHERE is_synthetic_anomaly = 1")
    print(f"   - Injected fraud anomalies: {cur.fetchone()[0]}")
    cur.execute("SELECT COUNT(*) FROM transactions WHERE category = 'subscription'")
    print(f"   - Subscription-pattern transactions: {cur.fetchone()[0]}")
    print(f"   - Users with circular transactions: {circular_users_count}")

    conn.close()


if __name__ == "__main__":
    main()
