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
            selected_index = df_info[df_info["Product Number"] == selected].index[0]
            product_info = df_info.loc[selected_index]
            img_rows = df_img[df_img["Product Number"] == selected]
            product_img = img_rows.iloc[0] if not img_rows.empty else None

            st.markdown("---")
            col1, col2 = st.columns([1, 1])
            with col1:
                if product_img is not None and pd.notna(product_img.get("First Image", "")):
                    st.image(product_img["First Image"], width=280)
                else:
                    st.markdown("_이미지가 없습니다._")

            with col2:
                st.markdown(f"**Product Number:** {product_info['Product Number']}")
                st.markdown(f"**Product Name:** {product_img.get('default product name(en)', '') if product_img is not None else ''}")
                erp_price = st.number_input("ERP PRICE", value=product_info.get("ERP PRICE", 0.0))
                shein_price = st.number_input("SHEIN PRICE", value=product_img.get("SHEIN PRICE", 0.0) if product_img is not None else 0.0)
                sleeve = st.text_input("SLEEVE", value=product_info.get("SLEEVE", ""))
                neckline = st.text_input("NECKLINE", value=product_info.get("NECKLINE", ""))
                length = st.text_input("LENGTH", value=product_info.get("LENGTH", ""))
                fit = st.text_input("FIT", value=product_info.get("FIT", ""))
                detail = st.text_input("DETAIL", value=product_info.get("DETAIL", ""))
                style_mood = st.text_input("STYLE MOOD", value=product_info.get("STYLE MOOD", ""))
                model = st.text_input("MODEL", value=product_info.get("MODEL", ""))
                notes = st.text_area("NOTES", value=product_info.get("NOTES", ""))

            st.markdown("---")
            st.markdown("### 📏 Size Chart")

            size_inputs = {}
            chart_sections = {
                "Top 1": ["TOP1_CHEST", "TOP1_LENGTH", "TOP1_SLEEVE"],
                "Top 2": ["TOP2_CHEST", "TOP2_LENGTH", "TOP2_SLEEVE"],
                "Bottom": ["BOTTOM_WAIST", "BOTTOM_HIP", "BOTTOM_LENGTH", "BOTTOM_INSEAM"]
            }

            for section, fields in chart_sections.items():
                st.markdown(f"**{section}**")
                chart_data = []
                for field in fields:
                    default_val = product_info.get(field, 0.0)
                    input_val = st.number_input(field.replace("_", " "), value=float(default_val) if pd.notna(default_val) else 0.0, key=field)
                    size_inputs[field] = input_val
                    chart_data.append({"Measurement": field.split("_")[1].capitalize(), "cm": input_val})
                chart_df = pd.DataFrame(chart_data)
                st.table(chart_df)

            if st.button("💾 수정 저장"):
                df_info.at[selected_index, "ERP PRICE"] = erp_price
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
                st.success("✅ 수정 사항이 저장되었습니다.")
        else:
            st.warning("❌ 해당 스타일을 찾을 수 없습니다.")
