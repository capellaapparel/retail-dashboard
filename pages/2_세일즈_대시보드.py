import streamlit as st
import pandas as pd
from utils import load_sales_data  # ← 예시. 실제 데이터 로딩 방식에 맞춰서 import

def sales_dashboard(df_all):

def get_periods(date_range):
    start, end = pd.to_datetime(date_range[0]), pd.to_datetime(date_range[1])
    delta = end - start
    prev_start, prev_end = start - (delta + timedelta(days=1)), start - timedelta(days=1)
    last_year_start, last_year_end = start - pd.DateOffset(years=1), end - pd.DateOffset(years=1)
    return (start, end), (prev_start, prev_end), (last_year_start, last_year_end)

def filter_sales(df, start, end, platform):
    df = df.copy()
    if platform != "BOTH":
        df = df[df["platform"] == platform]
    return df[(df["order date"] >= start) & (df["order date"] <= end)]

def sales_dashboard(df_all):
    st.title("세일즈 대시보드")

    # --- 필터
    platform = st.radio("플랫폼 선택", ["TEMU", "SHEIN", "BOTH"], horizontal=True)
    min_date, max_date = df_all["order date"].min(), df_all["order date"].max()
    date_range = st.date_input("날짜 필터", (min_date, max_date))

    # --- 기간 분리
    (sel_start, sel_end), (prev_start, prev_end), (ly_start, ly_end) = get_periods(date_range)

    # --- 데이터 분리
    sel_df  = filter_sales(df_all, sel_start, sel_end, platform)
    prev_df = filter_sales(df_all, prev_start, prev_end, platform)
    ly_df   = filter_sales(df_all, ly_start, ly_end, platform)

    # --- KPI 계산
    def kpi(df):
        return {
            "amount": df["sales"].sum(),
            "qty": int(df["qty"].sum()),
            "aov": df["sales"].sum() / max(1, df["order id"].nunique()),
            "cancel": int((df["order status"].str.lower() == "cancelled").sum())
        }
    kpi_sel, kpi_prev = kpi(sel_df), kpi(prev_df)

    # --- KPI 레이아웃 (증감 % 표시)
    col1, col2, col3, col4 = st.columns(4)
    def pct(val, prev):
        if prev == 0: return "N/A"
        v = (val-prev)/prev*100
        emoji = "⬆️" if v > 0 else "⬇️" if v < 0 else ""
        color = "red" if v < 0 else "green"
        return f"<span style='color:{color}'>{emoji} {v:.1f}%</span>"

    col1.metric("Total Order Amount", f"${kpi_sel['amount']:,.2f}", pct(kpi_sel["amount"], kpi_prev["amount"]))
    col2.metric("Total Order Quantity", f"{kpi_sel['qty']:,}", pct(kpi_sel["qty"], kpi_prev["qty"]))
    col3.metric("AOV", f"${kpi_sel['aov']:,.2f}", pct(kpi_sel["aov"], kpi_prev["aov"]))
    col4.metric("Canceled Order", f"{kpi_sel['cancel']:,}", pct(kpi_sel["cancel"], kpi_prev["cancel"]))

    # --- 일별 매출 그래프 (기간 3개)
    st.subheader("세일즈 그래프")
    def day_df(df, label):
        return df.groupby("order date").agg({"sales":"sum"}).rename(columns={"sales": label})
    chart_df = pd.concat([
        day_df(sel_df, "Selected period"),
        day_df(prev_df, "Previous period"),
        day_df(ly_df, "Same period last year")
    ], axis=1).fillna(0)
    st.line_chart(chart_df)

    # --- 베스트셀러
    st.subheader("Best Seller 10")
    best = sel_df.groupby("product number").agg({"qty":"sum", "sales":"sum"}).reset_index().sort_values("qty", ascending=False).head(10)
    st.dataframe(best)

    pass
if __name__ == "__main__" or "st" in globals():
    import streamlit as st
    df_all = load_sales_data(st.secrets)   # <- secrets 넘겨줘야함
    sales_dashboard(df_all)

