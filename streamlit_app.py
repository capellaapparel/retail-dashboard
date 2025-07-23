import streamlit as st
import pandas as pd
import os

INFO_CSV = "product_info_with_full_prices.csv"
IMAGE_CSV = "product_images.csv"

st.set_page_config(page_title="Capella Product Dashboard", layout="wide")
st.sidebar.title("📂 Capella Dashboard")
page = st.sidebar.radio("페이지 선택", ["🏠 홈", "🔍 스타일 정보 조회", "➕ 새로운 스타일 등록"])

# --- 드롭다운 옵션 목록 ---
STYLE_OPTIONS = {
    "SLEEVE": ["Sleeveless", "Short", "3/4", "Long"],
    "NECKLINE": ["Round", "Scoop", "V neck", "Halter", "Crew", "Off Shoulder", "One Shoulder", "Square", "Hooded", "Asymmetrical", "Spaghetti", "Double Strap", "Cami", "Split", "Mock", "High", "Tube", "Jacket", "Plunge", "Cut Out", "Collar", "Cowl"],
    "LENGTH": ["Crop Top", "Waist Top", "Long Top", "Mini Dress", "Midi Dress", "Maxi Dress", "Mini Skirt", "Midi Skirt", "Maxi Skirt", "Shorts", "Knee", "Capri", "Full"],
    "FIT": ["Slim", "Regular", "Loose"],
    "DETAIL": ["Ruched", "Cut Out", "Drawstring", "Slit", "Button", "Zipper", "Tie", "Backless", "Wrap", "Stripe", "Graphic", "Wide Leg", "Pocket", "Pleated", "Exposed Seam", "Criss Cross", "Ring", "Asymmetrical", "Mesh", "Puff", "Shirred", "Tie Dye", "Fringe", "Racer Back", "Corset", "Lace", "Tier", "Twist", "Lettuce Trim"],
    "STYLE MOOD": ["Sexy", "Casual", "Lounge", "Formal", "Activewear"],
    "MODEL": ["Latina", "Black", "Caucasian", "Plus", "Asian"]
}

def dropdown_or_input(label, value, options):
    """드롭다운 + 직접입력 UI"""
    options = list(dict.fromkeys(options))  # 중복 제거
    if value in options:
        method = st.selectbox(f"{label} 선택 방식", ["선택", "직접 입력"], key=f"{label}_method", index=0)
    else:
        method = "직접 입력"
    if method == "선택":
        return st.selectbox(label, options, index=options.index(value) if value in options else 0, key=label)
    else:
        return st.text_input(f"{label} (직접 입력)", value=value, key=f"{label}_custom")

