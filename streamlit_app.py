import streamlit as st
import pandas as pd
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime

# --- Google Sheet URL & Settings ---
GOOGLE_SHEET_URL = "https://docs.google.com/spreadsheets/d/1oyVzCgGK1Q3Qi_sbYwE-wKG6SArnfUDRe7rQfGOF-Eo"
SHEET_NAME = "Sheet1"
IMAGE_CSV = "product_images.csv"

st.set_page_config(page_title="Capella Product Dashboard", layout="wide")

# Sidebar Navigation
page = st.sidebar.radio("페이지 선택", ["📖 스타일 정보 조회", "📊 세일즈 데이터 분석"])

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

# --- 스타일 정보 조회 페이지 ---
if page == "📖 스타일 정보 조회":
    st.title("📖 스타일 정보 (읽기 전용)")
    try:
        df_info = load_google_sheet()
        df_img = load_images()
    except Exception as e:
        st.error("❌ 데이터 로드 실패: " + str(e))
        st.stop()

    if st.button("🔄 최신 데이터 불러오기"):
        st.cache_data.clear()
        st.experimental_rerun()

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

            def has_size_data(*args):
                return any(str(v).strip() not in ["", "0", "0.0"] for v in args)

            top1_vals = (row.get("TOP1_CHEST", ""), row.get("TOP1_LENGTH", ""), row.get("TOP1_SLEEVE", ""))
            top2_vals = (row.get("TOP2_CHEST", ""), row.get("TOP2_LENGTH", ""), row.get("TOP2_SLEEVE", ""))
            bottom_vals = (row.get("BOTTOM_WAIST", ""), row.get("BOTTOM_HIP", ""), row.get("BOTTOM_LENGTH", ""), row.get("BOTTOM_INSEAM", ""))

            html_parts = []

            if has_size_data(*top1_vals):
                html_parts.append(f"""
                <table style='width:60%; text-align:center; border-collapse:collapse; margin-bottom:10px' border='1'>
                    <tr><th colspan='2'>Top 1</th></tr>
                    <tr><td>Chest</td><td>{top1_vals[0]}</td></tr>
                    <tr><td>Length</td><td>{top1_vals[1]}</td></tr>
                    <tr><td>Sleeve</td><td>{top1_vals[2]}</td></tr>
                </table>
                """)

            if has_size_data(*top2_vals):
                html_parts.append(f"""
                <table style='width:60%; text-align:center; border-collapse:collapse; margin-bottom:10px' border='1'>
                    <tr><th colspan='2'>Top 2</th></tr>
                    <tr><td>Chest</td><td>{top2_vals[0]}</td></tr>
                    <tr><td>Length</td><td>{top2_vals[1]}</td></tr>
                    <tr><td>Sleeve</td><td>{top2_vals[2]}</td></tr>
                </table>
                """)

            if has_size_data(*bottom_vals):
                html_parts.append(f"""
                <table style='width:80%; text-align:center; border-collapse:collapse' border='1'>
                    <tr><th colspan='2'>Bottom</th></tr>
                    <tr><td>Waist</td><td>{bottom_vals[0]}</td></tr>
                    <tr><td>Hip</td><td>{bottom_vals[1]}</td></tr>
                    <tr><td>Length</td><td>{bottom_vals[2]}</td></tr>
                    <tr><td>Inseam</td><td>{bottom_vals[3]}</td></tr>
                </table>
                """)

            if html_parts:
                st.markdown("".join(html_parts), unsafe_allow_html=True)
            else:
                st.caption("사이즈 정보가 없습니다.")

# --- 세일즈 분석 페이지 ---
elif page == "📊 세일즈 데이터 분석":
    st.title("📊 세일즈 분석 대시보드")

    uploaded_file = st.file_uploader("📤 세일즈 데이터 업로드 (Excel)", type=["xlsx"])

    if uploaded_file:
        df = pd.read_excel(uploaded_file)

        # Rename for simplicity
        df.columns = df.columns.str.strip()
        df["Order Date"] = pd.to_datetime(df["Order basic information.24"], errors='coerce')
        df["Style"] = df["Order basic information.9"].str.extract(r'(\b[A-Z0-9]{4,}\b)', expand=False)
        df["Revenue"] = pd.to_numeric(df["Order basic information.33"], errors='coerce')
        df["Price"] = pd.to_numeric(df["Order basic information.29"], errors='coerce')
        df["Refunded"] = df["Order basic information.3"].str.contains("Refund", case=False)

        st.markdown("### 🔢 기본 요약")
        st.write(f"총 오더 수: {len(df)}")
        st.write(f"총 스타일 수: {df['Style'].nunique()}")
        st.write(f"총 매출액: ${df['Revenue'].sum():,.2f}")
        st.write(f"환불 비율: {df['Refunded'].mean() * 100:.2f}%")

        st.markdown("### 📈 일별 판매 추이")
        daily = df[~df["Refunded"]].groupby("Order Date")["Revenue"].sum()
        st.line_chart(daily)

        st.markdown("### 🏆 베스트셀러 TOP 10")
        top_styles = df[~df["Refunded"]].groupby("Style")["Revenue"].sum().sort_values(ascending=False).head(10)
        st.bar_chart(top_styles)

        st.markdown("### ⚠️ 리펀드율 높은 스타일")
        refund_rate = df.groupby("Style")["Refunded"].mean().sort_values(ascending=False).head(10)
        st.bar_chart(refund_rate)

        st.markdown("### 🔍 상세 데이터 보기")
        st.dataframe(df[['Order Date', 'Style', 'Revenue', 'Price', 'Refunded']].sort_values(by="Order Date", ascending=False))
