import streamlit as st
from style_info_page import style_info_page
from sales_dashboard_page import sales_dashboard_page

page = st.sidebar.radio("페이지 선택", ["📖 스타일 정보 조회", "📊 세일즈 대시보드"])

if page == "📖 스타일 정보 조회":
    style_info_page()
elif page == "📊 세일즈 대시보드":
    sales_dashboard_page()
