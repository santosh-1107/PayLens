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

# --- Visual theme (CSS / layout only) ---

COLORS = {
    "bg": "#F7F1E8",
    "card": "#FFFFFF",
    "primary": "#E8A87C",
    "secondary": "#D98E5F",
    "text": "#2B2B2B",
    "muted": "#8A8378",
    "success": "#9CBFA0",
    "warning": "#E0B15C",
    "error": "#E08578",
}


def inject_custom_css():
    c = COLORS
    st.markdown(
        f"""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

        :root {{
            --paylens-bg: {c["bg"]};
            --paylens-card: {c["card"]};
            --paylens-primary: {c["primary"]};
            --paylens-text: {c["text"]};
            --paylens-muted: {c["muted"]};
            --paylens-border: #E5DDD2;
        }}

        html, body, [class*="css"] {{
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            color: {c["text"]};
            line-height: 1.6;
        }}

        .stApp,
        [data-testid="stAppViewContainer"],
        [data-testid="stMain"],
        section.main {{
            background-color: {c["bg"]} !important;
        }}

        [data-testid="stHeader"] {{
            background: {c["bg"]} !important;
            border-bottom: none !important;
        }}

        [data-testid="stToolbar"] {{
            background: {c["bg"]} !important;
        }}

        [data-testid="stDecoration"] {{ display: none; }}
        #MainMenu {{ visibility: hidden; }}
        footer {{ visibility: hidden; }}
        .stDeployButton {{ display: none; }}

        .block-container {{
            padding-top: 2rem;
            padding-bottom: 3rem;
            padding-left: 2rem;
            padding-right: 2rem;
            max-width: 1120px;
            margin-left: auto !important;
            margin-right: auto !important;
        }}

        h1, h2, h3, .section-title {{
            color: {c["text"]} !important;
            font-weight: 600 !important;
            letter-spacing: -0.02em;
        }}

        p, .stMarkdown, .stCaption, label, .stSelectbox label {{
            color: {c["text"]};
        }}

        .stCaption, .muted-text {{
            color: {c["muted"]} !important;
        }}

        .section-card,
        [data-testid="stVerticalBlockBorderWrapper"] {{
            background: {c["card"]} !important;
            border-radius: 18px !important;
            box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06) !important;
            border: 1px solid var(--paylens-border) !important;
            padding: 24px !important;
            margin-bottom: 24px !important;
        }}

        .section-title {{
            font-size: 1.125rem;
            margin: 0 0 4px 0;
        }}

        .section-subtitle {{
            color: {c["muted"]};
            font-size: 0.875rem;
            margin: 0 0 20px 0;
        }}

        .page-header {{
            margin-bottom: 32px;
        }}

        .brand-title {{
            font-size: 2.75rem;
            font-weight: 700;
            color: {c["primary"]} !important;
            margin: 0 0 10px 0;
            letter-spacing: -0.03em;
            line-height: 1.1;
        }}

        .brand-accent-bar {{
            width: 72px;
            height: 4px;
            background: {c["primary"]};
            border-radius: 999px;
            margin-bottom: 14px;
        }}

        .brand-subtitle {{
            color: {c["muted"]};
            margin: 0;
            font-size: 1rem;
            line-height: 1.5;
        }}

        .user-meta {{
            color: {c["muted"]};
            font-size: 0.9rem;
            margin-top: 8px;
        }}

        .user-meta strong {{
            color: {c["text"]};
        }}

        .stSelectbox label,
        .stSelectbox [data-testid="stMarkdownContainer"] p {{
            color: {c["text"]} !important;
            font-weight: 500;
        }}

        .stSelectbox div[data-baseweb="select"] > div,
        .stSelectbox div[data-baseweb="select"] > div:focus-within {{
            background-color: {c["card"]} !important;
            color: {c["text"]} !important;
            border: 1px solid var(--paylens-border) !important;
            border-radius: 12px !important;
            box-shadow: none !important;
        }}

        .stSelectbox div[data-baseweb="select"] span,
        .stSelectbox div[data-baseweb="select"] svg {{
            color: {c["text"]} !important;
            fill: {c["text"]} !important;
        }}

        div[data-baseweb="popover"],
        div[data-baseweb="popover"] > div {{
            background-color: {c["card"]} !important;
            border: 1px solid var(--paylens-border) !important;
            border-radius: 12px !important;
        }}

        div[data-baseweb="popover"] ul {{
            background-color: {c["card"]} !important;
        }}

        div[data-baseweb="popover"] li {{
            color: {c["text"]} !important;
            background-color: {c["card"]} !important;
        }}

        div[data-baseweb="popover"] li:hover,
        div[data-baseweb="popover"] li[aria-selected="true"] {{
            background-color: {c["bg"]} !important;
            color: {c["text"]} !important;
        }}

        [data-testid="stBottom"],
        [data-testid="stBottomBlockContainer"],
        [data-testid="stChatInput"] {{
            background-color: {c["bg"]} !important;
        }}

        [data-testid="stBottomBlockContainer"] {{
            border-top: 1px solid var(--paylens-border) !important;
            padding-top: 0.75rem;
        }}

        [data-testid="stChatInput"] > div {{
            background-color: {c["card"]} !important;
            border: 1.5px solid {c["primary"]} !important;
            border-radius: 14px !important;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04) !important;
        }}

        [data-testid="stChatInput"] textarea,
        [data-testid="stChatInput"] input {{
            background-color: {c["card"]} !important;
            color: {c["text"]} !important;
            caret-color: {c["text"]} !important;
        }}

        [data-testid="stChatInput"] textarea::placeholder {{
            color: {c["muted"]} !important;
        }}

        [data-testid="stChatInput"] button {{
            color: {c["primary"]} !important;
        }}

        [data-testid="stChatInput"] button svg {{
            fill: {c["primary"]} !important;
        }}

        .event-card-header {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 12px;
            margin-bottom: 10px;
        }}

        .event-type {{
            font-weight: 600;
            color: {c["text"]};
            font-size: 0.95rem;
        }}

        .risk-badge, .status-badge {{
            display: inline-block;
            padding: 4px 12px;
            border-radius: 999px;
            font-size: 0.75rem;
            font-weight: 600;
            letter-spacing: 0.02em;
            white-space: nowrap;
        }}

        .event-summary {{
            color: {c["text"]};
            font-size: 0.95rem;
            margin: 0 0 6px 0;
            line-height: 1.5;
        }}

        .event-detail {{
            color: {c["muted"]};
            font-size: 0.85rem;
            margin: 0;
            line-height: 1.5;
        }}

        .score-hero {{
            text-align: left;
            margin-bottom: 24px;
        }}

        .score-value {{
            font-size: 2.5rem;
            font-weight: 700;
            color: {c["text"]};
            line-height: 1.1;
            margin: 4px 0;
        }}

        .score-label {{
            color: {c["muted"]};
            font-size: 0.85rem;
            text-transform: uppercase;
            letter-spacing: 0.06em;
            font-weight: 500;
        }}

        .progress-item {{
            margin-bottom: 18px;
        }}

        .progress-label {{
            display: flex;
            justify-content: space-between;
            font-size: 0.85rem;
            color: {c["text"]};
            margin-bottom: 8px;
            font-weight: 500;
        }}

        .progress-track {{
            height: 10px;
            background: #EDE6DC;
            border-radius: 999px;
            overflow: hidden;
        }}

        .progress-fill {{
            height: 100%;
            background: {c["secondary"]};
            border-radius: 999px;
            transition: width 0.3s ease;
        }}

        .stButton > button {{
            background-color: {c["primary"]} !important;
            color: #FFFFFF !important;
            border: none !important;
            border-radius: 999px !important;
            padding: 0.55rem 1.25rem !important;
            font-weight: 500 !important;
            box-shadow: none !important;
            transition: background-color 0.2s ease;
        }}

        .stButton > button:hover {{
            background-color: {c["secondary"]} !important;
            color: #FFFFFF !important;
            border: none !important;
        }}

        .stButton > button:focus {{
            box-shadow: 0 0 0 2px rgba(232, 168, 124, 0.35) !important;
        }}

        [data-testid="stMetric"] {{
            background: transparent;
        }}

        [data-testid="stMetricValue"] {{
            color: {c["text"]};
        }}

        [data-testid="stMetricLabel"] {{
            color: {c["muted"]};
        }}

        .stProgress > div > div {{
            background-color: {c["secondary"]} !important;
            border-radius: 999px !important;
        }}

        .stProgress > div {{
            background-color: #EDE6DC !important;
            border-radius: 999px !important;
        }}

        [data-testid="stChatMessage"] {{
            background: #FAFAF8 !important;
            border-radius: 14px !important;
            border: 1px solid var(--paylens-border) !important;
            color: {c["text"]} !important;
        }}

        [data-testid="stChatMessage"] p,
        [data-testid="stChatMessage"] span {{
            color: {c["text"]} !important;
        }}

        [data-testid="stExpander"] {{
            background: {c["card"]} !important;
            border-radius: 18px !important;
            border: 1px solid var(--paylens-border) !important;
            box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06) !important;
            margin-bottom: 24px !important;
        }}

        [data-testid="stExpander"] summary {{
            color: {c["text"]} !important;
        }}

        .stAlert {{
            background-color: {c["card"]} !important;
            color: {c["text"]} !important;
            border-radius: 12px !important;
            border: 1px solid var(--paylens-border) !important;
        }}

        hr {{
            border-color: var(--paylens-border) !important;
            margin: 28px 0 !important;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def open_section_card(title: str, subtitle: str = ""):
    subtitle_html = f'<p class="section-subtitle">{subtitle}</p>' if subtitle else ""
    st.markdown(
        f'<div class="section-card">'
        f'<h3 class="section-title">{title}</h3>{subtitle_html}',
        unsafe_allow_html=True,
    )


def close_section_card():
    st.markdown("</div>", unsafe_allow_html=True)


def risk_badge_html(risk_score: float) -> str:
    if risk_score >= 0.7:
        label, color = "High Risk", COLORS["error"]
    elif risk_score >= 0.4:
        label, color = "Medium Risk", COLORS["warning"]
    else:
        label, color = "Low Risk", COLORS["success"]
    return (
        f'<span class="risk-badge" style="background:{color}22;color:{color};'
        f'border:1px solid {color}55;">{label} · {risk_score:.2f}</span>'
    )


def subscription_badge_html() -> str:
    color = COLORS["success"]
    return (
        f'<span class="status-badge" style="background:{color}22;color:{color};'
        f'border:1px solid {color}55;">Subscription</span>'
    )


def progress_bar_html(label: str, value: float) -> str:
    pct = min(max(value, 0.0), 1.0)
    return f"""
    <div class="progress-item">
        <div class="progress-label">
            <span>{label}</span>
            <span>{value:.2f}</span>
        </div>
        <div class="progress-track">
            <div class="progress-fill" style="width:{pct * 100:.1f}%;"></div>
        </div>
    </div>
    """


@st.cache_resource
def get_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS complaints (
            complaint_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            txn_id TEXT NOT NULL,
            reason TEXT NOT NULL,
            details TEXT,
            status TEXT NOT NULL,
            filed_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users(user_id),
            FOREIGN KEY (txn_id) REFERENCES transactions(txn_id)
        );
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS subscription_actions (
            action_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            subscription_id TEXT NOT NULL,
            action_type TEXT NOT NULL,
            requested_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users(user_id),
            FOREIGN KEY (subscription_id) REFERENCES detected_subscriptions(subscription_id)
        );
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS income_authenticity_flags (
            flag_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            counterparty_vpa TEXT NOT NULL,
            counterparty_name TEXT,
            debit_txn_id TEXT NOT NULL,
            debit_timestamp TEXT NOT NULL,
            debit_amount REAL NOT NULL,
            credit_txn_id TEXT NOT NULL,
            credit_timestamp TEXT NOT NULL,
            credit_amount REAL NOT NULL,
            detected_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users(user_id),
            FOREIGN KEY (debit_txn_id) REFERENCES transactions(txn_id),
            FOREIGN KEY (credit_txn_id) REFERENCES transactions(txn_id)
        );
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS shared_risk_counterparties (
            counterparty_vpa TEXT PRIMARY KEY,
            counterparty_name TEXT,
            unique_user_count INTEGER NOT NULL,
            total_flag_count INTEGER NOT NULL,
            detected_at TEXT DEFAULT (datetime('now'))
        );
    """)
    conn.commit()
    return conn


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
            t.txn_id,
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
            subscription_id,
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


