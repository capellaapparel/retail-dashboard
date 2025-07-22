# streamlit_app.py
import streamlit as st
import pandas as pd

# CSV 불러오기
df = pd.read_csv("shein_sales_summary.csv")

# 제목
st.title("Shein 판매 분석 대시보드")

# 필터 옵션
option = st.selectbox("가격 제안 필터", ['전체 보기'] + df['가격 제안'].unique().tolist())

# 필터링 적용
if option != '전체 보기':
    df = df[df['가격 제안'] == option]

# 제품 표시
for idx, row in df.iterrows():
    st.markdown(f"### {row['Goods name']}")
    st.image(row['Product image link'], width=200)
    st.write(f"SKU: {row['SPU']}")
    st.write(f"판매량: {row['Sales Volume']}")
    st.write(f"가격 제안: {row['가격 제안']}")
    st.markdown("---")
