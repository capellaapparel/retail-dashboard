# pages/2_세일즈_대시보드.py
import streamlit as st
import pandas as pd
from dateutil import parser

st.set_page_config(page_title="세일즈 대시보드", layout="wide")

# -----------------------------
# Utils
# -----------------------------
@st.cache_data(show_spinner=False)
def load_google_sheet(sheet_name: str) -> pd.DataFrame:
    import gspread
    from oauth2client.service_account import ServiceAccountCredentials
    import json

    GOOGLE_SHEET_URL = "https://docs.google.com/spreadsheets/d/1oyVzCgGK1Q3Qi_sbYwE-wKG6SArnfUDRe7rQfGOF-Eo"
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive",
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

def parse_temudate(x):
    # TEMU: "Aug 3, 2025, 7:15 pm PDT(UTC-7)" 같은 포맷 포함 → 괄호 앞까지만 파싱
    try:
        return parser.parse(str(x).split("(")[0].strip(), fuzzy=True)
    except Exception:
        return pd.NaT

def parse_sheindate(x):
    try:
        return pd.to_datetime(str(x), errors="coerce", infer_datetime_format=True)
    except Exception:
        return pd.NaT

def to_float(s):
    # "$11.23", "11,23", " 12 " → float
    if pd.isna(s):
        return pd.NA
    z = str(s).replace("$", "").replace(",", "").strip()
    try:
        return float(z)
    except Exception:
        return pd.NA

def kpi_delta(now, prev):
    if prev in (None, 0) or pd.isna(prev):
        return ""
    pct = (now - prev) / prev * 100
    arrow = "▲" if pct >= 0 else "▼"
    color = "#11b500" if pct >= 0 else "red"
    return f"<span style='color:{color}'>{arrow} {abs(pct):.1f}%</span>"

# -----------------------------
# Load Data
# -----------------------------
df_temu = load_google_sheet("TEMU_SALES")
df_shein = load_google_sheet("SHEIN_SALES")
df_info = load_google_sheet("PRODUCT_INFO")

# Parse dates
df_temu["order date"] = df_temu["purchase date"].apply(parse_temudate)
df_shein["order date"] = df_shein["order processed on"].apply(parse_sheindate)

# Coerce numerics we use
df_temu["base price total"] = pd.to_numeric(df_temu["base price total"].apply(to_float), errors="coerce").fillna(0.0)
df_temu["quantity shipped"] = pd.to_numeric(df_temu["quantity shipped"], errors="coerce").fillna(0)
df_temu["quantity purchased"] = pd.to_numeric(df_temu.get("quantity purchased", 0), errors="coerce").fillna(0)

df_shein["product price"] = pd.to_numeric(df_shein["product price"].apply(to_float), errors="coerce").fillna(0.0)

# Images for best-seller
info_img = dict(zip(df_info["product number"].astype(str), df_info.get("image", "")))

# -----------------------------
# Date inputs (ALL as date objects)
# -----------------------------
def _to_date(x):
    return pd.to_datetime(x).date() if pd.notna(x) else None

min_dt = _to_date(min(df_temu["order date"].min(), df_shein["order date"].min()))
max_dt = _to_date(max(df_temu["order date"].max(), df_shein["order date"].max()))
today = pd.Timestamp.today().normalize().date()

default_start = max(min_dt, today - pd.Timedelta(days=30).to_pytimedelta())
default_end = min(max_dt, today)

if "sales_date_range" not in st.session_state:
    st.session_state["sales_date_range"] = (default_start, default_end)

st.title("세일즈 대시보드")

col1, col2 = st.columns([1.5, 8.5])
with col1:
    platform = st.radio("플랫폼 선택", ["TEMU", "SHEIN", "BOTH"], horizontal=True)
with col2:
    dr = st.date_input(
        "조회 기간",
        value=st.session_state["sales_date_range"],
        min_value=min_dt,
        max_value=max_dt,
    )
    if isinstance(dr, tuple):
        start_date, end_date = dr
    else:
        start_date = end_date = dr

    # Clamp inside bounds
    start_date = max(min_dt, min(start_date, max_dt))
    end_date = max(start_date, min(end_date, max_dt))
    st.session_state["sales_date_range"] = (start_date, end_date)

