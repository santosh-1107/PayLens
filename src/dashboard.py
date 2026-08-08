"""
dashboard.py
============
Streamlit dashboard for the UPI Transaction Intelligence Platform.

Run from inside src/:
    streamlit run dashboard.py
"""

import sqlite3
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

from chat_layer import explain

DB_PATH = "../data/upi_transactions.db"

REASON_LABELS = {
    "amount_spike": "Unusual amount spike vs. your typical spending",
    "odd_hour": "Transaction at an unusual hour (late night / early morning)",
    "new_payee": "First-time payee — never transacted with them before",
    "velocity_burst": "Multiple rapid transactions in a short window",
}


@st.cache_resource
def get_connection():
    return sqlite3.connect(DB_PATH, check_same_thread=False)


def load_users(conn) -> list[dict]:
    rows = conn.execute(
        "SELECT user_id, name, monthly_income_estimate FROM users ORDER BY name"
    ).fetchall()
    return [
        {"user_id": r[0], "name": r[1], "monthly_income_estimate": r[2]}
        for r in rows
    ]


def load_fraud_flags(conn, user_id: str) -> pd.DataFrame:
    df = pd.read_sql_query(
        """
        SELECT
            ff.flag_id,
            ff.risk_score,
            ff.reasons,
            ff.flagged_at,
            t.timestamp AS txn_timestamp,
            t.amount,
            t.direction,
            t.counterparty_vpa,
            t.counterparty_name,
            t.category
        FROM fraud_flags ff
        JOIN transactions t ON ff.txn_id = t.txn_id
        WHERE ff.user_id = ?
        ORDER BY ff.risk_score DESC, ff.flagged_at DESC
        """,
        conn,
        params=(user_id,),
    )
    if not df.empty:
        df["reasons_plain"] = df["reasons"].apply(format_reasons)
    return df


def load_subscriptions(conn, user_id: str) -> pd.DataFrame:
    return pd.read_sql_query(
        """
        SELECT
            counterparty_name,
            counterparty_vpa,
            avg_amount,
            interval_days,
            last_txn_date,
            next_expected_date,
            occurrence_count,
            confidence_score
        FROM detected_subscriptions
        WHERE user_id = ?
        ORDER BY confidence_score DESC
        """,
        conn,
        params=(user_id,),
    )


def load_credit_score(conn, user_id: str) -> dict | None:
    row = conn.execute(
        """
        SELECT score, income_regularity_component, expense_ratio_component,
               volatility_component, computed_at
        FROM credit_scores
        WHERE user_id = ?
        ORDER BY computed_at DESC
        LIMIT 1
        """,
        (user_id,),
    ).fetchone()
    if not row:
        return None
    return {
        "score": row[0],
        "income_regularity": row[1],
        "expense_ratio": row[2],
        "volatility": row[3],
        "computed_at": row[4],
    }


def format_reasons(reasons: str) -> str:
    if not reasons:
        return "No reasons recorded"
    parts = [REASON_LABELS.get(r.strip(), r.strip()) for r in reasons.split(",")]
    return "; ".join(parts)


def format_reasons_for_speech(reasons_plain: str) -> str:
    if not reasons_plain or reasons_plain == "No reasons recorded":
        return "it looks suspicious"
    return reasons_plain.replace("; ", " and ").rstrip(".").lower()


def build_voice_alert_text(amount: float, counterparty: str, reasons_plain: str) -> str:
    reasons = format_reasons_for_speech(reasons_plain)
    payee = counterparty or "an unknown payee"
    return (
        f"This payment of {amount:.2f} rupees to {payee} looks unusual "
        f"because {reasons}. Are you sure this was you?"
    )


def generate_voice_alert(text: str) -> bytes | None:
    """Generate MP3 bytes via gTTS; save via temp file. Returns None on failure."""
    tmp_path = None
    try:
        from gtts import gTTS

        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            tmp_path = tmp.name
        gTTS(text=text, lang="en").save(tmp_path)
        return Path(tmp_path).read_bytes()
    except Exception:
        return None
    finally:
        if tmp_path:
            Path(tmp_path).unlink(missing_ok=True)


