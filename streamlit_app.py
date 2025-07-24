import streamlit as st
import pandas as pd
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- Google Sheet URL & Settings ---
GOOGLE_SHEET_URL = "https://docs.google.com/spreadsheets/d/1oyVzCgGK1Q3Qi_sbYwE-wKG6SArnfUDRe7rQfGOF-Eo"
SHEET_NAME = "Sheet1"
IMAGE_CSV = "product_images.csv"

st.set_page_config(page_title="Capella Product Viewer", layout="wide")
st.title("📖 스타일 정보 (읽기 전용)")

@st.cache_data(show_spinner=False)
def load_google_sheet():
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive"
    ]

    json_data = {k: str(v) for k, v in st.secrets["gcp_service_account"].items()}

    with open("/tmp/service_account.json", "w") as f:
        json.dump(json_data, f)

    creds = ServiceAccountCredentials.from_json_keyfile_name("/tmp/service_account.json", scope)
    client = gspread.authorize(creds)
    sheet = client.open_by_url(GOOGLE_SHEET_URL).worksheet(SHEET_NAME)
    data = sheet.get_all_records()
    return pd.DataFrame(data)

@st.cache_data(show_spinner=False)
def load_images():
    return pd.read_csv(IMAGE_CSV)

# --- Load Data ---
try:
    df_info = load_google_sheet()
    df_img = load_images()
except Exception as e:
    st.error("❌ 데이터 로드 실패: " + str(e))
    st.stop()

# --- Style Number 검색 ---
style_input = st.text_input("🔍 스타일 번호를 입력하세요:", "")

if style_input:
    matched = df_info[df_info["Product Number"].astype(str).str.contains(style_input, case=False, na=False)]

    if matched.empty:
        st.warning("❌ 해당 스타일을 찾을 수 없습니다.")
    else:
        selected = st.selectbox("스타일 선택", matched["Product Number"].astype(str))
        row = df_info[df_info["Product Number"] == selected].iloc[0]
        img_row = df_img[df_img["Product Number"] == selected]
        image_url = img_row.iloc[0]["First Image"] if not img_row.empty else None

        st.markdown("---")
        col1, col2 = st.columns([1, 2])

        with col1:
            if image_url:
                st.image(image_url, width=300)
            else:
                st.caption("이미지 없음")

        with col2:
            st.subheader(row.get("default product name(en)", ""))
            st.markdown(f"**Product Number:** {row['Product Number']}")
            st.markdown(f"**ERP PRICE:** {row.get('ERP PRICE', '')}")
            st.markdown(f"**SHEIN PRICE:** (판매 데이터 기반 추후 반영)")
            st.markdown(f"**TEMU PRICE:** (판매 데이터 기반 추후 반영)")
            st.markdown(f"**SLEEVE:** {row.get('SLEEVE', '')}")
            st.markdown(f"**NECKLINE:** {row.get('NECKLINE', '')}")
            st.markdown(f"**LENGTH:** {row.get('LENGTH', '')}")
            st.markdown(f"**FIT:** {row.get('FIT', '')}")
            st.markdown(f"**DETAIL:** {row.get('DETAIL', '')}")
            st.markdown(f"**STYLE MOOD:** {row.get('STYLE MOOD', '')}")
            st.markdown(f"**MODEL:** {row.get('MODEL', '')}")
            st.markdown(f"**NOTES:** {row.get('NOTES', '')}")

        st.markdown("---")
        st.subheader("📏 Size Chart")

        # New layout format
        st.markdown("**Top 1**")
        col_top1 = st.columns(3)
        col_top1[0].markdown(f"Chest: {row.get('TOP1_CHEST', '')}")
        col_top1[1].markdown(f"Length: {row.get('TOP1_LENGTH', '')}")
        col_top1[2].markdown(f"Sleeve: {row.get('TOP1_SLEEVE', '')}")

        st.markdown("**Top 2**")
        col_top2 = st.columns(3)
        col_top2[0].markdown(f"Chest: {row.get('TOP2_CHEST', '')}")
        col_top2[1].markdown(f"Length: {row.get('TOP2_LENGTH', '')}")
        col_top2[2].markdown(f"Sleeve: {row.get('TOP2_SLEEVE', '')}")

        st.markdown("**Bottom**")
        col_bottom = st.columns(4)
        col_bottom[0].markdown(f"Waist: {row.get('BOTTOM_WAIST', '')}")
        col_bottom[1].markdown(f"Hip: {row.get('BOTTOM_HIP', '')}")
        col_bottom[2].markdown(f"Length: {row.get('BOTTOM_LENGTH', '')}")
        col_bottom[3].markdown(f"Inseam: {row.get('BOTTOM_INSEAM', '')}")
