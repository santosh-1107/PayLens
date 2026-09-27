"""
policy_engine.py
================
Lender Policy Engine for PayLens.

Core architectural separation:
    PayLens Risk Profile
            ↓
       Lender Policy
            ↓
         Decision

The PayLens score does NOT directly determine loan approval.
Each lender defines independent, versioned underwriting rules:
  - Minimum credit score
  - Income stability threshold
  - Debt obligation threshold (debt/expense ratio)
  - Recent default rule
  - Historical default window

Auditability: Every decision is immutably logged with applicant, lender,
policy version, evaluated rules, passed rules, failed rules, decision,
and timestamp.
"""

import json
import sqlite3
import uuid
from datetime import datetime, timedelta
from typing import Any, Optional


def ensure_policy_tables(conn: sqlite3.Connection):
    """Ensure credit_events, lender_policies, and policy_evaluations tables exist."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS credit_events (
            event_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            event_date TEXT NOT NULL,
            status TEXT NOT NULL,
            resolution_date TEXT,
            amount REAL,
            institution TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS lender_policies (
            policy_id TEXT PRIMARY KEY,
            lender_id TEXT NOT NULL,
            lender_name TEXT NOT NULL,
            policy_version TEXT NOT NULL,
            min_score REAL NOT NULL,
            min_income_stability REAL NOT NULL,
            max_debt_ratio REAL NOT NULL,
            max_recent_defaults INTEGER NOT NULL DEFAULT 0,
            recent_default_window_months INTEGER NOT NULL DEFAULT 12,
            historical_default_window_years INTEGER NOT NULL DEFAULT 5,
            allow_resolved_historical_defaults INTEGER NOT NULL DEFAULT 1,
            description TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS policy_evaluations (
            evaluation_id TEXT PRIMARY KEY,
            application_id INTEGER,
            applicant_id TEXT NOT NULL,
            lender_id TEXT NOT NULL,
            lender_name TEXT NOT NULL,
            policy_version TEXT NOT NULL,
            decision TEXT NOT NULL,
            rules_evaluated TEXT NOT NULL,
            rules_passed TEXT NOT NULL,
            rules_failed TEXT NOT NULL,
            primary_failed_factor TEXT,
            rejection_explanation TEXT,
            evaluated_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (applicant_id) REFERENCES users(user_id),
            FOREIGN KEY (application_id) REFERENCES loan_applications(application_id)
        )
        """
    )
    # Check if loan_applications needs extra columns
    cursor = conn.execute("PRAGMA table_info(loan_applications)")
    cols = [r[1] for r in cursor.fetchall()]
    for col in ["lender_id", "policy_version", "evaluation_id"]:
        if col not in cols:
            try:
                conn.execute(f"ALTER TABLE loan_applications ADD COLUMN {col} TEXT")
            except Exception:
                pass
    conn.commit()


# ============================================================================
# 1. RISK PROFILE EXTRACTION
# ============================================================================

def get_applicant_risk_profile(user_id: str, conn: sqlite3.Connection) -> dict:
    """
    Extracts the PayLens Risk Profile for an applicant without deciding approval.
    Pulls credit score components and calculates cash-flow debt ratio from transactions.
    """
    ensure_policy_tables(conn)

    # 1. Credit score
    credit_row = conn.execute(
        """
        SELECT score, income_regularity_component, expense_ratio_component, volatility_component, computed_at
        FROM credit_scores
        WHERE user_id = ?
        ORDER BY computed_at DESC
        LIMIT 1
        """,
        (user_id,),
    ).fetchone()

    score = float(credit_row[0]) if credit_row else 300.0
    income_stability = float(credit_row[1]) if credit_row else 0.0
    volatility = float(credit_row[3]) if credit_row else 0.0

    # 2. Real debt obligation ratio from transactions (Total Debits / Total Credits)
    txn_row = conn.execute(
        """
        SELECT 
            COALESCE(SUM(CASE WHEN direction = 'credit' THEN amount ELSE 0 END), 0.0) as total_credits,
            COALESCE(SUM(CASE WHEN direction = 'debit' THEN amount ELSE 0 END), 0.0) as total_debits,
            COUNT(*) as txn_count
        FROM transactions
        WHERE user_id = ?
        """,
        (user_id,),
    ).fetchone()

    total_credits = float(txn_row[0]) if txn_row else 0.0
    total_debits = float(txn_row[1]) if txn_row else 0.0

    if total_credits > 0:
        debt_ratio = round(total_debits / total_credits, 4)
    else:
        debt_ratio = 1.0  # conservative fallback if zero recorded credits

    # 3. Credit events count
    credit_events = get_credit_timeline(user_id, conn)

    return {
        "user_id": user_id,
        "score": score,
        "income_stability": income_stability,
        "debt_ratio": debt_ratio,
        "total_credits": total_credits,
        "total_debits": total_debits,
        "volatility": volatility,
        "credit_events": credit_events,
        "has_credit_history": len(credit_events) > 0,
    }