def init_session_state():
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "chat_user_id" not in st.session_state:
        st.session_state.chat_user_id = None
    if "pending_question" not in st.session_state:
        st.session_state.pending_question = None


def reset_chat_if_user_changed(user_id: str):
    if st.session_state.chat_user_id != user_id:
        st.session_state.messages = []
        st.session_state.chat_user_id = user_id


def render_credit_score(credit: dict | None):
    st.subheader("Credit Score")
    if not credit:
        st.info("No credit score computed for this user yet.")
        return

    st.metric("Overall Score", f"{credit['score']:.0f}", help="Range: 300–900")
    st.caption(f"Computed at {credit['computed_at']}")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Income Regularity", f"{credit['income_regularity']:.2f}")
        st.progress(min(max(credit["income_regularity"], 0.0), 1.0))
    with col2:
        st.metric("Expense Ratio", f"{credit['expense_ratio']:.2f}")
        st.progress(min(max(credit["expense_ratio"], 0.0), 1.0))
    with col3:
        st.metric("Volatility", f"{credit['volatility']:.2f}")
        st.progress(min(max(credit["volatility"], 0.0), 1.0))


def render_financial_events(fraud_df: pd.DataFrame, subs_df: pd.DataFrame):
    st.subheader("Financial Events")

    events = []

    for _, row in fraud_df.iterrows():
        payee = row["counterparty_name"] or row["counterparty_vpa"]
        events.append(
            {
                "sort_date": row["flagged_at"] or row["txn_timestamp"],
                "type": "Fraud Flag",
                "summary": (
                    f"Risk {row['risk_score']:.2f} — ₹{row['amount']:.2f} "
                    f"{row['direction']} to {payee} on {row['txn_timestamp']}"
                ),
                "detail": row["reasons_plain"],
                "flag_id": row["flag_id"],
                "risk_score": row["risk_score"],
                "amount": row["amount"],
                "counterparty": payee,
            }
        )

    for _, row in subs_df.iterrows():
        merchant = row["counterparty_name"] or row["counterparty_vpa"]
        events.append(
            {
                "sort_date": row["next_expected_date"] or row["last_txn_date"],
                "type": "Subscription",
                "summary": (
                    f"{merchant} — avg ₹{row['avg_amount']:.2f} every "
                    f"{row['interval_days']} days"
                ),
                "detail": (
                    f"Last charge: {row['last_txn_date']} · "
                    f"Next expected: {row['next_expected_date']} · "
                    f"{row['occurrence_count']} occurrences "
                    f"(confidence {row['confidence_score']:.0%})"
                ),
                "flag_id": None,
                "risk_score": 0,
                "amount": None,
                "counterparty": None,
            }
        )

    if not events:
        st.info("No fraud flags or subscriptions detected for this user.")
        return

    # Fraud first (by risk), then subscriptions by date
    events.sort(
        key=lambda e: (
            0 if e["type"] == "Fraud Flag" else 1,
            -e["risk_score"] if e["type"] == "Fraud Flag" else 0,
            e["sort_date"] or "",
        )
    )

    for event in events:
        icon = "🚨" if event["type"] == "Fraud Flag" else "🔁"
        with st.container(border=True):
            st.markdown(f"**{icon} {event['type']}**")
            st.write(event["summary"])
            st.caption(event["detail"])
            if event["flag_id"]:
                btn_col1, btn_col2 = st.columns(2)
                with btn_col1:
                    if st.button(
                        "Why was this flagged?",
                        key=f"flag_{event['flag_id']}",
                    ):
                        st.session_state.pending_question = (
                            f"Why was the transaction flagged with risk score "
                            f"{event['risk_score']:.2f}? The reasons were: "
                            f"{event['detail']}"
                        )
                        st.rerun()
                with btn_col2:
                    if st.button(
                        "Play Voice Alert",
                        key=f"voice_{event['flag_id']}",
                    ):
                        alert_text = build_voice_alert_text(
                            event["amount"],
                            event["counterparty"],
                            event["detail"],
                        )
                        audio_bytes = generate_voice_alert(alert_text)
                        audio_key = f"voice_audio_{event['flag_id']}"
                        error_key = f"voice_error_{event['flag_id']}"
                        if audio_bytes:
                            st.session_state[audio_key] = audio_bytes
                            st.session_state.pop(error_key, None)
                        else:
                            st.session_state[error_key] = True
                            st.session_state.pop(audio_key, None)
                        st.rerun()

                audio_key = f"voice_audio_{event['flag_id']}"
                error_key = f"voice_error_{event['flag_id']}"
                if audio_key in st.session_state:
                    st.audio(st.session_state[audio_key], format="audio/mp3")
                if st.session_state.get(error_key):
                    st.warning(
                        "Could not generate voice alert — gTTS may be unavailable "
                        "or you may be offline. The text alert is still shown above."
                    )