# --- 홈 ---
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
    st.title("🔍 스타일 정보 조회")

    if not os.path.exists(INFO_CSV):
        st.error("❌ 제품 정보 파일이 없습니다.")
        st.stop()

    df_info = pd.read_csv(INFO_CSV)
    df_img = pd.read_csv(IMAGE_CSV) if os.path.exists(IMAGE_CSV) else pd.DataFrame()

    style_input = st.text_input("🔍 스타일 번호 검색:", "")
    if style_input:
        df_info["Product Number"] = df_info["Product Number"].astype(str)
        matched = df_info[df_info["Product Number"].str.contains(style_input, case=False, na=False)]

        if not matched.empty:
            selected = st.selectbox("스타일 선택", matched["Product Number"])
            selected_index = df_info[df_info["Product Number"] == selected].index[0]
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
                shein_price = st.number_input("SHEIN PRICE", value=float(row.get("SHEIN PRICE", 0.0)))
                temu_price = st.number_input("TEMU PRICE", value=float(row.get("TEMU PRICE", 0.0)))

                inputs = {}
                for field in ["SLEEVE", "NECKLINE", "LENGTH", "FIT", "DETAIL", "STYLE MOOD", "MODEL"]:
                    inputs[field] = dropdown_or_input(field, str(row.get(field, "")), STYLE_OPTIONS[field])
                notes = st.text_area("NOTES", value=str(row.get("NOTES", "")))

            st.markdown("### 📏 사이즈 차트")

            size_inputs = {}
            st.markdown("**Top 1**")
            for col, field in zip(st.columns(3), ["TOP1_CHEST", "TOP1_LENGTH", "TOP1_SLEEVE"]):
                with col:
                    size_inputs[field] = st.number_input(field, value=float(row.get(field, 0.0)))

            st.markdown("**Top 2**")
            for col, field in zip(st.columns(3), ["TOP2_CHEST", "TOP2_LENGTH", "TOP2_SLEEVE"]):
                with col:
                    size_inputs[field] = st.number_input(field, value=float(row.get(field, 0.0)))

            st.markdown("**Bottom**")
            for col, field in zip(st.columns(4), ["BOTTOM_WAIST", "BOTTOM_HIP", "BOTTOM_LENGTH", "BOTTOM_INSEAM"]):
                with col:
                    size_inputs[field] = st.number_input(field, value=float(row.get(field, 0.0)))

            if st.button("💾 수정 저장"):
                df_info.at[selected_index, "ERP PRICE"] = erp_price
                df_info.at[selected_index, "SHEIN PRICE"] = shein_price
                df_info.at[selected_index, "TEMU PRICE"] = temu_price
                for k, v in inputs.items():
                    df_info.at[selected_index, k] = v
                df_info.at[selected_index, "NOTES"] = notes
                for field, val in size_inputs.items():
                    df_info.at[selected_index, field] = val
                df_info.to_csv(INFO_CSV, index=False)
                st.success("✅ 저장 완료")

        else:
            st.warning("❌ 일치하는 스타일이 없습니다.")

# --- 스타일 등록 ---
elif page == "➕ 새로운 스타일 등록":
    st.title("➕ 새 스타일 등록")

    if not os.path.exists(INFO_CSV):
        df_info = pd.DataFrame()
    else:
        df_info = pd.read_csv(INFO_CSV)

    with st.form("new_product_form"):
        st.subheader("기본 정보")
        product_number = st.text_input("Product Number*", placeholder="예: BT1234")
        erp_price = st.number_input("ERP PRICE*", min_value=0.0, value=0.0)
        shein_price = st.number_input("SHEIN PRICE", min_value=0.0, value=0.0)
        temu_price = st.number_input("TEMU PRICE", min_value=0.0, value=0.0)

        st.subheader("스타일 속성")
        inputs = {}
        for field in ["SLEEVE", "NECKLINE", "LENGTH", "FIT", "DETAIL", "STYLE MOOD", "MODEL"]:
            inputs[field] = dropdown_or_input(field, "", STYLE_OPTIONS[field])
        notes = st.text_area("NOTES")

        st.subheader("사이즈 차트")
        size_inputs = {}

        st.markdown("**Top 1**")
        for col, field in zip(st.columns(3), ["TOP1_CHEST", "TOP1_LENGTH", "TOP1_SLEEVE"]):
            with col:
                size_inputs[field] = st.number_input(field, min_value=0.0, value=0.0)

        st.markdown("**Top 2**")
        for col, field in zip(st.columns(3), ["TOP2_CHEST", "TOP2_LENGTH", "TOP2_SLEEVE"]):
            with col:
                size_inputs[field] = st.number_input(field, min_value=0.0, value=0.0)

        st.markdown("**Bottom**")
        for col, field in zip(st.columns(4), ["BOTTOM_WAIST", "BOTTOM_HIP", "BOTTOM_LENGTH", "BOTTOM_INSEAM"]):
            with col:
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
                    "SHEIN PRICE": shein_price,
                    "TEMU PRICE": temu_price,
                    "NOTES": notes,
                }
                new_row.update(inputs)
                new_row.update(size_inputs)

                for col in new_row:
                    if col not in df_info.columns:
                        df_info[col] = None

                df_info = pd.concat([df_info, pd.DataFrame([new_row])], ignore_index=True)
                df_info.to_csv(INFO_CSV, index=False)
                st.success("🎉 스타일이 등록되었습니다.")
