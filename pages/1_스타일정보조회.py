import streamlit as st
import pandas as pd

PRODUCT_CSV = "product_master.csv"

@st.cache_data
def load_data():
    try:
        df = pd.read_csv(PRODUCT_CSV, index_col=0)
        df.columns = df.columns.str.strip()
        return df
    except FileNotFoundError:
        return pd.DataFrame()

df = load_data()

st.title("Product Info Dashboard")
style_input = st.text_input("🔍 스타일 번호를 입력하세요:", "")

if style_input:
    if 'Product Number' not in df.columns:
        st.error("❌ 'Product Number' 컬럼이 존재하지 않습니다.")
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
