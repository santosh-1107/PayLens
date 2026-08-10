"""
pages/institution_report.py
===========================
Streamlit page for authorized financial institutions to analyze credit scores,
income authenticity flags (circular transactions), and shared risky counterparties.
"""

import os
import sys
import sqlite3
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

# Ensure parent directory (src/) is in sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dashboard import (
    get_connection,
    open_section_card,
    close_section_card,
    progress_bar_html,
    inject_custom_css,
    load_users,
    load_credit_score,
    render_credit_score
)


def calculate_income_stats(conn, user_id: str) -> dict:
    df = pd.read_sql_query(
        """
        SELECT timestamp, amount
        FROM transactions
        WHERE user_id = ? AND direction = 'credit'
        """,
        conn,
        params=(user_id,)
    )
    if df.empty:
        return {"avg": 0.0, "min": 0.0, "max": 0.0, "monthly_sums": pd.Series(dtype=float)}
    
    # Convert timestamp to YYYY-MM
    df["month"] = df["timestamp"].str.slice(0, 7)
    monthly_sums = df.groupby("month")["amount"].sum()
    
    return {
        "avg": monthly_sums.mean(),
        "min": monthly_sums.min(),
        "max": monthly_sums.max(),
        "monthly_sums": monthly_sums
    }


def load_income_authenticity_flags(conn, user_id: str) -> pd.DataFrame:
    return pd.read_sql_query(
        """
        SELECT counterparty_vpa, counterparty_name, debit_timestamp, debit_amount,
               credit_timestamp, credit_amount, detected_at
        FROM income_authenticity_flags
        WHERE user_id = ?
        """,
        conn,
        params=(user_id,)
    )


def load_user_shared_risk_flags(conn, user_id: str) -> pd.DataFrame:
    return pd.read_sql_query(
        """
        SELECT DISTINCT t.counterparty_vpa, t.counterparty_name, src.unique_user_count, src.total_flag_count
        FROM transactions t
        JOIN shared_risk_counterparties src ON t.counterparty_vpa = src.counterparty_vpa
        WHERE t.user_id = ?
        """,
        conn,
        params=(user_id,)
    )


def load_spending_trend(conn, user_id: str) -> dict:
    row = conn.execute(
        """
        SELECT income_trend_pct, spending_trend_pct, is_flagged
        FROM spending_trends
        WHERE user_id = ?
        """,
        (user_id,)
    ).fetchone()
    if row is None:
        return None
    return {
        "income_trend_pct": row[0],
        "spending_trend_pct": row[1],
        "is_flagged": bool(row[2])
    }


