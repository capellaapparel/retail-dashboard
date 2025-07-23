# streamlit_app.py
import streamlit as st

st.set_page_config(page_title="Capella Dashboard", layout="wide")

st.title("👋 Welcome to Capella Dashboard")
st.markdown("""
이 대시보드는 다음 기능을 포함합니다:

- 🔍 스타일 정보 조회
- ➕ 새로운 스타일 등록
- 📈 추후 세일즈 예측/추천 기능 확장 예정
""")
st.info("왼쪽 사이드바에서 페이지를 선택하세요.")
st.sidebar.title("Capella Dashboard")
st.sidebar.markdown("🔍 스타일 정보 조회 페이지")
