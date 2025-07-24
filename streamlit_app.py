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

# --- 세일즈 분석 페이지 ---
elif page == "📊 세일즈 데이터 분석 (Shein)":
    st.title("📊 Shein 세일즈 분석 대시보드")

    try:
        df = load_google_sheet("Sheet2")
    except Exception as e:
        st.error("❌ Shein 데이터 로드 실패: " + str(e))
        st.stop()

    if df.empty:
        st.warning("데이터가 없습니다.")
    else:
        df.columns = df.columns.str.strip()
        st.write("데이터 컬럼 미리보기:", df.columns.tolist())

        # 자동으로 날짜/스타일 컬럼 추측
        order_date_col = next((col for col in df.columns if "processed" in col.lower() or "date" in col.lower()), None)
        style_col = next((col for col in df.columns if "description" in col.lower()), None)
        status_col = next((col for col in df.columns if "status" in col.lower()), None)
        price_col = next((col for col in df.columns if "price" in col.lower()), None)
        revenue_col = next((col for col in df.columns if "revenue" in col.lower()), None)

        if not all([order_date_col, style_col, status_col, price_col, revenue_col]):
            st.error("데이터 형식이 예상과 다릅니다. 컬럼명을 확인하세요.")
            st.stop()

        df["Order Date"] = pd.to_datetime(df[order_date_col], errors='coerce')
        df["Style"] = df[style_col].str.extract(r'(\b[A-Z0-9]{4,}\b)', expand=False)
        df["Revenue"] = pd.to_numeric(df[revenue_col], errors='coerce')
        df["Price"] = pd.to_numeric(df[price_col], errors='coerce')
        df["Refunded"] = df[status_col].str.contains("Refund", case=False, na=False)

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