def main():
    st.set_page_config(
        page_title="PayLens - Institution Report",
        page_icon="🔒",
        layout="wide",
    )
    inject_custom_css()

    # 1. Confidentiality Banner
    st.markdown(
        """
        <div style="background-color: #ffebe9; border: 1px solid #ffc1c0; padding: 18px; border-radius: 12px; margin-bottom: 24px;">
            <h4 style="color: #cf222e; margin: 0 0 8px 0; font-weight: 700; letter-spacing: -0.01em;">🔒 CONFIDENTIAL — INSTITUTIONAL USE ONLY</h4>
            <p style="color: #24292f; margin: 0; font-size: 0.95rem; line-height: 1.5;">
                This report is intended for authorized lending institutions and financial partners. It must <strong>NOT</strong> be shared with or made visible to the individual it describes. Findings are flagged for human review and do not constitute automated fraud/credit decisions.
            </p>
        </div>
        """,
        unsafe_allow_html=True
    )

    st.markdown(
        """
        <div class="page-header">
            <h1 class="brand-title">Institutional Risk Report</h1>
            <div class="brand-accent-bar" style="background:#cf222e;"></div>
            <p class="brand-subtitle">Income authenticity verification and shared-risk profiling</p>
        </div>
        """,
        unsafe_allow_html=True
    )

    # 2. Access Gate
    load_dotenv(os.path.join(os.path.dirname(__file__), "../../.env"))
    access_code = os.getenv("INSTITUTION_ACCESS_CODE", "admin123")

    open_section_card("Authentication Gate", "Verification required to view confidential reports")
    entered_code = st.text_input("Enter Institutional Access Code", type="password", key="inst_code_input")
    close_section_card()

    if entered_code != access_code:
        if entered_code:
            st.error("Invalid access code. Please try again.")
        st.info("Please enter the institutional access code above to proceed.")
        st.stop()

    # 3. Report Dashboard Content
    conn = get_connection()
    users = load_users(conn)
    if not users:
        st.warning("No users found in database.")
        st.stop()

    open_section_card("Profile Selection", "Select user to audit")
    user_labels = {f"{u['name']} ({u['user_id']})": u["user_id"] for u in users}
    selected_label = st.selectbox("Select User Profile", list(user_labels.keys()))
    user_id = user_labels[selected_label]
    close_section_card()

    col_feed, col_score = st.columns([2, 1])

    with col_score:
        credit = load_credit_score(conn, user_id)
        render_credit_score(credit)

    with col_feed:
        # Income and gig volatility
        stats = calculate_income_stats(conn, user_id)
        open_section_card("Inflow & Gig-Work Volatility", "Monthly credit analysis and income range")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Average Monthly Inflow", f"₹{stats['avg']:,.2f}")
        with col2:
            st.metric("Minimum Monthly Inflow", f"₹{stats['min']:,.2f}")
        with col3:
            st.metric("Maximum Monthly Inflow", f"₹{stats['max']:,.2f}")
            
        st.markdown(f"**Monthly Volatility Range**: ₹{stats['min']:,.2f} to ₹{stats['max']:,.2f}")
        
        if not stats["monthly_sums"].empty:
            st.markdown("<p style='font-weight: 500; margin-top: 15px;'>Monthly Inflow Breakdown</p>", unsafe_allow_html=True)
            m_df = pd.DataFrame({
                "Month": stats["monthly_sums"].index,
                "Inflow (₹)": stats["monthly_sums"].values
            })
            st.dataframe(
                m_df.style.format({"Inflow (₹)": "₹{:,.2f}"}),
                hide_index=True,
                use_container_width=True
            )
        close_section_card()

        # Income Authenticity
        open_section_card("Circular Transaction Analysis", "Flagged for human review (not confirmed)")
        auth_flags_df = load_income_authenticity_flags(conn, user_id)
        if auth_flags_df.empty:
            st.success("✅ No self-funding loops or circular transactions detected for this profile.")
        else:
            st.warning("⚠️ Potential circular transactions detected (transactions looping between same counterparties).")
            for _, row in auth_flags_df.iterrows():
                st.info(
                    f"**Counterparty VPA**: `{row['counterparty_vpa']}` ({row['counterparty_name']})\n\n"
                    f"- **Debit transaction**: ₹{row['debit_amount']:.2f} on {row['debit_timestamp']}\n"
                    f"- **Credit transaction**: ₹{row['credit_amount']:.2f} on {row['credit_timestamp']}\n"
                    f"- **System Flagged on**: {row['detected_at']}"
                )
        close_section_card()

        # Spending vs Income Trend
        open_section_card("Spending vs Income Trend", "Analysis of monthly income vs spending growth trends")
        trend_data = load_spending_trend(conn, user_id)
        if trend_data is None:
            st.info("No spending trend analysis data available.")
        else:
            inc_trend = trend_data["income_trend_pct"]
            spd_trend = trend_data["spending_trend_pct"]
            is_flagged = trend_data["is_flagged"]

            col1, col2 = st.columns(2)
            with col1:
                st.metric("Income Trend (MoM)", f"{'+' if inc_trend >= 0 else ''}{inc_trend:.1f}%")
            with col2:
                st.metric("Spending Trend (MoM)", f"{'+' if spd_trend >= 0 else ''}{spd_trend:.1f}%")

            if is_flagged:
                st.warning(
                    "⚠️ **Unsustainable Spending Trend Flagged**\n\n"
                    "Spending growth rate is outpacing income growth rate. "
                    "This may indicate financial stress or unsustainable spending — recommend review."
                )
            else:
                st.success("✅ Spending growth trend is sustainable relative to income growth.")
        close_section_card()

        # Shared Risky counterparties
        open_section_card("Shared Risky Counterparties", "Cross-user systemic exposure check")
        shared_risk_df = load_user_shared_risk_flags(conn, user_id)
        if shared_risk_df.empty:
            st.success("✅ No transactions with known shared risky counterparties detected.")
        else:
            st.error("🚨 Transactions found with counterparties flagged as risky across 3+ other users.")
            st.dataframe(
                shared_risk_df.rename(columns={
                    "counterparty_vpa": "Risky VPA",
                    "counterparty_name": "Name",
                    "unique_user_count": "Flagged Users Count",
                    "total_flag_count": "Total Fraud Flags"
                }),
                hide_index=True,
                use_container_width=True
            )
        close_section_card()


if __name__ == "__main__":
    main()