VOICE_TEMPLATES = {
    "en": {
        "template": "This payment of {amount:.2f} rupees to {payee} looks unusual because {reasons}. Are you sure this was you?",
        "payee_default": "an unknown payee",
        "no_reasons": "it looks suspicious",
        "and_joiner": " and ",
        "reasons": {
            "amount_spike": "unusual amount spike vs. your typical spending",
            "odd_hour": "transaction at an unusual hour (late night / early morning)",
            "new_payee": "first-time payee — never transacted with them before",
            "velocity_burst": "multiple rapid transactions in a short window",
        }
    },
    "hi": {
        "template": "{payee} को {amount:.2f} रुपये का यह भुगतान असामान्य लग रहा है क्योंकि {reasons}। क्या आपको यकीन है कि यह आप ही थे?",
        "payee_default": "एक अज्ञात प्राप्तकर्ता",
        "no_reasons": "यह संदिग्ध लग रहा है",
        "and_joiner": " और ",
        "reasons": {
            "amount_spike": "यह आपके सामान्य खर्च की तुलना में असामान्य रूप से अधिक है",
            "odd_hour": "यह असामान्य समय पर किया गया लेन-देन है (देर रात या सुबह जल्दी)",
            "new_payee": "यह एक नया प्राप्तकर्ता है जिसके साथ पहले कभी लेन-देन नहीं किया गया है",
            "velocity_burst": "कम समय में कई तेज़ लेन-देन किए गए हैं",
        }
    },
    "ta": {
        "template": "{payee} என்பவருக்குச் செலுத்தப்பட்ட {amount:.2f} ரூபாய் வழக்கத்திற்கு மாறாக உள்ளது, ஏனெனில் {reasons}. இதை நீங்கள்தான் செய்தீர்களா?",
        "payee_default": "அறியப்படாத நபர்",
        "no_reasons": "இது சந்தேகத்திற்குரியதாகத் தெரிகிறது",
        "and_joiner": " மற்றும் ",
        "reasons": {
            "amount_spike": "இது உங்கள் வழக்கமான செலவை விட வழக்கத்திற்கு மாறாக அதிகமாக உள்ளது",
            "odd_hour": "இது வழக்கத்திற்கு மாறான நேரத்தில் நடந்த பரிவர்த்தனை (நள்ளிரவு அல்லது அதிகாலை)",
            "new_payee": "இது ஒரு புதிய நபர் — இதற்கு முன்பு நீங்கள் இவருடன் பரிவர்த்தனை செய்யவில்லை",
            "velocity_burst": "குறுகிய காலத்தில் பல விரைவான பரிவர்த்தனைகள் நடந்துள்ளன",
        }
    }
}


