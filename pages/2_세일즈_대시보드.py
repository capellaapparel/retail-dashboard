import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from dateutil import parser, relativedelta

# ========== 1. 데이터 로딩 ==========

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
    sheet = client.open_by_url("https://docs.google.com/spreadsheets/d/1oyVzCgGK1Q3Qi_sbYwE-wKG6SArnfUDRe7rQfGOF-Eo").worksheet(sheet_name)
    data = sheet.get_all_records()
    df = pd.DataFrame(data)
    df.columns = [c.lower().strip() for c in df.columns]
    return df

# ========== 2. 날짜 파서 ==========
def parse_temudate(dt):
    try:
        return parser.parse(str(dt).split('(')[0].strip(), fuzzy=True)
    except Exception:
        return pd.NaT

def parse_sheindate(dt):
    try:
        return pd.to_datetime(str(dt), errors="coerce")
    except:
        return pd.NaT

# ========== 3. 데이터 준비 ==========
df_temu = load_google_sheet("TEMU_SALES")
df_shein = load_google_sheet("SHEIN_SALES")
df_info = load_google_sheet("PRODUCT_INFO")

df_temu["order date"] = df_temu["purchase date"].apply(parse_temudate)
df_shein["order date"] = df_shein["order processed on"].apply(parse_sheindate)

# === 이미지 빠른 lookup을 위한 dict (스타일번호: 이미지URL)
info_img = {str(row["product number"]).strip().upper(): row.get("image", "") for _, row in df_info.iterrows()}

# ========== 4. UI ==========

st.set_page_config(page_title="세일즈 대시보드", layout="wide")
st.title("세일즈 대시보드")

# --- 플랫폼 선택(항상 위!) ---
platform = st.radio("플랫폼 선택", ["TEMU", "SHEIN", "BOTH"], horizontal=True)

# --- date_range 키, platform 따라 date_input 범위 유지 ---
def get_date_range(date_col):
    min_date, max_date = date_col.min().date(), date_col.max().date()
    if "sales_date_range" not in st.session_state:
        st.session_state["sales_date_range"] = (min_date, max_date)
    return min_date, max_date

if platform == "TEMU":
    date_col = df_temu["order date"].dropna()
elif platform == "SHEIN":
    date_col = df_shein["order date"].dropna()
else:
    date_col = pd.concat([df_temu["order date"].dropna(), df_shein["order date"].dropna()])

min_date, max_date = get_date_range(date_col)
date_range = st.date_input("조회 기간", value=st.session_state["sales_date_range"],
                          min_value=min_date, max_value=max_date, key="sales_date_range")
start = pd.to_datetime(date_range[0])
end = pd.to_datetime(date_range[1]) + pd.Timedelta(hours=23, minutes=59, seconds=59)

# ========== 5. KPI 집계 함수 ==========
def get_kpi_temu(df):
    sold_mask = df["order item status"].str.lower().isin(["shipped", "delivered"])
    df_sold = df[sold_mask]
    qty_sum = pd.to_numeric(df_sold["quantity shipped"], errors="coerce").fillna(0).sum()
    sales_sum = pd.to_numeric(df_sold["base price total"], errors="coerce").fillna(0).sum()
    aov = sales_sum / qty_sum if qty_sum > 0 else 0
    cancel_mask = df["order item status"].str.lower() == "canceled"
    cancel_qty = pd.to_numeric(df[cancel_mask]["quantity shipped"], errors="coerce").fillna(0).sum()
    return sales_sum, qty_sum, aov, cancel_qty, df_sold

def get_kpi_shein(df):
    # "Customer Refunded"만 캔슬로 보고, 나머지는 모두 정상
    df = df.copy()
    normal_mask = ~df["order status"].str.lower().eq("customer refunded")
    df_sold = df[normal_mask]
    qty_sum = len(df_sold)
    sales_sum = pd.to_numeric(df_sold["product price"], errors="coerce").fillna(0).sum()
    aov = sales_sum / qty_sum if qty_sum > 0 else 0
    cancel_qty = (df["order status"].str.lower() == "customer refunded").sum()
    return sales_sum, qty_sum, aov, cancel_qty, df_sold

