import streamlit as st
import pandas as pd
from dateutil import parser
import datetime

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

def kpi_delta(now, prev):
    if prev == 0: return ""
    pct = (now-prev)/prev*100
    color = "red" if pct < 0 else "#11b500"
    arrow = "▼" if pct < 0 else "▲"
    return f"<span style='color:{color}; font-size:0.97em;'>{arrow} {abs(pct):.1f}%</span>"

# ====== 데이터 불러오기 ======
df_temu = load_google_sheet("TEMU_SALES")
df_shein = load_google_sheet("SHEIN_SALES")
df_info = load_google_sheet("PRODUCT_INFO")

df_temu["order date"] = df_temu["purchase date"].apply(parse_temudate)
df_shein["order date"] = df_shein["order processed on"].apply(parse_sheindate)
info_img_dict = dict(zip(df_info["product number"].astype(str), df_info["image"]))

def temu_agg(df, start, end):
    mask = (df["order date"] >= start) & (df["order date"] <= end)
    df = df[mask].copy()
    sold_mask = df["order item status"].str.lower().isin(["shipped", "delivered"])
    df_sold = df[sold_mask]
    qty_sum = pd.to_numeric(df_sold["quantity shipped"], errors="coerce").fillna(0).sum()
    sales_sum = pd.to_numeric(df_sold["base price total"], errors="coerce").fillna(0).sum()
    aov = sales_sum / qty_sum if qty_sum > 0 else 0
    # Canceled는 quantity purchased로!
    cancel_qty = pd.to_numeric(df[df["order item status"].str.lower()=="canceled"]["quantity purchased"], errors="coerce").fillna(0).sum()
    return sales_sum, qty_sum, aov, cancel_qty, df_sold

def shein_agg(df, start, end):
    mask = (df["order date"] >= start) & (df["order date"] <= end)
    df = df[mask].copy()
    df_sold = df[~df["order status"].str.lower().isin(["customer refunded"])]
    qty_sum = df_sold.shape[0]
    sales_sum = pd.to_numeric(df_sold["product price"], errors="coerce").fillna(0).sum()
    aov = sales_sum / qty_sum if qty_sum > 0 else 0
    cancel_qty = df[df["order status"].str.lower()=="customer refunded"].shape[0]
    return sales_sum, qty_sum, aov, cancel_qty, df_sold

# ---- 스타일 ---
st.markdown("""
<style>
.center-container {max-width:1320px; margin:0 auto;}
.kpi-row {display: flex; width: 100%; justify-content: space-between;}
.kpi-card {
    display:inline-block; border-radius:18px;
    background:#fff; box-shadow:0 2px 10px #EAEAEA;
    padding:19px 32px 16px 30px;
    width: 24.5%;
    min-width:220px; max-width:350px;
    text-align:left; vertical-align:top; transition:box-shadow .2s;
    margin: 0 0.5% 0 0;
}
.kpi-main {font-size:2.01em; font-weight:700; margin-bottom:0;}
.kpi-label {font-size:1.07em; color:#444; margin-bottom:3px;}
.kpi-delta {font-size:1.01em; margin-top:3px;}
.kpi-card:last-child {margin-right: 0;}
.kpi-card:hover {box-shadow:0 4px 14px #d1e1fa;}
.best-table {width:100%!important; background:#fff;}
.best-table th {background:#f6f8fa; font-weight:600; color:#3c3c3c;}
.best-table td, .best-table th {padding:11px 17px !important; text-align:center;}
.best-table tr {border-bottom:1px solid #f2f2f2;}
.best-table img {border-radius:10px; box-shadow:0 2px 8px #EEE;}
@media (max-width:1400px) {.center-container{max-width:1000px;}}
@media (max-width:1000px) {.center-container{max-width:800px;}}
</style>
""", unsafe_allow_html=True)

st.title("세일즈 대시보드")

# --- 날짜 설정: 오늘을 기본으로, 범위 안에만 맞게 ---
min_date = min(df_temu["order date"].min(), df_shein["order date"].min())
max_date = max(df_temu["order date"].max(), df_shein["order date"].max())
today = datetime.datetime.now().date()
if isinstance(min_date, pd.Timestamp): min_date = min_date.date()
if isinstance(max_date, pd.Timestamp): max_date = max_date.date()

def clip_date(dt):
    if dt < min_date: return min_date
    if dt > max_date: return max_date
    return dt

default_range = (clip_date(today), clip_date(today))
if "sales_date_range" not in st.session_state:
    st.session_state["sales_date_range"] = default_range

platforms = ["TEMU", "SHEIN", "BOTH"]
colf1, colf2 = st.columns([2, 8])
with colf1:
    platform = st.radio("플랫폼 선택", platforms, horizontal=True, key="platform_radio")
