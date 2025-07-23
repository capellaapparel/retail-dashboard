import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import os

INFO_CSV = "product_info_with_full_prices.csv"
IMAGE_CSV = "product_images.csv"
GOOGLE_SHEET_URL = "https://docs.google.com/spreadsheets/d/1oyVzCgGK1Q3Qi_sbYwE-wKG6SArnfUDRe7rQfGOF-Eo/edit"

@st.cache_data
def load_google_sheet():
    scope = ['https://spreadsheets.google.com/feeds','https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_name(
        'capella-streamlit-9e0d7d0d1fd0.json', scope)
    client = gspread.authorize(creds)
    sheet = client.open_by_url(GOOGLE_SHEET_URL)
    worksheet = sheet.worksheet("Sheet1")
    data = worksheet.get_all_records()
    return pd.DataFrame(data)

st.set_page_config(page_title="Capella Product Dashboard", layout="wide")
st.sidebar.title("📂 Capella Dashboard")
page = st.sidebar.radio("페이지 선택", ["🏠 홈", "📖 스타일 조회 (Google Sheets)", "➕ 새로운 스타일 등록 (CSV 저장)"])

# --- 홈 ---
if page == "🏠 홈":
    st.title("👋 Welcome to Capella Dashboard")
    st.markdown("""
이 대시보드는 다음 기능을 포함합니다:

📖 Google Sheets 기반 스타일 정보 조회  
➕ CSV 기반 새로운 스타일 등록  
📈 추후 세일즈 분석/추천 기능 확장 예정
""")

# --- 스타일 조회 (Google Sheets) ---
elif page == "📖 스타일 조회 (Google Sheets)":
    st.title("📖 스타일 정보 (읽기 전용)")

    df = load_google_sheet()
    style_input = st.text_input("🔍 스타일 번호 검색:")

    if style_input:
        df["Product Number"] = df["Product Number"].astype(str)
        matched = df[df["Product Number"].str.contains(style_input, case=False, na=False)]
        if not matched.empty:
            st.dataframe(matched)
        else:
            st.warning("❌ 일치하는 스타일 없음")
    else:
        st.dataframe(df)

# --- 새로운 스타일 등록 (CSV 저장) ---
elif page == "➕ 새로운 스타일 등록 (CSV 저장)":
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
        sleeve = st.text_input("SLEEVE")
        neckline = st.text_input("NECKLINE")
        length = st.text_input("LENGTH")
        fit = st.text_input("FIT")
        detail = st.text_input("DETAIL")
        style_mood = st.text_input("STYLE MOOD")
        model = st.text_input("MODEL")
        notes = st.text_area("NOTES")

        st.subheader("사이즈 차트")
        size_inputs = {}
        for section, fields in {
            "Top 1": ["TOP1_CHEST", "TOP1_LENGTH", "TOP1_SLEEVE"],
            "Top 2": ["TOP2_CHEST", "TOP2_LENGTH", "TOP2_SLEEVE"],
            "Bottom": ["BOTTOM_WAIST", "BOTTOM_HIP", "BOTTOM_LENGTH", "BOTTOM_INSEAM"]
        }.items():
            st.markdown(f"**{section}**")
            cols = st.columns(len(fields))
            for col, field in zip(cols, fields):
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
                    "SLEEVE": sleeve,
                    "NECKLINE": neckline,
                    "LENGTH": length,
                    "FIT": fit,
                    "DETAIL": detail,
                    "STYLE MOOD": style_mood,
                    "MODEL": model,
                    "NOTES": notes,
                }
                new_row.update(size_inputs)

                for col in new_row:
                    if col not in df_info.columns:
                        df_info[col] = None

                df_info = pd.concat([df_info, pd.DataFrame([new_row])], ignore_index=True)
                df_info.to_csv(INFO_CSV, index=False)
                st.success("🎉 스타일이 등록되었습니다. (CSV에 저장됨)")
