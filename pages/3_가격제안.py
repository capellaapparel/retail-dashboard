import streamlit as st
import pandas as pd
from dateutil import parser

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

st.title("AI 기반 가격 변경 필요 스타일 추천")

# 데이터 불러오기
df_temu = load_google_sheet("TEMU_SALES")
df_temu = df_temu[df_temu["purchase date"].apply(lambda x: isinstance(x, str))]
df_temu["order date"] = pd.to_datetime(df_temu["purchase date"], errors="coerce")
df_temu = df_temu[df_temu["order date"].notna()]

today = df_temu["order date"].max()
last_month = today - pd.Timedelta(days=30)
prev_month = last_month - pd.Timedelta(days=30)

# 1. 최근 한 달, 그 전 한 달간 판매 집계
sales_recent = (
    df_temu[(df_temu["order date"] >= last_month) & (df_temu["order date"] <= today) & (df_temu["order item status"].str.lower().isin(["shipped", "delivered"]))]
    .groupby("product number")["quantity shipped"].sum()
    .rename("최근 30일 판매량")
)
sales_prev = (
    df_temu[(df_temu["order date"] >= prev_month) & (df_temu["order date"] < last_month) & (df_temu["order item status"].str.lower().isin(["shipped", "delivered"]))]
    .groupby("product number")["quantity shipped"].sum()
    .rename("이전 30일 판매량")
)
# 2. 합치기 및 증감률 계산
summary = pd.concat([sales_recent, sales_prev], axis=1).fillna(0)
summary["판매량 증감률(%)"] = summary.apply(
    lambda row: ((row["최근 30일 판매량"] - row["이전 30일 판매량"]) / row["이전 30일 판매량"] * 100)
    if row["이전 30일 판매량"] > 0 else (100 if row["최근 30일 판매량"] > 0 else 0), axis=1
)

# 3. 가격조정 ‘필요’ 추정(예시)
summary["가격조정 추천"] = summary.apply(
    lambda row:
        "▼ 가격 인하 추천" if row["최근 30일 판매량"] == 0 and row["이전 30일 판매량"] > 0 else
        ("▲ 가격 인상 고려" if row["최근 30일 판매량"] > 10 and row["판매량 증감률(%)"] > 100 else ""),
    axis=1
)
recommend = summary[summary["가격조정 추천"] != ""]

st.markdown("### 🔥 아래 스타일은 가격 조정이 필요할 수 있습니다")
if recommend.empty:
    st.info("가격 조정 필요 스타일이 없습니다. (모든 스타일이 정상 판매 중)")
else:
    st.dataframe(recommend[["최근 30일 판매량", "이전 30일 판매량", "판매량 증감률(%)", "가격조정 추천"]].sort_values("가격조정 추천", ascending=False))

st.caption("예시: 최근 한 달간 ‘판매 0’이거나 판매가 급증한 스타일만 추출.\n로직 원하는대로 변경 가능")
