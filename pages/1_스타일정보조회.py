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

                col1, col2 = st.columns([1, 2])
                with col1:
                    if 'First Image' in product and pd.notna(product['First Image']):
                        st.image(product['First Image'], width=300)

                with col2:
                    st.markdown("**ERP PRICE:** {:.2f}".format(product.get("ERP PRICE", 0.0)))
                    st.markdown("**SHEIN PRICE:** {:.2f}".format(product.get("SHEIN PRICE", 0.0)))
                    st.markdown("**TEMU PRICE:** {:.2f}".format(product.get("TEMU PRICE", 0.0)))
                    st.markdown("**SLEEVE:** {}".format(product.get("SLEEVE", "")))
                    st.markdown("**NECKLINE:** {}".format(product.get("NECKLINE", "")))
                    st.markdown("**LENGTH:** {}".format(product.get("LENGTH", "")))
                    st.markdown("**FIT:** {}".format(product.get("FIT", "")))
                    st.markdown("**DETAIL:** {}".format(product.get("DETAIL", "")))
                    st.markdown("**STYLE MOOD:** {}".format(product.get("STYLE MOOD", "")))
                    st.markdown("**MODEL:** {}".format(product.get("MODEL", "")))
                    st.markdown("**NOTES:** {}".format(product.get("NOTES", "")))

                st.markdown("---")
                st.subheader("📏 Size Chart")
                size_cols = [col for col in df.columns if any(x in col for x in ["TOP1_", "TOP2_", "BOTTOM_"])]
                size_data = product[size_cols].dropna()
                if not size_data.empty:
                    st.dataframe(size_data.T.rename(columns={product.name: "cm"}))
                else:
                    st.markdown("(사이즈 차트 정보가 없습니다)")
            else:
                st.warning("해당 스타일을 찾을 수 없습니다.")

# --- 새로운 스타일 등록 페이지 ---
elif page == "➕ 새로운 스타일 등록":
    st.title("➕ 새 스타일 등록")

    with st.form("new_style_form"):
        style_num = st.text_input("STYLE NUMBER")
        erp = st.number_input("ERP PRICE", step=0.01)
        shein_price = st.number_input("SHEIN PRICE", step=0.01)
        temu_price = st.number_input("TEMU PRICE", step=0.01)

        sleeve = st.text_input("SLEEVE")
        neckline = st.text_input("NECKLINE")
        length = st.text_input("LENGTH")
        fit = st.text_input("FIT")
        detail = st.text_input("DETAIL")
        style_mood = st.text_input("STYLE MOOD")
        piece = st.text_input("PIECE")
        model = st.text_input("MODEL")
        notes = st.text_area("NOTES")

        st.markdown("### 📏 Size Chart 입력")
        st.markdown("**TOP 1**")
        top1_chest = st.number_input("Top1 - Chest", step=0.1)
        top1_length = st.number_input("Top1 - Length", step=0.1)
        top1_sleeve = st.number_input("Top1 - Sleeve Length", step=0.1)

        st.markdown("**TOP 2 (선택)**")
        top2_chest = st.number_input("Top2 - Chest", step=0.1)
        top2_length = st.number_input("Top2 - Length", step=0.1)
        top2_sleeve = st.number_input("Top2 - Sleeve Length", step=0.1)

        st.markdown("**BOTTOM**")
        bottom_waist = st.number_input("Bottom - Waist", step=0.1)
        bottom_hip = st.number_input("Bottom - Hip", step=0.1)
        bottom_length = st.number_input("Bottom - Length", step=0.1)
        bottom_inseam = st.number_input("Bottom - Inseam", step=0.1)

        submitted = st.form_submit_button("등록하기")

        if submitted:
            new_row = pd.DataFrame([{
                "Product Number": style_num,
                "ERP PRICE": erp,
                "SHEIN PRICE": shein_price,
                "TEMU PRICE": temu_price,
                "SLEEVE": sleeve,
                "NECKLINE": neckline,
                "LENGTH": length,
                "FIT": fit,
                "DETAIL": detail,
                "STYLE MOOD": style_mood,
                "PIECE": piece,
                "MODEL": model,
                "NOTES": notes,
                "TOP1_CHEST": top1_chest,
                "TOP1_LENGTH": top1_length,
                "TOP1_SLEEVE": top1_sleeve,
                "TOP2_CHEST": top2_chest,
                "TOP2_LENGTH": top2_length,
                "TOP2_SLEEVE": top2_sleeve,
                "BOTTOM_WAIST": bottom_waist,
                "BOTTOM_HIP": bottom_hip,
                "BOTTOM_LENGTH": bottom_length,
                "BOTTOM_INSEAM": bottom_inseam
            }])
            df = pd.concat([df, new_row], ignore_index=True)
            df.to_csv(PRODUCT_CSV, index=False)
            st.success("✅ 새로운 스타일이 저장되었습니다.")