def render_chat(conn, user_id: str):
    st.subheader("Ask about your data")
    st.caption(
        "Ask about fraud flags, subscriptions, or your credit score. "
        "Financial advice is out of scope."
    )

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])

    # Handle pending question from a fraud-flag button
    if st.session_state.pending_question:
        question = st.session_state.pending_question
        st.session_state.pending_question = None
        st.session_state.messages.append({"role": "user", "content": question})
        with st.chat_message("user"):
            st.write(question)
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                answer = explain(user_id, question, conn)
            st.write(answer)
        st.session_state.messages.append({"role": "assistant", "content": answer})

    if prompt := st.chat_input("Ask a question about this user's financial data..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.write(prompt)
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                answer = explain(user_id, prompt, conn)
            st.write(answer)
        st.session_state.messages.append({"role": "assistant", "content": answer})


def main():
    st.set_page_config(
        page_title="UPI Transaction Intelligence",
        page_icon="💳",
        layout="wide",
    )
    st.title("UPI Transaction Intelligence Platform")
    st.caption("Rule-engine insights + Groq-powered explanations")

    init_session_state()
    conn = get_connection()

    users = load_users(conn)
    if not users:
        st.error("No users found. Run `python main.py` first to generate the database.")
        return

    user_labels = {f"{u['name']} ({u['user_id']})": u["user_id"] for u in users}
    selected_label = st.selectbox("Select user", list(user_labels.keys()))
    user_id = user_labels[selected_label]
    reset_chat_if_user_changed(user_id)

    selected_user = next(u for u in users if u["user_id"] == user_id)
    st.write(
        f"**{selected_user['name']}** · "
        f"Estimated income ₹{selected_user['monthly_income_estimate']:,.0f}/mo"
    )

    fraud_df = load_fraud_flags(conn, user_id)
    subs_df = load_subscriptions(conn, user_id)
    credit = load_credit_score(conn, user_id)

    col_feed, col_score = st.columns([2, 1])
    with col_feed:
        render_financial_events(fraud_df, subs_df)
    with col_score:
        render_credit_score(credit)

    if not fraud_df.empty:
        with st.expander("Fraud flags table"):
            display_cols = [
                "risk_score",
                "txn_timestamp",
                "amount",
                "direction",
                "counterparty_name",
                "counterparty_vpa",
                "category",
                "reasons_plain",
            ]
            st.dataframe(
                fraud_df[display_cols].rename(columns={"reasons_plain": "reasons"}),
                use_container_width=True,
                hide_index=True,
            )

    if not subs_df.empty:
        with st.expander("Subscriptions table"):
            st.dataframe(subs_df, use_container_width=True, hide_index=True)

    st.divider()
    render_chat(conn, user_id)


if __name__ == "__main__":
    main()
