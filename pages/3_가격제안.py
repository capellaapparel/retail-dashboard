import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# --- 구글시트 불러오기 함수 (필요시 utils에서 불러와도 됨) ---
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

# ---- 데이터 로드 ----
df_info = load_google_sheet("PRODUCT_INFO")
df_temu = load_google_sheet("TEMU_SALES")
df_shein = load_google_sheet("SHEIN_SALES")

# ---- 전처리 ----
df_temu["order date"] = pd.to_datetime(df_temu["purchase date"], errors="coerce")
df_shein["order date"] = pd.to_datetime(df_shein["order processed on"], errors="coerce")
df_info["erp price"] = pd.to_numeric(df_info["erp price"], errors="coerce")

today = datetime.now()
start_30d = today - timedelta(days=30)
start_60d = today - timedelta(days=60)
start_14d = today - timedelta(days=14)
start_7d = today - timedelta(days=7)

# 스타일 넘버 컬럼 정리
info_idx = df_info["product number"].astype(str)

# TEMU/SHEIN 판매가 평균
def temu_avg_price(prodnum):
    vals = df_temu[df_temu["product number"] == prodnum]["base price total"]
    vals = pd.to_numeric(vals, errors="coerce")
    vals = vals[vals > 0]
    return np.nan if vals.empty else float(vals.mean())

def shein_avg_price(prodnum):
    vals = df_shein[df_shein["product description"] == prodnum]["product price"]
    vals = pd.to_numeric(vals, errors="coerce")
    vals = vals[vals > 0]
    return np.nan if vals.empty else float(vals.mean())

df_info["temu_avg"] = df_info["product number"].map(temu_avg_price)
df_info["shein_avg"] = df_info["product number"].map(shein_avg_price)

# --- 판매량 집계 ---
def get_qty(df, col, prodnum, start, end):
    mask = (df["order date"] >= start) & (df["order date"] < end)
    if col == "product number":
        match = df["product number"] == prodnum
    else:
        match = df["product description"] == prodnum
    return int(df[mask & match].shape[0])

qty_30d = []
qty_prev30d = []
qty_14d = []
qty_7d = []
qty_all = []
for idx, row in df_info.iterrows():
    prodnum = row["product number"]
    qty_30d.append(get_qty(df_temu, "product number", prodnum, start_30d, today) + get_qty(df_shein, "product description", prodnum, start_30d, today))
    qty_prev30d.append(get_qty(df_temu, "product number", prodnum, start_60d, start_30d) + get_qty(df_shein, "product description", prodnum, start_60d, start_30d))
    qty_14d.append(get_qty(df_temu, "product number", prodnum, today - timedelta(days=14), today) + get_qty(df_shein, "product description", prodnum, today - timedelta(days=14), today))
    qty_7d.append(get_qty(df_temu, "product number", prodnum, today - timedelta(days=7), today) + get_qty(df_shein, "product description", prodnum, today - timedelta(days=7), today))
    qty_all.append(get_qty(df_temu, "product number", prodnum, pd.Timestamp('2000-01-01'), today) + get_qty(df_shein, "product description", prodnum, pd.Timestamp('2000-01-01'), today))
df_info["30d_qty"] = qty_30d
df_info["prev30d_qty"] = qty_prev30d
df_info["14d_qty"] = qty_14d
df_info["7d_qty"] = qty_7d
df_info["all_qty"] = qty_all

# --- AI 가격 제안 로직 ---
def suggest_price(row, similar_avg):
    erp = float(row["erp price"]) if pd.notna(row["erp price"]) else 0
    # 기본 제안
    min_sug = max(erp * 1.3 + 2, 9)
    base_sug = max(erp * 1.3 + 7, 9)
    # 비슷한 스타일 가격 (없으면 erp 기준)
    avg = similar_avg if pd.notna(similar_avg) else base_sug
    # 추천가격 (avg와 base의 평균값으로)
    rec = np.mean([base_sug, avg])
    if rec < min_sug:
        rec = min_sug
    return round(rec, 2)

