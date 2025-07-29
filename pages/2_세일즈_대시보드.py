import streamlit as st
import pandas as pd
from dateutil import parser, relativedelta
from datetime import timedelta

@st.cache_data(show_spinner=False)
def load_google_sheet(sheet_name):
    # 실제 구글 시트 로드 코드 삽입
    import gspread, json
    from oauth2client.service_account import ServiceAccountCredentials
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

def metric_card(label, value):
    st.markdown(
        f"""
        <div style="background: #fff; border-radius: 14px; border: 1.5px solid #e5e7eb; box-shadow: 0 1px 4px #0001;
            padding: 18px 10px 18px 18px; margin-bottom: 0.5rem; min-width: 160px; min-height: 80px; display: flex; flex-direction: column; justify-content: center;">
            <div style="font-size:15px; color: #444; font-weight: 400;">{label}</div>
            <div style="font-size: 2rem; font-weight: 600; margin-top: 6px; color: #232323; line-height: 2.2rem; word-break:break-all;">{value}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

def get_prev_period(date_range):
    # 입력: (start, end)
    start, end = pd.to_datetime(date_range[0]), pd.to_datetime(date_range[1])
    delta = end - start
    prev_start = start - (delta + timedelta(days=1))
    prev_end = start - timedelta(days=1)
    return prev_start, prev_end

# ---- 데이터 로드 ----
df_temu = load_google_sheet("TEMU_SALES")
df_info = load_google_sheet("PRODUCT_INFO")  # 이미지용

# 날짜 파싱
df_temu["order date"] = df_temu["purchase date"].apply(parse_temudate)

# ---- 날짜 필터 UI ----
min_date, max_date = df_temu["order date"].min(), df_temu["order date"].max()
date_range = st.date_input("조회 기간", (min_date, max_date))

# ---- 기간 구하기 ----
start, end = pd.to_datetime(date_range[0]), pd.to_datetime(date_range[1])
prev_start, prev_end = get_prev_period(date_range)

# ---- 데이터 필터 ----
def temu_filter(df, start, end, status=None):
    mask = (df["order date"] >= start) & (df["order date"] <= end)
    df = df[mask]
    if status:
        df = df[df["order item status"].str.lower().isin(status)]
    return df

df_sold = temu_filter(df_temu, start, end, status=["shipped", "delivered"])
df_prev = temu_filter(df_temu, prev_start, prev_end, status=["shipped", "delivered"])
df_canceled = temu_filter(df_temu, start, end, status=["canceled"])
df_canceled_prev = temu_filter(df_temu, prev_start, prev_end, status=["canceled"])

# ---- KPI 계산 ----
def kpi(df_sold, df_canceled):
    qty_sum = pd.to_numeric(df_sold.get("quantity shipped", 0), errors="coerce").fillna(0).sum()
    sales_sum = pd.to_numeric(df_sold.get("base price total", 0), errors="coerce").fillna(0).sum()
    aov = sales_sum / qty_sum if qty_sum > 0 else 0
    cancel_qty = pd.to_numeric(df_canceled.get("quantity shipped", 0), errors="coerce").fillna(0).sum()
    return {"amount": sales_sum, "qty": int(qty_sum), "aov": aov, "cancel": int(cancel_qty)}

kpi_sel = kpi(df_sold, df_canceled)
kpi_prev = kpi(df_prev, df_canceled_prev)

def pct(val, prev):
    if prev == 0: return ""
    v = (val-prev)/prev*100
    emoji = "⬆️" if v > 0 else "⬇️" if v < 0 else ""
    color = "red" if v < 0 else "green"
    return f"<span style='color:{color}; font-size:1rem'>{emoji} {v:.1f}%</span>"

# ---- KPI 카드 레이아웃 ----
col1, col2, col3, col4 = st.columns(4)
with col1:
    metric_card("Total Order Amount", f"${kpi_sel['amount']:,.2f} {pct(kpi_sel['amount'], kpi_prev['amount'])}")
with col2:
    metric_card("Total Order Quantity", f"{kpi_sel['qty']:,} {pct(kpi_sel['qty'], kpi_prev['qty'])}")
with col3:
    metric_card("AOV", f"${kpi_sel['aov']:,.2f} {pct(kpi_sel['aov'], kpi_prev['aov'])}")
with col4:
    metric_card("Canceled Order", f"{kpi_sel['cancel']:,} {pct(kpi_sel['cancel'], kpi_prev['cancel'])}")

# ---- 일별 추이 ----
st.subheader("일별 판매 추이")
daily = df_sold.groupby("order date").agg({
    "quantity shipped": "sum",
    "base price total": "sum"
}).reset_index()
daily = daily.sort_values("order date")
st.line_chart(daily.set_index("order date")[["quantity shipped", "base price total"]])

# ---- 베스트셀러 10 (이미지+판매수량) ----
st.subheader("Best Seller 10")
# merge: TEMU의 product number와 상품 정보의 image 매칭
best = (
    df_sold.groupby("product number")["quantity shipped"].sum()
    .reset_index()
    .sort_values("quantity shipped", ascending=False)
    .head(10)
)
best = best.merge(df_info[["product number", "image"]], on="product number", how="left")

for _, row in best.iterrows():
    cols = st.columns([1, 4])
    with cols[0]:
        if pd.notna(row["image"]) and str(row["image"]).startswith("http"):
            st.image(row["image"], width=60)
    with cols[1]:
        st.markdown(f"**{row['product number']}** — {int(row['quantity shipped'])}개")

