import streamlit as st
import pandas as pd
from dateutil import parser, relativedelta

# ----- 데이터 불러오기 -----
@st.cache_data(show_spinner=False)
def load_google_sheet(sheet_name):
    import gspread
    from oauth2client.service_account import ServiceAccountCredentials
    import json
    GOOGLE_SHEET_URL = "https://docs.google.com/spreadsheets/d/1oyVzCgGK1Q3Qi_sbYwE-wKG6SArnfUDRe7rQfGOF-Eo"
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
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

df_info = load_google_sheet("PRODUCT_INFO")
df_temu = load_google_sheet("TEMU_SALES")
df_shein = load_google_sheet("SHEIN_SALES")

# ----- 날짜 변환 -----
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

df_temu["order date"] = df_temu["purchase date"].apply(parse_temudate)
df_shein["order date"] = df_shein["order processed on"].apply(parse_sheindate)

# ----- 기본정보 -----
today = pd.Timestamp.now().normalize()
start_30 = today - pd.Timedelta(days=30)
start_60 = today - pd.Timedelta(days=60)
start_14 = today - pd.Timedelta(days=14)
start_7 = today - pd.Timedelta(days=7)

# ----- 스타일별 판매 데이터 집계 -----
def get_sales(df, key, price_col, start, end):
    mask = (df["order date"] >= start) & (df["order date"] < end)
    df = df[mask]
    cnt = df.groupby(key).size()
    amount = df.groupby(key)[price_col].apply(lambda s: pd.to_numeric(s, errors="coerce").fillna(0).sum())
    return cnt, amount

# ----- 추천가 계산 -----
def safe_float(x):
    try:
        return float(str(x).replace(",", "").strip())
    except Exception:
        return 0

def suggest_price(row, similar_avg):
    erp = safe_float(row.get("erp price", 0))
    if erp == 0:
        return "-", "ERP 없음"
    min_price = max(erp * 1.3 + 2, 9)
    std_price = max(erp * 1.3 + 7, 9)
    if similar_avg is not None and not pd.isna(similar_avg) and similar_avg > 0:
        price = max(similar_avg, min_price)
        reason = "유사 스타일 평균 반영"
    else:
        price = std_price
        reason = "기본 공식 적용"
    return f"{price:.2f}", reason


price_list, reason_list = [], []
for idx, row in info.iterrows():
    similar_avg = find_similar_price(row, info, temu_price_dict, shein_price_dict)
    sug, why = suggest_price(row, similar_avg)
    price_list.append(sug)
    reason_list.append(why)
info["추천가"] = price_list
info["추천사유"] = reason_list

# ----- 비슷한 스타일 평균가 계산 -----
def find_similar_price(row, df_info, temu_prices, shein_prices):
    # 비슷한 스타일: SLEEVE, LENGTH, FIT 등 주요 속성 일치
    cond = (df_info["sleeve"] == row["sleeve"]) & (df_info["length"] == row["length"]) & (df_info["fit"] == row["fit"])
    similar_styles = df_info[cond & (df_info["product number"] != row["product number"])]
    if similar_styles.empty:
        return None
    style_nums = similar_styles["product number"].tolist()
    prices = []
    for sn in style_nums:
        # TEMU + SHEIN 가격 둘 다 취합
        t = temu_prices.get(sn)
        s = shein_prices.get(sn)
        if t and t > 0: prices.append(t)
        if s and s > 0: prices.append(s)
    if not prices:
        return None
    return sum(prices) / len(prices)

