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

def to_date(s):
    try: return pd.to_datetime(s)
    except: return pd.NaT

st.title("AI 기반 가격제안 (판매기록/스타일/트렌드 기반)")

df_info = load_google_sheet("PRODUCT_INFO")
df_temu = load_google_sheet("TEMU_SALES")
df_shein = load_google_sheet("SHEIN_SALES")

# 날짜 칼럼 파싱
df_temu["order date"] = df_temu["purchase date"].apply(to_date)
df_shein["order date"] = df_shein["order processed on"].apply(to_date)

today = pd.to_datetime("today").normalize()
# 판매 구분
temu_sold = set(df_temu["product number"].astype(str).unique())
shein_sold = set(df_shein["product description"].astype(str).unique())
sold_total = temu_sold.union(shein_sold)
all_products = df_info["product number"].astype(str).tolist()

recommend_rows = []

for idx, row in df_info.iterrows():
    pn = str(row["product number"])
    erp = row.get("erp price", "")
    if pd.isna(erp) or str(erp).strip() == "":
        continue
    try: erp = float(str(erp).replace("$", ""))
    except: continue
    base_min = erp*1.3 + 2
    base_max = erp*1.3 + 7

    # 해당 스타일 TEMU/쉬인 판매내역 합치기
    temu_sales = df_temu[df_temu["product number"].astype(str) == pn]
    shein_sales = df_shein[df_shein["product description"].astype(str) == pn]
    all_sales = pd.concat([temu_sales, shein_sales])
    all_sales = all_sales[~all_sales["order date"].isna()]
    all_sales = all_sales.sort_values("order date")

    total_sold = 0
    price_list = []

    # 테무 수량/금액
    if not temu_sales.empty:
        t_mask = temu_sales["order item status"].str.lower().isin(["shipped", "delivered"])
        sold_qty = pd.to_numeric(temu_sales[t_mask]["quantity shipped"], errors="coerce").fillna(0).sum()
        total_sold += sold_qty
        prices = pd.to_numeric(temu_sales[t_mask]["base price total"], errors="coerce")
        qtys = pd.to_numeric(temu_sales[t_mask]["quantity shipped"], errors="coerce").replace(0, 1)
        unit_prices = prices / qtys
        price_list += unit_prices.tolist()
    # 쉬인
    if not shein_sales.empty:
        s_mask = ~shein_sales["order status"].str.lower().isin(["customer refunded"])
        sold_qty = s_mask.sum()
        total_sold += sold_qty
        price_list += pd.to_numeric(shein_sales[s_mask]["product price"], errors="coerce").tolist()

    # 최근 30/14/7일 판매량 추이
    sales_last_30 = all_sales[all_sales["order date"] >= today - pd.Timedelta(days=30)]
    sales_last_14 = all_sales[all_sales["order date"] >= today - pd.Timedelta(days=14)]
    sales_last_7  = all_sales[all_sales["order date"] >= today - pd.Timedelta(days=7)]
    qty_30 = sales_last_30.shape[0]
    qty_14 = sales_last_14.shape[0]
    qty_7 = sales_last_7.shape[0]

    # 유사 스타일 평균 가격 (TEMU/쉬인 모두)
    key_attrs = ["sleeve", "length", "neckline", "fit"]
    attr_query = {k: str(row.get(k, "")).strip().lower() for k in key_attrs}
    match = df_info.copy()
    for k, v in attr_query.items():
        if v and v != "nan": match = match[match[k].astype(str).str.lower() == v]
    sim_nums = set(match["product number"].astype(str).unique())
    sim_prices = []
    for spn in sim_nums:
        if spn == pn: continue
        t_sales = df_temu[df_temu["product number"].astype(str) == spn]
        s_sales = df_shein[df_shein["product description"].astype(str) == spn]
        if not t_sales.empty:
            t_mask = t_sales["order item status"].str.lower().isin(["shipped", "delivered"])
            prices = pd.to_numeric(t_sales[t_mask]["base price total"], errors="coerce")
            qtys = pd.to_numeric(t_sales[t_mask]["quantity shipped"], errors="coerce").replace(0, 1)
            sim_prices += (prices / qtys).tolist()
        if not s_sales.empty:
            s_mask = ~s_sales["order status"].str.lower().isin(["customer refunded"])
            sim_prices += pd.to_numeric(s_sales[s_mask]["product price"], errors="coerce").tolist()
    sim_prices = [p for p in sim_prices if pd.notna(p) and p > 0]
    sim_avg = round(sum(sim_prices) / len(sim_prices), 2) if sim_prices else None

    # --- AI 가격 제안 조건 ---
    reason = ""
    suggested = None

    if total_sold == 0:
        # 미판매
        suggested = max(base_min, sim_avg or 0, 9)
        suggested = min(suggested, base_max)
        reason = "한 번도 팔린 적 없음 (신상)"
    elif total_sold <= 2:
        # 판매기록 거의 없음
        suggested = max(base_min, sim_avg or 0, 9)
        suggested = min(suggested, base_max)
        reason = "판매기록 거의 없음"
    elif qty_7 > 2 or qty_14 > 4 or qty_30 > 8:
        # 최근 판매량 높음 → 가격 올려도 됨
        last_price = price_list[-1] if price_list else sim_avg or base_min
        up_price = max(last_price*1.08, base_min, sim_avg or 0)
        suggested = min(up_price, base_max)
        reason = "최근 판매량 높음 (가격 인상 추천)"
    elif qty_30 > 0 and qty_7 == 0 and qty_14 == 0:
        # 최근 급감/정체
        suggested = max(base_min, (sim_avg or 0) * 0.95, 9)
        suggested = min(suggested, base_max)
        reason = "최근 판매 없음 (가격 소폭 인하/유지)"
    else:
        continue  # 딱히 변화 필요 없음

    recommend_rows.append({
        "Product Number": pn,
        "Name": row.get("default product name(en)", ""),
        "ERP Price": erp,
        "유사 스타일 평균": sim_avg if sim_avg else "",
        "최근 30/14/7일 판매량": f"{qty_30}/{qty_14}/{qty_7}",
        "추천가격": round(suggested,2) if suggested else "",
        "사유": reason
    })

st.markdown("### 💡 가격 조정/추천 필요한 스타일")
df_out = pd.DataFrame(recommend_rows)
if df_out.empty:
    st.info("가격 제안/조정이 필요한 스타일이 없습니다.")
else:
    st.dataframe(df_out, height=1000)

st.caption("""
- ERP Price*1.3+2~7, 유사 스타일 평균가, 최근 판매트렌드 기반
- 미판매/판매저조/판매급상승/정체 등 케이스별로 가격 추천
- 9불 미만으로는 제안하지 않음
""")
