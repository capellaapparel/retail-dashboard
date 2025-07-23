import streamlit as st
import pandas as pd
import os

INFO_CSV = "product_info.csv"

st.set_page_config(page_title="Capella Product Dashboard", layout="wide")
st.sidebar.title("📂 Capella Dashboard")
page = st.sidebar.radio("페이지 선택", ["🏠 홈", "🔍 스타일 정보 조회", "➕ 새로운 스타일 등록"])

# --- 홈 화면 ---
if page == "🏠 홈":
    st.title("👋 Welcome to Capella Dashboard")
    st.markdown("""
이 대시보드는 다음 기능을 포함합니다:

🔍 스타일 정보 조회  
➕ 새로운 스타일 등록  
📈 추후 세일즈 예측/추천 기능 확장 예정
""")

# --- 스타일 조회 ---
elif page == "🔍 스타일 정보 조회":
    st.title("Product Info Dashboard")

    if os.path.exists(INFO_CSV):
        df = pd.read_csv(INFO_CSV)
    else:
        st.warning("❌ product_info.csv 파일이 없습니다.")
        st.stop()

    style_input = st.text_input("🔍 스타일 번호를 입력하세요:", "")

    if style_input:
        matched = df[df["Product Number"].astype(str).str.contains(style_input, case=False, na=False)]

        if not matched.empty:
            selected = st.selectbox("스타일 선택", matched["Product Number"].astype(str))
            selected_index = df[df["Product Number"].astype(str) == selected].index[0]
            product_info = df.loc[selected_index]

            st.markdown("---")
            st.markdown(f"**Product Number:** `{product_info['Product Number']}`")

            col1, col2 = st.columns(2)
            with col1:
                erp_price = st.number_input("ERP PRICE", value=float(product_info.get("ERP PRICE", 0.0)))
                temu_price = st.number_input("TEMU PRICE", value=float(product_info.get("TEMU PRICE", 0.0)))
                sleeve = st.text_input("SLEEVE", value=str(product_info.get("SLEEVE", "")))
                neckline = st.text_input("NECKLINE", value=str(product_info.get("NECKLINE", "")))
                length = st.text_input("LENGTH", value=str(product_info.get("LENGTH", "")))
                fit = st.text_input("FIT", value=str(product_info.get("FIT", "")))

            with col2:
                detail = st.text_input("DETAIL", value=str(product_info.get("DETAIL", "")))
                style_mood = st.text_input("STYLE MOOD", value=str(product_info.get("STYLE MOOD", "")))
                model = st.text_input("MODEL", value=str(product_info.get("MODEL", "")))
                notes = st.text_area("NOTES", value=str(product_info.get("NOTES", "")))

            st.markdown("### 📏 Size Chart")
            size_inputs = {}
            size_fields = [
                "TOP1_CHEST", "TOP1_LENGTH", "TOP1_SLEEVE",
                "TOP2_CHEST", "TOP2_LENGTH", "TOP2_SLEEVE",
                "BOTTOM_WAIST", "BOTTOM_HIP", "BOTTOM_LENGTH", "BOTTOM_INSEAM"
            ]
            cols = st.columns(5)
            for i, field in enumerate(size_fields):
                with cols[i % 5]:
                    size_inputs[field] = st.number_input(field, value=float(product_info.get(field, 0.0)))

            if st.button("💾 수정 저장"):
                df.at[selected_index, "ERP PRICE"] = erp_price
                df.at[selected_index, "TEMU PRICE"] = temu_price
                df.at[selected_index, "SLEEVE"] = sleeve
                df.at[selected_index, "NECKLINE"] = neckline
                df.at[selected_index, "LENGTH"] = length
                df.at[selected_index, "FIT"] = fit
                df.at[selected_index, "DETAIL"] = detail
                df.at[selected_index, "STYLE MOOD"] = style_mood
                df.at[selected_index, "MODEL"] = model
                df.at[selected_index, "NOTES"] = notes
                for field, value in size_inputs.items():
                    df.at[selected_index, field] = value
                df.to_csv(INFO_CSV, index=False)
                st.success("✅ 수정 사항이 저장되었습니다.")
                st.experimental_rerun()
        else:
            st.warning("❌ 일치하는 스타일이 없습니다.")

# --- 스타일 등록 페이지 ---
elif page == "➕ 새로운 스타일 등록":
    st.title("➕ 새 스타일 등록")

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
        style_mood = st.multiselect("STYLE MOOD", ["Casual", "Elegant", "Street", "Sexy", "Active"])
        custom_mood = st.text_input("새로운 무드 추가 (옵션)")
        model = st.text_input("MODEL")
        notes = st.text_area("NOTES")

        st.subheader("사이즈 차트")
        size_inputs = {}
        size_fields = [
            "TOP1_CHEST", "TOP1_LENGTH", "TOP1_SLEEVE",
            "TOP2_CHEST", "TOP2_LENGTH", "TOP2_SLEEVE",
            "BOTTOM_WAIST", "BOTTOM_HIP", "BOTTOM_LENGTH", "BOTTOM_INSEAM"
        ]
        for field in size_fields:
            size_inputs[field] = st.number_input(field, min_value=0.0, value=0.0)

        submitted = st.form_submit_button("✅ 스타일 등록")

        if submitted:
            if not product_number or erp_price == 0.0:
                st.error("❌ 필수 항목이 비어있습니다.")
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

                for col in new_row:
                    if col not in df.columns:
                        df[col] = None

                df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
                df.to_csv(INFO_CSV, index=False)
                st.success("🎉 새로운 스타일이 등록되었습니다.")
                st.experimental_rerun()