SUBSCRIPTION_VOICE_TEMPLATES = {
    "en": {
        "template": "You have a subscription to {counterparty_name} for ₹{avg_amount:.2f}, charged every {interval_days} days. Your next payment is expected on {next_expected_date}.",
    },
    "hi": {
        "template": "आपके पास {counterparty_name} की ₹{avg_amount:.2f} की सदस्यता है, जिसका भुगतान हर {interval_days} दिनों में किया जाता है। आपका अगला भुगतान {next_expected_date} को होने की उम्मीद है।",
    },
    "ta": {
        "template": "உங்களிடம் {counterparty_name}க்கான ₹{avg_amount:.2f} சந்தா உள்ளது, இதற்கான கட்டணம் ஒவ்வொரு {interval_days} நாட்களுக்கு ஒருமுறை வசூலிக்கப்படுகிறது. உங்களது அடுத்த கட்டணம் {next_expected_date} அன்று எதிர்பார்க்கப்படுகிறது.",
    }
}


CANCELLATION_LOCALIZATION = {
    "en": {
        "button": "Mark for Cancellation",
        "success": "Cancellation request logged successfully!",
        "status": "🚫 Cancellation requested on {date}",
        "disclaimer": "ℹ️ **Note:** This logs your intent to cancel. Actually stopping the auto-debit requires action with your bank or the UPI Autopay settings in your banking app — this prototype does not have access to cancel real mandates."
    },
    "hi": {
        "button": "रद्द करने के लिए चिह्नित करें",
        "success": "रद्दीकरण का अनुरोध सफलतापूर्वक दर्ज किया गया!",
        "status": "🚫 {date} को रद्दीकरण का अनुरोध किया गया",
        "disclaimer": "ℹ️ **नोट:** यह रद्द करने के आपके इरादे को दर्ज करता है। ऑटो-डेबिट को वास्तव में रोकने के लिए आपके बैंक या आपके बैंकिंग ऐप में UPI ऑटोपे (Autopay) सेटिंग्स के साथ कार्रवाई की आवश्यकता होती है — इस प्रोटोटाइप के पास वास्तविक मैंडेट को रद्द करने की पहुंच नहीं है।"
    },
    "ta": {
        "button": "ரத்து செய்யக் குறியிடவும்",
        "success": "ரத்து செய்வதற்கான கோரிக்கை வெற்றிகரமாகப் பதிவு செய்யப்பட்டது!",
        "status": "🚫 {date} அன்று ரத்து செய்யக் கோரப்பட்டது",
        "disclaimer": "ℹ️ **குறிப்பு:** இது ரத்து செய்வதற்கான உங்கள் நோக்கத்தை மட்டுமே பதிவு செய்கிறது. தானியங்கி கழிப்பை (auto-debit) நிறுத்த, உங்கள் வங்கி அல்லது உங்கள் வங்கி செயலியில் உள்ள UPI Autopay அமைப்புகளில் நடவடிக்கை எடுக்க வேண்டும் — இந்த முன்மாதிரிக்கு உண்மையான கட்டளைகளை (mandates) ரத்து செய்ய அணுகல் இல்லை."
    }
}


