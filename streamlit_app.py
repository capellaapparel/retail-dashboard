import streamlit as st
import pandas as pd
import os

# 실제 파일 경로 지정
INFO_CSV = "product_info_with_sizes.csv"
IMAGE_CSV = "product_images.csv"

st.set_page_config(page_title="Capella Product Dashboard", layout="wide")
st.sidebar.title("📂 Capella Dashboard")
page = st.sidebar.radio("페이지 선택", ["🏠 홈", "🔍 스타일 정보 조회", "➕ 새로운 스타일 등록"])

# --- 홈 페이지 ---
if page == "🏠 홈":
    st.title("👋 Welcome to Capella Dashboard")
    st.markdown("""
이 대시보드는 다음 기능을 포함합니다:

🔍 스타일 정보 조회  
➕ 새로운 스타일 등록  
📈 추후 세일즈 예측/추천 기능 확장 예정
""")

# --- 스타일 정보 조회 페이지 ---
elif page == "🔍 스타일 정보 조회":
    st.title("🔍 스타일 정보 조회")

    if os.path.exists(INFO_CSV):
        df_info = pd.read_csv(INFO_CSV)
    else:
        st.warning("❌ product_info_with_sizes.csv 파일이 없습니다.")
        st.stop()

    if os.path.exists(IMAGE_CSV):
        df_img = pd.read_csv(IMAGE_CSV)
    else:
        df_img = pd.DataFrame()

    style_input = st.text_input("🔍 스타일 번호 검색:", "")

    if style_input:
        df_info["Product Number"] = df_info["Product Number"].astype(str)
        df_info = df_info[df_info["Product Number"].notna()]
        matched = df_info[df_info["Product Number"].str.contains(style_input, case=False, na=False)]

        if not matched.empty:
            selected = st.selectbox("스타일 선택", matched["Product Number"].astype(str))
            selected_index = df_info[df_info["Product Number"].astype(str) == selected].index[0]
            row = df_info.loc[selected_index]

            st.markdown("---")
            col1, col2 = st.columns([1, 2])

            with col1:
                img_row = df_img[df_img["Product Number"] == selected]
                if not img_row.empty and pd.notna(img_row.iloc[0].get("First Image", "")):
                    st.image(img_row.iloc[0]["First Image"], width=250)
                else:
                    st.markdown("_이미지 없음_")

            with col2:
                st.markdown(f"**Product Number:** `{row['Product Number']}`")
                erp_price = st.number_input("ERP PRICE", value=float(row.get("ERP PRICE", 0.0)))
                temu_price = st.number_input("TEMU PRICE", value=float(row.get("TEMU PRICE", 0.0)))
                sleeve = st.text_input("SLEEVE", value=str(row.get("SLEEVE", "")))
                neckline = st.text_input("NECKLINE", value=str(row.get("NECKLINE", "")))
                length = st.text_input("LENGTH", value=str(row.get("LENGTH", "")))
                fit = st.text_input("FIT", value=str(row.get("FIT", "")))
                detail = st.text_input("DETAIL", value=str(row.get("DETAIL", "")))
                style_mood = st.text_input("STYLE MOOD", value=str(row.get("STYLE MOOD", "")))
                model = st.text_input("MODEL", value=str(row.get("MODEL", "")))
                notes = st.text_area("NOTES", value=str(row.get("NOTES", "")))

            st.markdown("### 📏 사이즈 차트")
            size_fields = [
                "TOP1_CHEST", "TOP1_LENGTH", "TOP1_SLEEVE",
                "TOP2_CHEST", "TOP2_LENGTH", "TOP2_SLEEVE",
                "BOTTOM_WAIST", "BOTTOM_HIP", "BOTTOM_LENGTH", "BOTTOM_INSEAM"
            ]
            size_inputs = {}
            cols = st.columns(5)
            for i, field in enumerate(size_fields):
                with cols[i % 5]:
                    size_inputs[field] = st.number_input(field, value=float(row.get(field, 0.0)))

            if st.button("💾 수정 저장"):
                df_info.at[selected_index, "ERP PRICE"] = erp_price
                df_info.at[selected_index, "TEMU PRICE"] = temu_price
                df_info.at[selected_index, "SLEEVE"] = sleeve
                df_info.at[selected_index, "NECKLINE"] = neckline
                df_info.at[selected_index, "LENGTH"] = length
                df_info.at[selected_index, "FIT"] = fit
                df_info.at[selected_index, "DETAIL"] = detail
                df_info.at[selected_index, "STYLE MOOD"] = style_mood
                df_info.at[selected_index, "MODEL"] = model
                df_info.at[selected_index, "NOTES"] = notes
                for field, val in size_inputs.items():
                    df_info.at[selected_index, field] = val

                df_info.to_csv(INFO_CSV, index=False)
                st.success("✅ 저장 완료")
                st.experimental_rerun()

        else:
            st.warning("❌ 일치하는 스타일이 없습니다.")

# --- 새로운 스타일 등록 페이지 ---
elif page == "➕ 새로운 스타일 등록":
    st.title("➕ 새 스타일 등록")

    if os.path.exists(INFO_CSV):
        df_info = pd.read_csv(INFO_CSV)
    else:
        df_info = pd.DataFrame()

    with st.form("new_product_form"):
        st.subheader("기본 정보")
        product_number = st.text_input("Product Number*", placeholder="예: BT1234")
        erp_price = st.number_input("ERP PRICE*", min_value=0.0, value=0.0)
        temu_price = st.number_input("TEMU PRICE", min_value=0.0, value=0.0)

        st.subheader("스타일 속성")
        sleeve = st.text_input("SLEEVE")
        neckline = st.text_input("NECKLINE")
        length = st.text_input("LENGTH")
        fit = st.text_input("FIT")
        detail = st.text_input("DETAIL")
        style_mood = st.text_input("STYLE MOOD")
        model = st.text_input("MODEL")
        notes = st.text_area("NOTES")

        st.subheader("사이즈 차트")
        size_fields = [
            "TOP1_CHEST", "TOP1_LENGTH", "TOP1_SLEEVE",
            "TOP2_CHEST", "TOP2_LENGTH", "TOP2_SLEEVE",
            "BOTTOM_WAIST", "BOTTOM_HIP", "BOTTOM_LENGTH", "BOTTOM_INSEAM"
        ]
        size_inputs = {}
        cols = st.columns(5)
        for i, field in enumerate(size_fields):
            with cols[i % 5]:
                size_inputs[field] = st.number_input(field, min_value=0.0, value=0.0)

        submitted = st.form_submit_button("✅ 스타일 등록")

        if submitted:
            if not product_number or erp_price == 0.0:
                st.error("❌ 필수 입력값이 누락되었습니다.")
            elif product_number in df_info["Product Number"].astype(str).values:
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
                    "STYLE MOOD": style_mood,
                    "MODEL": model,
                    "NOTES": notes
                }
                new_row.update(size_inputs)

                for col in new_row:
                    if col not in df_info.columns:
                        df_info[col] = None

                df_info = pd.concat([df_info, pd.DataFrame([new_row])], ignore_index=True)
                df_info.to_csv(INFO_CSV, index=False)
                st.success("🎉 스타일이 등록되었습니다.")
                st.experimental_rerun()
