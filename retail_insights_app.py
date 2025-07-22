
import streamlit as st
import pandas as pd
import os
from datetime import datetime

# 페이지 설정
st.set_page_config(page_title="Retail Insights", layout="wide")
st.title("🛍️ Retail Sales Dashboard – Shein & Temu")

# 플랫폼 선택
platform = st.radio("플랫폼 선택", ["Shein", "Temu"], horizontal=True)

# 파일 업로드
uploaded_file = st.file_uploader(f"{platform} 판매 데이터를 업로드하세요 (엑셀 파일)", type=["xlsx"])

# 저장 디렉토리 설정
base_dir = "retail_data"
platform_dir = os.path.join(base_dir, platform.lower())
os.makedirs(platform_dir, exist_ok=True)

if uploaded_file:
    # 날짜 추출 (오늘 날짜 기준)
    today_str = datetime.today().strftime('%Y-%m-%d')
    filename = f"{platform.lower()}_sales_{today_str}.xlsx"
    file_path = os.path.join(platform_dir, filename)

    # 파일 저장
    with open(file_path, "wb") as f:
        f.write(uploaded_file.getbuffer())

    st.success(f"{platform} 판매 데이터가 업로드되어 저장되었습니다: {filename}")

    # 데이터 미리보기 및 간단 분석
    try:
        df = pd.read_excel(file_path)
        st.subheader("📄 데이터 미리보기")
        st.dataframe(df.head())

        st.subheader("📊 기본 분석")
        if 'Sales Volume' in df.columns:
            st.metric("총 판매량", int(df['Sales Volume'].sum()))
        if 'Gross Merchandise Volume' in df.columns:
            st.metric("총 매출액 ($)", round(df['Gross Merchandise Volume'].sum(), 2))
        if 'SPU' in df.columns:
            st.write(f"제품 수: {df['SPU'].nunique()}개")
    except Exception as e:
        st.error(f"파일을 분석하는 중 오류 발생: {e}")