COMPLAINT_LOCALIZATION = {
    "en": {
        "title": "File Complaint",
        "txn_id": "Transaction ID",
        "amount": "Amount (₹)",
        "counterparty": "Counterparty",
        "date": "Date",
        "reason_label": "Reason for Complaint",
        "reasons": ["Unauthorized transaction", "Sent to wrong recipient", "Suspected fraud", "Other"],
        "details_label": "Additional Details",
        "submit": "Submit Complaint",
        "cancel": "Cancel",
        "success": "Complaint submitted successfully! Reference ID: {ref_id}",
        "status_submitted": "Submitted — awaiting review",
        "demo_note": "ℹ️ **Note:** This demonstrates a unified complaint-intake concept. In production, this would route to your bank and NPCI's grievance redressal system — this prototype logs the complaint locally only.",
        "complaint_already_filed": "✅ Complaint already filed — Status: {status}",
    },
    "hi": {
        "title": "शिकायत दर्ज करें",
        "txn_id": "लेन-देने आईडी",
        "amount": "राशि (₹)",
        "counterparty": "प्राप्तकर्ता",
        "date": "दिनांक",
        "reason_label": "शिकायत का कारण",
        "reasons": ["अनधिकृत लेन-देन", "गलत प्राप्तकर्ता को भेजा गया", "संदिग्ध धोखाधड़ी", "अन्य"],
        "details_label": "अतिरिक्त विवरण",
        "submit": "शिकायत दर्ज करें",
        "cancel": "रद्द करें",
        "success": "शिकायत सफलतापूर्वक दर्ज की गई! संदर्भ आईडी: {ref_id}",
        "status_submitted": "जमा किया गया — समीक्षा की प्रतीक्षा है",
        "demo_note": "ℹ️ **नोट:** यह एक एकीकृत शिकायत-निवारण अवधारणा को दर्शाता है। उत्पादन (production) में, यह आपके बैंक और NPCI के शिकायत निवारण तंत्र पर भेजा जाएगा — यह प्रोटोटाइप केवल स्थानीय रूप से शिकायत को लॉग करता है।",
        "complaint_already_filed": "✅ शिकायत पहले ही दर्ज की जा चुकी है — स्थिति: {status}",
    },
    "ta": {
        "title": "புகார் அளிக்கவும்",
        "txn_id": "பரிவர்த்தனை ஐடி",
        "amount": "தொகை (₹)",
        "counterparty": "பெறுநர்",
        "date": "தேதி",
        "reason_label": "புகாருக்கான காரணம்",
        "reasons": ["அங்கீகரிக்கப்படாத பரிவர்த்தனை", "தவறான பெறுநருக்கு அனுப்பப்பட்டது", "சந்தேகத்திற்குரிய மோசடி", "மற்றவை"],
        "details_label": "கூடுதல் விவரங்கள்",
        "submit": "புகாரைச் சமர்ப்பிக்கவும்",
        "cancel": "ரத்துசெய்",
        "success": "புகார் வெற்றிகரமாக சமர்ப்பிக்கப்பட்டது! குறிப்பு ஐடி: {ref_id}",
        "status_submitted": "சமர்ப்பிக்கப்பட்டது — மதிப்பாய்வுக்காகக் காத்திருக்கிறது",
        "demo_note": "ℹ️ **குறிப்பு:** இது ஒரு ஒருங்கிணைந்த புகார்-தாக்கல் கருத்தை நிரூபிக்கிறது. தயாரிப்பில் (production), இது உங்கள் வங்கி மற்றும் NPCI-இன் குறை தீர்க்கும் அமைப்பிற்கு அனுப்பப்படும் — இந்த முன்மாதிரி புகாரை உள்நாட்டில் மட்டுமே பதிவு செய்கிறது.",
        "complaint_already_filed": "✅ புகார் ஏற்கனவே சமர்ப்பிக்கப்பட்டது — நிலை: {status}",
    }
}