# ----- 모든 스타일별 가격/판매 정보 취합 -----
info = df_info.copy()
# 가격: TEMU, SHEIN 마지막 거래 평균
temu_price_dict = df_temu.groupby("product number")["base price total"].apply(
    lambda s: pd.to_numeric(s, errors="coerce").mean()
).to_dict()
shein_price_dict = df_shein.groupby("product description")["product price"].apply(
    lambda s: pd.to_numeric(s, errors="coerce").mean()
).to_dict()
info["temu price"] = info["product number"].map(temu_price_dict)
info["shein price"] = info["product number"].map(shein_price_dict)
# 최근 30/14/7일 판매량
info["30d sales"] = info["product number"].map(
    get_sales(df_temu, "product number", "quantity shipped", start_30, today)[0]
    .add(get_sales(df_shein, "product description", "product price", start_30, today)[0], fill_value=0)
).fillna(0).astype(int)
info["14d sales"] = info["product number"].map(
    get_sales(df_temu, "product number", "quantity shipped", start_14, today)[0]
    .add(get_sales(df_shein, "product description", "product price", start_14, today)[0], fill_value=0)
).fillna(0).astype(int)
info["7d sales"] = info["product number"].map(
    get_sales(df_temu, "product number", "quantity shipped", start_7, today)[0]
    .add(get_sales(df_shein, "product description", "product price", start_7, today)[0], fill_value=0)
).fillna(0).astype(int)
info["60_30d sales"] = info["product number"].map(
    get_sales(df_temu, "product number", "quantity shipped", start_60, start_30)[0]
    .add(get_sales(df_shein, "product description", "product price", start_60, start_30)[0], fill_value=0)
).fillna(0).astype(int)

# ----- 추천가, 분류 -----
price_list, reason_list = [], []
for idx, row in info.iterrows():
    similar_avg = find_similar_price(row, info, temu_price_dict, shein_price_dict)
    sug, why = suggest_price(row, similar_avg)
    price_list.append(sug)
    reason_list.append(why)
info["추천가"] = price_list
info["추천사유"] = reason_list

# ----- 분류 -----
info["신상/미판매"] = info["30d sales"] == 0
info["슬로우셀러"] = (info["30d sales"] > 0) & (info["30d sales"] <= 2)
info["판매급감"] = (info["60_30d sales"] > 0) & (info["30d sales"] / info["60_30d sales"] <= 0.5)
info["베스트셀러"] = info["30d sales"] >= 20

# ----- Streamlit UI -----
st.title("💡 가격 제안 AI (판매 데이터 기반 추천)")
st.markdown("""
- 최근 30일간 판매량 0 (신상/미판매 스타일)
- 지난달 대비 판매 급감
- 판매가 1~2건 등 극히 적음 (slow seller)
- 너무 잘 팔리는 아이템 (가격 인상 추천)
- 기본 가격 제시: **erp price × 1.3 + 7** (최소 erp×1.3+2, $9 미만 비추천)
""")

tabs = st.tabs([
    "🆕 미판매/신상", "🐢 판매 저조", "📉 판매 급감", "📈 가격 인상 추천"
])

# ----- 탭별 데이터 -----
with tabs[0]:
    st.markdown("#### 🆕 최근 30일간 판매 0 (신상/미판매)")
    df = info[info["신상/미판매"]][["product number","sleeve","length","fit","erp price","temu price","shein price","추천가","추천사유","30d sales"]]
    st.dataframe(df, use_container_width=True, height=500)

with tabs[1]:
    st.markdown("#### 🐢 판매 저조 (1~2건/30일)")
    df = info[info["슬로우셀러"]][["product number","sleeve","length","fit","erp price","temu price","shein price","추천가","추천사유","30d sales"]]
    st.dataframe(df, use_container_width=True, height=500)

with tabs[2]:
    st.markdown("#### 📉 판매 급감 (전월대비 50%↓)")
    df = info[info["판매급감"]][["product number","sleeve","length","fit","erp price","temu price","shein price","추천가","추천사유","60_30d sales","30d sales"]]
    st.dataframe(df, use_container_width=True, height=500)

with tabs[3]:
    st.markdown("#### 📈 가격 인상 추천 (30일 20건↑)")
    df = info[info["베스트셀러"]][["product number","sleeve","length","fit","erp price","temu price","shein price","추천가","추천사유","30d sales"]]
    st.dataframe(df, use_container_width=True, height=500)
