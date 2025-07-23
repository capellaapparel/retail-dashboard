import streamlit as st
import pandas as pd

@st.cache_data
def load_data():
    try:
        return pd.read_csv("shein_sales_summary.csv")
    except FileNotFoundError:
        return pd.DataFrame()

df = load_data()

st.title("Product Info Dashboard")

style_input = st.text_input("🔍 스타일 번호를 입력하세요:", "")

if style_input:
    matched = df[df['SPU'].str.contains(style_input, case=False, na=False)]
    if not matched.empty:
        selected = st.selectbox("스타일 선택", matched['SPU'] + " - " + matched['Goods name'])
        selected_spu = selected.split(" - ")[0]
        product = df[df['SPU'] == selected_spu].iloc[0]

        st.image(product['Product image link'], width=300)

        st.subheader("📏 Size Chart")
        st.markdown("**TOP 1**")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.number_input("Chest", key="top1_chest")
        with col2:
            st.number_input("Length", key="top1_length")
        with col3:
            st.number_input("Sleeve Length", key="top1_sleeve")

        st.markdown("**TOP 2**")
        col4, col5, col6 = st.columns(3)
        with col4:
            st.number_input("Chest", key="top2_chest")
        with col5:
            st.number_input("Length", key="top2_length")
        with col6:
            st.number_input("Sleeve Length", key="top2_sleeve")

        st.markdown("**BOTTOM**")
        col7, col8, col9, col10 = st.columns(4)
        with col7:
            st.number_input("Waist", key="bottom_waist")
        with col8:
            st.number_input("Hip", key="bottom_hip")
        with col9:
            st.number_input("Length", key="bottom_length")
        with col10:
            st.number_input("Inseam", key="bottom_inseam")

        st.subheader("💡 Product Info")
        st.write(f"**ERP PRICE**: {product['Gross Merchandise Volume']}")
        st.write("**SHEIN PRICE**: 자동입력 예정")
        st.write("**TEMU PRICE**: 자동입력 예정")
    else:
        st.warning("해당 스타일을 찾을 수 없습니다.")
