import streamlit as st
from style_info_page import style_info_page
from sales_dashboard_page import sales_dashboard_page
from cross_platform_page import cross_platform_page      # 5_교차플랫폼_비교.py의 함수
from cancel_rate_page import cancel_rate_page            # 6_반품_취소율.py의 함수

page = st.sidebar.radio(
    "페이지 선택",
    [
        "📖 스타일 정보 조회",
        "📊 세일즈 대시보드",
        "🔁 교차 플랫폼 비교",
        "↩️ 반품·취소율 분석"
    ]
)

if page == "📖 스타일 정보 조회":
    style_info_page()
elif page == "📊 세일즈 대시보드":
    sales_dashboard_page()
elif page == "🔁 교차 플랫폼 비교":
    cross_platform_page()
elif page == "↩️ 반품·취소율 분석":
    cancel_rate_page()
