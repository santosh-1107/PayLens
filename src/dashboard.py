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
from auth import login_user

DB_PATH = str(Path(__file__).resolve().parent.parent / "data" / "upi_transactions.db")

REASON_LABELS = {
    "amount_spike": "Unusual amount spike vs. your typical spending",
    "odd_hour": "Transaction at an unusual hour (late night / early morning)",
    "new_payee": "First-time payee — never transacted with them before",
    "velocity_burst": "Multiple rapid transactions in a short window",
}

# --- Visual theme (CSS / layout only) ---

COLORS = {
    "bg": "#FBF7F0",
    "card": "#FFFDF9",
    "primary": "#934F22",
    "secondary": "#7E3F18",
    "text": "#3D2A20",
    "muted": "#806F62",
    "success": "#4A7C59",
    "warning": "#C29338",
    "error": "#B33939",
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
            --paylens-border: #E9DED0;
            --paylens-input: #FCF8F2;
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
            max-width: 1200px;
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
            border-radius: 14px !important;
            box-shadow: 0 4px 20px rgba(61, 42, 32, 0.02) !important;
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
            background-color: #FCF8F2 !important;
            color: {c["text"]} !important;
            border: 1px solid var(--paylens-border) !important;
            border-radius: 10px !important;
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
            border-radius: 10px !important;
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
            border-radius: 12px !important;
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
            background: #E9DED0;
            border-radius: 999px;
            overflow: hidden;
        }}

        .progress-fill {{
            height: 100%;
            background: {c["primary"]};
            border-radius: 999px;
            transition: width 0.3s ease;
        }}

        .stButton > button {{
            background-color: {c["primary"]} !important;
            color: #FFFFFF !important;
            border: none !important;
            border-radius: 10px !important;
            padding: 0.55rem 1.25rem !important;
            font-weight: 600 !important;
            box-shadow: none !important;
            transition: all 0.2s ease;
        }}

        .stButton > button:hover {{
            background-color: {c["secondary"]} !important;
            color: #FFFFFF !important;
            border: none !important;
        }}

        .stButton > button:focus {{
            box-shadow: 0 0 0 2px rgba(147, 79, 34, 0.25) !important;
        }}

        .stButton > button[kind="secondary"] {{
            background-color: #FFFDF9 !important;
            color: #806F62 !important;
            border: 1px solid #E9DED0 !important;
            border-radius: 10px !important;
            font-weight: 500 !important;
            transition: all 0.2s ease !important;
        }}

        .stButton > button[kind="secondary"]:hover {{
            background-color: #FCF8F2 !important;
            color: #3D2A20 !important;
            border-color: #806F62 !important;
        }}

        .stButton > button[kind="secondary"]:focus {{
            box-shadow: 0 0 0 2px rgba(128, 111, 98, 0.15) !important;
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
            background-color: {c["primary"]} !important;
            border-radius: 999px !important;
        }}

        .stProgress > div {{
            background-color: #E9DED0 !important;
            border-radius: 999px !important;
        }}

        [data-testid="stChatMessage"] {{
            background: #FFFDF9 !important;
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
            border-radius: 14px !important;
            border: 1px solid var(--paylens-border) !important;
            box-shadow: 0 4px 20px rgba(61, 42, 32, 0.02) !important;
            margin-bottom: 24px !important;
        }}

        [data-testid="stExpander"] summary {{
            color: {c["text"]} !important;
        }}

        .stAlert {{
            background-color: {c["card"]} !important;
            color: {c["text"]} !important;
            border-radius: 10px !important;
            border: 1px solid var(--paylens-border) !important;
        }}

        /* Search bar & Page Heading overrides */
        .global-search-marker {{
            display: none;
        }}

        div:has(> .global-search-marker) + div [data-testid="stTextInput"] input {{
            background-color: #FCF8F2 !important;
            border: 1px solid #E9DED0 !important;
            border-radius: 8px !important;
            color: #33241B !important;
            padding: 8px 12px 8px 36px !important;
            height: 38px !important;
            background-image: url('data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="none" stroke="%23806F62" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>') !important;
            background-repeat: no-repeat !important;
            background-position: 12px center !important;
            font-size: 0.85rem !important;
        }}

        div:has(> .global-search-marker) + div [data-testid="stTextInput"] input:focus {{
            border-color: #934F22 !important;
            box-shadow: 0 0 0 2px rgba(147, 79, 34, 0.08) !important;
        }}

        .page-heading {{
            margin-bottom: 28px;
            margin-top: 10px;
        }}
        .page-title {{
            font-size: 1.75rem !important;
            font-weight: 600 !important;
            color: #33241B !important;
            margin: 0 !important;
            letter-spacing: -0.02em;
        }}
        .page-description {{
            font-size: 0.85rem !important;
            color: #806F62 !important;
            margin: 4px 0 0 0 !important;
        }}

        /* Hover animation on cards */
        [data-testid="stVerticalBlockBorderWrapper"]:hover {{
            box-shadow: 0 6px 24px rgba(147, 79, 34, 0.03) !important;
            transform: translateY(-2px);
            transition: all 0.2s ease;
        }}

        /* Sidebar Styling */
        [data-testid="stSidebar"] {{
            background-color: #FFFDF9 !important;
            border-right: 1px solid #E9DED0 !important;
        }}

        [data-testid="stSidebar"] [data-testid="stRadio"] [role="radiogroup"] label {{
            display: flex !important;
            align-items: center !important;
            padding: 10px 16px !important;
            border-radius: 10px !important;
            margin-bottom: 4px !important;
            border: 1px solid transparent !important;
            background-color: transparent !important;
            cursor: pointer !important;
            transition: all 0.2s ease !important;
        }}

        [data-testid="stSidebar"] [data-testid="stRadio"] [role="radiogroup"] label:hover {{
            background-color: #FCF8F2 !important;
        }}

        [data-testid="stSidebar"] [data-testid="stRadio"] [role="radiogroup"] label:has(input:checked) {{
            background-color: #FCF8F2 !important;
            border-color: #E9DED0 !important;
            box-shadow: 0 2px 6px rgba(147, 79, 34, 0.04) !important;
        }}

        [data-testid="stSidebar"] [data-testid="stRadio"] [role="radiogroup"] label:has(input:checked) p {{
            color: #934F22 !important;
            font-weight: 600 !important;
        }}

        [data-testid="stSidebar"] [data-testid="stRadio"] [role="radiogroup"] label > div:first-child {{
            display: none !important;
        }}

        [data-testid="stSidebar"] [data-testid="stSelectbox"] div[data-baseweb="select"] > div {{
            background-color: #FCF8F2 !important;
            border: 1px solid #E9DED0 !important;
            border-radius: 10px !important;
        }}

        /* Login Page custom styling */
        .login-card-anchor {{
            display: none;
        }}
        
        .stApp:has(.login-card-anchor) .page-header {{
            display: none !important;
        }}
        
        /* Set page background to warm cream */
        .stApp:has(.login-card-anchor),
        .stApp:has(.login-card-anchor) [data-testid="stAppViewContainer"] {{
            background-color: {c["bg"]} !important;
        }}
        
        /* Make outer block transparent on login page (target ones without login-card-marker) */
        .stApp:has(.login-card-anchor) [data-testid="stVerticalBlockBorderWrapper"]:not(:has(.login-card-marker)) {{
            background-color: transparent !important;
            border: none !important;
            box-shadow: none !important;
            padding: 0 !important;
        }}
        
        /* Style the login container card */
        .stApp:has(.login-card-anchor) [data-testid="stVerticalBlockBorderWrapper"]:has(.login-card-marker) {{
            background-color: {c["card"]} !important;
            border-radius: 16px !important;
            box-shadow: 0 4px 24px rgba(61, 42, 32, 0.04) !important;
            border: 1px solid var(--paylens-border) !important;
            padding: 40px !important;
            max-width: 480px !important;
            margin: 0 auto !important;
        }}
        
        /* Make st.form transparent inside the card */
        .stApp:has(.login-card-anchor) [data-testid="stForm"] {{
            background-color: transparent !important;
            border: none !important;
            box-shadow: none !important;
            padding: 0 !important;
            max-width: 100% !important;
            margin: 0 auto !important;
        }}
        
        .login-card-marker {{
            display: none;
        }}
        
        /* Style input elements inside login form */
        .stApp:has(.login-card-anchor) [data-testid="stForm"] [data-testid="stTextInput"] input {{
            background-color: #FCF8F2 !important;
            border: 1px solid #E9DED0 !important;
            border-radius: 10px !important;
            color: #3D2A20 !important;
            padding: 12px 16px 12px 42px !important;
            height: 48px !important;
            font-size: 0.95rem !important;
        }}
        
        .stApp:has(.login-card-anchor) [data-testid="stForm"] [data-testid="stTextInput"] input:focus {{
            border-color: #934F22 !important;
            box-shadow: 0 0 0 2px rgba(147, 79, 34, 0.1) !important;
        }}
        
        .stApp:has(.login-card-anchor) [data-testid="stForm"] label {{
            color: #806F62 !important;
            font-weight: 600 !important;
            font-size: 0.9rem !important;
            margin-bottom: 6px !important;
        }}
        
        /* Username marker styles */
        div:has(> .username-input-marker) + div [data-testid="stTextInput"] input {{
            background-image: url('data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="%23934F22" viewBox="0 0 16 16"><path d="M3 14s-1 0-1-1 1-4 6-4 6 3 6 4-1 1-1 1zm5-6a3 3 0 1 0 0-6 3 3 0 0 0 0 6z"/></svg>') !important;
            background-repeat: no-repeat !important;
            background-position: 14px center !important;
        }}
        
        /* Password marker styles */
        div:has(> .password-input-marker) + div [data-testid="stTextInput"] input {{
            background-image: url('data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="%23934F22" viewBox="0 0 16 16"><path d="M8 1a2 2 0 0 1 2 2v4H6V3a2 2 0 0 1 2-2m3 6V3a3 3 0 0 0-6 0v4a2 2 0 0 0-2 2v5a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2M5 8h6a1 1 0 0 1 1 1v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V9a1 1 0 0 1 1-1"/></svg>') !important;
            background-repeat: no-repeat !important;
            background-position: 14px center !important;
        }}
        
        /* Segment switcher segment */
        div:has(> .tab-switcher-marker) + div {{
            background-color: #FCF8F2 !important;
            border-radius: 10px !important;
            padding: 4px !important;
            border: 1px solid #E9DED0 !important;
            margin-bottom: 24px !important;
        }}
        
        div:has(> .tab-switcher-marker) + div [data-testid="column"] {{
            background-color: transparent !important;
            border: none !important;
            box-shadow: none !important;
            padding: 0 !important;
        }}
        
        div:has(> .tab-switcher-marker) + div [data-testid="column"] button {{
            background-color: transparent !important;
            color: #806F62 !important;
            border: none !important;
            font-weight: 600 !important;
            border-radius: 8px !important;
            padding: 8px 16px !important;
            box-shadow: none !important;
            transition: all 0.2s ease !important;
            height: 38px !important;
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
        }}
        
        div:has(> .tab-switcher-marker) + div button[kind="secondary"] {{
            background-color: transparent !important;
            color: #806F62 !important;
            border: none !important;
            box-shadow: none !important;
        }}
        
        div:has(> .tab-switcher-marker) + div button[kind="primary"] {{
            background-color: #FFFDF9 !important;
            color: #934F22 !important;
            box-shadow: 0 2px 8px rgba(147, 79, 34, 0.08) !important;
            border: 1px solid #E9DED0 !important;
        }}
        
        /* Remember row custom alignment styling */
        div:has(> .remember-row-marker) + div {{
            background-color: transparent !important;
            border: none !important;
            box-shadow: none !important;
            padding: 0 !important;
            margin-top: 10px !important;
            margin-bottom: 16px !important;
        }}
        
        div:has(> .remember-row-marker) + div [data-testid="column"] {{
            background-color: transparent !important;
            border: none !important;
            box-shadow: none !important;
            padding: 0 !important;
        }}
        
        div:has(> .remember-row-marker) + div [data-testid="column"] [data-testid="stCheckbox"] label {{
            color: #806F62 !important;
            font-size: 0.85rem !important;
        }}
        
        /* Form submit button */
        .stApp:has(.login-card-anchor) [data-testid="stFormSubmitButton"] button {{
            background-color: #934F22 !important;
            color: #FFFFFF !important;
            border-radius: 10px !important;
            padding: 12px 24px !important;
            font-weight: 600 !important;
            border: none !important;
            height: 48px !important;
            transition: all 0.2s ease !important;
            width: 100% !important;
            font-size: 1rem !important;
            box-shadow: 0 4px 12px rgba(147, 79, 34, 0.15) !important;
        }}
        
        .stApp:has(.login-card-anchor) [data-testid="stFormSubmitButton"] button:hover {{
            background-color: #7E3F18 !important;
            box-shadow: 0 6px 16px rgba(147, 79, 34, 0.2) !important;
        }}
        .stApp:has(.login-card-anchor) [data-testid="stFormSubmitButton"] button:active {{
            background-color: #6B3310 !important;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_top_header():
    col_search, col_profile = st.columns([1, 1])
    with col_search:
        st.markdown('<div class="global-search-marker"></div>', unsafe_allow_html=True)
        st.text_input("Search", placeholder="Search transactions, insights, accounts...", label_visibility="collapsed", key="global_search")
    with col_profile:
        role_label = "Banker" if st.session_state.role == "banker" else "Client User"
        col_prof_text, col_prof_logout = st.columns([4, 1])
        with col_prof_text:
            st.markdown(
                f"""
                <div style="display: flex; align-items: center; justify-content: flex-end; gap: 16px; margin-top: 4px;">
                    <div style="display: flex; gap: 12px; margin-right: 8px;">
                        <span style="cursor: pointer; font-size: 1.15rem; color: #806F62;" title="Notifications">🔔</span>
                        <span style="cursor: pointer; font-size: 1.15rem; color: #806F62;" title="Settings">⚙️</span>
                    </div>
                    <div style="display: flex; align-items: center; gap: 8px;">
                        <div class="user-avatar-circle" style="width: 32px; height: 32px; border-radius: 50%; background-color: #934F22; color: #FFFFFF; display: flex; align-items: center; justify-content: center; font-weight: 600; font-size: 0.9rem;">
                            {st.session_state.user_id[:2].upper() if st.session_state.user_id else "U"}
                        </div>
                        <div style="text-align: left; line-height: 1.2;">
                            <div style="font-size: 0.85rem; font-weight: 600; color: #33241B;">{st.session_state.user_id}</div>
                            <div style="font-size: 0.75rem; color: #806F62;">{role_label}</div>
                        </div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True
            )
        with col_prof_logout:
            if st.button("Logout", key="btn_header_logout", use_container_width=True):
                st.session_state.logged_in = False
                st.session_state.user_id = None
                st.session_state.role = None
                st.session_state.messages = []
                st.session_state.chat_user_id = None
                st.rerun()


def render_top_overview_cards(user_id, credit, fraud_df, subs_df, language="en"):
    # Calculate stats
    score = credit["score"] if credit else 300
    computed_at = credit["computed_at"] if credit else "N/A"
    
    fraud_count = len(fraud_df)
    subs_count = len(subs_df)
    subs_total = subs_df["avg_amount"].sum() if not subs_df.empty else 0.0
    
    # Rating label for circle
    if score >= 750:
        rating = "EXCELLENT"
    elif score >= 650:
        rating = "GOOD"
    elif score >= 550:
        rating = "FAIR"
    else:
        rating = "POOR"
        
    percentage = (score - 300) / 600.0
    stroke_offset = 314 - (314 * percentage)
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        # Credit Score Card with Circular SVG Progress Ring
        st.markdown(
            f"""
            <div class="section-card" style="height: 100%; display: flex; flex-direction: column; justify-content: space-between; align-items: center; text-align: center; padding: 20px !important;">
                <div style="font-size: 0.75rem; font-weight: 700; color: #806F62; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 12px; align-self: flex-start;">Credit Score</div>
                <div class="circular-progress-container" style="position: relative; width: 120px; height: 120px; display: flex; align-items: center; justify-content: center; margin-bottom: 12px;">
                    <svg width="120" height="120" viewBox="0 0 120 120" style="position: absolute; top: 0; left: 0;">
                        <circle cx="60" cy="60" r="50" stroke="#FCF8F2" stroke-width="8" fill="transparent" />
                        <circle cx="60" cy="60" r="50" stroke="#934F22" stroke-width="8" fill="transparent" 
                                stroke-dasharray="314" stroke-dashoffset="{stroke_offset:.1f}" stroke-linecap="round" transform="rotate(-90 60 60)" />
                    </svg>
                    <div style="z-index: 10;">
                        <div style="font-size: 1.85rem; font-weight: 700; color: #33241B; line-height: 1.1;">{score:.0f}</div>
                        <div style="font-size: 0.65rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; color: #806F62; margin-top: 2px;">{rating}</div>
                    </div>
                </div>
                <div style="font-size: 0.75rem; color: #806F62;">Computed {computed_at}</div>
            </div>
            """,
            unsafe_allow_html=True
        )
        
    with col2:
        # Fraud Alerts Card
        st.markdown(
            f"""
            <div class="section-card" style="height: 100%; display: flex; flex-direction: column; justify-content: space-between; padding: 20px !important;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                    <div style="font-size: 0.75rem; font-weight: 700; color: #806F62; text-transform: uppercase; letter-spacing: 0.05em;">Fraud Alerts</div>
                    <div style="color: #B33939; font-size: 1.1rem;">🛡️</div>
                </div>
                <div style="margin: 20px 0;">
                    <div style="font-size: 2.5rem; font-weight: 700; color: #33241B; line-height: 1;">{fraud_count}</div>
                    <div style="margin-top: 10px;">
                        <span class="status-badge" style="background: rgba(179, 57, 57, 0.05); color: #B33939; border: 1px solid rgba(179, 57, 57, 0.15); font-size: 0.75rem; font-weight: 600; padding: 2px 8px; border-radius: 4px;">
                            {"⚠️ Active Attention" if fraud_count > 0 else "✅ System Clean"}
                        </span>
                    </div>
                </div>
                <div style="font-size: 0.75rem; color: #806F62;">Flags detected by rule engine</div>
            </div>
            """,
            unsafe_allow_html=True
        )
        
    with col3:
        # Active Subs Card
        st.markdown(
            f"""
            <div class="section-card" style="height: 100%; display: flex; flex-direction: column; justify-content: space-between; padding: 20px !important;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                    <div style="font-size: 0.75rem; font-weight: 700; color: #806F62; text-transform: uppercase; letter-spacing: 0.05em;">Active Subs</div>
                    <div style="color: #4A7C59; font-size: 1.1rem;">💳</div>
                </div>
                <div style="margin: 20px 0;">
                    <div style="font-size: 2.5rem; font-weight: 700; color: #33241B; line-height: 1;">{subs_count}</div>
                    <div style="font-size: 0.95rem; font-weight: 600; color: #934F22; margin-top: 4px;">₹{subs_total:,.2f} / mo</div>
                </div>
                <div style="font-size: 0.75rem; color: #806F62;">Recurring Autopays detected</div>
            </div>
            """,
            unsafe_allow_html=True
        )


def render_credit_score_details(credit: dict | None, language: str = "en"):
    open_section_card("Credit Score Insights", "Mathematical component breakdown")
    if not credit:
        st.info("No credit score computed for this user yet.")
        close_section_card()
        return

    st.markdown(
        progress_bar_html("Income Regularity", credit["income_regularity"], f"{credit['income_regularity'] * 100:.0f}%")
        + progress_bar_html("Expense Ratio", credit["expense_ratio"], f"{credit['expense_ratio'] * 100:.0f}%")
        + progress_bar_html("Volatility Index", credit["volatility"], f"{credit['volatility']:.2f}v"),
        unsafe_allow_html=True,
    )

    income_reg = credit["income_regularity"]
    expense_score = credit["expense_ratio"]
    volatility_score = credit["volatility"]

    income_weighted = income_reg * 0.45
    expense_weighted = expense_score * 0.30
    volatility_weighted = volatility_score * 0.25
    weighted_sum = income_weighted + expense_weighted + volatility_weighted
    score_contrib = weighted_sum * 600
    final_computed = 300 + score_contrib
    final_score = round(final_computed)

    loc = CREDIT_SCORE_EXPLANATION_LOCALIZATION.get(language, CREDIT_SCORE_EXPLANATION_LOCALIZATION["en"])

    with st.expander(loc["expander_title"]):
        st.markdown(f"**{loc['formula_title']}**")
        st.markdown(
            f"""
            ```text
            Score = 300 + (Income Regularity × 0.45 + Expense Ratio × 0.30 + Volatility × 0.25) × 600
            = 300 + ({fmt_component(income_reg)} × 0.45 + {fmt_component(expense_score)} × 0.30 + {fmt_component(volatility_score)} × 0.25) × 600
            = 300 + ({fmt_weighted(income_weighted)} + {fmt_weighted(expense_weighted)} + {fmt_weighted(volatility_weighted)}) × 600
            = 300 + {score_contrib:.2f} = {final_score}
            ```
            """,
            unsafe_allow_html=True
        )
        st.markdown(
            f"""
            - **{loc['income_reg_label']} ({income_reg:.2f}/1.0):** {loc['income_reg_desc']}
            - **{loc['expense_ratio_label']} ({expense_score:.2f}/1.0):** {loc['expense_ratio_desc']}
            - **{loc['volatility_label']} ({volatility_score:.2f}/1.0):** {loc['volatility_desc']}
            """
        )

    close_section_card()


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


def progress_bar_html(label: str, value: float, display_val: str = None) -> str:
    pct = min(max(value, 0.0), 1.0)
    disp = display_val if display_val is not None else f"{value:.2f}"
    return f"""
    <div class="progress-item">
        <div class="progress-label" style="display: flex; justify-content: space-between; font-size: 0.9rem; font-weight: 500; color: #33241B; margin-bottom: 6px;">
            <span>{label}</span>
            <span style="font-weight: 600; color: #934F22;">{disp}</span>
        </div>
        <div class="progress-track" style="height: 6px; background: #E9DED0; border-radius: 999px; overflow: hidden; margin-bottom: 16px;">
            <div class="progress-fill" style="height: 100%; width: {pct * 100:.1f}%; background: #934F22; border-radius: 999px; transition: width 0.3s ease;"></div>
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
        "SELECT user_id, name, monthly_income_estimate FROM users WHERE role = 'user' ORDER BY name"
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
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False
    if "user_id" not in st.session_state:
        st.session_state.user_id = None
    if "role" not in st.session_state:
        st.session_state.role = None
    if "txn_limit" not in st.session_state:
        st.session_state.txn_limit = 50


def reset_chat_if_user_changed(user_id: str):
    if st.session_state.chat_user_id != user_id:
        st.session_state.messages = []
        st.session_state.chat_user_id = user_id


CREDIT_SCORE_EXPLANATION_LOCALIZATION = {
    "en": {
        "expander_title": "How is this score calculated?",
        "formula_title": "Mathematical Breakdown",
        "income_reg_label": "Income Regularity",
        "expense_ratio_label": "Expense Ratio",
        "volatility_label": "Volatility",
        "income_reg_desc": "Your income arrives at consistent intervals and amounts — this is the strongest factor in your score (45% weight).",
        "expense_ratio_desc": "You're spending significantly less than you earn — a low score here usually means overspending relative to income, but a very low number can also reflect limited transaction history.",
        "volatility_desc": "Your month-to-month cash flow is highly variable — lower stability here reduces your score.",
    },
    "hi": {
        "expander_title": "यह स्कोर कैसे गिना जाता है?",
        "formula_title": "गणितीय विश्लेषण (Mathematical Breakdown)",
        "income_reg_label": "आय की नियमितता (Income Regularity)",
        "expense_ratio_label": "व्यय अनुपात (Expense Ratio)",
        "volatility_label": "उतार-चढ़ाव (Volatility)",
        "income_reg_desc": "आपकी आय लगातार अंतराल और मात्रा में आती है — यह आपके स्कोर में सबसे मजबूत कारक है (45% भार)।",
        "expense_ratio_desc": "आप अपनी कमाई से काफी कम खर्च कर रहे हैं — यहाँ कम स्कोर का मतलब आमतौर पर आय के सापेक्ष अधिक खर्च होता है, लेकिन बहुत कम संख्या सीमित लेनदेन इतिहास को भी दर्शा सकती है।",
        "volatility_desc": "आपका महीने-दर-महीने का कैश फ्लो अत्यधिक परिवर्तनशील है — यहाँ कम स्थिरता आपके स्कोर को कम करती है।",
    },
    "ta": {
        "expander_title": "இந்த மதிப்பெண் எவ்வாறு கணக்கிடப்படுகிறது?",
        "formula_title": "கணித முறிவு (Mathematical Breakdown)",
        "income_reg_label": "வருமான ஒழுங்குமுறை (Income Regularity)",
        "expense_ratio_label": "செலவு விகிதம் (Expense Ratio)",
        "volatility_label": "பணப்புழக்க ஏற்ற இறக்கம் (Volatility)",
        "income_reg_desc": "உங்கள் வருமானம் சீரான இடைவெளிகளிலும் அளவுகளிலும் வருகிறது — இது உங்கள் மதிப்பெண்ணில் வலுவான காரணியாகும் (45% முக்கியத்துவம்).",
        "expense_ratio_desc": "நீங்கள் சம்பாதிப்பதை விட கணிசமாகக் குறைவாகச் செலவிடுகிறீர்கள் — இதில் குறைவான மதிப்பெண் என்பது பொதுவாக வருமானத்தை விட அதிக செலவைக் குறிக்கும், ஆனால் மிகக் குறைந்த எண் குறைந்த பரிவர்த்தனை வரலாற்றையும் பிரதிபலிக்கும்.",
        "volatility_desc": "உங்கள் மாதாந்திர பணப்புழக்கம் மிகவும் மாறுபடக்கூடியது — இங்கு குறைந்த நிலைத்தன்மை உங்கள் மதிப்பெண்ணைக் குறைக்கும்.",
    }
}


def fmt_component(v: float) -> str:
    if round(v, 2) == round(v, 3):
        return f"{v:.2f}"
    return f"{v:.3f}"


def fmt_weighted(v: float) -> str:
    s = f"{v:.5f}"
    while s.endswith("0") and len(s.split(".")[1]) > 2:
        s = s[:-1]
    return s


def render_credit_score(credit: dict | None, language: str = "en"):
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

    # Surfacing live math breakdown and localized explanation
    income_reg = credit["income_regularity"]
    expense_score = credit["expense_ratio"]
    volatility_score = credit["volatility"]

    income_weighted = income_reg * 0.45
    expense_weighted = expense_score * 0.30
    volatility_weighted = volatility_score * 0.25
    weighted_sum = income_weighted + expense_weighted + volatility_weighted
    score_contrib = weighted_sum * 600
    final_computed = 300 + score_contrib
    final_score = round(final_computed)

    loc = CREDIT_SCORE_EXPLANATION_LOCALIZATION.get(language, CREDIT_SCORE_EXPLANATION_LOCALIZATION["en"])

    with st.expander(loc["expander_title"]):
        st.markdown(f"**{loc['formula_title']}**")
        st.markdown(
            f"""
            ```text
            Score = 300 + (Income Regularity × 0.45 + Expense Ratio × 0.30 + Volatility × 0.25) × 600
            = 300 + ({fmt_component(income_reg)} × 0.45 + {fmt_component(expense_score)} × 0.30 + {fmt_component(volatility_score)} × 0.25) × 600
            = 300 + ({fmt_weighted(income_weighted)} + {fmt_weighted(expense_weighted)} + {fmt_weighted(volatility_weighted)}) × 600
            = 300 + {score_contrib:.2f} = {final_score}
            ```
            """,
            unsafe_allow_html=True
        )
        st.markdown(
            f"""
            - **{loc['income_reg_label']} ({income_reg:.2f}/1.0):** {loc['income_reg_desc']}
            - **{loc['expense_ratio_label']} ({expense_score:.2f}/1.0):** {loc['expense_ratio_desc']}
            - **{loc['volatility_label']} ({volatility_score:.2f}/1.0):** {loc['volatility_desc']}
            """
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


LOAN_LOCALIZATION = {
    "en": {
        "apply_title": "Apply for a Micro-Loan",
        "apply_subtitle": "Request cash-flow based financing based on your alternate credit profile",
        "current_score_label": "Your Current Credit Score:",
        "amount_label": "Amount Requested (₹)",
        "purpose_label": "Purpose of Loan",
        "purposes": {
            "Business Expansion": "Business Expansion",
            "Personal / Household": "Personal / Household",
            "Medical / Emergency": "Medical / Emergency",
            "Other": "Other"
        },
        "submit_btn": "Submit Loan Application",
        "success_msg": "Loan application submitted successfully! It is now pending review.",
        "history_title": "Your Loan Applications",
        "history_subtitle": "Status and history of submitted applications",
        "no_apps": "You have not submitted any loan applications yet.",
        "headers": {
            "applied_at": "Applied Date",
            "amount_requested": "Requested (₹)",
            "purpose": "Purpose",
            "status": "Status",
            "reviewed_by": "Reviewed By",
            "reviewed_at": "Reviewed Date",
            "decision_notes": "Decision Notes"
        },
        "status_labels": {
            "pending": "⏳ Pending",
            "approved": "✅ Approved",
            "rejected": "❌ Rejected"
        }
    },
    "hi": {
        "apply_title": "माइक्रो-लोन (ऋण) के लिए आवेदन करें",
        "apply_subtitle": "अपने वैकल्पिक क्रेडिट प्रोफाइल के आधार पर कैश-फ्लो आधारित वित्तपोषण का अनुरोध करें",
        "current_score_label": "आपका वर्तमान क्रेडिट स्कोर:",
        "amount_label": "अनुरोधित राशि (₹)",
        "purpose_label": "ऋण का उद्देश्य",
        "purposes": {
            "Business Expansion": "व्यवसाय विस्तार (Business Expansion)",
            "Personal / Household": "व्यक्तिगत / घरेलू (Personal / Household)",
            "Medical / Emergency": "चिकित्सा / आपातकालीन (Medical / Emergency)",
            "Other": "अन्य (Other)"
        },
        "submit_btn": "ऋण आवेदन जमा करें",
        "success_msg": "ऋण आवेदन सफलतापूर्वक जमा हो गया! यह अब समीक्षा के लिए लंबित है।",
        "history_title": "आपके ऋण आवेदन",
        "history_subtitle": "जमा किए गए आवेदनों की स्थिति और इतिहास",
        "no_apps": "आपने अभी तक कोई ऋण आवेदन जमा नहीं किया है।",
        "headers": {
            "applied_at": "आवेदन तिथि",
            "amount_requested": "अनुरोधित राशि (₹)",
            "purpose": "उद्देश्य",
            "status": "स्थिति",
            "reviewed_by": "समीक्षक",
            "reviewed_at": "समीक्षा तिथि",
            "decision_notes": "निर्णय नोट्स"
        },
        "status_labels": {
            "pending": "⏳ लंबित",
            "approved": "✅ स्वीकृत",
            "rejected": "❌ अस्वीकृत"
        }
    },
    "ta": {
        "apply_title": "நுண்கடன் விண்ணப்பம்",
        "apply_subtitle": "உங்கள் மாற்று கிரெடிட் சுயவிவரத்தின் அடிப்படையில் பணப்புழக்க நிதி கோரவும்",
        "current_score_label": "உங்களது தற்போதைய கிரெடிட் மதிப்பெண்:",
        "amount_label": "கோரப்பட்ட தொகை (₹)",
        "purpose_label": "கடனின் நோக்கம்",
        "purposes": {
            "Business Expansion": "வணிக விரிவாக்கம் (Business Expansion)",
            "Personal / Household": "தனிப்பட்ட / குடும்பம் (Personal / Household)",
            "Medical / Emergency": "மருத்துவ / அவசரநிலை (Medical / Emergency)",
            "Other": "இதர (Other)"
        },
        "submit_btn": "கடன் விண்ணப்பத்தைச் சமர்ப்பிக்கவும்",
        "success_msg": "கடன் விண்ணப்பம் வெற்றிகரமாகச் சமர்ப்பிக்கப்பட்டது! இது இப்போது மதிப்பாய்வில் உள்ளது.",
        "history_title": "உங்கள் கடன் விண்ணப்பங்கள்",
        "history_subtitle": "சமர்ப்பிக்கப்பட்ட விண்ணப்பங்களின் நிலை மற்றும் வரலாறு",
        "no_apps": "நீங்கள் இன்னும் கடன் விண்ணப்பங்கள் எதையும் சமர்ப்பிக்கவில்லை.",
        "headers": {
            "applied_at": "விண்ணப்பித்த தேதி",
            "amount_requested": "கோரப்பட்ட தொகை (₹)",
            "purpose": "நோக்கம்",
            "status": "நிலை",
            "reviewed_by": "மதிப்பாய்வு செய்தவர்",
            "reviewed_at": "மதிப்பாய்வு தேதி",
            "decision_notes": "முடிவு குறிப்புகள்"
        },
        "status_labels": {
            "pending": "⏳ நிலுவையில் உள்ளது",
            "approved": "✅ அங்கீகரிக்கப்பட்டது",
            "rejected": "❌ நிராகரிக்கப்பட்டது"
        }
    }
}


def render_loan_application_section(conn, user_id: str, language: str = "en"):
    loc = LOAN_LOCALIZATION.get(language, LOAN_LOCALIZATION["en"])
    
    # 1. Fetch user's current score
    credit_row = conn.execute(
        "SELECT score FROM credit_scores WHERE user_id = ? ORDER BY computed_at DESC LIMIT 1",
        (user_id,)
    ).fetchone()
    current_score = credit_row[0] if credit_row else 300
    
    open_section_card(loc["apply_title"], loc["apply_subtitle"])
    
    st.markdown(
        f"""
        <div style="background-color: rgba(74, 124, 89, 0.04); border: 1px solid rgba(74, 124, 89, 0.2); padding: 12px; border-radius: 10px; margin-bottom: 20px;">
            <p style="margin: 0; color: #4A7C59; font-weight: 500; font-size: 0.95rem;">
                📈 {loc['current_score_label']} <strong style="font-size: 1.15rem;">{current_score:.0f}</strong> (Range 300-900)
            </p>
        </div>
        """,
        unsafe_allow_html=True
    )
    
    with st.form(key=f"loan_apply_form_{user_id}"):
        amount = st.number_input(loc["amount_label"], min_value=1000.0, max_value=500000.0, step=5000.0, value=25000.0)
        
        purpose_options = list(loc["purposes"].keys())
        selected_purpose_label = st.selectbox(loc["purpose_label"], purpose_options)
        
        submitted = st.form_submit_button(loc["submit_btn"], use_container_width=True)
        if submitted:
            try:
                conn.execute(
                    """
                    INSERT INTO loan_applications (user_id, amount_requested, purpose, status)
                    VALUES (?, ?, ?, 'pending')
                    """,
                    (user_id, amount, selected_purpose_label)
                )
                conn.commit()
                st.success(loc["success_msg"])
                st.rerun()
            except Exception as e:
                st.error(f"Error submitting application: {e}")
                
    st.markdown("---")
    st.markdown(f"#### {loc['history_title']}")
    
    # Fetch user's applications
    apps_df = pd.read_sql_query(
        """
        SELECT applied_at, amount_requested, purpose, status, reviewed_by, reviewed_at, decision_notes
        FROM loan_applications
        WHERE user_id = ?
        ORDER BY applied_at DESC
        """,
        conn,
        params=(user_id,)
    )
    
    if apps_df.empty:
        st.info(loc["no_apps"])
    else:
        # Localize status badges
        apps_df["status"] = apps_df["status"].apply(lambda s: loc["status_labels"].get(s, s))
        
        # Rename columns to localized headers
        renamed_df = apps_df.rename(columns=loc["headers"])
        st.dataframe(
            renamed_df,
            hide_index=True,
            use_container_width=True
        )
        
    close_section_card()


TXN_LOCALIZATION = {
    "en": {
        "title": "My Transactions",
        "subtitle": "Recent credit and debit transaction logs",
        "load_more": "Load More Transactions",
        "headers": {
            "timestamp": "Date & Time",
            "amount": "Amount (₹)",
            "direction": "Type",
            "counterparty_name": "Counterparty Name",
            "counterparty_vpa": "UPI ID / VPA",
            "category": "Category"
        },
        "no_txns": "No transaction records found."
    },
    "hi": {
        "title": "मेरे लेन-देने",
        "subtitle": "हालिया क्रेडिट और डेबिट लेन-देन लॉग",
        "load_more": "अधिक लेन-देन लोड करें",
        "headers": {
            "timestamp": "दिनांक और समय",
            "amount": "राशि (₹)",
            "direction": "प्रकार",
            "counterparty_name": "प्राप्तकर्ता/भेजनेवाला",
            "counterparty_vpa": "UPI आईडी / VPA",
            "category": "श्रेणी"
        },
        "no_txns": "कोई लेन-देन रिकॉर्ड नहीं मिला।"
    },
    "ta": {
        "title": "எனது பரிவர்த்தனைகள்",
        "subtitle": "சமீபத்திய கிரெடிட் மற்றும் டெபிட் பரிவர்த்தனை பதிவுகள்",
        "load_more": "கூடுதல் பரிவர்த்தனைகளை ஏற்றுக",
        "headers": {
            "timestamp": "தேதி & நேரம்",
            "amount": "தொகை (₹)",
            "direction": "வகை",
            "counterparty_name": "பெறுநர் பெயர்",
            "counterparty_vpa": "UPI ஐடி / VPA",
            "category": "பிரிவு"
        },
        "no_txns": "பரிவர்த்தனை பதிவுகள் எதுவும் இல்லை."
    }
}


def load_user_transactions(conn, user_id: str, limit: int) -> pd.DataFrame:
    return pd.read_sql_query(
        """
        SELECT timestamp, amount, direction, counterparty_name, counterparty_vpa, category
        FROM transactions
        WHERE user_id = ?
        ORDER BY timestamp DESC
        LIMIT ?
        """,
        conn,
        params=(user_id, limit)
    )


def render_user_transactions(conn, user_id: str, language: str = "en"):
    loc = TXN_LOCALIZATION.get(language, TXN_LOCALIZATION["en"])
    
    if "txn_limit" not in st.session_state:
        st.session_state.txn_limit = 50
        
    limit = st.session_state.txn_limit
    df = load_user_transactions(conn, user_id, limit)
    
    open_section_card(loc["title"], loc["subtitle"])
    if df.empty:
        st.info(loc["no_txns"])
    else:
        # Style direction
        df["direction"] = df["direction"].apply(lambda d: "🟢 Credit" if d == "credit" else "🔴 Debit")
        
        # Format Amount
        df["amount"] = df["amount"].apply(lambda a: f"₹{a:,.2f}")
        
        st.dataframe(
            df.rename(columns=loc["headers"]),
            hide_index=True,
            use_container_width=True
        )
        
        # Check total count
        total_count = conn.execute(
            "SELECT COUNT(*) FROM transactions WHERE user_id = ?",
            (user_id,)
        ).fetchone()[0]
        
        if total_count > limit:
            if st.button(loc["load_more"], use_container_width=True):
                st.session_state.txn_limit += 50
                st.rerun()
                
    close_section_card()


def render_login_page(conn):
    st.markdown('<div class="login-card-anchor"></div>', unsafe_allow_html=True)
    
    if "login_mode" not in st.session_state:
        st.session_state.login_mode = "user"

    st.markdown(
        """
        <div style="max-width: 480px; margin: 60px auto 10px auto; text-align: center;">
            <div style="font-size: 3.25rem; font-weight: 700; color: #8C5A3C; margin-bottom: 2px; letter-spacing: -0.03em; font-family: 'Plus Jakarta Sans', sans-serif;">PayLens</div>
            <p style="color: #8C8273; font-size: 0.95rem; margin-bottom: 30px; letter-spacing: 0.05em; font-weight: 500;">Fintech Operator Platform</p>
        </div>
        """,
        unsafe_allow_html=True
    )
    
    is_client = st.session_state.login_mode == "user"
    
    with st.container():
        st.markdown('<div class="login-card-marker"></div>', unsafe_allow_html=True)
        
        # Segment switcher (placed inside the container, outside the form, so st.button works!)
        st.markdown('<div class="tab-switcher-marker"></div>', unsafe_allow_html=True)
        col_tab1, col_tab2 = st.columns(2)
        with col_tab1:
            if st.button("User", use_container_width=True, type="primary" if st.session_state.login_mode == "user" else "secondary", key="btn_login_tab_user"):
                st.session_state.login_mode = "user"
                st.rerun()
        with col_tab2:
            if st.button("Banker", use_container_width=True, type="primary" if st.session_state.login_mode == "banker" else "secondary", key="btn_login_tab_banker"):
                st.session_state.login_mode = "banker"
                st.rerun()
                
        # Borderless form for security/validation inputs
        with st.form("login_form", border=False):
            # Operator ID input
            st.markdown('<div class="username-input-marker"></div>', unsafe_allow_html=True)
            username = st.text_input("Operator ID" if is_client else "Banker ID", placeholder="Enter your ID")
            
            # Passcode input
            st.markdown('<div class="password-input-marker"></div>', unsafe_allow_html=True)
            password = st.text_input("Passcode", type="password", placeholder="••••••••")
            
            # Remember row
            st.markdown('<div class="remember-row-marker"></div>', unsafe_allow_html=True)
            col_rem, col_rec = st.columns(2)
            with col_rem:
                remember_device = st.checkbox("Remember device", value=False)
            with col_rec:
                st.markdown(
                    '<p style="text-align: right; margin-top: 6px; margin-bottom: 0px;">'
                    '<a href="#" style="color: #8C5A3C; text-decoration: none; font-size: 0.85rem; font-weight: 600;">Recovery</a>'
                    '</p>',
                    unsafe_allow_html=True
                )
                
            submitted = st.form_submit_button("Authenticate Session \u2192", use_container_width=True)
            if submitted:
                if not username or not password:
                    st.error("Please enter both ID and passcode.")
                else:
                    res = login_user(conn, username, password)
                    if res:
                        user_id, role = res
                        if is_client and role != "user":
                            st.error("This account belongs to a Banker. Please authenticate through the Banker Portal.")
                        elif not is_client and role != "banker":
                            st.error("This account belongs to a Client. Please authenticate through the User Portal.")
                        else:
                            st.session_state.logged_in = True
                            st.session_state.user_id = user_id
                            st.session_state.role = role
                            st.session_state.chat_user_id = user_id
                            st.session_state.messages = []
                            st.success("Authenticated successfully!")
                            st.rerun()
                    else:
                        st.error("Invalid credentials.")

    st.markdown(
        '<p style="text-align: center; color: #8C8273; font-size: 0.85rem; margin-top: 40px; font-weight: 500;">'
        '<span style="margin-right: 8px; vertical-align: middle;">🛡️</span>End-to-End Encrypted Connection'
        '</p>',
        unsafe_allow_html=True
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


def render_banker_dashboard(conn):
    st.markdown(
        """
        <div style="background-color: rgba(179, 57, 57, 0.04); border: 1px solid rgba(179, 57, 57, 0.15); padding: 18px; border-radius: 12px; margin-bottom: 24px;">
            <h4 style="color: #B33939; margin: 0 0 8px 0; font-weight: 700; letter-spacing: -0.01em;">🔒 CONFIDENTIAL — BANKER PORTAL</h4>
            <p style="color: #3D2A20; margin: 0; font-size: 0.95rem; line-height: 1.5;">
                Authorized risk audit view. Review applicant details and log credit decisions.
            </p>
        </div>
        <div class="page-heading">
            <h2 class="page-title">Banker Dashboard</h2>
            <p class="page-description">Review cash-flow based loan requests from applicants and analyze volatility.</p>
        </div>
        """,
        unsafe_allow_html=True
    )

    # 1. Pending Queue
    open_section_card("Pending Loan Applications Queue", "Review cash-flow based loan requests from applicants")

    pending_apps = pd.read_sql_query(
        """
        SELECT la.application_id, u.name, la.user_id, la.amount_requested, la.purpose, la.applied_at
        FROM loan_applications la
        JOIN users u ON la.user_id = u.user_id
        WHERE la.status = 'pending'
        ORDER BY la.applied_at ASC
        """,
        conn
    )

    auditing_app_id = None
    selected_user_id = None

    if pending_apps.empty:
        st.success("🎉 No pending loan applications to review.")
        close_section_card()
    else:
        st.dataframe(
            pending_apps.rename(columns={
                "name": "Applicant Name",
                "user_id": "User ID",
                "amount_requested": "Amount Requested (₹)",
                "purpose": "Purpose",
                "applied_at": "Applied Date"
            }).drop(columns=["application_id"]),
            hide_index=True,
            use_container_width=True
        )

        app_labels = {
            f"{row['name']} ({row['user_id']}) - ₹{row['amount_requested']:,.0f} ({row['purpose']})": (row['application_id'], row['user_id'])
            for _, row in pending_apps.iterrows()
        }
        selected_app_label = st.selectbox("Select Pending Application to Audit", list(app_labels.keys()), key="pending_app_select")
        auditing_app_id, selected_user_id = app_labels[selected_app_label]
        reset_chat_if_user_changed(selected_user_id)
        close_section_card()

    # If an application is selected, render their full auditing profile
    if selected_user_id:
        lang_options = {"English": "en", "Hindi": "hi", "Tamil": "ta"}
        selected_lang_name = st.selectbox("Select language for audit view", list(lang_options.keys()), key="banker_audit_lang")
        selected_lang = lang_options[selected_lang_name]

        selected_user = conn.execute("SELECT name, monthly_income_estimate FROM users WHERE user_id = ?", (selected_user_id,)).fetchone()
        if selected_user:
            st.markdown(
                f'<p class="user-meta"><strong>Auditing Applicant: {selected_user[0]}</strong> · '
                f'Declared income ₹{selected_user[1]:,.0f}/mo</p>',
                unsafe_allow_html=True,
            )

        fraud_df = load_fraud_flags(conn, selected_user_id)
        subs_df = load_subscriptions(conn, selected_user_id)
        credit = load_credit_score(conn, selected_user_id)

        render_top_overview_cards(selected_user_id, credit, fraud_df, subs_df, language=selected_lang)
        st.markdown("<div style='height: 16px;'></div>", unsafe_allow_html=True)

        col_feed, col_score = st.columns([2, 1])
        with col_feed:
            render_financial_events(fraud_df, subs_df, conn, selected_user_id, language=selected_lang)
        with col_score:
            render_credit_score_details(credit, language=selected_lang)

        # Inflow & Gig-Work Volatility
        stats = calculate_income_stats(conn, selected_user_id)
        with col_feed:
            open_section_card("Inflow & Gig-Work Volatility", "Monthly credit analysis and income range")
            col_m1, col_m2, col_m3 = st.columns(3)
            with col_m1:
                st.metric("Average Monthly Inflow", f"₹{stats['avg']:,.2f}")
            with col_m2:
                st.metric("Minimum Monthly Inflow", f"₹{stats['min']:,.2f}")
            with col_m3:
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

        # Recent Transactions (Last 20)
        txns_df = pd.read_sql_query(
            """
            SELECT timestamp, amount, direction, counterparty_name, counterparty_vpa, category
            FROM transactions
            WHERE user_id = ?
            ORDER BY timestamp DESC
            LIMIT 20
            """,
            conn,
            params=(selected_user_id,)
        )
        with col_feed:
            open_section_card("Recent Transactions (Last 20)", "Applicant's recent UPI credit/debit transactions")
            if txns_df.empty:
                st.info("No transaction history found for this applicant.")
            else:
                st.dataframe(
                    txns_df.rename(columns={
                        "timestamp": "Timestamp",
                        "amount": "Amount (₹)",
                        "direction": "Direction",
                        "counterparty_name": "Counterparty Name",
                        "counterparty_vpa": "VPA",
                        "category": "Category"
                    }),
                    hide_index=True,
                    use_container_width=True
                )
            close_section_card()

        # Institutional Risk Auditing Metrics
        open_section_card("Risk Assessment Details", "Anomalies, trends, and systemic exposure")

        # Spending Trend
        trend_row = conn.execute(
            "SELECT income_trend_pct, spending_trend_pct, is_flagged FROM spending_trends WHERE user_id = ?",
            (selected_user_id,)
        ).fetchone()

        # Circular Transactions
        circular_flags = conn.execute(
            """
            SELECT counterparty_vpa, counterparty_name, debit_timestamp, debit_amount,
                   credit_timestamp, credit_amount, detected_at
            FROM income_authenticity_flags
            WHERE user_id = ?
            """,
            (selected_user_id,)
        ).fetchall()

        # Shared Risky counterparties
        shared_risk_flags = conn.execute(
            """
            SELECT DISTINCT t.counterparty_vpa, t.counterparty_name, src.unique_user_count, src.total_flag_count
            FROM transactions t
            JOIN shared_risk_counterparties src ON t.counterparty_vpa = src.counterparty_vpa
            WHERE t.user_id = ?
            """,
            (selected_user_id,)
        ).fetchall()

        audit_col1, audit_col2 = st.columns(2)
        with audit_col1:
            st.markdown("**Circular Transactions & Income Authenticity:**")
            if not circular_flags:
                st.success("✅ No circular transaction loops or self-funding patterns detected.")
            else:
                st.warning(f"⚠️ {len(circular_flags)} potential self-funding circular loops detected.")
                for row in circular_flags:
                    st.info(
                        f"**VPA**: `{row[0]}` ({row[1]})\n"
                        f"- Debit: ₹{row[3]:,.2f} on {row[2]}\n"
                        f"- Credit: ₹{row[5]:,.2f} on {row[4]}"
                    )
        with audit_col2:
            st.markdown("**Spending vs Income Trend (MoM):**")
            if trend_row:
                inc_trend, spd_trend, is_flagged = trend_row[0], trend_row[1], bool(trend_row[2])
                st.metric("Income Trend (MoM)", f"{'+' if inc_trend >= 0 else ''}{inc_trend:.1f}%")
                st.metric("Spending Trend (MoM)", f"{'+' if spd_trend >= 0 else ''}{spd_trend:.1f}%")
                if is_flagged:
                    st.error("🚨 Unsustainable Spending: Spending growth exceeds income growth rate.")
                else:
                    st.success("✅ Spending growth trend is sustainable relative to income.")
            else:
                st.info("No spending trend data available for this profile.")

        if shared_risk_flags:
            st.markdown("---")
            st.markdown("**Shared Risky Counterparties:**")
            st.error("🚨 Transactions found with counterparties flagged as risky across 3+ other users.")
            df_shared = pd.DataFrame([
                {"Risky VPA": r[0], "Name": r[1], "Flagged Users Count": r[2], "Total Fraud Flags": r[3]}
                for r in shared_risk_flags
            ])
            st.dataframe(df_shared, hide_index=True, use_container_width=True)

        close_section_card()

        # Active Complaints review
        complaints_df = load_complaints(conn, selected_user_id)
        if not complaints_df.empty:
            render_my_complaints(complaints_df, language=selected_lang)

        # Decision Panel
        if auditing_app_id is not None:
            open_section_card("Loan Decision Panel", "Approve or Reject the loan application based on applicant credit profile")

            app_info = pending_apps[pending_apps["application_id"] == auditing_app_id].iloc[0]
            st.markdown(
                f"""
                **Reviewing Loan Request:**
                - **Applicant:** {app_info['name']} (`{app_info['user_id']}`)
                - **Requested Amount:** ₹{app_info['amount_requested']:,.2f}
                - **Purpose:** {app_info['purpose']}
                - **Applied At:** {app_info['applied_at']}
                """
            )

            decision_notes = st.text_area("Decision Notes / Rationale", placeholder="Explain the rationale for approval or rejection...", key="banker_decision_notes")

            col_app, col_rej = st.columns(2)
            with col_app:
                if st.button("Approve Loan", use_container_width=True, type="primary", key="btn_approve"):
                    try:
                        conn.execute(
                            """
                            UPDATE loan_applications
                            SET status = 'approved',
                                reviewed_by = ?,
                                reviewed_at = datetime('now'),
                                decision_notes = ?
                            WHERE application_id = ?
                            """,
                            (st.session_state.user_id, decision_notes, auditing_app_id)
                        )
                        conn.commit()
                        st.success("Loan application APPROVED successfully!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error approving loan: {e}")

            with col_rej:
                if st.button("Reject Loan", use_container_width=True, key="btn_reject"):
                    try:
                        conn.execute(
                            """
                            UPDATE loan_applications
                            SET status = 'rejected',
                                reviewed_by = ?,
                                reviewed_at = datetime('now'),
                                decision_notes = ?
                            WHERE application_id = ?
                            """,
                            (st.session_state.user_id, decision_notes, auditing_app_id)
                        )
                        conn.commit()
                        st.warning("Loan application REJECTED successfully.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error rejecting loan: {e}")

            close_section_card()

        # Interactive Banker Audit Chatbot
        st.markdown("### Interactive Risk Inquiry")
        render_chat(conn, selected_user_id, language=selected_lang)

    # 2. Historical applications review log (always show at the bottom)
    history_apps = pd.read_sql_query(
        """
        SELECT u.name, la.amount_requested, la.purpose, la.applied_at, la.status, la.reviewed_by, la.reviewed_at, la.decision_notes
        FROM loan_applications la
        JOIN users u ON la.user_id = u.user_id
        WHERE la.status != 'pending'
        ORDER BY la.reviewed_at DESC
        """,
        conn
    )
    if not history_apps.empty:
        open_section_card("Reviewed Loan Applications History", "Transparent log of approved and rejected loan requests")
        st.dataframe(
            history_apps.rename(columns={
                "name": "Applicant Name",
                "amount_requested": "Amount (₹)",
                "purpose": "Purpose",
                "applied_at": "Applied Date",
                "status": "Decision",
                "reviewed_by": "Reviewed By",
                "reviewed_at": "Reviewed Date",
                "decision_notes": "Notes / Rationale"
            }),
            hide_index=True,
            use_container_width=True
        )
        close_section_card()


def main():
    st.set_page_config(
        page_title="PayLens",
        page_icon="💳",
        layout="wide",
    )
    inject_custom_css()

    init_session_state()
    conn = get_connection()

    # 1. Require login first
    if not st.session_state.logged_in:
        render_login_page(conn)
        st.stop()

    # 2. Render Premium Logged-in Top Header bar
    render_top_header()

    users = load_users(conn)
    if not users:
        st.error("No users found. Run `python main.py` first to generate the database.")
        return

    # 3. Route based on role
    if st.session_state.role == "banker":
        render_banker_dashboard(conn)
    else:
        # Client user dashboard (scoped to logged-in user_id only)
        user_id = st.session_state.user_id
        reset_chat_if_user_changed(user_id)

        # Navigation menu in sidebar
        st.sidebar.markdown(
            """
            <div style="padding: 10px 0 20px 0; text-align: center;">
                <h3 style="color: #3D2A20; margin: 0; font-weight: 700; letter-spacing: -0.02em;">PayLens</h3>
                <p style="color: #806F62; margin: 2px 0 0 0; font-size: 0.825rem;">Alternate Credit Engine</p>
                <div style="width: 48px; height: 3px; background: #934F22; margin: 10px auto 0 auto; border-radius: 999px;"></div>
            </div>
            """,
            unsafe_allow_html=True
        )

        NAV_LOCALIZATION = {
            "en": {
                "Home": "🏠 Home",
                "Transactions": "💳 Transactions",
                "Loans": "💰 Loans",
                "Chat": "💬 Chat Assistant"
            },
            "hi": {
                "Home": "🏠 होम (Home)",
                "Transactions": "💳 लेन-देन (Transactions)",
                "Loans": "💰 ऋण (Loans)",
                "Chat": "💬 चैट सहायक (Chat)"
            },
            "ta": {
                "Home": "🏠 முகப்பு (Home)",
                "Transactions": "💳 பரிவர்த்தனைகள் (Transactions)",
                "Loans": "💰 கடன்கள் (Loans)",
                "Chat": "💬 அரட்டை உதவியாளர் (Chat)"
            }
        }

        # Language selection in sidebar
        lang_options = {"English": "en", "Hindi": "hi", "Tamil": "ta"}
        selected_lang_name = st.sidebar.selectbox("Language / भाषा / மொழி", list(lang_options.keys()))
        selected_lang = lang_options.get(selected_lang_name, "en")

        loc_nav = NAV_LOCALIZATION.get(selected_lang, NAV_LOCALIZATION["en"])

        active_tab = st.sidebar.radio(
            "Navigation",
            options=list(loc_nav.keys()),
            format_func=lambda x: loc_nav[x],
            label_visibility="collapsed"
        )

        selected_user = next(u for u in users if u["user_id"] == user_id)
        
        st.markdown(
            f'<div style="background-color: #FFFDF9; border: 1px solid #E9DED0; padding: 20px; border-radius: 12px; margin-bottom: 24px; box-shadow: 0 4px 20px rgba(61, 42, 32, 0.02);">'
            f'<h2 style="margin: 0; font-weight: 700; color: #3D2A20; letter-spacing: -0.02em;">Welcome, {selected_user["name"]}</h2>'
            f'<p style="color: #806F62; margin: 6px 0 0 0; font-size: 0.95rem;">Estimated income: <strong>₹{selected_user["monthly_income_estimate"]:,.0f}/mo</strong> · ID: <code style="background-color:#FCF8F2; color:#934F22; padding: 2px 6px; border-radius: 4px; border:1px solid #E9DED0;">{user_id}</code></p>'
            f'</div>',
            unsafe_allow_html=True,
        )

        fraud_df = load_fraud_flags(conn, user_id)
        subs_df = load_subscriptions(conn, user_id)
        credit = load_credit_score(conn, user_id)

        # Tab Routing
        if active_tab == "Home":
            st.markdown(
                """
                <div class="page-heading">
                    <h2 class="page-title">Overview</h2>
                    <p class="page-description">Your high-level financial health indicators.</p>
                </div>
                """,
                unsafe_allow_html=True
            )
            render_top_overview_cards(user_id, credit, fraud_df, subs_df, language=selected_lang)
            st.markdown("<div style='height: 16px;'></div>", unsafe_allow_html=True)
            
            col_feed, col_score = st.columns([2, 1])
            with col_feed:
                render_financial_events(fraud_df, subs_df, conn, user_id, language=selected_lang)
            with col_score:
                render_credit_score_details(credit, language=selected_lang)

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

        elif active_tab == "Transactions":
            st.markdown(
                """
                <div class="page-heading">
                    <h2 class="page-title">Transactions</h2>
                    <p class="page-description">Comprehensive log of UPI transactions.</p>
                </div>
                """,
                unsafe_allow_html=True
            )
            render_user_transactions(conn, user_id, language=selected_lang)

        elif active_tab == "Loans":
            st.markdown(
                """
                <div class="page-heading">
                    <h2 class="page-title">Micro-Loans</h2>
                    <p class="page-description">Apply for financing and view previous application logs.</p>
                </div>
                """,
                unsafe_allow_html=True
            )
            render_loan_application_section(conn, user_id, language=selected_lang)

        elif active_tab == "Chat":
            st.markdown(
                """
                <div class="page-heading">
                    <h2 class="page-title">Chat Assistant</h2>
                    <p class="page-description">Ask queries about fraud alerts, subscriptions, or scores.</p>
                </div>
                """,
                unsafe_allow_html=True
            )
            render_chat(conn, user_id, language=selected_lang)


if __name__ == "__main__":
    main()