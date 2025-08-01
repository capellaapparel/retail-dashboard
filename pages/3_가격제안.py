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

st.title("AI 기반 신상 가격 제안")

# 데이터 불러오기
df_info = load_google_sheet("PRODUCT_INFO")
df_temu = load_google_sheet("TEMU_SALES")
df_shein = load_google_sheet("SHEIN_SALES")

# TEMU, SHEIN에서 한 번이라도 판매된 product number 추출
sold_temus = set(df_temu["product number"].astype(str).unique())
sold_sheins = set(df_shein["product description"].astype(str).unique())
sold_total = sold_temus.union(sold_sheins)

# PRODUCT_INFO 전체 스타일 중 한번도 판매안된 애들 찾기
all_products = df_info["product number"].astype(str).tolist()
unsold = [p for p in all_products if p not in sold_total]

# 추천 결과 저장
suggest_rows = []

for pn in unsold:
    row = df_info[df_info["product number"].astype(str) == pn].iloc[0]
    erp_price = row.get("erp price", "")
    if pd.isna(erp_price) or str(erp_price).strip() == "":
        continue
    try:
        erp_price = float(str(erp_price).replace("$", ""))
    except:
        erp_price = None

    # 스타일 유사도 기준: sleeve, length, neckline, fit 등
    key_attrs = ["sleeve", "length", "neckline", "fit"]
    attr_query = {k: str(row.get(k, "")).strip().lower() for k in key_attrs}
    # TEMU에서 유사 스타일 찾기
    match_temu = df_info.copy()
    for k, v in attr_query.items():
        if v and v != "nan":
            match_temu = match_temu[match_temu[k].astype(str).str.lower() == v]
    match_temu_nums = set(match_temu["product number"].astype(str).unique())
    sold_matches = [s for s in match_temu_nums if s in sold_temus]

    # 실제 판매된 TEMU 가격 참고 (최근 판매가)
    temu_prices = []
    for sold_pn in sold_matches:
        sold_rows = df_temu[df_temu["product number"].astype(str) == sold_pn]
        sold_rows = sold_rows[sold_rows["order item status"].str.lower().isin(["shipped", "delivered"])]
        if not sold_rows.empty:
            prices = pd.to_numeric(sold_rows["base price total"], errors="coerce")
            qtys = pd.to_numeric(sold_rows["quantity shipped"], errors="coerce")
            unit_prices = prices / qtys.replace(0,1)
            temu_prices.extend(unit_prices[unit_prices>0].tolist())

    # SHEIN도 마찬가지
    sold_matches_shein = [s for s in match_temu_nums if s in sold_sheins]
    shein_prices = []
    for sold_pn in sold_matches_shein:
        sold_rows = df_shein[df_shein["product description"].astype(str) == sold_pn]
        sold_rows = sold_rows[~sold_rows["order status"].str.lower().isin(["customer refunded"])]
        if not sold_rows.empty:
            pps = pd.to_numeric(sold_rows["product price"], errors="coerce")
            shein_prices.extend(pps[pps>0].tolist())

    # 평균값 (동일 스타일, 같은 플랫폼 기준)
    base_prices = temu_prices + shein_prices
    base_prices = [p for p in base_prices if pd.notna(p) and p > 0]
    if base_prices:
        avg_price = round(sum(base_prices) / len(base_prices), 2)
        # ERP의 1.1배~2배(너무 싸게 안잡히게, 유사스타일 판매가 평균보다 ERP가 높으면 ERP+0.5~1 정도 추천)
        suggest_price = max(avg_price, erp_price * 1.1)
    elif erp_price:
        suggest_price = erp_price * 1.3  # 그냥 ERP의 1.3배(최소 마진)
    else:
        suggest_price = ""
    suggest_rows.append({
        "Product Number": pn,
        "Name": row.get("default product name(en)", ""),
        "ERP Price": erp_price,
        "유사 스타일 평균 판매가": round(avg_price,2) if base_prices else "",
        "추천가격": round(suggest_price, 2) if suggest_price else ""
    })

st.markdown("### 💡 판매기록 없는 스타일에 대한 가격 제안")
df_out = pd.DataFrame(suggest_rows)
if df_out.empty:
    st.info("모든 스타일이 이미 판매기록이 있거나, 유사 스타일이 없습니다.")
else:
    st.dataframe(df_out)

st.caption("""
- 'ERP Price'보다 너무 낮게 제안하지 않으며,  
- 동일/유사 스타일(슬리브, 길이, 넥라인 등) 중 실제 팔린 제품 가격 평균을 기반으로 제안합니다.
- 최근 판매 내역이 없는 경우 ERP 기준 30%~40% 가산 추천
""")
