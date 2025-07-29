import streamlit as st
import pandas as pd
from dateutil import parser

@st.cache_data(show_spinner=False)
def load_google_sheet(sheet_name):
    # ... (구글 시트 불러오는 코드) ...
    df = pd.DataFrame(data)
    df.columns = [c.lower().strip() for c in df.columns]
    return df  # <- 이게 빠지면 None이 반환됨!

def parse_temudate(dt):
    try:
        return parser.parse(str(dt).split('(')[0].strip(), fuzzy=True)
    except:
        return pd.NaT

# 데이터 로딩
df_temu = load_google_sheet("TEMU_SALES")
df_temu.columns = [c.lower().strip() for c in df_temu.columns]

# 날짜 파싱
df_temu["order date"] = df_temu["purchase date"].apply(parse_temudate)

# 필터 UI
min_date, max_date = df_temu["order date"].min(), df_temu["order date"].max()
date_range = st.date_input("조회 기간", (min_date, max_date))

# 날짜 필터
start, end = pd.to_datetime(date_range[0]), pd.to_datetime(date_range[1])
mask = (df_temu["order date"] >= start) & (df_temu["order date"] <= end)
df_view = df_temu[mask]

# 1. 판매(매출) 데이터 (Shipped + Delivered)
sold_mask = df_view["order item status"].str.lower().isin(["shipped", "delivered"])
df_sold = df_view[sold_mask]
qty_sum = pd.to_numeric(df_sold["quantity shipped"], errors="coerce").fillna(0).sum()
sales_sum = pd.to_numeric(df_sold["base price total"], errors="coerce").fillna(0).sum()
aov = sales_sum / qty_sum if qty_sum > 0 else 0

# 2. 취소 데이터 (Canceled)
cancel_mask = df_view["order item status"].str.lower() == "canceled"
df_cancel = df_view[cancel_mask]
cancel_qty = pd.to_numeric(df_cancel["quantity shipped"], errors="coerce").fillna(0).sum()

# KPI 레이아웃
col1, col2, col3, col4 = st.columns(4)
col1.metric("Total Order Amount", f"${sales_sum:,.2f}")
col2.metric("Total Order Quantity", f"{int(qty_sum):,}")
col3.metric("AOV", f"${aov:,.2f}")
col4.metric("Canceled Order", f"{int(cancel_qty):,}")

# 일별 그래프
st.subheader("일별 판매 추이")
daily = df_sold.groupby("order date").agg({
    "quantity shipped": "sum",
    "base price total": "sum"
}).reset_index()
daily = daily.sort_values("order date")
st.line_chart(daily.set_index("order date")[["quantity shipped", "base price total"]])

# 베스트셀러 10
st.subheader("Best Seller 10")
best = (
    df_sold.groupby("product number")["quantity shipped"].sum()
    .reset_index()
    .sort_values("quantity shipped", ascending=False)
    .head(10)
)
st.dataframe(best)

