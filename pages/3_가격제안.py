import streamlit as st
import pandas as pd
import numpy as np
from dateutil import parser
from datetime import datetime, timedelta

# --- 구글시트 데이터 로드 ---
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

def safe_float(x):
    try: return float(x)
    except: return np.nan

# --- 데이터 준비 ---
df_info = load_google_sheet("PRODUCT_INFO")
df_temu = load_google_sheet("TEMU_SALES")
df_shein = load_google_sheet("SHEIN_SALES")

df_temu["order date"] = df_temu["purchase date"].apply(parse_temudate)
df_shein["order date"] = df_shein["order processed on"].apply(parse_sheindate)

today = pd.Timestamp.now().normalize()
day_30ago = today - timedelta(days=30)
day_60ago = today - timedelta(days=60)

# --- 스타일별 판매량/평균가 ---
def temu_qty(style, start, end):
    mask = (df_temu["order date"] >= start) & (df_temu["order date"] <= end)
    s = df_temu[mask & (df_temu["product number"] == style) & 
                (df_temu["order item status"].str.lower().isin(["shipped","delivered"]))]
    return s["quantity shipped"].sum()

def shein_qty(style, start, end):
    mask = (df_shein["order date"] >= start) & (df_shein["order date"] <= end)
    s = df_shein[mask & (df_shein["product description"] == style) & 
                 (~df_shein["order status"].str.lower().isin(["customer refunded"]))]
    return len(s)

def temu_avg_price(style):
    p = df_temu[
        (df_temu["product number"] == style) &
        (df_temu["order item status"].str.lower().isin(["shipped", "delivered"]))
    ]["base price total"]
    # 문자/공백/NaN 등 포함시에도 안전하게 처리
    p_numeric = pd.to_numeric(p, errors="coerce").dropna()
    return safe_float(p_numeric.mean()) if not p_numeric.empty else np.nan


def shein_avg_price(style):
    p = df_shein[
        (df_shein["product description"] == style) &
        (~df_shein["order status"].str.lower().isin(["customer refunded"]))
    ]["product price"]
    p_numeric = pd.to_numeric(p, errors="coerce").dropna()
    return safe_float(p_numeric.mean()) if not p_numeric.empty else np.nan


def price_suggestion(erp, similar_avg=None, mode="normal"):
    erp = safe_float(erp)
    base = erp*1.3 + 7
    min_sug = max(erp*1.3+2, 9)
    max_sug = base + 4
    # mode: "normal", "increase", "low"
    if mode == "low":  # 판매 저조
        sug = min_sug
        reason = "신상품/미판매/저조 스타일: 최소가격 제시"
    elif mode == "increase":  # 가격 인상추천
        sug = max(base, min(base+3, max_sug))
        reason = "판매호조: 소폭 가격인상 추천"
    else:  # 기본
        sug = base
        reason = "ERP 기반 일반 제시가"
    if similar_avg and not np.isnan(similar_avg):
        if mode == "low" and similar_avg > sug:
            sug = similar_avg
            reason += ", 동종평균 반영"
        elif mode == "increase" and similar_avg > sug:
            sug = similar_avg + 1
            reason += ", 동종평균+1"
    return round(sug,2), reason

# --- 집계 ---
info = df_info.copy()
style_list = info["product number"].astype(str).unique()

# 최근 30일 판매량
info["30d_qty"] = info["product number"].map(lambda x: temu_qty(x, day_30ago, today) + shein_qty(x, day_30ago, today))
info["prev30d_qty"] = info["product number"].map(lambda x: temu_qty(x, day_60ago, day_30ago- pd.Timedelta(days=1)) + shein_qty(x, day_60ago, day_30ago- pd.Timedelta(days=1)))
info["all_qty"] = info["product number"].map(lambda x: temu_qty(x, pd.Timestamp('2020-01-01'), today) + shein_qty(x, pd.Timestamp('2020-01-01'), today))
info["temu_avg"] = info["product number"].map(temu_avg_price)
info["shein_avg"] = info["product number"].map(shein_avg_price)
info["erp"] = info["erp price"].apply(safe_float)

# --- 유형 분류 ---
no_sales = info[info["all_qty"] == 0].copy()
slow = info[(info["all_qty"] <= 2) & (info["all_qty"] > 0)].copy()
drop = info[(info["30d_qty"] < info["prev30d_qty"]) & (info["prev30d_qty"] > 0)].copy()
hot = info[info["30d_qty"] >= 8].copy()

# --- 가격 추천 생성 ---
for df, mode in [(no_sales,"low"), (slow,"low"), (drop,"low"), (hot,"increase")]:
    df["추천가"], df["추천 근거"] = zip(*[
        price_suggestion(row["erp"], 
            similar_avg = info[(info["sleeve"]==row["sleeve"]) & (info["length"]==row["length"]) & (info["fit"]==row["fit"]) & (info["all_qty"]>0)]["temu_avg"].mean(),
            mode = mode)
        for _,row in df.iterrows()
    ])

# --- 탭 UI ---
st.title("💡 가격 제안 대시보드")
tab1, tab2, tab3, tab4 = st.tabs([
    "🆕 판매 없음 (신상/미판매)", 
    "⏳ 판매 저조", 
    "📉 판매 급감", 
    "🔥 가격 인상 추천"
])

def display_table(df, tip):
    if df.empty:
        st.info("해당되는 스타일이 없습니다.")
        return
    show = df[["product number","default product name(en)","erp price","추천가","추천 근거","30d_qty","prev30d_qty","all_qty"]]
    show.columns = ["Style#","Name","ERP","추천가","사유","최근30일","이전30일","누적판매"]
    st.markdown(f"<div style='margin:0 0 6px 0; color:#888;font-size:1.05em'>{tip}</div>", unsafe_allow_html=True)
    st.dataframe(show, use_container_width=True)

with tab1:
    display_table(no_sales, "판매 기록 없는 신상/미판매 스타일의 최소가격 제시 (동종 평균가 반영)")
with tab2:
    display_table(slow, "판매 1~2건 등 극저조 스타일의 최소가격 제시")
with tab3:
    display_table(drop, "지난달 대비 판매 급감 스타일")
with tab4:
    display_table(hot, "지속적 판매 인기스타일 – 가격 인상 제안")

st.caption("• 기준: ERP×1.3+7 (기본), 최소가 ERP×1.3+2 또는 $9 / 동종 평균 반영")
