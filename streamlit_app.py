import streamlit as st
import pandas as pd
import os

INFO_CSV = "product_info.csv"

# --- 사이드바 메뉴 ---
st.sidebar.title("📂 Capella Dashboard")
page = st.sidebar.radio("페이지 선택", ["🏠 홈", "🔍 스타일 정보 조회", "➕ 새로운 스타일 등록"])

# --- 홈 페이지 ---
if page == "🏠 홈":
    st.set_page_config(page_title="Capella Product Dashboard", layout="wide")
    st.title("👋 Welcome to Capella Dashboard")
    st.markdown("""
이 대시보드는 다음 기능을 포함합니다:

🔍 스타일 정보 조회  
➕ 새로운 스타일 등록  
📈 추후 세일즈 예측/추천 기능 확장 예정

왼쪽 사이드바에서 페이지를 선택하세요.
""")

# --- 스타일 등록 페이지 ---
elif page == "➕ 새로운 스타일 등록":
    st.title("➕ 새 스타일 등록")

    # 기존 파일 불러오기 또는 초기화
    if os.path.exists(INFO_CSV):
        df = pd.read_csv(INFO_CSV)
    else:
        df = pd.DataFrame()

    with st.form("new_product_form"):
        st.subheader("기본 정보")

        product_number = st.text_input("Product Number*", placeholder="예: BT1234")
        erp_price = st.number_input("ERP PRICE*", min_value=0.0, value=0.0, step=0.01)
        temu_price = st.number_input("TEMU PRICE", min_value=0.0, value=0.0, step=0.01)

        st.subheader("스타일 속성")

        sleeve = st.text_input("SLEEVE")
        neckline = st.text_input("NECKLINE")
        length = st.text_input("LENGTH")
        fit = st.text_input("FIT")
        detail = st.text_input("DETAIL")
        style_mood = st.multiselect("STYLE MOOD (복수 선택 가능)", ["Casual", "Elegant", "Street", "Sexy", "Active"])
        custom_mood = st.text_input("새로운 무드 추가 (옵션)")
        model = st.text_input("MODEL")
        notes = st.text_area("NOTES")

        st.subheader("사이즈 차트")

        size_fields = {
            "TOP1_CHEST": 0.0,
            "TOP1_LENGTH": 0.0,
            "TOP1_SLEEVE": 0.0,
            "TOP2_CHEST": 0.0,
            "TOP2_LENGTH": 0.0,
            "TOP2_SLEEVE": 0.0,
            "BOTTOM_WAIST": 0.0,
            "BOTTOM_HIP": 0.0,
            "BOTTOM_LENGTH": 0.0,
            "BOTTOM_INSEAM": 0.0
        }
        size_inputs = {}
        for key in size_fields:
            size_inputs[key] = st.number_input(key, min_value=0.0, value=0.0, step=0.1)

        submitted = st.form_submit_button("✅ 스타일 등록")

        if submitted:
            if not product_number or erp_price == 0.0:
                st.error("❌ 'Product Number'와 'ERP PRICE'는 필수 항목입니다.")
            elif product_number in df["Product Number"].astype(str).values:
                st.error("❌ 이미 존재하는 Product Number입니다.")
            else:
                new_row = {
                    "Product Number": product_number,
                    "ERP PRICE": erp_price,
                    "TEMU PRICE": temu_price,
                    "SLEEVE": sleeve,
                    "NECKLINE": neckline,
                    "LENGTH": length,
                    "FIT": fit,
                    "DETAIL": detail,
                    "STYLE MOOD": ", ".join(style_mood + ([custom_mood] if custom_mood else [])),
                    "MODEL": model,
                    "NOTES": notes
                }
                new_row.update(size_inputs)

                # 누락된 컬럼이 있으면 추가
                for col in new_row:
                    if col not in df.columns:
                        df[col] = None

                # 새 행 추가 후 저장
                df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
                df.to_csv(INFO_CSV, index=False)
                st.success("🎉 새로운 스타일이 등록되었습니다!")
                st.experimental_rerun()

# --- 스타일 조회 페이지 (선택사항: 추후 연결)
