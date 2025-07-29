import streamlit as st
import pandas as pd
from dateutil import parser
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# === 구글 시트 데이터 로딩 ===
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

def parse_sheindate(dt):
    try:
        return pd.to_datetime(str(dt), errors="coerce", infer_datetime_format=True)
    except:
        return pd.NaT

# === 데이터 로딩 ===
df_temu = load_google_sheet("TEMU_SALES")
df_shein = load_google_sheet("SHEIN_SALES")
df_info = load_google_sheet("PRODUCT_INFO")

# 날짜 파싱
df_temu["order date"] = df_temu["purchase date"].apply(parse_temudate)
df_shein["order date"] = df_shein["order processed on"].apply(parse_sheindate)

# --- 플랫폼 필터 UI
platform = st.radio("플랫폼 선택", ["TEMU", "SHEIN", "BOTH"], horizontal=True)

# === 날짜필터 (00:00 ~ 23:59) ===
if platform == "TEMU":
    date_col = df_temu["order date"]
elif platform == "SHEIN":
    date_col = df_shein["order date"]
else:
    date_col = pd.concat([df_temu["order date"], df_shein["order date"]])

min_date, max_date = date_col.min().date(), date_col.max().date()
date_range = st.date_input("조회 기간", (min_date, max_date))
start = pd.to_datetime(date_range[0])
end = pd.to_datetime(date_range[1]) + pd.Timedelta(hours=23, minutes=59, seconds=59)

# === 데이터 필터링 함수 ===
def filter_temu(df, start, end):
    mask = (df["order date"] >= start) & (df["order date"] <= end)
    df = df[mask]
    sold_mask = df["order item status"].str.lower().isin(["shipped", "delivered"])
    cancel_mask = df["order item status"].str.lower() == "canceled"
    df_sold = df[sold_mask]
    df_cancel = df[cancel_mask]
    qty = pd.to_numeric(df_sold["quantity shipped"], errors="coerce").fillna(0).sum()
    sales = pd.to_numeric(df_sold["base price total"], errors="coerce").fillna(0).sum()
    aov = sales / qty if qty > 0 else 0
    cancel_qty = pd.to_numeric(df_cancel["quantity shipped"], errors="coerce").fillna(0).sum()
    return df_sold, qty, sales, aov, cancel_qty

def filter_shein(df, start, end):
    mask = (df["order date"] >= start) & (df["order date"] <= end)
    df = df[mask]
    # 상태가 refunded인 경우만 cancel로 처리, 나머지는 다 판매
    is_cancel = df["order status"].str.lower().str.strip() == "customer refunded"
    df_cancel = df[is_cancel]
    df_sold = df[~is_cancel]
    qty = len(df_sold)
    sales = pd.to_numeric(df_sold["product price"], errors="coerce").fillna(0).sum()
    aov = sales / qty if qty > 0 else 0
    cancel_qty = len(df_cancel)
    return df_sold, qty, sales, aov, cancel_qty

# --- 실제 데이터 분기 및 통합
if platform == "TEMU":
    df_sold, qty_sum, sales_sum, aov, cancel_qty = filter_temu(df_temu, start, end)
elif platform == "SHEIN":
    df_sold, qty_sum, sales_sum, aov, cancel_qty = filter_shein(df_shein, start, end)
else:
    df_sold_temu, qty_temu, sales_temu, aov_temu, cancel_temu = filter_temu(df_temu, start, end)
    df_sold_shein, qty_shein, sales_shein, aov_shein, cancel_shein = filter_shein(df_shein, start, end)
    qty_sum = qty_temu + qty_shein
    sales_sum = sales_temu + sales_shein
    aov = sales_sum / qty_sum if qty_sum > 0 else 0
    cancel_qty = cancel_temu + cancel_shein
    df_sold = pd.concat([df_sold_temu, df_sold_shein], sort=False)

# === KPI 카드 (증감 비교는 TEMU만 일단)
def kpi_delta(now, prev):
    if prev == 0: return ""
    pct = (now-prev)/prev*100
    color = "red" if pct < 0 else "green"
    arrow = "▼" if pct < 0 else "▲"
    return f"<span style='color:{color}; font-size:0.95em;'>{arrow} {pct:.1f}%</span>"

# 이전 기간 계산 (기간동일)
period_days = (end - start).days + 1
prev_start = start - pd.Timedelta(days=period_days)
prev_end = end - pd.Timedelta(days=period_days)

if platform == "TEMU":
    prev_sold, prev_qty, prev_sales, prev_aov, prev_cancel = filter_temu(df_temu, prev_start, prev_end)
elif platform == "SHEIN":
    prev_sold, prev_qty, prev_sales, prev_aov, prev_cancel = filter_shein(df_shein, prev_start, prev_end)
else:
    prev_temu, qty_temu, sales_temu, aov_temu, cancel_temu = filter_temu(df_temu, prev_start, prev_end)
    prev_shein, qty_shein, sales_shein, aov_shein, cancel_shein = filter_shein(df_shein, prev_start, prev_end)
    prev_qty = qty_temu + qty_shein
    prev_sales = sales_temu + sales_shein
    prev_aov = prev_sales / prev_qty if prev_qty > 0 else 0
    prev_cancel = cancel_temu + cancel_shein

