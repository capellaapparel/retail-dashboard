import streamlit as st
import pandas as pd

PRODUCT_CSV = "product_master.csv"

@st.cache_data
def load_data():
    df = pd.read_csv(PRODUCT_CSV)
    df.columns = df.columns.str.strip()
    return df

df = load_data()

st.title("Product Info Dashboard")

style_input = st.text_input("🔍 스타일 번호를 입력하세요 (예: BT33)", "")

if style_input:
    matches = df[df["Product Number"].astype(str).str.contains(style_input, case=False, na=False)]

    if not matches.empty:
        selected = st.selectbox(
            "스타일 선택",
            matches["Product Number"].astype(str) + " - " + matches.get("default product name(en)", "")
        )

        selected_style = selected.split(" - ")[0]
        product_rows = df[df["Product Number"] == selected_style]

        # 대표 row 하나 선택 (일단 첫 번째)
        product = product_rows.iloc[0]

        # --- 이미지 ---
        if pd.notna(product.get("First Image", "")):
            st.image(product["First Image"], width=320)
        else:
            st.markdown("*이미지가 없습니다*")

        # --- 제품 정보 요약 ---
        st.markdown("### 🧾 Product Info")
        col1, col2 = st.columns(2)
        with col1:
            st.markdown(f"**Product Number:** {product.get('Product Number', '')}")
            st.markdown(f"**Product Name:** {product.get('default product name(en)', '')}")
            st.markdown(f"**ERP PRICE:** ${product.get('ERP PRICE', 0):.2f}")
            st.markdown(f"**SHEIN PRICE:** ${product.get('Special Offer Price(shein-us_USD)', 0):.2f}")
        with col2:
            st.markdown(f"**SLEEVE:** {product.get('SLEEVE', '')}")
            st.markdown(f"**NECKLINE:** {product.get('NECKLINE', '')}")
            st.markdown(f"**LENGTH:** {product.get('LENGTH', '')}")
            st.markdown(f"**FIT:** {product.get('FIT', '')}")
            st.markdown(f"**DETAIL:** {product.get('DETAIL', '')}")
            st.markdown(f"**STYLE MOOD:** {product.get('STYLE MOOD', '')}")
            st.markdown(f"**MODEL:** {product.get('MODEL', '')}")
            st.markdown(f"**NOTES:** {product.get('NOTES', '')}")

        # --- 사이즈 차트 ---
        st.markdown("### 📏 Size Chart")
        size_cols = [col for col in df.columns if any(x in col for x in ["TOP1_", "TOP2_", "BOTTOM_"])]
        size_data = product[size_cols].dropna()

        if not size_data.empty:
            size_df = pd.DataFrame(size_data).T.reset_index()
            size_df.columns = ["Measurement", "cm"]
            st.dataframe(size_df, use_container_width=True)
        else:
            st.markdown("_사이즈 정보 없음_")
    else:
        st.warning("해당 스타일을 찾을 수 없습니다.")