MY_COMPLAINTS_LOCALIZATION = {
    "en": {
        "title": "My Complaints",
        "no_complaints": "No complaints filed yet.",
        "headers": {
            "reason": "Reason",
            "details": "Details",
            "status": "Status",
            "filed_at": "Filed Date"
        }
    },
    "hi": {
        "title": "मेरी शिकायतें",
        "no_complaints": "अभी तक कोई शिकायत दर्ज नहीं की गई है।",
        "headers": {
            "reason": "शिकायत का कारण",
            "details": "विवरण",
            "status": "स्थिति",
            "filed_at": "दर्ज करने की तिथि"
        }
    },
    "ta": {
        "title": "எனது புகார்கள்",
        "no_complaints": "இன்னும் புகார்கள் எதுவும் தாக்கல் செய்யப்படவில்லை.",
        "headers": {
            "reason": "காரணம்",
            "details": "விவரங்கள்",
            "status": "நிலை",
            "filed_at": "சமர்ப்பிக்கப்பட்ட தேதி"
        }
    }
}


def build_voice_alert_text(amount: float, counterparty: str, raw_reasons: str, language: str = "en") -> str:
    lang_cfg = VOICE_TEMPLATES.get(language, VOICE_TEMPLATES["en"])
    
    payee = counterparty or lang_cfg["payee_default"]
    
    if not raw_reasons:
        reasons_str = lang_cfg["no_reasons"]
    else:
        reason_keys = [r.strip() for r in str(raw_reasons).split(",") if r.strip()]
        translated_reasons = []
        for rk in reason_keys:
            translated = lang_cfg["reasons"].get(rk) or VOICE_TEMPLATES["en"]["reasons"].get(rk, rk)
            translated_reasons.append(translated)
        
        if not translated_reasons:
            reasons_str = lang_cfg["no_reasons"]
        else:
            reasons_str = lang_cfg["and_joiner"].join(translated_reasons)
            
    return lang_cfg["template"].format(amount=amount, payee=payee, reasons=reasons_str)