# ============================================================================
# 2. HISTORICAL CREDIT CONTEXT & TIMELINE
# ============================================================================

def calculate_event_age(event_date_str: str, ref_date: Optional[datetime] = None) -> tuple[float, int, str]:
    """
    Computes (age_years: float, age_months: int, human_label: str).
    Does NOT invent missing dates.
    """
    if not event_date_str:
        return 0.0, 0, "Unknown age"

    try:
        dt = datetime.strptime(event_date_str[:10], "%Y-%m-%d")
    except ValueError:
        return 0.0, 0, "Invalid date"

    ref = ref_date or datetime.now()
    diff_days = (ref - dt).days
    if diff_days < 0:
        diff_days = 0

    age_years = round(diff_days / 365.25, 2)
    age_months = int(diff_days / 30.4375)

    if age_years >= 1.0:
        human_label = f"{age_years:.1f} yr{'s' if age_years != 1.0 else ''} ago"
    elif age_months >= 1:
        human_label = f"{age_months} mo{'s' if age_months != 1 else ''} ago"
    else:
        human_label = f"{diff_days} day{'s' if diff_days != 1 else ''} ago"

    return age_years, age_months, human_label


def get_credit_timeline(user_id: str, conn: sqlite3.Connection, ref_date: Optional[datetime] = None) -> list[dict]:
    """
    Returns applicant's chronological credit timeline.
    Tracks for each event:
      - event_type (default, missed_payment, settlement, loan_closure, on_time_payment)
      - event_date
      - status (active, resolved, written_off, closed)
      - resolution_date (if available, else None)
      - age (formatted age string)
      - current_status
    Do NOT invent missing credit data.
    """
    ensure_policy_tables(conn)

    rows = conn.execute(
        """
        SELECT event_id, event_type, event_date, status, resolution_date, amount, institution
        FROM credit_events
        WHERE user_id = ?
        ORDER BY event_date DESC
        """,
        (user_id,),
    ).fetchall()

    timeline = []
    for r in rows:
        event_id, event_type, event_date, status, resolution_date, amount, institution = r
        age_years, age_months, age_str = calculate_event_age(event_date, ref_date=ref_date)
        
        timeline.append({
            "event_id": event_id,
            "event_type": event_type,
            "event_date": event_date,
            "status": status,
            "resolution_date": resolution_date if resolution_date else None,
            "amount": float(amount) if amount is not None else None,
            "institution": institution or "Unspecified Institution",
            "age_years": age_years,
            "age_months": age_months,
            "age": age_str,
            "current_status": status.title(),
        })

    return timeline


# ============================================================================
# 3. LENDER POLICIES CONFIGURATION & VERSIONING
# ============================================================================

DEFAULT_POLICIES = [
    {
        "policy_id": "pol_prime_bank_v1",
        "lender_id": "lender_prime_bank",
        "lender_name": "Prime Bank Retail",
        "policy_version": "v1.0",
        "min_score": 680.0,
        "min_income_stability": 0.55,
        "max_debt_ratio": 0.45,
        "max_recent_defaults": 0,
        "recent_default_window_months": 24,
        "historical_default_window_years": 5,
        "allow_resolved_historical_defaults": 0,  # strict: zero defaults in 5 years even if resolved
        "description": "Tier-1 prime underwriting policy with strict debt and historical default windows.",
    },
    {
        "policy_id": "pol_nbfc_flexi_v1",
        "lender_id": "lender_nbfc_flexi",
        "lender_name": "NBFC Flexi-Credit",
        "policy_version": "v1.0",
        "min_score": 600.0,
        "min_income_stability": 0.40,
        "max_debt_ratio": 0.55,
        "max_recent_defaults": 0,
        "recent_default_window_months": 12,
        "historical_default_window_years": 3,
        "allow_resolved_historical_defaults": 1,  # lenient: old resolved defaults past 3 years are accepted
        "description": "Flexible NBFC policy designed for gig/informal workers. Treats resolved historical defaults fairly.",
    },
    {
        "policy_id": "pol_fintech_grow_v2",
        "lender_id": "lender_fintech_grow",
        "lender_name": "Fintech Micro-Grow",
        "policy_version": "v2.0",
        "min_score": 530.0,
        "min_income_stability": 0.30,
        "max_debt_ratio": 0.65,
        "max_recent_defaults": 0,
        "recent_default_window_months": 6,
        "historical_default_window_years": 2,
        "allow_resolved_historical_defaults": 1,
        "description": "High-inclusion micro-credit policy focusing on recent 6-month cash flow.",
    },
]


