

import streamlit as st
import pandas as pd
from dateutil import parser, relativedelta

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
    color = "red" if pct < 0 else "green"
    arrow = "▼" if pct < 0 else "▲"
    return f"<span style='color:{color}; font-size:0.95em;'>{arrow} {pct:.1f}%</span>"

# ====== 데이터 불러오기 ======
df_temu = load_google_sheet("TEMU_SALES")
df_shein = load_google_sheet("SHEIN_SALES")
df_info = load_google_sheet("PRODUCT_INFO")

# 날짜 파싱
df_temu["order date"] = df_temu["purchase date"].apply(parse_temudate)
df_shein["order date"] = df_shein["order processed on"].apply(parse_sheindate)

# 모든 style number, 이미지 정보 미리 추출
info_img_dict = dict(zip(df_info["product number"].astype(str), df_info["image"]))

# 1. TEMU Sales 집계
def temu_agg(df, start, end):
    mask = (df["order date"] >= start) & (df["order date"] <= end)
    df = df[mask].copy()
    sold_mask = df["order item status"].fillna("").str.lower().isin(["shipped", "delivered"])
    df_sold = df[sold_mask]
    qty_sum = pd.to_numeric(df_sold["quantity shipped"], errors="coerce").fillna(0).sum()
    sales_sum = pd.to_numeric(df_sold["base price total"], errors="coerce").fillna(0).sum()
    aov = sales_sum / qty_sum if qty_sum > 0 else 0
    # === 캔슬 오더 개선!
    st.write(df["order item status"].unique())
    cancel_mask = df["order item status"].fillna("").str.lower() == "canceled"
    cancel_qty = pd.to_numeric(df[cancel_mask]["quantity shipped"], errors="coerce").fillna(0).sum()
    return sales_sum, qty_sum, aov, cancel_qty, df_sold

# 2. SHEIN Sales 집계
def shein_agg(df, start, end):
    mask = (df["order date"] >= start) & (df["order date"] <= end)
    df = df[mask].copy()
    df_sold = df[~df["order status"].str.lower().isin(["customer refunded"])]
    qty_sum = df_sold.shape[0]  # 한 줄 한 개
    sales_sum = pd.to_numeric(df_sold["product price"], errors="coerce").fillna(0).sum()
    aov = sales_sum / qty_sum if qty_sum > 0 else 0
    cancel_qty = df[df["order status"].str.lower()=="customer refunded"].shape[0]
    return sales_sum, qty_sum, aov, cancel_qty, df_sold

# --- 대시보드 UI ---

st.title("세일즈 대시보드")

# 필터
platforms = ["TEMU", "SHEIN", "BOTH"]
# session_state로 날짜유지
if "sales_date_range" not in st.session_state:
    min_dt = min(df_temu["order date"].min(), df_shein["order date"].min())
    max_dt = max(df_temu["order date"].max(), df_shein["order date"].max())
    st.session_state["sales_date_range"] = (min_dt, max_dt)

platform = st.radio("플랫폼 선택", platforms, horizontal=True, key="platform_radio")
min_date = min(df_temu["order date"].min(), df_shein["order date"].min())
max_date = max(df_temu["order date"].max(), df_shein["order date"].max())
date_range = st.date_input("조회 기간", st.session_state["sales_date_range"], min_value=min_date, max_value=max_date, key="sales_date_input")
st.session_state["sales_date_range"] = date_range

# 날짜 range: 00:00~23:59까지 포함
start = pd.to_datetime(date_range[0])
end = pd.to_datetime(date_range[1]) + pd.Timedelta(hours=23, minutes=59, seconds=59)

# 이전 동일 기간 계산
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
    sales_sum = ss1 + ss2
    qty_sum = int(q1) + int(q2)   # <== 여기서 int로 합산!
    cancel_qty = int(c1) + int(c2)
    aov = sales_sum / qty_sum if qty_sum > 0 else 0
    df_sold = pd.concat([df1, df2], ignore_index=True)
    # prev
    pss1, pq1, pa1, pc1, _ = temu_agg(df_temu, prev_start, prev_end)
    pss2, pq2, pa2, pc2, _ = shein_agg(df_shein, prev_start, prev_end)
    prev_sales = pss1 + pss2
    prev_qty = int(pq1) + int(pq2)
    prev_cancel = int(pc1) + int(pc2)
    prev_aov = prev_sales / prev_qty if prev_qty > 0 else 0

# --- KPI 카드 스타일 ---
kpi_style = """
<style>
.kpi-card {
    display:inline-block;
    margin:0 10px 0 0;
    border-radius:18px;
    background:#fff;
    box-shadow:0 2px 8px #EEE;
    padding:20px 25px;
    min-width:220px;      /* 기존 170px → 220px으로 증가 */
    text-align:left;
    vertical-align:top;
}
.kpi-main {font-size:2.1em; font-weight:700; margin-bottom:0;}
.kpi-label {font-size:1em; color:#444; margin-bottom:2px;}
.kpi-delta {font-size:1em; margin-top:2px;}
</style>
"""
st.markdown(kpi_style, unsafe_allow_html=True)

# 숫자 포맷 분기
if sales_sum > 1e6:
    sales_sum_str = f"${sales_sum:,.0f}"
else:
    sales_sum_str = f"${sales_sum:,.2f}"

