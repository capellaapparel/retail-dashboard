# streamlit_app.py
import streamlit as st
import pandas as pd
import os

# --- 데이터 파일 경로 ---
INFO_CSV = "product_info.csv"
IMAGE_CSV = "product_images.csv"

# --- Streamlit 페이지 구분 ---
page = st.sidebar.radio("페이지 선택", ["🏠 홈", "🔍 스타일 정보 조회", "➕ 새로운 스타일 등록"])

# --- 홈 ---
if page == "🏠 홈":
    st.set_page_config(page_title="Capella Product Dashboard", layout="wide")
    st.title("👋 Welcome to Capella Dashboard")
    st.markdown("""
    이 대시보드는 다음 기능을 포함합니다:

    - 🔍 스타일 정보 조회
    - ➕ 새로운 스타일 등록
    - 📈 추후 세일즈 예측/추천 기능 확장 예정
    """)
    st.info("왼쪽 사이드바에서 기능을 선택하세요.")

# --- 스타일 정보 조회 페이지 ---
elif page == "🔍 스타일 정보 조회":
    st.title("Product Info Dashboard")

    @st.cache_data
    def load_data():
        df_info = pd.read_csv(INFO_CSV)
        df_img = pd.read_csv(IMAGE_CSV)
        return df_info, df_img

    df_info, df_img = load_data()

    style_input = st.text_input("🔍 스타일 번호를 입력하세요:", "")

    if style_input:
        matched = df_info[df_info["Product Number"].astype(str).str.contains(style_input, case=False, na=False)]

        if not matched.empty:
            selected = st.selectbox("스타일 선택", matched["Product Number"].astype(str))
            product_info = df_info[df_info["Product Number"] == selected].iloc[0]
            img_rows = df_img[df_img["Product Number"] == selected]
            product_img = img_rows.iloc[0] if not img_rows.empty else None

            col1, col2 = st.columns([1, 2])
            with col1:
                if product_img is not None and pd.notna(product_img.get("First Image", "")):
                    st.image(product_img["First Image"], width=300)
                else:
                    st.markdown("_이미지가 없습니다._")

            with col2:
                st.markdown(f"**Product Number:** {product_info['Product Number']}")
                st.markdown(f"**Product Name:** {product_img.get('default product name(en)', '') if product_img is not None else ''}")
                st.markdown(f"**ERP PRICE:** ${product_info.get('ERP PRICE', 0):.2f}")
                st.markdown(f"**SHEIN PRICE:** ${product_img.get('SHEIN PRICE', 0):.2f}" if product_img is not None else "")
                st.markdown(f"**SLEEVE:** {product_info.get('SLEEVE', '')}")
                st.markdown(f"**NECKLINE:** {product_info.get('NECKLINE', '')}")
                st.markdown(f"**LENGTH:** {product_info.get('LENGTH', '')}")
                st.markdown(f"**FIT:** {product_info.get('FIT', '')}")
                st.markdown(f"**DETAIL:** {product_info.get('DETAIL', '')}")
                st.markdown(f"**STYLE MOOD:** {product_info.get('STYLE MOOD', '')}")
                st.markdown(f"**MODEL:** {product_info.get('MODEL', '')}")
                st.markdown(f"**NOTES:** {product_info.get('NOTES', '')}")

            st.markdown("---")
            st.markdown("### 📏 Size Chart")

            size_fields = {
                "Top 1": ["TOP1_CHEST", "TOP1_LENGTH", "TOP1_SLEEVE"],
                "Top 2": ["TOP2_CHEST", "TOP2_LENGTH", "TOP2_SLEEVE"],
                "Bottom": ["BOTTOM_WAIST", "BOTTOM_HIP", "BOTTOM_LENGTH", "BOTTOM_INSEAM"]
            }

            for section, fields in size_fields.items():
                size_data = []
                for field in fields:
                    if field in product_info and pd.notna(product_info[field]):
                        label = field.split("_")[1].capitalize()
                        size_data.append((label, product_info[field]))
                if size_data:
                    st.markdown(f"**{section}**")
                    st.table(pd.DataFrame(size_data, columns=["Measurement", "cm"]))
        else:
            st.warning("❌ 해당 스타일을 찾을 수 없습니다.")

# --- 새로운 스타일 등록 페이지 ---
elif page == "➕ 새로운 스타일 등록":
    st.title("➕ 새 스타일 등록")
    st.warning("현재 이 기능은 표시만 되고 CSV 저장은 수동입니다.")
