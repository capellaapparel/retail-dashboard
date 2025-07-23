import streamlit as st
import pandas as pd

INFO_CSV = "product_info.csv"
IMAGE_CSV = "product_images.csv"

@st.cache_data
def load_data():
    df_info = pd.read_csv(INFO_CSV)
    df_img = pd.read_csv(IMAGE_CSV)
    return df_info, df_img

df_info, df_img = load_data()

st.title("Product Info Dashboard")

style_input = st.text_input("🔍 스타일 번호를 입력하세요:", "")

if style_input:
    matched = df_info[df_info["Product Number"].astype(str).str.contains(style_input, case=False, na=False)]

    if not matched.empty:
        selected = st.selectbox(
            "스타일 선택",
            matched["Product Number"].astype(str)
        )
        product_info = df_info[df_info["Product Number"] == selected].iloc[0]
        product_img = df_img[df_img["Product Number"] == selected].iloc[0] if not df_img[df_img["Product Number"] == selected].empty else {}

        # 🔲 상단: 이미지 + 인포
        col1, col2 = st.columns([1, 2])

        with col1:
            if product_img and pd.notna(product_img.get("First Image", "")):
                st.image(product_img["First Image"], width=300)
            else:
                st.markdown("_이미지가 없습니다._")

        with col2:
            st.markdown(f"**Product Number:** {product_info['Product Number']}")
            st.markdown(f"**Product Name:** {product_img.get('default product name(en)', '')}")
            st.markdown(f"**ERP PRICE:** ${product_info.get('ERP PRICE', 0):.2f}")
            st.markdown(f"**SHEIN PRICE:** ${product_img.get('SHEIN PRICE', 0):.2f}")
            st.markdown(f"**SLEEVE:** {product_info.get('SLEEVE', '')}")
            st.markdown(f"**NECKLINE:** {product_info.get('NECKLINE', '')}")
            st.markdown(f"**LENGTH:** {product_info.get('LENGTH', '')}")
            st.markdown(f"**FIT:** {product_info.get('FIT', '')}")
            st.markdown(f"**DETAIL:** {product_info.get('DETAIL', '')}")
            st.markdown(f"**STYLE MOOD:** {product_info.get('STYLE MOOD', '')}")
            st.markdown(f"**MODEL:** {product_info.get('MODEL', '')}")
            st.markdown(f"**NOTES:** {product_info.get('NOTES', '')}")

        # 📏 하단: 사이즈 차트
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