# KPI 카드 한 줄에 적용
st.markdown(kpi_style, unsafe_allow_html=True)
st.markdown(
    "<div class='center-container'><div style='display:flex;'>"
    f"<div class='kpi-card'><div class='kpi-label'>Total Order Amount</div><div class='kpi-main'>{sales_sum_str}</div><div class='kpi-delta'>{kpi_delta(sales_sum, prev_sales)}</div></div>"
    f"<div class='kpi-card'><div class='kpi-label'>Total Order Quantity</div><div class='kpi-main'>{int(qty_sum):,}</div><div class='kpi-delta'>{kpi_delta(qty_sum, prev_qty)}</div></div>"
    f"<div class='kpi-card'><div class='kpi-label'>AOV</div><div class='kpi-main'>${aov:,.2f}</div><div class='kpi-delta'>{kpi_delta(aov, prev_aov)}</div></div>"
    f"<div class='kpi-card'><div class='kpi-label'>Canceled Order</div><div class='kpi-main'>{int(cancel_qty):,}</div><div class='kpi-delta'>{kpi_delta(cancel_qty, prev_cancel)}</div></div>"
    "</div></div>", unsafe_allow_html=True
)
# --- 일별 판매 그래프 ---
st.subheader("일별 판매 추이")
if platform == "SHEIN":
    daily = df_sold.groupby("order date").agg({"product price":"sum"}).reset_index().rename(columns={"product price":"Total Sales"})
    daily["qty"] = 1
    daily = daily.groupby("order date").agg({"Total Sales":"sum", "qty":"sum"}).reset_index()
    st.line_chart(daily.set_index("order date")[["qty", "Total Sales"]])
elif platform == "TEMU":
    daily = df_sold.groupby("order date").agg({
        "quantity shipped": "sum",
        "base price total": "sum"
    }).reset_index().rename(columns={"quantity shipped":"qty", "base price total":"Total Sales"})
    st.line_chart(daily.set_index("order date")[["qty", "Total Sales"]])
else:
    # BOTH: 날짜별로 각각 groupby 후 merge(sum)
    daily_temu = df_temu[df_temu["order date"].between(start, end)]
    daily_temu = daily_temu[daily_temu["order item status"].str.lower().isin(["shipped", "delivered"])]
    temu_daily = daily_temu.groupby("order date").agg({
        "quantity shipped": "sum",
        "base price total": "sum"
    }).reset_index().rename(columns={"quantity shipped":"qty", "base price total":"Total Sales"})
    daily_shein = df_shein[df_shein["order date"].between(start, end)]
    daily_shein = daily_shein[~daily_shein["order status"].str.lower().isin(["customer refunded"])]
    shein_daily = daily_shein.groupby("order date").agg({"product price":"sum"}).reset_index().rename(columns={"product price":"Total Sales"})
    shein_daily["qty"] = 1
    shein_daily = shein_daily.groupby("order date").agg({"Total Sales":"sum", "qty":"sum"}).reset_index()
    # 날짜 기준 합치기
    daily = pd.merge(temu_daily, shein_daily, on="order date", how="outer", suffixes=('_temu', '_shein')).fillna(0)
    daily["Total Sales"] = daily["Total Sales_temu"] + daily["Total Sales_shein"]
    daily["qty"] = daily["qty_temu"] + daily["qty_shein"]
    daily = daily[["order date", "qty", "Total Sales"]].sort_values("order date")
    st.line_chart(daily.set_index("order date")[["qty", "Total Sales"]])

# --- 베스트셀러 TOP 10: 사진, 스타일넘버, 판매량 ---
st.subheader("Best Seller 10")
if platform == "SHEIN":
    best = df_sold.groupby("product description").size().reset_index(name="판매수량").sort_values("판매수량", ascending=False).head(10)
    best["이미지"] = best["product description"].astype(str).map(info_img_dict)
    best = best[["이미지", "product description", "판매수량"]]
    best.columns = ["Image", "Style Number", "Sold Qty"]
elif platform == "TEMU":
    best = df_sold.groupby("product number")["quantity shipped"].sum().reset_index().sort_values("quantity shipped", ascending=False).head(10)
    best["이미지"] = best["product number"].astype(str).map(info_img_dict)
    best = best[["이미지", "product number", "quantity shipped"]]
    best.columns = ["Image", "Style Number", "Sold Qty"]
else:
    # BOTH: TEMU/SHEIN 각각 스타일넘버별 집계 후 합치기
    best_temu = df_temu[df_temu["order item status"].str.lower().isin(["shipped", "delivered"])]
    best_temu = best_temu[best_temu["order date"].between(start, end)]
    b1 = best_temu.groupby("product number")["quantity shipped"].sum().reset_index()
    b1.columns = ["Style Number", "Sold Qty"]
    b2 = df_shein[~df_shein["order status"].str.lower().isin(["customer refunded"])]
    b2 = b2[b2["order date"].between(start, end)]
    b2 = b2.groupby("product description").size().reset_index(name="Sold Qty")
    b2.columns = ["Style Number", "Sold Qty"]
    best = pd.concat([b1, b2])
    best = best.groupby("Style Number")["Sold Qty"].sum().reset_index()
    best["Sold Qty"] = best["Sold Qty"].astype(int)   # <== 소수점 방지!
    best["Image"] = best["Style Number"].astype(str).map(info_img_dict)
    best = best[["Image", "Style Number", "Sold Qty"]].sort_values("Sold Qty", ascending=False).head(10)


def make_img_tag(url):
    if pd.notna(url) and str(url).startswith("http"):
        return f"<img src='{url}' style='width:60px;height:auto;'>"
    return ""

if not best.empty:
    best["Image"] = best["Image"].apply(make_img_tag)
    st.markdown("""
    <style>
    .best-table td, .best-table th {padding:8px 14px !important;}
    .best-table {width:100% !important;}
    </style>
    """, unsafe_allow_html=True)
    st.markdown(
        best.to_html(escape=False, index=False, classes="best-table"),
        unsafe_allow_html=True
    )
else:
    st.info("데이터가 없습니다.")



