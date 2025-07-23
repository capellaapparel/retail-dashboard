# streamlit_app.py
import streamlit as st

st.set_page_config(page_title="Capella Product Dashboard", layout="wide")

page = st.sidebar.radio("페이지 선택", ["🏠 홈"])

if page == "🏠 홈":
    st.title("👋 Welcome to Capella Dashboard")
    st.markdown(\"\"\"
    이 대시보드는 다음 기능을 포함합니다:

    - 🔍 스타일 정보 조회
    - ➕ 새로운 스타일 등록
    - 📈 추후 세일즈 예측/추천 기능 확장 예정
    \"\"\")
    st.info("왼쪽 사이드바에서 기능을 선택하세요.")
