import streamlit as st
import pandas as pd
from dateutil import parser, tz
from datetime import timedelta
from utils import expand_date_range   # 날짜 범위 함수 utils.py에 구현 필요

@st.cache_data(show_spinner=False)
def load_google_sheet(sheet_name):
    # (구글시트 불러오는 코드. 실제 서비스에서는 secrets 활용)
    import gspread
    from oauth2client.service_account import ServiceAccountCredentials
    GOOGLE_SHEET_URL = "https://docs.google.com/spreadsheets/d/1oyVzCgGK1Q3Qi_sbYwE-wKG6SArnfUDRe7rQfGOF-Eo"
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive"
    ]
    json_data = {k: str(v) for k, v in st.secrets["gcp_service_account"].items()}
    with open("/tmp/service_account.json", "w") as f:
        import json; json.dump(json_data, f)
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

# === 데이터 로딩 ===
df_temu = load_google_sheet("TEMU_SALES")
df_temu["order date"] = df_temu["purchase date"].apply(parse_temudate)

# === 날짜필터 UI ===
min_date, max_date = df_temu["order date"].min(), df_temu["order date"].max()
date_range = st.date_input("조회 기간", (min_date, max_date))
start, end = expand_date_range(date_range)   # end = 23:59:59

# === 기간 필터링 ===
mask = (df_temu["order date"] >= start) & (df_temu["order date"] <= end)
df_view = df_temu[mask]

# === 판매/취소 분리 ===
sold_mask = df_view["order item status"].str.lower().isin(["shipped", "delivered"])
df_sold = df_view[sold_mask]
qty_sum = pd.to_numeric(df_sold["quantity shipped"], errors="coerce").fillna(0).sum()
sales_sum = pd.to_numeric(df_sold["base price total"], errors="coerce").fillna(0).sum()
aov = sales_sum / qty_sum if qty_sum > 0 else 0

cancel_mask = df_view["order item status"].str.lower() == "canceled"
df_cancel = df_view[cancel_mask]
cancel_qty = pd.to_numeric(df_cancel["quantity shipped"], errors="coerce").fillna(0).sum()

# ---- KPI 카드 (네모 상자)
def metric_card(label, value):
    st.markdown(
        f"""
        <div style="background: #fff; border-radius: 14px; border: 1.5px solid #e5e7eb; box-shadow: 0 1px 4px #0001; padding: 18px 10px 8px 18px; margin-bottom: 0.5rem; min-width: 140px;">
            <div style="font-size:14px; color: #555;">{label}</div>
            <div style="font-size: 2rem; font-weight: 600; margin-top: 2px; color: #232323;">{value}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

col1, col2, col3, col4 = st.columns(4)
with col1:
    metric_card("Total Order Amount", f"${sales_sum:,.2f}")
with col2:
    metric_card("Total Order Quantity", f"{int(qty_sum):,}")
with col3:
    metric_card("AOV", f"${aov:,.2f}")
with col4:
    metric_card("Canceled Order", f"{int(cancel_qty):,}")

# === 일별 판매 추이 ===
st.subheader("일별 판매 추이")
daily = df_sold.groupby("order date").agg({
    "quantity shipped": "sum",
    "base price total": "sum"
}).reset_index()
daily = daily.sort_values("order date")
st.line_chart(daily.set_index("order date")[["quantity shipped", "base price total"]])

# ---- 베스트셀러 테이블 (이미지 + 판매수량)
st.subheader("Best Seller 10")

# df_info = load_google_sheet("PRODUCT_INFO")  # <-- 스타일 넘버/이미지URL 매칭용, 필요시 불러오기
# df_info는 product number(소문자)/image(소문자) 컬럼 필요

# 베스트셀러 데이터
best = (
    df_sold.groupby("product number")["quantity shipped"].sum()
    .reset_index()
    .sort_values("quantity shipped", ascending=False)
    .head(10)
)

# 이미지URL 붙이기 (df_info에 image 컬럼이 있어야함)
try:
    df_info = load_google_sheet("PRODUCT_INFO")
    df_info.columns = [c.lower().strip() for c in df_info.columns]
    best = pd.merge(best, df_info[["product number", "image"]], on="product number", how="left")
except Exception as e:
    best["image"] = ""

# Streamlit 표 (이미지+판매수량만)
def image_table(df):
    html = """
    <table style='width:100%; border-collapse:collapse;'>
      <tr>
        <th>Image</th><th>Product Number</th><th>Sold Qty</th>
      </tr>
    """
    for _, row in df.iterrows():
        img = f"<img src='{row['image']}' width='60'>" if row['image'] else ""
        html += f"<tr style='height:68px; border-bottom:1px solid #eee;'><td>{img}</td><td>{row['product number']}</td><td style='font-size:1.2rem; font-weight:600'>{int(row['quantity shipped'])}</td></tr>"
    html += "</table>"
    return html

st.markdown(image_table(best), unsafe_allow_html=True)