# ---- 분류 ----
no_sales, slow, drop, inc = [], [], [], []
for idx, row in df_info.iterrows():
    prodnum = row["product number"]
    erp = row["erp price"] if pd.notna(row["erp price"]) else np.nan
    # 비슷한 스타일 평균 (sleeve, length, fit 3개)
    mask = (
        (df_info["sleeve"] == row["sleeve"]) &
        (df_info["length"] == row["length"]) &
        (df_info["fit"] == row["fit"]) &
        (df_info["product number"] != prodnum)
    )
    similar = df_info[mask]
    similar_avg = np.nan
    if not similar.empty:
        pricevals = pd.concat([similar["temu_avg"], similar["shein_avg"]]).dropna()
        if not pricevals.empty:
            similar_avg = pricevals.mean()
    sug = suggest_price(row, similar_avg)
    reason = []
    # 분류
    if row["30d_qty"] == 0 and row["all_qty"] == 0:
        reason.append("한 번도 팔린적 없음(신상/미판매)")
        no_sales.append({**row, "추천가": sug, "추천 근거": "동종 평균가/ERP 기준" if pd.notna(similar_avg) else "ERP 기준"})
    elif row["30d_qty"] == 0 and row["all_qty"] > 0:
        reason.append("최근 30일 판매 없음 (미판매)")
        no_sales.append({**row, "추천가": sug, "추천 근거": "이전 판매 있음, 최근 미판매"})
    elif row["30d_qty"] <= 2 and row["all_qty"] > 0:
        reason.append("최근 30일 판매 극소 (slow seller)")
        slow.append({**row, "추천가": sug, "추천 근거": "판매 저조"})
    elif row["30d_qty"] < row["prev30d_qty"] / 2 and row["prev30d_qty"] > 0:  # 급감(이전 30일대비 50%이상 감소)
        reason.append("지난달 대비 판매 급감")
        drop.append({**row, "추천가": sug, "추천 근거": "판매 급감"})
    elif row["30d_qty"] >= 10 or row["all_qty"] > 30:
        reason.append("지속적으로 잘 팔림 (가격 인상 고려)")
        sug_high = round(sug + 1.5, 2)
        inc.append({**row, "추천가": sug_high, "추천 근거": "판매호조/가격 인상 제안"})
    # else는 기타

# 데이터프레임 변환
def list_to_df(lst):
    if not lst: return pd.DataFrame()
    df = pd.DataFrame(lst)
    # 컬럼 일치화
    expect = ["product number","default product name(en)","erp price","추천가","추천 근거","30d_qty","prev30d_qty","all_qty"]
    for col in expect:
        if col not in df.columns:
            df[col] = ""
    return df[expect]

no_sales_df = list_to_df(no_sales)
slow_df = list_to_df(slow)
drop_df = list_to_df(drop)
inc_df = list_to_df(inc)

# ---- UI ----
st.markdown("""
    <style>
    .block-container {padding-top:2.2rem;}
    .stTabs [data-baseweb="tab-list"] {flex-wrap: wrap;}
    </style>
""", unsafe_allow_html=True)
st.title("💡 가격 제안 대시보드")

st.markdown("""
- 최근 30일간 판매량 0 (신상/미판매 스타일)
- 지난달 대비 판매 급감
- 판매가 1~2건 등 극히 적음 (slow seller)
- 너무 잘 팔리는 아이템 (가격 인상 추천)
- 기본 가격 제시: <b>erp price × 1.3 + 7</b> (최소 erp×1.3+2, $9 미만 비추천)
""", unsafe_allow_html=True)

tabs = st.tabs(
    ["🆕 판매 없음 (신상/미판매)", "🟠 판매 저조", "📉 판매 급감", "🔥 가격 인상 추천"]
)

def display_table(df, title):
    st.markdown(f"#### {title}")
    if df.empty:
        st.info("추천되는 스타일이 없습니다.")
    else:
        st.dataframe(df, use_container_width=True, hide_index=True)

with tabs[0]:
    display_table(no_sales_df, "판매 기록 없는 신상/미판매 스타일의 최소가격 제시 (동종 평균가 반영)")

with tabs[1]:
    display_table(slow_df, "판매 저조 스타일 추천가")

with tabs[2]:
    display_table(drop_df, "판매 급감 스타일 추천가")

with tabs[3]:
    display_table(inc_df, "판매호조(가격 인상) 스타일 추천가")
