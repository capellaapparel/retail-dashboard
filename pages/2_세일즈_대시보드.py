# pages/2_세일즈_대시보드.py
import streamlit as st
import pandas as pd
from dateutil import parser

# ---------- UI ----------
st.set_page_config(page_title="세일즈 대시보드", layout="wide")
st.title("세일즈 대시보드")

# ---------- Style ----------
CARD_CSS = """
<style>
.card {border:1px solid #e9e9ef; border-radius:12px; padding:16px; margin-bottom:12px; background:#fff;}
.card .title {font-weight:700; font-size:1.05rem; margin-bottom:10px;}
.insight-item {margin:2px 0;}
</style>
"""
st.markdown(CARD_CSS, unsafe_allow_html=True)

def card(title=None):
    class _Card:
        def __enter__(self):
            st.markdown('<div class="card">', unsafe_allow_html=True)
            if title:
                st.markdown(f'<div class="title">{title}</div>', unsafe_allow_html=True)
            return self
        def __exit__(self, exc_type, exc, tb):
            st.markdown("</div>", unsafe_allow_html=True)
    return _Card()

# ---------- Helpers ----------
@st.cache_data(show_spinner=False)
def load_google_sheet(sheet_name: str) -> pd.DataFrame:
    import gspread
    from oauth2client.service_account import ServiceAccountCredentials
    import json

    GOOGLE_SHEET_URL = "https://docs.google.com/spreadsheets/d/1oyVzCgGK1Q3Qi_sbYwE-wKG6SArnfUDRe7rQfGOF-Eo"
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive",
    ]
    creds_json = {k: str(v) for k, v in st.secrets["gcp_service_account"].items()}
    with open