# Range to timestamps (include 23:59:59)
start = pd.to_datetime(st.session_state["sales_date_range"][0])
end = pd.to_datetime(st.session_state["sales_date_range"][1]) + pd.Timedelta(hours=23, minutes=59, seconds=59)
period_days = (end - start).days + 1
prev_start = start - pd.Timedelta(days=period_days)
prev_end = start - pd.Timedelta(seconds=1)

# -----------------------------
# Aggregations
# -----------------------------
def temu_agg(df: pd.DataFrame, s, e):
    q = df[(df["order date"] >= s) & (df["order date"] <= e)].copy()
    sold = q[q["order item status"].str.lower().isin(["shipped", "delivered"])]
    sales_sum = sold["base price total"].sum()            # ← amount
    qty_sum = sold["quantity shipped"].sum()
    aov = (sales_sum / qty_sum) if qty_sum > 0 else 0.0
    cancel_qty = q[q["order item status"].str.lower() == "canceled"]["quantity purchased"].sum()
    return sales_sum, qty_sum, aov, cancel_qty, sold

def shein_agg(df: pd.DataFrame, s, e):
    q = df[(df["order date"] >= s) & (df["order date"] <= e)].copy()
    sold = q[~q["order status"].str.lower().isin(["customer refunded"])]
    qty_sum = sold.shape[0]  # 1 row = 1 unit
    sales_sum = sold["product price"].sum()
    aov = (sales_sum / qty_sum) if qty_sum > 0 else 0.0
    cancel_qty = q[q["order status"].str.lower() == "customer refunded"].shape[0]
    return sales_sum, qty_sum, aov, cancel_qty, sold

if platform == "TEMU":
    sales_sum, qty_sum, aov, cancel_qty, df_sold = temu_agg(df_temu, start, end)
    p_sales, p_qty, p_aov, p_cancel, _ = temu_agg(df_temu, prev_start, prev_end)
elif platform == "SHEIN":
    sales_sum, qty_sum, aov, cancel_qty, df_sold = shein_agg(df_shein, start, end)
    p_sales, p_qty, p_aov, p_cancel, _ = shein_agg(df_shein, prev_start, prev_end)
else:
    s1, q1, a1, c1, sold1 = temu_agg(df_temu, start, end)
    s2, q2, a2, c2, sold2 = shein_agg(df_shein, start, end)
    sales_sum, qty_sum, cancel_qty = s1 + s2, q1 + q2, c1 + c2
    aov = (sales_sum / qty_sum) if qty_sum > 0 else 0.0
    df_sold = pd.concat([sold1, sold2], ignore_index=True)

    ps1, pq1, pa1, pc1, _ = temu_agg(df_temu, prev_start, prev_end)
    ps2, pq2, pa2, pc2, _ = shein_agg(df_shein, prev_start, prev_end)
    p_sales, p_qty, p_cancel = ps1 + ps2, pq1 + pq2, pc1 + pc2
    p_aov = (p_sales / p_qty) if p_qty > 0 else 0.0

# -----------------------------
# KPI Row (clean layout)
# -----------------------------
st.markdown(
    """
<style>
.kpi {display:flex; gap:16px; margin:8px 0 18px 0;}
.kpi > div {flex:1; background:#fff; border-radius:16px; padding:18px 22px;
            box-shadow:0 2px 10px rgba(0,0,0,.06);}
.kpi .label {font-size:0.95rem; color:#666;}
.kpi .val {font-size:1.8rem; font-weight:700;}
.kpi .delta {margin-top:4px;}
</style>
""",
    unsafe_allow_html=True,
)

kpi_html = f"""
<div class="kpi">
  <div>
    <div class="label">Total Order Amount</div>
    <div class="val">${sales_sum:,.2f}</div>
    <div class="delta">{kpi_delta(sales_sum, p_sales)}</div>
  </div>
  <div>
    <div class="label">Total Order Quantity</div>
    <div class="val">{int(qty_sum):,}</div>
    <div class="delta">{kpi_delta(qty_sum, p_qty)}</div>
  </div>
  <div>
    <div class="label">AOV</div>
    <div class="val">${aov:,.2f}</div>
    <div class="delta">{kpi_delta(aov, p_aov)}</div>
  </div>
  <div>
    <div class="label">Canceled Order</div>
    <div class="val">{int(cancel_qty):,}</div>
    <div class="delta">{kpi_delta(cancel_qty, p_cancel)}</div>
  </div>
</div>
"""
st.markdown(kpi_html, unsafe_allow_html=True)