# --- KPI 네모 카드 스타일 (크기 자동)
kpi_style = """
<style>
.kpi-flex {display:flex; flex-wrap:nowrap; gap:18px;}
.kpi-card {
    border-radius:18px; background:#fff;
    box-shadow:0 2px 8px #EEE;
    padding:16px 16px 12px 20px;
    text-align:left; vertical-align:top;
    display:flex; flex-direction:column; justify-content:center;
}
.kpi-amount {min-width:230px; max-width:260px; flex:2;}
.kpi-mid    {min-width:160px; max-width:190px; flex:1.1;}
.kpi-small  {min-width:90px;  max-width:100px; flex:0.6;}
.kpi-main {font-size:2.0em; font-weight:700; margin-bottom:0; line-height:1.09;}
.kpi-label {font-size:1em; color:#444; margin-bottom:2px;}
.kpi-delta {font-size:1em; margin-top:2px;}
</style>
"""
st.markdown(kpi_style, unsafe_allow_html=True)
st.markdown(
    "<div class='kpi-flex'>"
    f"<div class='kpi-card kpi-amount'><div class='kpi-label'>Total Order Amount</div><div class='kpi-main'>${sales_sum:,.2f}</div><div class='kpi-delta'>{kpi_delta(sales_sum, prev_sales)}</div></div>"
    f"<div class='kpi-card kpi-mid'><div class='kpi-label'>Total Order Quantity</div><div class='kpi-main'>{int(qty_sum):,}</div><div class='kpi-delta'>{kpi_delta(qty_sum, prev_qty)}</div></div>"
    f"<div class='kpi-card kpi-mid'><div class='kpi-label'>AOV</div><div class='kpi-main'>${aov:,.2f}</div><div class='kpi-delta'>{kpi_delta(aov, prev_aov)}</div></div>"
    f"<div class='kpi-card kpi-small'><div class='kpi-label'>Canceled Order</div><div class='kpi-main'>{int(cancel_qty):,}</div><div class='kpi-delta'>{kpi_delta(cancel_qty, prev_cancel)}</div></div>"
    "</div>",
    unsafe_allow_html=True
)

# === 일별 그래프 (판매수량, 매출)
st.subheader("일별 판매 추이")
if platform == "TEMU":
    daily = df_sold.groupby("order date").agg({
        "quantity shipped": "sum",
        "base price total": "sum"
    }).reset_index().sort_values("order date")
    st.line_chart(daily.set_index("order date")[["quantity shipped", "base price total"]])
elif platform == "SHEIN":
    daily = df_sold.groupby("order date").agg({
        "product price": "count"
    }).rename(columns={"product price": "qty"}).reset_index().sort_values("order date")
    daily["sales"] = pd.to_numeric(df_sold.groupby("order date")["product price"].sum())
    st.line_chart(daily.set_index("order date")[["qty", "sales"]])
else:
    # BOTH
    daily_temu = df_sold_temu.groupby("order date").agg({
        "quantity shipped": "sum",
        "base price total": "sum"
    }).rename(columns={"quantity shipped":"qty_temu", "base price total":"sales_temu"})
    daily_shein = df_sold_shein.groupby("order date").agg({
        "product price": "count"
    }).rename(columns={"product price":"qty_shein"})
    daily_shein["sales_shein"] = pd.to_numeric(df_sold_shein.groupby("order date")["product price"].sum())
    daily = pd.DataFrame(index=pd.date_range(start, end, freq='D'))
    if not daily_temu.empty:
        daily = daily.join(daily_temu, how="left")
    if not daily_shein.empty:
        daily = daily.join(daily_shein, how="left")
    daily = daily.fillna(0)
    daily["qty"] = daily.get("qty_temu", 0) + daily.get("qty_shein", 0)
    daily["sales"] = daily.get("sales_temu", 0) + daily.get("sales_shein", 0)
    st.line_chart(daily[["qty", "sales"]])

# === 베스트셀러 10
st.subheader("Best Seller 10")
if platform == "TEMU":
    best = (
        df_sold.groupby("product number")["quantity shipped"].sum()
        .reset_index()
        .sort_values("quantity shipped", ascending=False)
        .head(10)
    )
    best = best.merge(df_info[["product number", "image"]], how="left", on="product number")
    best["qty"] = best["quantity shipped"]
elif platform == "SHEIN":
    best = (
        df_sold.groupby("product description").size()
        .reset_index(name="qty")
        .sort_values("qty", ascending=False)
        .rename(columns={"product description": "product number"})
        .head(10)
    )
    best = best.merge(df_info[["product number", "image"]], how="left", on="product number")
else:
    best_temu = (
        df_sold_temu.groupby("product number")["quantity shipped"].sum()
        .reset_index()
        .rename(columns={"quantity shipped":"qty"})
    )
    best_shein = (
        df_sold_shein.groupby("product description").size()
        .reset_index(name="qty")
        .rename(columns={"product description":"product number"})
    )
    best = pd.concat([best_temu, best_shein]).groupby("product number")["qty"].sum().reset_index()
    best = best.sort_values("qty", ascending=False).head(10)
    best = best.merge(df_info[["product number", "image"]], how="left", on="product number")

table_html = """
    <table style='width:100%;text-align:center;border-collapse:separate;border-spacing:0 12px;font-size:1.04rem;'>
        <tr>
            <th style='width:80px'> </th>
            <th style='width:40%'>Style</th>
            <th style='width:30%'>Sold</th>
        </tr>
"""
for _, row in best.iterrows():
    img = f"<img src='{row['image']}' width='60' style='border-radius:10px'>" if isinstance(row['image'], str) and row['image'].startswith("http") else ""
    table_html += f"<tr style='background:white;border-radius:16px;box-shadow:0 2px 8px #eee;'><td>{img}</td><td>{row['product number']}</td><td style='font-weight:600'>{int(row['qty'])}</td></tr>"
table_html += "</table>"
st.markdown(table_html, unsafe_allow_html=True)
