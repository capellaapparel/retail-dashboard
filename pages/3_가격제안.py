import streamlit as st
import pandas as pd
from sklearn.linear_model import LinearRegression

# 1. 구글시트에서 TEMU 데이터 불러오기
@st.cache_data(show_spinner=False)
def load_google_sheet(sheet_name):
    # (생략: 본인 load_google_sheet 함수 이용)
    ...

df_temu = load_google_sheet("TEMU_SALES")
df_temu["order date"] = pd.to_datetime(df_temu["purchase date"], errors="coerce")
df_temu = df_temu[df_temu["order item status"].str.lower().isin(["shipped", "delivered"])]

# 2. 스타일 번호 선택
style = st.selectbox("스타일 선택", sorted(df_temu["product number"].dropna().unique()))

df_one = df_temu[df_temu["product number"] == style]
if len(df_one) < 8:
    st.warning("AI 추천을 위해 최소 8개 이상의 판매 데이터가 필요합니다.")
else:
    # 3. 가격대별 판매수량 집계
    df_one["price"] = pd.to_numeric(df_one["base price total"], errors="coerce")
    group = df_one.groupby("price")["quantity shipped"].sum().reset_index()

    # 4. 수요-가격 curve 피팅(선형)
    model = LinearRegression()
    model.fit(group[["price"]], group["quantity shipped"])
    # 5. 후보가격별 예상판매량/이익
    cost = st.number_input("해당 스타일 원가(USD)", value=5.0)
    candidate_prices = pd.Series([round(x,2) for x in list(group["price"].unique()) + list(range(int(group["price"].min()), int(group["price"].max())+3))])
    pred_qty = model.predict(candidate_prices.values.reshape(-1,1)).clip(min=0)
    profit = (candidate_prices - cost) * pred_qty
    idx = profit.idxmax()
    st.success(f"AI 추천 판매가: **${candidate_prices[idx]:.2f}** (예상 이익 최대)")

    st.line_chart(pd.DataFrame({"예상판매수량":pred_qty, "이익":profit}, index=candidate_prices))

    st.caption("실제 모델링은 더 고도화 가능 (예: 시계열, 경쟁가 반영, 수익/판매량 동시최적화 등)")