with colf2:
    date_range = st.date_input(
        "조회 기간",
        st.session_state["sales_date_range"],
        min_value=min_date,
        max_value=max_date,
        key="sales_date_input"
    )
    st.session_state["sales_date_range"] = date_range

# 날짜 range: 00:00~23:59까지 포함
if isinstance(date_range, tuple):
    start = pd.to_datetime(date_range[0])
    end = pd.to_datetime(date_range[1]) + pd.Timedelta(hours=23, minutes=59, seconds=59)
else:
    start = pd.to_datetime(date_range)
    end = start + pd.Timedelta(hours=23, minutes=59, seconds=59)
period_days = (end - start).days + 1
prev_start = start - pd.Timedelta(days=period_days)
prev_end = end - pd.Timedelta(days=period_days)

# === KPI, Best Seller ===
if platform == "TEMU":
    sales_sum, qty_sum, aov, cancel_qty, df_sold = temu_agg(df_temu, start, end)
    prev_sales, prev_qty, prev_aov, prev_cancel, _ = temu_agg(df_temu, prev_start, prev_end)
elif platform == "SHEIN":
    sales_sum, qty_sum, aov, cancel_qty, df_sold = shein_agg(df_shein, start, end)
    prev_sales, prev_qty, prev_aov, prev_cancel, _ = shein_agg(df_shein, prev_start, prev_end)
else:  # BOTH
    ss1, q1, a1, c1, df1 = temu_agg(df_temu, start, end)
    ss2, q2, a2, c2, df2 = shein_agg(df_shein, start, end)
    sales_sum, qty_sum, cancel_qty = ss1 + ss2, q1 + q2, c1 + c2
    aov = sales_sum / qty_sum if qty_sum > 0 else 0
    df_sold = pd.concat([df1, df2])
    # prev
    pss1, pq1, pa1, pc1, _ = temu_agg(df_temu, prev_start, prev_end)
    pss2, pq2, pa2, pc2, _ = shein_agg(df_shein, prev_start, prev_end)
    prev_sales, prev_qty, prev_cancel = pss1 + pss2, pq1 + pq2, pc1 + pc2
    prev_aov = prev_sales / prev_qty if prev_qty > 0 else 0

# --- KPI 카드 ---
sales_sum_str = f"${sales_sum:,.2f}"
kpi_box = (
    f"<div class='center-container'><div class='kpi-row'>"
    f"<div class='kpi-card'><div class='kpi-label'>Total Order Amount</div><div class='kpi-main'>{sales_sum_str}</div><div class='kpi-delta'>{kpi_delta(sales_sum, prev_sales)}</div></div>"
    f"<div class='kpi-card'><div class='kpi-label'>Total Order Quantity</div><div class='kpi-main'>{int(qty_sum):,}</div><div class='kpi-delta'>{kpi_delta(qty_sum, prev_qty)}</div></div>"
    f"<div class='kpi-card'><div class='kpi-label'>AOV</div><div class='kpi-main'>${aov:,.2f}</div><div class='kpi-delta'>{kpi_delta(aov, prev_aov)}</div></div>"
    f"<div class='kpi-card'><div class='kpi-label'>Canceled Order</div><div class='kpi-main'>{int(cancel_qty):,}</div><div class='kpi-delta'>{kpi_delta(cancel_qty, prev_cancel)}</div></div>"
    "</div></div>"
)
st.markdown(kpi_box, unsafe_allow_html=True)