def build_subscription_voice_text(
    counterparty_name: str,
    avg_amount: float,
    interval_days: int,
    next_expected_date: str,
    language: str = "en"
) -> str:
    lang_cfg = SUBSCRIPTION_VOICE_TEMPLATES.get(language, SUBSCRIPTION_VOICE_TEMPLATES["en"])
    return lang_cfg["template"].format(
        counterparty_name=counterparty_name,
        avg_amount=avg_amount,
        interval_days=interval_days,
        next_expected_date=next_expected_date
    )


def generate_voice_alert(text: str, language: str = "en") -> bytes | None:
    """Generate MP3 bytes via gTTS; save via temp file. Returns None on failure."""
    tmp_path = None
    try:
        from gtts import gTTS

        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            tmp_path = tmp.name
        gTTS(text=text, lang=language).save(tmp_path)
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
    open_section_card("Credit Score", "Latest computed score and component breakdown")
    if not credit:
        st.info("No credit score computed for this user yet.")
        close_section_card()
        return

    st.markdown(
        f"""
        <div class="score-hero">
            <div class="score-label">Overall Score</div>
            <div class="score-value">{credit['score']:.0f}</div>
            <div class="muted-text">Range 300–900 · Computed {credit['computed_at']}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        progress_bar_html("Income Regularity", credit["income_regularity"])
        + progress_bar_html("Expense Ratio", credit["expense_ratio"])
        + progress_bar_html("Volatility", credit["volatility"]),
        unsafe_allow_html=True,
    )
    close_section_card()


def render_complaint_form(conn, user_id: str, event: dict, language: str = "en"):
    loc = COMPLAINT_LOCALIZATION.get(language, COMPLAINT_LOCALIZATION["en"])
    
    st.markdown(f"##### {loc['title']}")
    st.info(loc["demo_note"])
    
    with st.form(key=f"complaint_form_{event['flag_id']}"):
        st.text_input(loc["txn_id"], value=event["txn_id"], disabled=True)
        st.number_input(loc["amount"], value=float(event["amount"]), disabled=True)
        st.text_input(loc["counterparty"], value=event["counterparty"], disabled=True)
        st.text_input(loc["date"], value=event["txn_timestamp"], disabled=True)
        
        reason = st.selectbox(loc["reason_label"], loc["reasons"])
        details = st.text_area(loc["details_label"])
        
        submitted = st.form_submit_button(loc["submit"])
        if submitted:
            try:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO complaints (user_id, txn_id, reason, details, status)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (user_id, event["txn_id"], reason, details, loc["status_submitted"])
                )
                conn.commit()
                st.session_state.pop("active_complaint_txn_id", None)
                st.session_state.pop("active_complaint_event", None)
                st.success(loc["success"].format(ref_id=cursor.lastrowid))
                st.rerun()
            except Exception as e:
                st.error(f"Error saving complaint: {e}")
                
    if st.button(loc["cancel"], key=f"cancel_btn_{event['flag_id']}"):
        st.session_state.pop("active_complaint_txn_id", None)
        st.session_state.pop("active_complaint_event", None)
        st.rerun()


def load_complaints(conn, user_id: str) -> pd.DataFrame:
    return pd.read_sql_query(
        """
        SELECT reason, details, status, filed_at
        FROM complaints
        WHERE user_id = ?
        ORDER BY filed_at DESC
        """,
        conn,
        params=(user_id,),
    )


def render_my_complaints(complaints_df: pd.DataFrame, language: str = "en"):
    loc = MY_COMPLAINTS_LOCALIZATION.get(language, MY_COMPLAINTS_LOCALIZATION["en"])
    with st.expander(loc["title"]):
        if complaints_df.empty:
            st.info(loc["no_complaints"])
        else:
            renamed_df = complaints_df.rename(columns=loc["headers"])
            st.dataframe(renamed_df, use_container_width=True, hide_index=True)


def render_financial_events(fraud_df: pd.DataFrame, subs_df: pd.DataFrame, conn, user_id: str, language: str = "en"):
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
                "display_summary": (
                    f"₹{row['amount']:.2f} {row['direction']} to {payee} "
                    f"on {row['txn_timestamp']}"
                ),
                "detail": row["reasons_plain"],
                "raw_reasons": row["reasons"],
                "flag_id": row["flag_id"],
                "txn_id": row["txn_id"],
                "txn_timestamp": row["txn_timestamp"],
                "risk_score": row["risk_score"],
                "amount": row["amount"],
                "counterparty": payee,
            }
        )

    for idx, (_, row) in enumerate(subs_df.iterrows()):
        merchant = row["counterparty_name"] or row["counterparty_vpa"]
        events.append(
            {
                "sort_date": row["next_expected_date"] or row["last_txn_date"],
                "type": "Subscription",
                "summary": (
                    f"{merchant} — avg ₹{row['avg_amount']:.2f} every "
                    f"{row['interval_days']} days"
                ),
                "display_summary": (
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
                "counterparty_name": merchant,
                "avg_amount": row["avg_amount"],
                "interval_days": row["interval_days"],
                "next_expected_date": row["next_expected_date"],
                "sub_id": f"sub_{idx}",
                "subscription_id": row["subscription_id"],
            }
        )

    fraud_events = [e for e in events if e["type"] == "Fraud Flag"]
    sub_events = [e for e in events if e["type"] == "Subscription"]

    fraud_events.sort(key=lambda e: (-e["risk_score"], e["sort_date"] or ""))
    sub_events.sort(key=lambda e: e["sort_date"] or "")

    open_section_card(
        "Fraud Flags",
        "Suspicious transactions flagged by the rule engine",
    )
    if not fraud_events:
        st.info("No fraud flags detected for this user.")
    else:
        for event in fraud_events:
            with st.container(border=True):
                st.markdown(
                    f"""
                    <div class="event-card-header">
                        <span class="event-type">Fraud Alert</span>
                        {risk_badge_html(event["risk_score"])}
                    </div>
                    <p class="event-summary">{event["display_summary"]}</p>
                    <p class="event-detail">{event["detail"]}</p>
                    """,
                    unsafe_allow_html=True,
                )
                btn_col1, btn_col2, btn_col3 = st.columns(3)
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
                            event["raw_reasons"],
                            language=language,
                        )
                        audio_bytes = generate_voice_alert(alert_text, language=language)
                        audio_key = f"voice_audio_{event['flag_id']}"
                        error_key = f"voice_error_{event['flag_id']}"
                        if audio_bytes:
                            st.session_state[audio_key] = audio_bytes
                            st.session_state.pop(error_key, None)
                        else:
                            st.session_state[error_key] = True
                            st.session_state.pop(audio_key, None)
                        st.rerun()
                with btn_col3:
                    c_row = conn.execute("SELECT status FROM complaints WHERE txn_id = ?", (event["txn_id"],)).fetchone()
                    if c_row:
                        status = c_row[0]
                        already_filed_text = COMPLAINT_LOCALIZATION.get(language, COMPLAINT_LOCALIZATION["en"])["complaint_already_filed"].format(status=status)
                        st.markdown(f"<div style='font-size:0.85rem; color:var(--paylens-muted); padding-top:10px;'>{already_filed_text}</div>", unsafe_allow_html=True)
                    else:
                        file_complaint_lbl = COMPLAINT_LOCALIZATION.get(language, COMPLAINT_LOCALIZATION["en"])["title"]
                        if st.button(
                            file_complaint_lbl,
                            key=f"complaint_btn_{event['flag_id']}",
                        ):
                            st.session_state.active_complaint_txn_id = event["txn_id"]
                            st.session_state.active_complaint_event = event
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
                
                if st.session_state.get("active_complaint_txn_id") == event["txn_id"]:
                    render_complaint_form(conn, user_id, event, language=language)
    close_section_card()

    open_section_card(
        "Subscriptions",
        "Recurring payments detected from transaction patterns",
    )
    if not sub_events:
        st.info("No recurring subscriptions detected for this user.")
    else:
        for event in sub_events:
            with st.container(border=True):
                st.markdown(
                    f"""
                    <div class="event-card-header">
                        <span class="event-type">Recurring Payment</span>
                        {subscription_badge_html()}
                    </div>
                    <p class="event-summary">{event["display_summary"]}</p>
                    <p class="event-detail">{event["detail"]}</p>
                    """,
                    unsafe_allow_html=True,
                )
                
                btn_col1, btn_col2 = st.columns(2)
                with btn_col1:
                    if st.button(
                        "Play Voice Summary",
                        key=f"sub_voice_btn_{event['sub_id']}",
                    ):
                        alert_text = build_subscription_voice_text(
                            counterparty_name=event["counterparty_name"],
                            avg_amount=event["avg_amount"],
                            interval_days=event["interval_days"],
                            next_expected_date=event["next_expected_date"],
                            language=language,
                        )
                        audio_bytes = generate_voice_alert(alert_text, language=language)
                        audio_key = f"sub_audio_{event['sub_id']}"
                        error_key = f"sub_error_{event['sub_id']}"
                        if audio_bytes:
                            st.session_state[audio_key] = audio_bytes
                            st.session_state.pop(error_key, None)
                        else:
                            st.session_state[error_key] = True
                            st.session_state.pop(audio_key, None)
                        st.rerun()

                with btn_col2:
                    cancel_row = conn.execute(
                        "SELECT requested_at FROM subscription_actions WHERE user_id = ? AND subscription_id = ? AND action_type = 'cancellation_requested'",
                        (user_id, event["subscription_id"])
                    ).fetchone()
                    if cancel_row:
                        requested_at = cancel_row[0]
                        status_tpl = CANCELLATION_LOCALIZATION.get(language, CANCELLATION_LOCALIZATION["en"])["status"]
                        status_text = status_tpl.format(date=requested_at)
                        st.markdown(f"<div style='font-size:0.85rem; color:var(--paylens-muted); padding-top:10px;'>{status_text}</div>", unsafe_allow_html=True)
                    else:
                        cancel_lbl = CANCELLATION_LOCALIZATION.get(language, CANCELLATION_LOCALIZATION["en"])["button"]
                        if st.button(
                            cancel_lbl,
                            key=f"cancel_btn_{event['sub_id']}",
                        ):
                            try:
                                cursor = conn.cursor()
                                cursor.execute(
                                    """
                                    INSERT INTO subscription_actions (user_id, subscription_id, action_type)
                                    VALUES (?, ?, ?)
                                    """,
                                    (user_id, event["subscription_id"], "cancellation_requested")
                                )
                                conn.commit()
                                success_msg = CANCELLATION_LOCALIZATION.get(language, CANCELLATION_LOCALIZATION["en"])["success"]
                                st.success(success_msg)
                                st.rerun()
                            except Exception as e:
                                st.error(f"Error requesting cancellation: {e}")

                audio_key = f"sub_audio_{event['sub_id']}"
                error_key = f"sub_error_{event['sub_id']}"
                if audio_key in st.session_state:
                    st.audio(st.session_state[audio_key], format="audio/mp3")
                if st.session_state.get(error_key):
                    st.warning(
                        "Could not generate voice summary — gTTS may be unavailable "
                        "or you may be offline. The summary text is still shown above."
                    )
        
        # Display cancellation disclaimer near the feature
        disclaimer_text = CANCELLATION_LOCALIZATION.get(language, CANCELLATION_LOCALIZATION["en"])["disclaimer"]
        st.markdown(disclaimer_text)
    close_section_card()


def render_chat(conn, user_id: str, language: str = "en"):
    open_section_card(
        "Ask about your data",
        "Ask about fraud flags, subscriptions, or your credit score. Financial advice is out of scope.",
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
                answer = explain(user_id, question, conn, language=language)
            st.write(answer)
        st.session_state.messages.append({"role": "assistant", "content": answer})

    if prompt := st.chat_input("Ask a question about this user's financial data..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.write(prompt)
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                answer = explain(user_id, prompt, conn, language=language)
            st.write(answer)
        st.session_state.messages.append({"role": "assistant", "content": answer})

    close_section_card()


def main():
    st.set_page_config(
        page_title="PayLens",
        page_icon="💳",
        layout="wide",
    )
    inject_custom_css()

    st.markdown(
        """
        <div class="page-header">
            <h1 class="brand-title">PayLens</h1>
            <div class="brand-accent-bar"></div>
            <p class="brand-subtitle">Rule-engine insights with Groq-powered explanations</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    init_session_state()
    conn = get_connection()

    users = load_users(conn)
    if not users:
        st.error("No users found. Run `python main.py` first to generate the database.")
        return

    open_section_card("Account", "Select user and language")
    col1, col2 = st.columns(2)
    with col1:
        user_labels = {f"{u['name']} ({u['user_id']})": u["user_id"] for u in users}
        selected_label = st.selectbox("Select user", list(user_labels.keys()))
        user_id = user_labels[selected_label]
        reset_chat_if_user_changed(user_id)
    with col2:
        lang_options = {"English": "en", "Hindi": "hi", "Tamil": "ta"}
        selected_lang_name = st.selectbox("Select language", list(lang_options.keys()))
        selected_lang = lang_options.get(selected_lang_name, "en")

    selected_user = next(u for u in users if u["user_id"] == user_id)
    st.markdown(
        f'<p class="user-meta"><strong>{selected_user["name"]}</strong> · '
        f'Estimated income ₹{selected_user["monthly_income_estimate"]:,.0f}/mo</p>',
        unsafe_allow_html=True,
    )
    close_section_card()

    fraud_df = load_fraud_flags(conn, user_id)
    subs_df = load_subscriptions(conn, user_id)
    credit = load_credit_score(conn, user_id)

    col_feed, col_score = st.columns([2, 1])
    with col_feed:
        render_financial_events(fraud_df, subs_df, conn, user_id, language=selected_lang)
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

    complaints_df = load_complaints(conn, user_id)
    render_my_complaints(complaints_df, language=selected_lang)

    render_chat(conn, user_id, language=selected_lang)


if __name__ == "__main__":
    main()
