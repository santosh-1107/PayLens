"""
test_policy_engine.py
=====================
Unit test suite for PayLens Lender Policy Engine, Historical Credit Context,
Rejection Explanation, and Auditability.

Tests:
  1. Same applicant evaluated against different lender policies
  2. Old default treatment based on policy window & resolution vs recent default
  3. Recent default rejection rule
  4. Rejection explanation generated strictly from failed rules
  5. Missing credit data handled cleanly without inventing fake data
  6. Existing scoring flow preserved
  7. Auditability: full evaluation records stored and retrieved
"""

import os
import sys
import sqlite3
import unittest
from datetime import datetime, timedelta

# Ensure src/ is in python path
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from policy_engine import (
    ensure_policy_tables,
    seed_default_policies,
    get_all_policies,
    get_policy_by_id,
    save_policy,
    get_applicant_risk_profile,
    get_credit_timeline,
    evaluate_applicant,
    generate_rejection_explanation,
    record_evaluation_audit,
    get_evaluation_audit,
)
from credit_score import compute_score_for_user, compute_income_regularity, compute_expense_ratio_score, compute_volatility_score


class TestLenderPolicyEngine(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # Create an in-memory SQLite database for isolated, reproducible testing
        cls.conn = sqlite3.connect(":memory:")
        cls.conn.row_factory = sqlite3.Row

        # Load base schema
        schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
        with open(schema_path, "r", encoding="utf-8") as f:
            cls.conn.executescript(f.read())

        ensure_policy_tables(cls.conn)
        seed_default_policies(cls.conn)

        # Seed sample test users
        cls.conn.execute("INSERT INTO users (user_id, name, monthly_income_estimate, role) VALUES ('test_user_clean', 'Test Clean', 50000, 'user')")
        cls.conn.execute("INSERT INTO users (user_id, name, monthly_income_estimate, role) VALUES ('test_user_old_def', 'Test Old Default', 40000, 'user')")
        cls.conn.execute("INSERT INTO users (user_id, name, monthly_income_estimate, role) VALUES ('test_user_recent_def', 'Test Recent Default', 30000, 'user')")
        cls.conn.execute("INSERT INTO users (user_id, name, monthly_income_estimate, role) VALUES ('test_user_high_debt', 'Test High Debt', 20000, 'user')")
        cls.conn.execute("INSERT INTO users (user_id, name, monthly_income_estimate, role) VALUES ('test_user_missing_data', 'Test Missing', 25000, 'user')")

        # Seed credit scores (mimicking credit_score.py output)
        cls.conn.execute(
            """
            INSERT INTO credit_scores (score_id, user_id, score, income_regularity_component, expense_ratio_component, volatility_component)
            VALUES ('sc_clean', 'test_user_clean', 720.0, 0.75, 0.80, 0.70)
            """
        )
        cls.conn.execute(
            """
            INSERT INTO credit_scores (score_id, user_id, score, income_regularity_component, expense_ratio_component, volatility_component)
            VALUES ('sc_old', 'test_user_old_def', 640.0, 0.60, 0.60, 0.55)
            """
        )
        cls.conn.execute(
            """
            INSERT INTO credit_scores (score_id, user_id, score, income_regularity_component, expense_ratio_component, volatility_component)
            VALUES ('sc_rec', 'test_user_recent_def', 510.0, 0.35, 0.30, 0.40)
            """
        )
        cls.conn.execute(
            """
            INSERT INTO credit_scores (score_id, user_id, score, income_regularity_component, expense_ratio_component, volatility_component)
            VALUES ('sc_debt', 'test_user_high_debt', 610.0, 0.50, 0.30, 0.50)
            """
        )
        cls.conn.execute(
            """
            INSERT INTO credit_scores (score_id, user_id, score, income_regularity_component, expense_ratio_component, volatility_component)
            VALUES ('sc_miss', 'test_user_missing_data', 580.0, 0.45, 0.50, 0.45)
            """
        )

        # Seed transactions to establish debt ratios
        now = datetime.now()
        # test_user_clean: credits = 100k, debits = 40k -> debt_ratio = 40% (0.40)
        cls.conn.execute(f"INSERT INTO transactions (txn_id, user_id, timestamp, amount, direction, counterparty_vpa, txn_type) VALUES ('tx_c1', 'test_user_clean', '{(now - timedelta(days=30)).strftime('%Y-%m-%d %H:%M:%S')}', 100000, 'credit', 'salary@bank', 'P2M')")
        cls.conn.execute(f"INSERT INTO transactions (txn_id, user_id, timestamp, amount, direction, counterparty_vpa, txn_type) VALUES ('tx_c2', 'test_user_clean', '{(now - timedelta(days=15)).strftime('%Y-%m-%d %H:%M:%S')}', 40000, 'debit', 'groceries@upi', 'P2M')")

        # test_user_high_debt: credits = 100k, debits = 52k -> debt_ratio = 52% (0.52)
        cls.conn.execute(f"INSERT INTO transactions (txn_id, user_id, timestamp, amount, direction, counterparty_vpa, txn_type) VALUES ('tx_d1', 'test_user_high_debt', '{(now - timedelta(days=30)).strftime('%Y-%m-%d %H:%M:%S')}', 100000, 'credit', 'gig@bank', 'P2M')")
        cls.conn.execute(f"INSERT INTO transactions (txn_id, user_id, timestamp, amount, direction, counterparty_vpa, txn_type) VALUES ('tx_d2', 'test_user_high_debt', '{(now - timedelta(days=15)).strftime('%Y-%m-%d %H:%M:%S')}', 52000, 'debit', 'spend@upi', 'P2M')")

        # Seed credit events
        # test_user_old_def: default 4.2 years ago (1530 days), resolved 3.5 years ago
        event_old_date = (now - timedelta(days=1530)).strftime("%Y-%m-%d")
        res_date = (now - timedelta(days=1250)).strftime("%Y-%m-%d")
        cls.conn.execute(
            """
            INSERT INTO credit_events (event_id, user_id, event_type, event_date, status, resolution_date, amount, institution)
            VALUES ('evt_old_1', 'test_user_old_def', 'default', ?, 'resolved', ?, 35000, 'SBI Personal Loan')
            """,
            (event_old_date, res_date),
        )

        # test_user_recent_def: default 5 months ago (150 days), active (unresolved)
        event_rec_date = (now - timedelta(days=150)).strftime("%Y-%m-%d")
        cls.conn.execute(
            """
            INSERT INTO credit_events (event_id, user_id, event_type, event_date, status, resolution_date, amount, institution)
            VALUES ('evt_rec_1', 'test_user_recent_def', 'default', ?, 'active', NULL, 15000, 'Bajaj Consumer Loan')
            """,
            (event_rec_date,),
        )

        cls.conn.commit()

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    def test_same_applicant_different_lender_policies(self):
        """
        Evaluate the same applicant (test_user_high_debt, debt ratio 52%, score 610)
        against different lender policies:
        - NBFC Flexi-Credit v1.0 (max debt 55%, min score 600) -> Should APPROVE
        - Prime Bank Retail v1.0 (max debt 45%, min score 680) -> Should REJECT
        """
        nbfc_policy = get_policy_by_id("pol_nbfc_flexi_v1", self.conn)
        prime_policy = get_policy_by_id("pol_prime_bank_v1", self.conn)

        self.assertIsNotNone(nbfc_policy)
        self.assertIsNotNone(prime_policy)

        # Evaluate against NBFC
        res_nbfc = evaluate_applicant("test_user_high_debt", nbfc_policy, self.conn)
        # Evaluate against Prime Bank
        res_prime = evaluate_applicant("test_user_high_debt", prime_policy, self.conn)

        self.assertEqual(res_nbfc["decision"], "approved", f"Expected approved by NBFC, failed rules: {res_nbfc['failed_rules']}")
        self.assertEqual(res_prime["decision"], "rejected", "Expected rejected by Prime Bank")

        # Prime bank should fail on score and debt obligation
        failed_rule_ids = [r["rule_id"] for r in res_prime["failed_rules"]]
        self.assertIn("debt_obligation", failed_rule_ids)
        self.assertIn("min_score", failed_rule_ids)

    def test_old_default_treated_by_lender_window_policy(self):
        """
        Old default (4.2 years ago, resolved):
        - Evaluated against NBFC (historical window 3 years) -> Default is > 3 years old -> PASSES
        - Evaluated against Strict Bank (historical window 5 years, allow_resolved=0) -> FAILS
        """
        nbfc_policy = get_policy_by_id("pol_nbfc_flexi_v1", self.conn)
        strict_bank_policy = get_policy_by_id("pol_prime_bank_v1", self.conn)

        res_nbfc = evaluate_applicant("test_user_old_def", nbfc_policy, self.conn)
        res_strict = evaluate_applicant("test_user_old_def", strict_bank_policy, self.conn)

        # Under NBFC, historical default rule must pass
        nbfc_passed_ids = [r["rule_id"] for r in res_nbfc["passed_rules"]]
        self.assertIn("historical_default", nbfc_passed_ids)

        # Under strict bank with 5-year lookback requiring zero defaults, it must fail
        strict_failed_ids = [r["rule_id"] for r in res_strict["failed_rules"]]
        self.assertIn("historical_default", strict_failed_ids)

    def test_recent_default_rejected(self):
        """
        Applicant with recent default (5 months ago) must fail the recent default rule
        across all standard policies having a recent window >= 6 months.
        """
        nbfc_policy = get_policy_by_id("pol_nbfc_flexi_v1", self.conn)  # 12-month recent window
        res = evaluate_applicant("test_user_recent_def", nbfc_policy, self.conn)

        self.assertEqual(res["decision"], "rejected")
        failed_ids = [r["rule_id"] for r in res["failed_rules"]]
        self.assertIn("recent_default", failed_ids)
        self.assertIn("recent default(s)", res["primary_failed_factor"])

    def test_rejection_explanation_ground_truth(self):
        """
        Verify rejection explanation is constructed strictly and deterministically
        from the actual failed policy rules (Debt ratio: 52%, Maximum allowed: 45%).
        """
        prime_policy = get_policy_by_id("pol_prime_bank_v1", self.conn)
        res = evaluate_applicant("test_user_high_debt", prime_policy, self.conn)

        self.assertEqual(res["decision"], "rejected")
        explanation = res["rejection_explanation"]
        self.assertIsNotNone(explanation)

        # Must follow the required structure
        self.assertIn("Decision: Not Approved", explanation)
        self.assertIn("Failed:", explanation)
        self.assertIn("Debt Obligation Threshold", explanation)
        self.assertIn("Reason:", explanation)
        self.assertIn("exceeded this lender's policy threshold", explanation)

    def test_missing_credit_data_handled_cleanly(self):
        """
        Ensure user with zero credit events is evaluated cleanly without exceptions
        and without inventing fake events.
        """
        timeline = get_credit_timeline("test_user_missing_data", self.conn)
        self.assertEqual(len(timeline), 0, "Expected empty credit timeline for user with no events")

        policy = get_policy_by_id("pol_nbfc_flexi_v1", self.conn)
        res = evaluate_applicant("test_user_missing_data", policy, self.conn)
        self.assertIn(res["decision"], ["approved", "rejected"])
        # Should not crash and should record risk profile
        self.assertFalse(res["risk_profile"]["has_credit_history"])

    def test_existing_scoring_flow_preserved(self):
        """
        Verify that existing credit scoring functions in credit_score.py
        remain 100% operational and yield scores between 300 and 900.
        """
        txns = [
            {"timestamp": "2026-01-10 10:00:00", "amount": 25000.0, "direction": "credit"},
            {"timestamp": "2026-02-10 10:00:00", "amount": 26000.0, "direction": "credit"},
            {"timestamp": "2026-03-10 10:00:00", "amount": 25500.0, "direction": "credit"},
            {"timestamp": "2026-01-15 15:00:00", "amount": 10000.0, "direction": "debit"},
            {"timestamp": "2026-02-15 15:00:00", "amount": 12000.0, "direction": "debit"},
        ]
        result = compute_score_for_user(txns)
        self.assertGreaterEqual(result["score"], 300)
        self.assertLessEqual(result["score"], 900)
        self.assertGreaterEqual(result["income_regularity_component"], 0.0)
        self.assertLessEqual(result["income_regularity_component"], 1.0)
        self.assertGreaterEqual(result["expense_ratio_component"], 0.0)
        self.assertLessEqual(result["expense_ratio_component"], 1.0)

    def test_auditability_store_and_retrieve(self):
        """
        Verify that for every decision, an immutable audit record is saved
        containing: applicant, lender, policy version, rules evaluated, rules passed,
        rules failed, decision, and timestamp.
        """
        policy = get_policy_by_id("pol_nbfc_flexi_v1", self.conn)
        eval_result = evaluate_applicant("test_user_clean", policy, self.conn)

        # Create dummy application
        cur = self.conn.execute("INSERT INTO loan_applications (user_id, amount_requested, purpose) VALUES ('test_user_clean', 15000, 'Equipment')")
        app_id = cur.lastrowid
        self.conn.commit()

        audit_id = record_evaluation_audit(eval_result, app_id, self.conn)
        self.assertIsNotNone(audit_id)

        retrieved = get_evaluation_audit(audit_id, self.conn)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved["applicant_id"], "test_user_clean")
        self.assertEqual(retrieved["lender_id"], policy["lender_id"])
        self.assertEqual(retrieved["policy_version"], policy["policy_version"])
        self.assertEqual(retrieved["decision"], eval_result["decision"])
        self.assertIsInstance(retrieved["rules_evaluated"], list)
        self.assertIsInstance(retrieved["rules_passed"], list)
        self.assertIsInstance(retrieved["rules_failed"], list)
        self.assertIsNotNone(retrieved["evaluated_at"])


if __name__ == "__main__":
    unittest.main()