# -----------------------------
# Daily chart (qty + amount)
# -----------------------------
st.subheader("일별 판매 추이")

if platform == "TEMU":
    daily = (
        df_sold.groupby(df_sold["order date"].dt.date)
        .agg(qty=("quantity shipped", "sum"), total=("base price total", "sum"))
        .reset_index()
        .rename(columns={"order date": "date"})
    )
elif platform == "SHEIN":
    daily = (
        df_sold.groupby(df_sold["order date"].dt.date)
        .agg(qty=("product price", "size"))   # row count
        .assign(total=lambda d: 0.0 + df_sold.groupby(df_sold["order date"].dt.date)["product price"].sum().values)
        .reset_index()
        .rename(columns={"order date": "date"})
    )
else:
    temu_daily = (
        df_temu[(df_temu["order date"] >= start) & (df_temu["order date"] <= end) & 
                (df_temu["order item status"].str.lower().isin(["shipped","delivered"])) ]
        .groupby(df_temu["order date"].dt.date)
        .agg(t_qty=("quantity shipped", "sum"), t_total=("base price total", "sum"))
    )
    shein_daily = (
        df_shein[(df_shein["order date"] >= start) & (df_shein["order date"] <= end) &
                 (~df_shein["order status"].str.lower().isin(["customer refunded"])) ]
        .groupby(df_shein["order date"].dt.date)
        .agg(s_qty=("product price", "size"), s_total=("product price", "sum"))
    )
    both = pd.concat([temu_daily, shein_daily], axis=1).fillna(0)
    both["qty"] = both["t_qty"] + both["s_qty"]
    both["total"] = both["t_total"] + both["s_total"]
    daily = both.reset_index().rename(columns={"index": "date"})

if daily.empty:
    st.info("해당 기간에 데이터가 없습니다.")
else:
    daily = daily.sort_values("date")
    daily = daily.set_index("date")[["qty", "total"]]
    daily.columns = ["qty", "Total Sales"]
    st.line_chart(daily)

# -----------------------------
# Best Seller 10 (image + style + qty)
# -----------------------------
st.subheader("Best Seller 10")

def img_tag(u):
    if pd.notna(u) and str(u).startswith("http"):
        return f"<img src='{u}' style='width:60px; border-radius:10px'>"
    return ""

if platform == "TEMU":
    best = (
        df_sold.groupby("product number")["quantity shipped"].sum()
        .reset_index().sort_values("quantity shipped", ascending=False).head(10)
    )
    best["Image"] = best["product number"].astype(str).map(info_img)
    best["Image"] = best["Image"].apply(img_tag)
    best = best[["Image","product number","quantity shipped"]]
    best.columns = ["Image","Style Number","Sold Qty"]
elif platform == "SHEIN":
    best = (
        df_sold.groupby("product description").size()
        .reset_index(name="Sold Qty").sort_values("Sold Qty", ascending=False).head(10)
    )
    best["Image"] = best["product description"].astype(str).map(info_img)
    best["Image"] = best["Image"].apply(img_tag)
    best = best[["Image","product description","Sold Qty"]]
    best.columns = ["Image","Style Number","Sold Qty"]
else:
    temu_count = (
        df_temu[(df_temu["order date"] >= start) & (df_temu["order date"] <= end) &
                (df_temu["order item status"].str.lower().isin(["shipped","delivered"])) ]
        .groupby("product number")["quantity shipped"].sum()
    )
    shein_count = (
        df_shein[(df_shein["order date"] >= start) & (df_shein["order date"] <= end) &
                 (~df_shein["order status"].str.lower().isin(["customer refunded"])) ]
        .groupby("product description").size()
    )
    summary = pd.DataFrame({"TEMU Qty": temu_count}).merge(
        shein_count.rename("SHEIN Qty"), left_index=True, right_index=True, how="outer"
    ).fillna(0)
    summary["Sold Qty"] = summary["TEMU Qty"] + summary["SHEIN Qty"]
    best = summary.sort_values("Sold Qty", ascending=False).head(10).reset_index().rename(columns={"index":"Style Number"})
    best["Image"] = best["Style Number"].astype(str).map(info_img)
    best["Image"] = best["Image"].apply(img_tag)
    best = best[["Image","Style Number","Sold Qty"]]

st.markdown(
    best.to_html(escape=False, index=False, classes="best-table"),
    unsafe_allow_html=True
)