def get_kpi_both(df_temu, df_shein):
    sales1, qty1, aov1, cancel1, df_sold1 = get_kpi_temu(df_temu)
    sales2, qty2, aov2, cancel2, df_sold2 = get_kpi_shein(df_shein)
    sales_sum = sales1 + sales2
    qty_sum = qty1 + qty2
    aov = sales_sum / qty_sum if qty_sum > 0 else 0
    cancel_qty = cancel1 + cancel2
    df_sold = pd.concat([df_sold1, df_sold2], ignore_index=True)
    return sales_sum, qty_sum, aov, cancel_qty, df_sold

# === 이전 기간 (동일 일수만큼) 집계 ===
period_days = (end - start).days + 1
prev_start = start - pd.Timedelta(days=period_days)
prev_end = end - pd.Timedelta(days=period_days) + pd.Timedelta(hours=23, minutes=59, seconds=59)

if platform == "TEMU":
    df_view = df_temu[(df_temu["order date"] >= start) & (df_temu["order date"] <= end)]
    df_prev = df_temu[(df_temu["order date"] >= prev_start) & (df_temu["order date"] <= prev_end)]
    sales_sum, qty_sum, aov, cancel_qty, df_sold = get_kpi_temu(df_view)
    prev_sales, prev_qty, prev_aov, prev_cancel, _ = get_kpi_temu(df_prev)
elif platform == "SHEIN":
    df_view = df_shein[(df_shein["order date"] >= start) & (df_shein["order date"] <= end)]
    df_prev = df_shein[(df_shein["order date"] >= prev_start) & (df_shein["order date"] <= prev_end)]
    sales_sum, qty_sum, aov, cancel_qty, df_sold = get_kpi_shein(df_view)
    prev_sales, prev_qty, prev_aov, prev_cancel, _ = get_kpi_shein(df_prev)
else:
    df_view_temu = df_temu[(df_temu["order date"] >= start) & (df_temu["order date"] <= end)]
    df_prev_temu = df_temu[(df_temu["order date"] >= prev_start) & (df_temu["order date"] <= prev_end)]
    df_view_shein = df_shein[(df_shein["order date"] >= start) & (df_shein["order date"] <= end)]
    df_prev_shein = df_shein[(df_shein["order date"] >= prev_start) & (df_shein["order date"] <= prev_end)]
    sales_sum, qty_sum, aov, cancel_qty, df_sold = get_kpi_both(df_view_temu, df_view_shein)
    prev_sales, prev_qty, prev_aov, prev_cancel, _ = get_kpi_both(df_prev_temu, df_prev_shein)

def kpi_delta(now, prev):
    if prev == 0: return ""
    pct = (now-prev)/prev*100
    color = "red" if pct < 0 else "green"
    arrow = "▼" if pct < 0 else "▲"
    return f"<span style='color:{color}; font-size:0.9em;'>{arrow} {pct:.1f}%</span>"

