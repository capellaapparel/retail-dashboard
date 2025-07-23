# streamlit_app.py
import streamlit as st
import pandas as pd
import os

# --- 유저 정의 옵션 저장 경로 ---
NECKLINE_FILE = "neckline_options.csv"
DETAIL_FILE = "detail_options.csv"
PRODUCT_CSV = "product_master.csv"

# --- 기본값 정의 ---
def load_or_create_options(file_path, default_list):
    if os.path.exists(file_path):
        return pd.read_csv(file_path)["option"].tolist()
    else:
        pd.DataFrame({"option": default_list}).to_csv(file_path, index=False)
        return default_list

def save_new_option(file_path, new_option):
    if new_option:
        df = pd.read_csv(file_path)
        if new_option not in df["option"].values:
            df.loc[len(df)] = new_option
            df.to_csv(file_path, index=False)

# --- 데이터 로딩 ---
@st.cache_data
def load_data():
    try:
        df = pd.read_csv(PRODUCT_CSV, index_col=0)
        df.columns = df.columns.str.strip()  # 공백 제거
        return df
    except FileNotFoundError:
        return pd.DataFrame()

df = load_data()

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
    style_input = st.text_input("🔍 스타일 번호를 입력하세요:", "")

    if style_input:
        if 'Product Number' not in df.columns:
            st.error("❌ 'Product Number' 컬럼이 존재하지 않습니다. CSV 파일을 확인해주세요.")
        else:
            matched = df[df['Product Number'].astype(str).str.contains(style_input, case=False, na=False)]
            if not matched.empty:
                selected = st.selectbox("스타일 선택", matched['Product Number'] + " - " + matched.get('Default product name(en)', ""))
                selected_style = selected.split(" - ")[0]
                product = df[df['Product Number'] == selected_style].iloc[0]

                if 'First Image' in product and pd.notna(product['First Image']):
                    st.image(product['First Image'], width=300)

                st.subheader("✏️ 수정 가능 항목")
                erp_price = st.number_input("ERP PRICE", value=product.get("ERP PRICE", 0.0))
                shein_price = st.number_input("SHEIN PRICE", value=product.get("Special Offer Price(shein-us_USD)", 0.0))
                temu_price = st.number_input("TEMU PRICE", value=product.get("TEMU PRICE", 0.0))
                notes = st.text_area("NOTES", value=product.get("NOTES", ""))

                if st.button("💾 수정 저장"):
                    df.loc[df['Product Number'] == selected_style, 'ERP PRICE'] = erp_price
                    df.loc[df['Product Number'] == selected_style, 'SHEIN PRICE'] = shein_price
                    df.loc[df['Product Number'] == selected_style, 'TEMU PRICE'] = temu_price
                    df.loc[df['Product Number'] == selected_style, 'NOTES'] = notes
                    df.to_csv(PRODUCT_CSV, index=False)
                    st.success("✅ 수정사항이 저장되었습니다.")

                st.subheader("📏 Size Chart")
                st.markdown("(표시용 구현은 다음 단계에서 진행)")
            else:
                st.warning("해당 스타일을 찾을 수 없습니다.")

# --- 새로운 스타일 등록 페이지 ---
elif page == "➕ 새로운 스타일 등록":
    st.title("➕ 새 스타일 등록")
    st.warning("현재 이 기능은 표시만 되고 CSV 저장은 수동입니다.")
