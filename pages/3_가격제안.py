import streamlit as st
import pandas as pd
import numpy as np
from dateutil import parser, relativedelta
from datetime import datetime, timedelta

# 구글시트 로딩 함수 (utils와 동일)
@st.cache_data(show_spinner=False)
def load_google_sheet(sheet_name):
    import gspread
    from oauth2client.service_account import ServiceAccountCredentials
    import json
    GOOGLE_SHEET_URL = "https://docs.google.com/spreadsheets/d/1oyVzCgGK1Q3Qi_sbYwE-wKG6SArnfUDRe7rQfGOF-Eo"
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive"
    ]
    json_data = {k: str(v) for k, v in st.secrets["gcp_service_account"].items()}
    with open("/tmp/service_account.json", "w") as f:
        json.dump(json_data, f)
    creds = ServiceAccountCredentials.from_json_keyfile_name("/tmp/service_account.json", scope)
    client = gspread.authorize(creds)
    sheet = client.open_by_url(GOOGLE_SHEET_URL).worksheet(sheet_name)
    data = sheet.get_all_records()
    df = pd.DataFrame(data)
    df.columns = [c.lower().strip() for c in df.columns]
    return df

def parse_temudate(dt):
    try:
        return parser.parse(str(dt).split('(')[0].strip(), fuzzy=True)
    except Exception:
        return pd.NaT

def parse_sheindate(dt):
    try:
        return pd.to_datetime(str(dt), errors="coerce", infer_datetime_format=True)
    except Exception:
        return pd.NaT

def is_zero(x):
    try:
        return float(x) == 0 or pd.isna(x)
    except:
        return True

# === 데이터 불러오기 ===
df_info = load_google_sheet("PRODUCT_INFO")
df_temu = load_google_sheet("TEMU_SALES")
df_shein = load_google_sheet("SHEIN_SALES")

df_temu["order date"] = df_temu["purchase date"].apply(parse_temudate)
df_shein["order date"] = df_shein["order processed on"].apply(parse_sheindate)

today = pd.Timestamp.now().normalize()
day_30ago = today - timedelta(days=30)
day_60ago = today - timedelta(days=60)
month_ago_start = (today - pd.DateOffset(months=1)).replace(day=1)
this_month_start = today.replace(day=1)

# ---- 스타일별 판매 집계 ----
# TEMU: quantity shipped 합, SHEIN: 1줄=1개
temu_sales = df_temu[df_temu["order item status"].str.lower().isin(["shipped", "delivered"])]
shein_sales = df_shein[~df_shein["order status"].str.lower().isin(["customer refunded"])]

# 최근 30일 판매량
temu_30 = temu_sales[temu_sales["order date"] >= day_30ago].groupby("product number")["quantity shipped"].sum()
shein_30 = shein_sales[shein_sales["order date"] >= day_30ago].groupby("product description").size()
recent_30_sales = temu_30.add(shein_30, fill_value=0)

# 이전 30일 판매량
temu_60 = temu_sales[(temu_sales["order date"] >= day_60ago) & (temu_sales["order date"] < day_30ago)].groupby("product number")["quantity shipped"].sum()
shein_60 = shein_sales[(shein_sales["order date"] >= day_60ago) & (shein_sales["order date"] < day_30ago)].groupby("product description").size()
prev_30_sales = temu_60.add(shein_60, fill_value
