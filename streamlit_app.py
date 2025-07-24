import streamlit as st
import pandas as pd
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

# --- Google Sheet URL & Settings ---
GOOGLE_SHEET_URL = "https://docs.google.com/spreadsheets/d/1oyVzCgGK1Q3Qi_sbYwE-wKG6SArnfUDRe7rQfGOF-Eo"
IMAGE_CSV = "product_images.csv"

st.set_page_config(page_title="Capella Product Dashboard", layout="wide")

# Sidebar Navigation
page = st.sidebar.radio("페이지 선택", ["📖 스타일 정보 조회", "📊 세일즈 데이터 분석 (Shein)"])

@st.cache_data(show_spinner=False)
def load_google_sheet(sheet_name):
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive"
    ]
    json_data = {k: str(v) for k, v in st.secrets["gcp_service_account"].items()}
    with open("/tmp/service_account.json", "w") as f:
        json.dump(json_data, f)
    creds = ServiceAccountCredentials.from_json_keyfile_name("/tmp/service_account.json", scope)
    client = gspread.authorize(creds)
    sheet = client.open_by_url(GOOGLE_SHEET_URL).worksheet(sheet_name)
    data = sheet.get_all_records()
    return pd.DataFrame(data)

@st.cache_data(show_spinner=False)
def load_images():
    return pd.read_csv(IMAGE_CSV)

# --- 스타일 정보 조회 페이지 ---
if page == "📖 스타일 정보 조회":
    st.title("📖 스타일 정보 (읽기 전용)")
    try:
        df_info = load_google_sheet("Sheet1")
        df_img = load_images()
        df_sales = load_google_sheet("Sheet2")
    except Exception as e:
        st.error("❌ 데이터 로드 실패: " + str(e))
        st.stop()

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

                df_sales.columns = df_sales.columns.str.strip()
                df_sales["Order Date"] = pd.to_datetime(df_sales[df_sales.columns[24]], errors="coerce")
                df_sales["Style"] = df_sales["Product Description"].astype(str)
                df_sales["Price"] = pd.to_numeric(df_sales["Product Price"], errors="coerce")
                df_filtered = df_sales[df_sales["Style"] == selected].dropna(subset=["Order Date"])

                shein_price = "-"
                if not df_filtered.empty:
                    closest_row = df_filtered.iloc[(df_filtered["Order Date"] - pd.Timestamp.today()).abs().argsort()].iloc[0]
                    shein_price = closest_row["Price"]

                st.markdown(f"**SHEIN PRICE:** ${shein_price}")
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
                <table style='width:80%; text-align:center; border-collapse:collapse; margin-bottom:10px' border='1'>
                    <tr><th colspan='2'>Top 1</th></tr>
                    <tr><td>Chest</td><td>{top1_vals[0]}</td></tr>
                    <tr><td>Length</td><td>{top1_vals[1]}</td></tr>
                    <tr><td>Sleeve</td><td>{top1_vals[2]}</td></tr>
                </table>
                """)

            if has_size_data(*top2_vals):
                html_parts.append(f"""
                <table style='width:80%; text-align:center; border-collapse:collapse; margin-bottom:10px' border='1'>
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


# --- 세일즈 데이터 분석 페이지 ---
elif page == "📊 세일즈 데이터 분석 (Shein)":
    st.title("📊 Shein 세일즈 데이터 분석")
    try:
        df_sales = load_google_sheet("Sheet2")
    except Exception as e:
        st.error("❌ 데이터 로드 실패: " + str(e))
        st.stop()

    df_sales.columns = df_sales.columns.str.strip()
    df_sales["Order Date"] = pd.to_datetime(df_sales["Order processed on"], errors="coerce")
    df_sales["Style"] = df_sales["Product Description"].astype(str)
    df_sales["Price"] = pd.to_numeric(df_sales["Product Price"], errors="coerce")

    st.markdown("### 🔢 요약 통계")
    st.write(df_sales.groupby("Style")["Price"].agg(["count", "mean", "sum"]).rename(columns={
        "count": "주문 수", "mean": "평균 가격", "sum": "총 매출"
    }).sort_values("총 매출", ascending=False).head(20))

    st.markdown("### 📅 날짜별 매출 추이")
    df_daily = df_sales.groupby("Order Date")["Price"].sum().reset_index()
    st.line_chart(df_daily.set_index("Order Date"))

