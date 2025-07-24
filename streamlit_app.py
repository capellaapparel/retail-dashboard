import streamlit as st
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd

# --- 설정값
GOOGLE_SHEET_URL = "https://docs.google.com/spreadsheets/d/1oyVzCgGK1Q3Qi_sbYwE-wKG6SArnfUDRe7rQfGOF-Eo"
IMAGE_CSV = "product_images.csv"

# --- Google Sheets 로드 함수
@st.cache_data
def load_sheet():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    
    # Streamlit Secrets에서 서비스 계정 정보 받아와 임시 저장
    json_data = st.secrets["gcp_service_account"]
    with open("/tmp/service_account.json", "w") as f:
        json.dump(json_data, f)

    creds = ServiceAccountCredentials.from_json_keyfile_name("/tmp/service_account.json", scope)
    client = gspread.authorize(creds)
    sheet = client.open_by_url(GOOGLE_SHEET_URL).worksheet("Sheet1")
    data = sheet.get_all_records()
    return pd.DataFrame(data)

# --- 이미지 CSV 로드
@st.cache_data
def load_images():
    try:
        return pd.read_csv(IMAGE_CSV)
    except FileNotFoundError:
        return pd.DataFrame()

# --- Streamlit 페이지 설정
st.set_page_config(page_title="Capella Product Viewer", layout="wide")
st.title("📖 Capella 제품 정보 (Google Sheets 기반 조회 전용)")

df_info = load_sheet()
df_img = load_images()

# --- 검색 입력
style_input = st.text_input("🔍 스타일 번호 검색:")

if style_input:
    df_info["Product Number"] = df_info["Product Number"].astype(str)
    matched = df_info[df_info["Product Number"].str.contains(style_input, case=False, na=False)]

    if not matched.empty:
        selected = st.selectbox("스타일 선택", matched["Product Number"])
        row = matched[matched["Product Number"] == selected].iloc[0]

        st.markdown("---")
        col1, col2 = st.columns([1, 2])

        # --- 이미지 표시
        with col1:
            img_row = df_img[df_img["Product Number"] == selected]
            if not img_row.empty and pd.notna(img_row.iloc[0].get("First Image", "")):
                st.image(img_row.iloc[0]["First Image"], width=280)
            else:
                st.markdown("_이미지 없음_")

        # --- 제품 기본 정보
        with col2:
            for field in [
                "Product Number", "ERP PRICE", "SLEEVE", "NECKLINE", "LENGTH",
                "FIT", "DETAIL", "STYLE MOOD", "MODEL", "NOTES"
            ]:
                value = row.get(field, "")
                st.markdown(f"**{field}:** {value}")

        # --- 사이즈 차트
        st.markdown("### 📏 Size Chart")
        for section, fields in {
            "Top 1": ["TOP1_CHEST", "TOP1_LENGTH", "TOP1_SLEEVE"],
            "Top 2": ["TOP2_CHEST", "TOP2_LENGTH", "TOP2_SLEEVE"],
            "Bottom": ["BOTTOM_WAIST", "BOTTOM_HIP", "BOTTOM_LENGTH", "BOTTOM_INSEAM"]
        }.items():
            st.markdown(f"**{section}**")
            cols = st.columns(len(fields))
            for col, field in zip(cols, fields):
                with col:
                    st.metric(label=field, value=row.get(field, "—"))

    else:
        st.warning("❌ 일치하는 스타일 없음")
else:
    st.info("좌측 상단에서 스타일 번호를 검색하세요.")