# --- 일별 판매 그래프 ---
st.subheader("일별 판매 추이")
try:
    if platform == "SHEIN":
        daily = df_sold.groupby("order date").agg({"product price":"sum"}).reset_index().rename(columns={"product price":"Total Sales"})
        daily["qty"] = 1
        daily = daily.groupby("order date").agg({"Total Sales":"sum", "qty":"sum"}).reset_index()
        daily = daily.set_index("order date")
        if not daily.empty and "qty" in daily.columns and "Total Sales" in daily.columns:
            st.line_chart(daily[["qty", "Total Sales"]])
        else:
            st.info("해당 기간에 데이터가 없습니다.")
    elif platform == "TEMU":
        daily = df_sold.groupby("order date").agg({
            "quantity shipped": "sum",
            "base price total": "sum"
        }).reset_index().rename(columns={"quantity shipped":"qty", "base price total":"Total Sales"})
        daily = daily.set_index("order date")
        if not daily.empty and "qty" in daily.columns and "Total Sales" in daily.columns:
            st.line_chart(daily[["qty", "Total Sales"]])
        else:
            st.info("해당 기간에 데이터가 없습니다.")
    else:
        # BOTH (qty: temu qty + shein qty, sales: temu+shein)
        temu_daily = df_temu[(df_temu["order date"] >= start) & (df_temu["order date"] <= end)]
        temu_daily = temu_daily[temu_daily["order item status"].str.lower().isin(["shipped", "delivered"])]
        temu_group = temu_daily.groupby("order date").agg({"quantity shipped":"sum", "base price total":"sum"})
        shein_daily = df_shein[(df_shein["order date"] >= start) & (df_shein["order date"] <= end)]
        shein_daily = shein_daily[~shein_daily["order status"].str.lower().isin(["customer refunded"])]
        shein_group = shein_daily.groupby("order date").agg({"product price":"sum"})
        shein_group["qty"] = 1
        shein_group = shein_group.groupby("order date").agg({"qty":"sum", "product price":"sum"})
        both_daily = pd.DataFrame({
            "qty": temu_group["quantity shipped"].fillna(0).add(shein_group["qty"].fillna(0), fill_value=0),
            "Total Sales": temu_group["base price total"].fillna(0).add(shein_group["product price"].fillna(0), fill_value=0)
        })
        if not both_daily.empty and "qty" in both_daily.columns and "Total Sales" in both_daily.columns:
            st.line_chart(both_daily[["qty", "Total Sales"]])
        else:
            st.info("해당 기간에 데이터가 없습니다.")
except Exception as e:
    st.info("해당 기간에 데이터가 없습니다.")

# --- 베스트셀러 TOP 10: 사진, 스타일넘버, 판매량 ---
st.subheader("Best Seller 10")

def make_img_tag(url):
    if pd.notna(url) and str(url).startswith("http"):
        return f"<img src='{url}' style='width:60px;height:auto;'>"
    return ""

if platform == "BOTH":
    temu_best = df_temu[(df_temu["order date"] >= start) & (df_temu["order date"] <= end)]
    shein_best = df_shein[(df_shein["order date"] >= start) & (df_shein["order date"] <= end)]
    temu_count = temu_best[temu_best["order item status"].str.lower().isin(["shipped", "delivered"])]
    temu_count = temu_count.groupby("product number")["quantity shipped"].sum()
    shein_count = shein_best[~shein_best["order status"].str.lower().isin(["customer refunded"])]
    shein_count = shein_count.groupby("product description").size()
    summary = pd.DataFrame({
        "TEMU Qty": temu_count,
        "SHEIN Qty": shein_count
    }).fillna(0)
    summary["TEMU Qty"] = summary["TEMU Qty"].astype(int)
    summary["SHEIN Qty"] = summary["SHEIN Qty"].astype(int)
    summary["Sold Qty"] = summary["TEMU Qty"] + summary["SHEIN Qty"]
    summary = summary.sort_values("Sold Qty", ascending=False).head(10)
    summary["Image"] = summary.index.map(info_img_dict)
    summary["Sold Qty"] = (
        summary["Sold Qty"].astype(int).astype(str) + 
        "<br><span style='color:#bbb; font-size:0.97em'>(TEMU: " +
        summary["TEMU Qty"].astype(str) + ", SHEIN: " + summary["SHEIN Qty"].astype(str) + ")</span>"
    )
    summary = summary.reset_index().rename(columns={"index": "Style Number"})
    summary = summary[["Image", "Style Number", "Sold Qty"]]
    summary["Image"] = summary["Image"].apply(make_img_tag)
    st.markdown(
        summary.to_html(escape=False, index=False, classes="best-table"),
        unsafe_allow_html=True
    )
elif platform == "SHEIN":
    best = df_sold.groupby("product description").size().reset_index(name="판매수량").sort_values("판매수량", ascending=False).head(10)
    best["이미지"] = best["product description"].astype(str).map(info_img_dict)
    best = best[["이미지", "product description", "판매수량"]]
    best.columns = ["Image", "Style Number", "Sold Qty"]
    best["Image"] = best["Image"].apply(make_img_tag)
    st.markdown(
        best.to_html(escape=False, index=False, classes="best-table"),
        unsafe_allow_html=True
    )
else:
    best = df_sold.groupby("product number")["quantity shipped"].sum().reset_index().sort_values("quantity shipped", ascending=False).head(10)
    best["이미지"] = best["product number"].astype(str).map(info_img_dict)
    best = best[["이미지", "product number", "quantity shipped"]]
    best.columns = ["Image", "Style Number", "Sold Qty"]
    best["Image"] = best["Image"].apply(make_img_tag)
    st.markdown(
        best.to_html(escape=False, index=False, classes="best-table"),
        unsafe_allow_html=True
    )
