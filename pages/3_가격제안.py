import streamlit as st
import pandas as pd
from dateutil import parser
import numpy as np

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

# ========== 데이터 불러오기 ==========
df_info = load_google_sheet("PRODUCT_INFO")
df_temu = load_google_sheet("TEMU_SALES")
df_shein = load_google_sheet("SHEIN_SALES")

df_temu["order date"] = df_temu["purchase date"].apply(parse_temudate)
df_shein["order date"] = df_shein["order processed on"].apply(parse_sheindate)

# 컬럼명 보정
df_info.columns = [c.lower() for c in df_info.columns]
df_temu.columns = [c.lower() for c in df_temu.columns]
df_shein.columns = [c.lower() for c in df_shein.columns]

st.title("💡 가격 제안 AI (판매 데이터 기반 추천)")

st.markdown("""
- 최근 30일간 판매량 0 (신상/미판매 스타일)
- 지난달 대비 판매 급감
- 판매가 1~2건 등 극히 적음 (slow seller)
- 너무 잘 팔리는 아이템 (가격 인상 추천)
- 기본 가격 제시: **erp price × 1.3 + 7** (최소 erp×1.3+2, $9 미만 비추천)
""")

import datetime
today = pd.Timestamp.today().normalize()
last_30d = today - pd.Timedelta(days=30)
last_60d = today - pd.Timedelta(days=60)

# 유사 스타일 찾기 (SLEEVE, FIT, LENGTH 기준)
def find_similar_price(row, ref_df):
    ref = ref_df[
        (ref_df["sleeve"].str.lower() == str(row.get("sleeve", "")).lower()) &
        (ref_df["fit"].str.lower() == str(row.get("fit", "")).lower()) &
        (ref_df["length"].str.lower() == str(row.get("length", "")).lower())
    ]
    return ref

def suggest_price(erp, ref_prices):
    # 기본 가격 로직
    try:
        erp = float(erp)
    except:
        return ""
    base = erp * 1.3 + 7
    base_min = max(erp * 1.3 + 2, 9)
    # AI 추천: 유사 스타일 평균/중앙값 등 (판매가 많은 스타일 기준)
    if len(ref_prices) > 0:
        ai_price = np.median(ref_prices)
        if ai_price < base_min:
            ai_price = base_min
        return f"${ai_price:.2f} (AI/유사:{base_min:.2f}~)"
    else:
        return f"${base:.2f}"

# 판매 없는/적은 스타일만 추출
info = df_info.copy()
info["erp price"] = pd.to_numeric(info["erp price"], errors="coerce")
info["temu price"] = info["product number"].map(
    lambda x: df_temu[df_temu["product number"]==x]["base price total"].dropna().astype(float).mean()
)
info["shein price"] = info["product number"].map(
    lambda x: df_shein[df_shein["product description"]==x]["product price"].dropna().astype(float).mean()
)
info["temu_qty30"] = info["product number"].map(
    lambda x: df_temu[(df_temu["product number"]==x) & (df_temu["order date"]>=last_30d)]["quantity shipped"].sum()
)
info["shein_qty30"] = info["product number"].map(
    lambda x: df_shein[(df_shein["product description"]==x) & (df_shein["order date"]>=last_30d)].shape[0]
)
info["total_qty30"] = info["temu_qty30"].fillna(0) + info["shein_qty30"].fillna(0)

# 판매 없는 신상/미판매 스타일
unsold = info[info["total_qty30"]==0].copy()

# 유사 스타일(AI) 평균가격 기반 추천
rows = []
for idx, row in unsold.iterrows():
    ref = find_similar_price(row, info[info["total_qty30"]>0])
    prices = []
    if not ref.empty:
        if not ref["temu price"].isnull().all():
            prices += ref["temu price"].dropna().tolist()
        if not ref["shein price"].isnull().all():
            prices += ref["shein price"].dropna().tolist()
    suggest = suggest_price(row["erp price"], prices)
    rows.append({
        "Product Number": row["product number"],
        "SLEEVE": row.get("sleeve", ""),
        "LENGTH": row.get("length", ""),
        "FIT": row.get("fit", ""),
        "ERP Price": row["erp price"],
        "TEMU/SHEIN 판매가격": f"${row['temu price']:.2f}/{row['shein price']:.2f}" if pd.notna(row['temu price']) and pd.notna(row['shein price']) else "-",
        "최근 30일 판매": int(row["total_qty30"]),
        "AI 추천가": suggest,
    })

# 지난달 대비 급감, 판매 극저조, 너무 잘 팔림 등도 유사하게 추출 가능 (아래는 예시)
# 예: total_qty30 <= 2 ("느리게 팔림")
slows = info[(info["total_qty30"] > 0) & (info["total_qty30"] <= 2)].copy()
for idx, row in slows.iterrows():
    ref = find_similar_price(row, info[info["total_qty30"]>2])
    prices = []
    if not ref.empty:
        if not ref["temu price"].isnull().all():
            prices += ref["temu price"].dropna().tolist()
        if not ref["shein price"].isnull().all():
            prices += ref["shein price"].dropna().tolist()
    suggest = suggest_price(row["erp price"], prices)
    rows.append({
        "Product Number": row["product number"],
        "SLEEVE": row.get("sleeve", ""),
        "LENGTH": row.get("length", ""),
        "FIT": row.get("fit", ""),
        "ERP Price": row["erp price"],
        "TEMU/SHEIN 판매가격": f"${row['temu price']:.2f}/{row['shein price']:.2f}" if pd.notna(row['temu price']) and pd.notna(row['shein price']) else "-",
        "최근 30일 판매": int(row["total_qty30"]),
        "AI 추천가": suggest,
    })

# 너무 잘 팔리는 스타일(30일 판매량 상위 10% 중, 가격 낮은 스타일) 등 추가 가능

# ------------------ 표 출력 ------------------
recommend_df = pd.DataFrame(rows)
st.subheader("📋 가격 조정 필요 스타일 (AI 추천)")

if recommend_df.empty:
    st.info("가격 제안이 필요한 스타일이 없습니다.")
else:
    st.dataframe(recommend_df, height=600, use_container_width=True)
