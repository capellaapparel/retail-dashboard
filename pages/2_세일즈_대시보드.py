import streamlit as st
import pandas as pd
from dateutil import parser
import gspread
from oauth2client.service_account import ServiceAccountCredentials

@st.cache_data(show_spinner=False)
def load_google_sheet(sheet_name):
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive"
    ]
    json_data = {k: str(v) for k, v in st.secrets["gcp_service_account"].items()}
    with open("/tmp/service_account.json", "w") as f:
        import json
        json.dump(json_data, f)
    creds = ServiceAccountCredentials.from_json_keyfile_name("/tmp/service_account.json", scope)
    client = gspread.authorize(creds)
    GOOGLE_SHEET_URL = "https://docs.google.com/spreadsheets/d/1oyVzCgGK1Q3Qi_sbYwE-wKG6SArnfUDRe7rQfGOF-Eo"
    sheet = client.open_by_url(GOOGLE_SHEET_URL).worksheet(sheet_name)
    data = sheet.get_all_records()
    df = pd.DataFrame(data)
    df.columns = [c.lower().strip() for c in df.columns]
    return df

def parse_temudate(dt):
    try:
        return parser.parse(str(dt).split('(')[0].strip(), fuzzy=True)
    except:
        return pd.NaT

# === 데이터 로딩 ===
df_temu = load_google_sheet("TEMU_SALES")
df_info = load_google_sheet("PRODUCT_INFO")
df_temu["order date"] = df_temu["purchase date"].apply(parse_temudate)

# === 날짜필터 (00:00 ~ 23:59) ===
min_date, max_date = df_temu["order date"].min().date(), df_temu["order date"].max().date()
date_range = st.date_input("조회 기간", (min_date, max_date))
# 선택한 날짜의 00:00:00 ~ 23:59:59
start = pd.to_datetime(date_range[0])
end = pd.to_datetime(date_range[1]) + pd.Timedelta(hours=23, minutes=59, seconds=59)
mask = (df_temu["order date"] >= start) & (df_temu["order date"] <= end)
df_view = df_temu[mask]

# === KPI (Shipped + Delivered) & Canceled 따로 ===
sold_mask = df_view["order item status"].str.lower().isin(["shipped", "delivered"])
df_sold = df_view[sold_mask]
qty_sum = pd.to_numeric(df_sold["quantity shipped"], errors="coerce").fillna(0).sum()
sales_sum = pd.to_numeric(df_sold["base price total"], errors="coerce").fillna(0).sum()
aov = sales_sum / qty_sum if qty_sum > 0 else 0

cancel_mask = df_view["order item status"].str.lower() == "canceled"
cancel_qty = pd.to_numeric(df_view[cancel_mask]["quantity shipped"], errors="coerce").fillna(0).sum()

# === KPI 비교 (이전 동일 기간)
period_days = (end - start).days + 1
prev_start = start - pd.Timedelta(days=period_days)
prev_end = end - pd.Timedelta(days=period_days)
prev_mask = (df_temu["order date"] >= prev_start) & (df_temu["order date"] <= prev_end)
df_prev = df_temu[prev_mask]
prev_sold = df_prev[df_prev["order item status"].str.lower().isin(["shipped", "delivered"])]
prev_qty = pd.to_numeric(prev_sold["quantity shipped"], errors="coerce").fillna(0).sum()
prev_sales = pd.to_numeric(prev_sold["base price total"], errors="coerce").fillna(0).sum()
prev_aov = prev_sales / prev_qty if prev_qty > 0 else 0
prev_cancel = pd.to_numeric(df_prev[df_prev["order item status"].str.lower()=="canceled"]["quantity shipped"], errors="coerce").fillna(0).sum()

def kpi_delta(now, prev):
    if prev == 0: return ""
    pct = (now-prev)/prev*100
    color = "red" if pct < 0 else "green"
    arrow = "▼" if pct < 0 else "▲"
    return f"<span style='color:{color}; font-size:0.95em;'>{arrow} {pct:.1f}%</span>"

# === KPI 네모 카드 한 줄 & 증감 아래 표시
kpi_style = """
<style>
.kpi-card {display:inline-block; margin:0 10px 0 0; border-radius:18px; background:#fff; box-shadow:0 2px 8px #EEE; padding:20px 25px; min-width:170px; text-align:left; vertical-align:top;}
.kpi-main {font-size:2.1em; font-weight:700; margin-bottom:0;}
.kpi-label {font-size:1em; color:#444; margin-bottom:2px;}
.kpi-delta {font-size:1em; margin-top:2px;}
</style>
"""
st.markdown(kpi_style, unsafe_allow_html=True)
st.markdown("<div style='display:flex;'>"
            f"<div class='kpi-card'><div class='kpi-label'>Total Order Amount</div><div class='kpi-main'>${sales_sum:,.2f}</div><div class='kpi-delta'>{kpi_delta(sales_sum, prev_sales)}</div></div>"
            f"<div class='kpi-card'><div class='kpi-label'>Total Order Quantity</div><div class='kpi-main'>{int(qty_sum):,}</div><div class='kpi-delta'>{kpi_delta(qty_sum, prev_qty)}</div></div>"
            f"<div class='kpi-card'><div class='kpi-label'>AOV</div><div class='kpi-main'>${aov:,.2f}</div><div class='kpi-delta'>{kpi_delta(aov, prev_aov)}</div></div>"
            f"<div class='kpi-card'><div class='kpi-label'>Canceled Order</div><div class='kpi-main'>{int(cancel_qty):,}</div><div class='kpi-delta'>{kpi_delta(cancel_qty, prev_cancel)}</div></div>"
            "</div>", unsafe_allow_html=True)

    
# === 일별 그래프
st.subheader("일별 판매 추이")
daily = df_sold.groupby("order date").agg({
    "quantity shipped": "sum",
    "base price total": "sum"
}).reset_index().sort_values("order date")
st.line_chart(daily.set_index("order date")[["quantity shipped", "base price total"]])

# === 베스트셀러 10: (이미지+스타일넘버+판매수량 표로, 숫자X)
st.subheader("Best Seller 10")
best10 = (
    df_sold.groupby("product number")["quantity shipped"].sum().reset_index()
    .sort_values("quantity shipped", ascending=False).head(10)
)
# 이미지 링크 merge
df_info['product number'] = df_info['product number'].astype(str).str.strip().str.upper()
best10['product number'] = best10['product number'].astype(str).str.strip().str.upper()
best10 = best10.merge(df_info[['product number','image']], on='product number', how='left')

def render_img_table(df):
    # HTML 표 생성 (이미지+스타일넘버+판매갯수)
    html = "<table style='width:80%;text-align:center;'><tr><th></th><th>Style</th><th>Sold</th></tr>"
    for _, row in df.iterrows():
        img_tag = f"<img src='{row['image']}' width='60'>" if pd.notna(row['image']) and str(row['image']).startswith("http") else ""
        html += f"<tr><td>{img_tag}</td><td>{row['product number']}</td><td>{int(row['quantity shipped'])}</td></tr>"
    html += "</table>"
    return html

st.markdown(render_img_table(best10), unsafe_allow_html=True)