# === KPI 네모 카드 한줄 (숫자 폰트 자동 줄임)
kpi_style = """
<style>
.kpi-row {display:flex; flex-wrap:wrap; gap:16px;}
.kpi-card {flex:1; min-width:150px; border-radius:16px; background:#fff; box-shadow:0 2px 8px #eee; padding:18px 12px; margin:0 0 12px 0; text-align:center;}
.kpi-main {font-size:2.0em; font-weight:700; margin-bottom:0; line-height:1.1; word-break:break-all;}
.kpi-label {font-size:1em; color:#444; margin-bottom:2px;}
.kpi-delta {font-size:1em; margin-top:2px;}
</style>
"""
st.markdown(kpi_style, unsafe_allow_html=True)
st.markdown(
    "<div class='kpi-row'>"
    f"<div class='kpi-card'><div class='kpi-label'>Total Order Amount</div><div class='kpi-main' style='font-size:1.5em'>
    if sales_sum > 1e6:
    sales_sum_str = f"${sales_sum:,.0f}"
else:
    sales_sum_str = f"${sales_sum:,.2f}"
    # KPI 카드 HTML
st.markdown(
    "<div class='kpi-row'>"
    f"<div class='kpi-card'><div class='kpi-label'>Total Order Amount</div><div class='kpi-main' style='font-size:1.5em'>{sales_sum_str}</div><div class='kpi-delta'>{kpi_delta(sales_sum, prev_sales)}</div></div>"
    f"<div class='kpi-card'><div class='kpi-label'>Total Order Quantity</div><div class='kpi-main'>{int(qty_sum):,}</div><div class='kpi-delta'>{kpi_delta(qty_sum, prev_qty)}</div></div>"
    f"<div class='kpi-card'><div class='kpi-label'>AOV</div><div class='kpi-main'>${aov:,.2f}</div><div class='kpi-delta'>{kpi_delta(aov, prev_aov)}</div></div>"
    f"<div class='kpi-card' style='min-width:100px; max-width:120px;'><div class='kpi-label'>Canceled Order</div><div class='kpi-main'>{int(cancel_qty):,}</div><div class='kpi-delta'>{kpi_delta(cancel_qty, prev_cancel)}</div></div>"
    "</div>", unsafe_allow_html=True
)

# === 일별 추이 ===
st.subheader("일별 판매 추이")
if platform == "TEMU":
    chart = df_sold.groupby("order date").agg(qty=("quantity shipped", "sum"), sales=("base price total", "sum")).reset_index()
elif platform == "SHEIN":
    chart = df_sold.groupby("order date").agg(qty=("product description", "count"), sales=("product price", "sum")).reset_index()
else:
    chart_temu = df_temu[df_temu["order date"].between(start, end) & df_temu["order item status"].str.lower().isin(["shipped","delivered"])]
    chart_shein = df_shein[df_shein["order date"].between(start, end) & ~df_shein["order status"].str.lower().eq("customer refunded")]
    chart = pd.concat([
        chart_temu.groupby("order date").agg(qty=("quantity shipped", "sum"), sales=("base price total", "sum")),
        chart_shein.groupby("order date").agg(qty=("product description", "count"), sales=("product price", "sum"))
    ]).groupby("order date").sum().reset_index()
chart = chart.sort_values("order date")
st.line_chart(chart.set_index("order date")[["qty", "sales"]])

# === 베스트셀러 10 ===
st.subheader("Best Seller 10")
if platform == "TEMU":
    top10 = df_sold.groupby("product number")["quantity shipped"].sum().reset_index().sort_values("quantity shipped", ascending=False).head(10)
    top10["이미지"] = top10["product number"].apply(lambda x: info_img.get(str(x).strip().upper(),""))
    top10 = top10[["이미지","product number","quantity shipped"]]
elif platform == "SHEIN":
    top10 = df_sold.groupby("product description").size().reset_index(name="qty").sort_values("qty", ascending=False).head(10)
    top10["이미지"] = top10["product description"].apply(lambda x: info_img.get(str(x).strip().upper(),""))
    top10 = top10[["이미지","product description","qty"]].rename(columns={"product description":"product number","qty":"quantity shipped"})
else:
    t1 = df_temu[df_temu["order date"].between(start,end) & df_temu["order item status"].str.lower().isin(["shipped","delivered"])]
    t2 = df_shein[df_shein["order date"].between(start,end) & ~df_shein["order status"].str.lower().eq("customer refunded")]
    t1_agg = t1.groupby("product number")["quantity shipped"].sum()
    t2_agg = t2.groupby("product description").size()
    both = pd.concat([t1_agg, t2_agg]).groupby(level=0).sum().reset_index()
    both.columns = ["product number", "quantity shipped"]
    both["이미지"] = both["product number"].apply(lambda x: info_img.get(str(x).strip().upper(),""))
    top10 = both.sort_values("quantity shipped", ascending=False).head(10)
    top10 = top10[["이미지","product number","quantity shipped"]]

# === 표 스타일: 이미지 + 스타일넘버 + 수량 ===
def render_image_table(df):
    html = """
    <style>
    .bstbl {width:100%; border-collapse:collapse; background:#fff;}
    .bstbl th,.bstbl td {border:0; border-bottom:1px solid #eee; padding:6px 8px; text-align:left;}
    .bstbl th {background:#f7f7f7; font-weight:600;}
    .bstbl img {max-width:60px; max-height:65px; border-radius:12px;}
    </style>
    <table class='bstbl'><tr>
        <th>이미지</th><th>스타일번호</th><th>판매수량</th></tr>
    """
    for _, r in df.iterrows():
        html += f"<tr><td><img src='{r['이미지']}'></td><td>{r['product number']}</td><td>{int(r['quantity shipped'])}</td></tr>"
    html += "</table>"
    st.markdown(html, unsafe_allow_html=True)

render_image_table(top10)