def seed_default_policies(conn: sqlite3.Connection):
    """Seed initial default lender policies if none exist."""
    ensure_policy_tables(conn)
    count = conn.execute("SELECT COUNT(*) FROM lender_policies").fetchone()[0]
    if count == 0:
        for p in DEFAULT_POLICIES:
            conn.execute(
                """
                INSERT INTO lender_policies (
                    policy_id, lender_id, lender_name, policy_version,
                    min_score, min_income_stability, max_debt_ratio,
                    max_recent_defaults, recent_default_window_months,
                    historical_default_window_years, allow_resolved_historical_defaults,
                    description
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    p["policy_id"], p["lender_id"], p["lender_name"], p["policy_version"],
                    p["min_score"], p["min_income_stability"], p["max_debt_ratio"],
                    p["max_recent_defaults"], p["recent_default_window_months"],
                    p["historical_default_window_years"], p["allow_resolved_historical_defaults"],
                    p["description"],
                ),
            )
        conn.commit()


def get_all_policies(conn: sqlite3.Connection) -> list[dict]:
    """Retrieve all configured lender policies."""
    ensure_policy_tables(conn)
    seed_default_policies(conn)
    rows = conn.execute(
        """
        SELECT 
            policy_id, lender_id, lender_name, policy_version,
            min_score, min_income_stability, max_debt_ratio,
            max_recent_defaults, recent_default_window_months,
            historical_default_window_years, allow_resolved_historical_defaults,
            description, created_at
        FROM lender_policies
        ORDER BY lender_name, policy_version DESC
        """
    ).fetchall()

    policies = []
    for r in rows:
        policies.append({
            "policy_id": r[0],
            "lender_id": r[1],
            "lender_name": r[2],
            "policy_version": r[3],
            "min_score": float(r[4]),
            "min_income_stability": float(r[5]),
            "max_debt_ratio": float(r[6]),
            "max_recent_defaults": int(r[7]),
            "recent_default_window_months": int(r[8]),
            "historical_default_window_years": int(r[9]),
            "allow_resolved_historical_defaults": bool(r[10]),
            "description": r[11] or "",
            "created_at": r[12],
        })
    return policies


def get_policy_by_id(policy_id: str, conn: sqlite3.Connection) -> Optional[dict]:
    policies = get_all_policies(conn)
    for p in policies:
        if p["policy_id"] == policy_id:
            return p
    return None


def save_policy(policy_data: dict, conn: sqlite3.Connection) -> str:
    """Creates or updates a versioned lender policy."""
    ensure_policy_tables(conn)
    policy_id = policy_data.get("policy_id") or f"pol_{uuid.uuid4().hex[:8]}"

    conn.execute(
        """
        INSERT INTO lender_policies (
            policy_id, lender_id, lender_name, policy_version,
            min_score, min_income_stability, max_debt_ratio,
            max_recent_defaults, recent_default_window_months,
            historical_default_window_years, allow_resolved_historical_defaults,
            description
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(policy_id) DO UPDATE SET
            lender_name = excluded.lender_name,
            policy_version = excluded.policy_version,
            min_score = excluded.min_score,
            min_income_stability = excluded.min_income_stability,
            max_debt_ratio = excluded.max_debt_ratio,
            max_recent_defaults = excluded.max_recent_defaults,
            recent_default_window_months = excluded.recent_default_window_months,
            historical_default_window_years = excluded.historical_default_window_years,
            allow_resolved_historical_defaults = excluded.allow_resolved_historical_defaults,
            description = excluded.description
        """,
        (
            policy_id,
            policy_data["lender_id"],
            policy_data["lender_name"],
            policy_data["policy_version"],
            float(policy_data["min_score"]),
            float(policy_data["min_income_stability"]),
            float(policy_data["max_debt_ratio"]),
            int(policy_data.get("max_recent_defaults", 0)),
            int(policy_data.get("recent_default_window_months", 12)),
            int(policy_data.get("historical_default_window_years", 5)),
            1 if policy_data.get("allow_resolved_historical_defaults", True) else 0,
            policy_data.get("description", ""),
        ),
    )
    conn.commit()
    return policy_id


# ============================================================================
# 4. POLICY EVALUATION & REJECTION EXPLANATION
# ============================================================================

def evaluate_applicant(user_id: str, policy: dict, conn: sqlite3.Connection, ref_date: Optional[datetime] = None) -> dict:
    """
    Evaluates an applicant against a specific lender policy.
    
    Returns structured results:
    {
        "decision": "approved" | "rejected",
        "passed_rules": [...],
        "failed_rules": [...],
        "primary_failed_factor": str | None,
        "rejection_explanation": str | None,
        "policy_version": str,
        "lender_id": str,
        "lender_name": str,
        "risk_profile": dict
    }
    """
    profile = get_applicant_risk_profile(user_id, conn)
    passed_rules = []
    failed_rules = []

    # ----------------------------------------------------
    # Rule 1: Minimum PayLens Credit Score
    # ----------------------------------------------------
    actual_score = profile["score"]
    min_score = policy["min_score"]
    rule_score = {
        "rule_id": "min_score",
        "label": "Minimum Credit Score",
        "category": "Credit Score",
        "actual_display": f"{actual_score:.0f}",
        "threshold_display": f"Min {min_score:.0f}",
        "actual_value": actual_score,
        "threshold_value": min_score,
    }
    if actual_score >= min_score:
        rule_score["status"] = "pass"
        passed_rules.append(rule_score)
    else:
        rule_score["status"] = "fail"
        rule_score["reason"] = f"PayLens credit score ({actual_score:.0f}) did not meet this lender's minimum requirement of {min_score:.0f}."
        failed_rules.append(rule_score)

    # ----------------------------------------------------
    # Rule 2: Income Stability Threshold
    # ----------------------------------------------------
    actual_stability = profile["income_stability"]
    min_stability = policy["min_income_stability"]
    rule_stability = {
        "rule_id": "income_stability",
        "label": "Income Stability",
        "category": "Income Regularity",
        "actual_display": f"{actual_stability * 100:.1f}%",
        "threshold_display": f"Min {min_stability * 100:.0f}%",
        "actual_value": actual_stability,
        "threshold_value": min_stability,
    }
    if actual_stability >= min_stability:
        rule_stability["status"] = "pass"
        passed_rules.append(rule_stability)
    else:
        rule_stability["status"] = "fail"
        rule_stability["reason"] = f"Income stability ({actual_stability * 100:.1f}%) is below this lender's required regularity threshold of {min_stability * 100:.0f}%."
        failed_rules.append(rule_stability)

    # ----------------------------------------------------
    # Rule 3: Debt Obligation Threshold (Debt Ratio)
    # ----------------------------------------------------
    actual_debt_ratio = profile["debt_ratio"]
    max_debt_ratio = policy["max_debt_ratio"]
    rule_debt = {
        "rule_id": "debt_obligation",
        "label": "Debt Obligation Threshold",
        "category": "Debt Ratio",
        "actual_display": f"{actual_debt_ratio * 100:.1f}%",
        "threshold_display": f"Max {max_debt_ratio * 100:.0f}%",
        "actual_value": actual_debt_ratio,
        "threshold_value": max_debt_ratio,
    }
    if actual_debt_ratio <= max_debt_ratio:
        rule_debt["status"] = "pass"
        passed_rules.append(rule_debt)
    else:
        rule_debt["status"] = "fail"
        rule_debt["reason"] = f"Existing debt obligations ({actual_debt_ratio * 100:.1f}%) exceeded this lender's policy threshold of {max_debt_ratio * 100:.0f}%."
        failed_rules.append(rule_debt)

    # ----------------------------------------------------
    # Rule 4: Recent Default Rule
    # ----------------------------------------------------
    recent_months = policy["recent_default_window_months"]
    max_recent_defaults = policy["max_recent_defaults"]

    # Filter credit events for defaults within recent window
    recent_defaults = [
        e for e in profile["credit_events"]
        if e["event_type"].lower() == "default" and e["age_months"] <= recent_months
    ]
    recent_def_count = len(recent_defaults)

    rule_recent_default = {
        "rule_id": "recent_default",
        "label": "Recent Default Rule",
        "category": "Repayment History",
        "actual_display": f"{recent_def_count} default(s) in last {recent_months}mo",
        "threshold_display": f"Max {max_recent_defaults} allowed",
        "actual_value": recent_def_count,
        "threshold_value": max_recent_defaults,
    }
    if recent_def_count <= max_recent_defaults:
        rule_recent_default["status"] = "pass"
        passed_rules.append(rule_recent_default)
    else:
        rule_recent_default["status"] = "fail"
        rule_recent_default["reason"] = f"Found {recent_def_count} recent default(s) within the last {recent_months} months (maximum allowed: {max_recent_defaults})."
        failed_rules.append(rule_recent_default)

    # ----------------------------------------------------
    # Rule 5: Historical Default Window
    # ----------------------------------------------------
    hist_years = policy["historical_default_window_years"]
    allow_resolved = policy.get("allow_resolved_historical_defaults", True)

    # Historical defaults: older than recent window, but within historical window
    hist_defaults = [
        e for e in profile["credit_events"]
        if e["event_type"].lower() == "default"
        and e["age_months"] > recent_months
        and e["age_years"] <= hist_years
    ]

    rule_hist_default = {
        "rule_id": "historical_default",
        "label": "Historical Default Window",
        "category": "Repayment History",
        "actual_display": f"{len(hist_defaults)} default(s) within {hist_years}yr window",
        "threshold_display": f"{hist_years}-yr window ({'Resolved Allowed' if allow_resolved else 'Zero Allowed'})",
        "actual_value": len(hist_defaults),
        "threshold_value": hist_years,
    }

    if not hist_defaults:
        rule_hist_default["status"] = "pass"
        passed_rules.append(rule_hist_default)
    else:
        # Check if all historical defaults are resolved
        unresolved = [e for e in hist_defaults if e["status"].lower() not in ("resolved", "closed")]
        if allow_resolved and not unresolved:
            # Policy explicitly allows resolved historical defaults!
            rule_hist_default["status"] = "pass"
            rule_hist_default["actual_display"] += " (All Resolved)"
            passed_rules.append(rule_hist_default)
        elif not allow_resolved:
            rule_hist_default["status"] = "fail"
            rule_hist_default["reason"] = f"Found {len(hist_defaults)} historical default(s) within the {hist_years}-year lookback window (lender requires zero defaults within {hist_years} years)."
            failed_rules.append(rule_hist_default)
        else:
            rule_hist_default["status"] = "fail"
            rule_hist_default["reason"] = f"Found {len(unresolved)} unresolved historical default(s) within the {hist_years}-year lookback window."
            failed_rules.append(rule_hist_default)

    # ----------------------------------------------------
    # Final Decision & Deterministic Rejection Explanation
    # ----------------------------------------------------
    decision = "approved" if len(failed_rules) == 0 else "rejected"
    
    # In standard credit underwriting, hard knockout factors (recent defaults, historical defaults)
    # take precedence as the primary rejection rationale, followed by debt ratio, income stability, and score.
    if failed_rules:
        severity_rank = {
            "recent_default": 1,
            "historical_default": 2,
            "debt_obligation": 3,
            "income_stability": 4,
            "min_score": 5,
        }
        sorted_failed = sorted(failed_rules, key=lambda f: severity_rank.get(f.get("rule_id"), 99))
        primary_failed_factor = sorted_failed[0]["reason"]
    else:
        primary_failed_factor = None

    rejection_explanation = generate_rejection_explanation(failed_rules, policy, primary_reason=primary_failed_factor) if decision == "rejected" else None

    return {
        "decision": decision,
        "passed_rules": passed_rules,
        "failed_rules": failed_rules,
        "primary_failed_factor": primary_failed_factor,
        "rejection_explanation": rejection_explanation,
        "policy_version": policy.get("policy_version", "v1.0"),
        "lender_id": policy.get("lender_id", "unknown_lender"),
        "lender_name": policy.get("lender_name", "Unknown Lender"),
        "risk_profile": profile,
        "evaluated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def generate_rejection_explanation(failed_rules: list[dict], policy: dict, primary_reason: Optional[str] = None) -> str:
    """
    Generates a deterministic plain-text explanation ONLY from actual failed policy rules.
    Matches the required specification:
        Decision: Not Approved
        
        Failed:
        Debt ratio: 52%
        Maximum allowed: 45%
        
        Reason:
        Existing debt obligations exceeded this lender's policy threshold.
    """
    if not failed_rules:
        return "Decision: Approved\n\nAll policy rules satisfied."

    lines = ["Decision: Not Approved\n"]
    lines.append("Failed:")
    for f in failed_rules:
        lines.append(f"{f['label']}: {f['actual_display']}")
        lines.append(f"Maximum/Minimum allowed: {f['threshold_display']}")

    lines.append("\nReason:")
    primary = primary_reason or (failed_rules[0]["reason"] if failed_rules else "Policy requirements not met.")
    lines.append(primary)

    additional = [f["reason"] for f in failed_rules if f["reason"] != primary]
    if additional:
        lines.append("\nAdditional Failed Factors:")
        for r in additional:
            lines.append(f"- {r}")

    return "\n".join(lines)


# ============================================================================
# 5. AUDITABILITY & STORAGE
# ============================================================================

def record_evaluation_audit(evaluation: dict, application_id: Optional[int], conn: sqlite3.Connection) -> str:
    """
    Stores an immutable audit record for every decision.
    Ensures full explainability of why a decision occurred later.
    """
    ensure_policy_tables(conn)
    evaluation_id = f"eval_{uuid.uuid4().hex[:12]}"
    applicant_id = evaluation["risk_profile"]["user_id"]

    conn.execute(
        """
        INSERT INTO policy_evaluations (
            evaluation_id, application_id, applicant_id,
            lender_id, lender_name, policy_version,
            decision, rules_evaluated, rules_passed, rules_failed,
            primary_failed_factor, rejection_explanation, evaluated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            evaluation_id,
            application_id,
            applicant_id,
            evaluation["lender_id"],
            evaluation["lender_name"],
            evaluation["policy_version"],
            evaluation["decision"],
            json.dumps(evaluation["passed_rules"] + evaluation["failed_rules"]),
            json.dumps(evaluation["passed_rules"]),
            json.dumps(evaluation["failed_rules"]),
            evaluation["primary_failed_factor"],
            evaluation["rejection_explanation"],
            evaluation["evaluated_at"],
        ),
    )

    if application_id is not None:
        conn.execute(
            """
            UPDATE loan_applications
            SET lender_id = ?,
                policy_version = ?,
                evaluation_id = ?,
                decision_notes = COALESCE(?, decision_notes)
            WHERE application_id = ?
            """,
            (
                evaluation["lender_id"],
                evaluation["policy_version"],
                evaluation_id,
                evaluation["rejection_explanation"] if evaluation["decision"] == "rejected" else f"Approved by {evaluation['lender_name']} ({evaluation['policy_version']})",
                application_id,
            ),
        )

    conn.commit()
    return evaluation_id


def get_evaluation_audit(evaluation_id: str, conn: sqlite3.Connection) -> Optional[dict]:
    """Retrieve full audit record for a past decision."""
    ensure_policy_tables(conn)
    row = conn.execute(
        """
        SELECT 
            evaluation_id, application_id, applicant_id,
            lender_id, lender_name, policy_version,
            decision, rules_evaluated, rules_passed, rules_failed,
            primary_failed_factor, rejection_explanation, evaluated_at
        FROM policy_evaluations
        WHERE evaluation_id = ?
        """,
        (evaluation_id,),
    ).fetchone()

    if not row:
        return None

    return {
        "evaluation_id": row[0],
        "application_id": row[1],
        "applicant_id": row[2],
        "lender_id": row[3],
        "lender_name": row[4],
        "policy_version": row[5],
        "decision": row[6],
        "rules_evaluated": json.loads(row[7]),
        "rules_passed": json.loads(row[8]),
        "rules_failed": json.loads(row[9]),
        "primary_failed_factor": row[10],
        "rejection_explanation": row[11],
        "evaluated_at": row[12],
    }


def get_latest_evaluation_for_applicant(user_id: str, conn: sqlite3.Connection) -> Optional[dict]:
    """Retrieve the most recent policy evaluation for an applicant."""
    ensure_policy_tables(conn)
    row = conn.execute(
        """
        SELECT evaluation_id
        FROM policy_evaluations
        WHERE applicant_id = ?
        ORDER BY evaluated_at DESC
        LIMIT 1
        """,
        (user_id,),
    ).fetchone()

    if not row:
        return None
    return get_evaluation_audit(row[0], conn)
