import streamlit as st
import pandas as pd
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# === 구글시트 시트명 ===
PRODUCT_SHEET = "PRODUCT_INFO"
SHEIN_SHEET = "SHEIN_SALES"
TEMU_SHEET = "TEMU_SALES"
IMAGE_CSV = "product_images.csv"
GOOGLE_SHEET_URL = "https://docs.google.com/spreadsheets/d/1oyVzCgGK1Q3Qi_sbYwE-wKG6SArnfUDRe7rQfGOF-Eo"

st.set_page_config(page_title="Capella Product Dashboard", layout="wide")
page = st.sidebar.radio("페이지 선택", ["📖 스타일 정보 조회"])

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

def get_latest_shein_price(df_sales, product_number):
    filtered = df_sales[df_sales["Product Description"].astype(str).str.strip().str.upper() == str(product_number).upper()]
    if not filtered.empty:
        filtered = filtered.copy()
        filtered["Order Date"] = pd.to_datetime(filtered["Order Processed On"], errors="coerce")
        filtered = filtered.dropna(subset=["Order Date"])
        if not filtered.empty:
            latest = filtered.sort_values("Order Date").iloc[-1]
            price = latest["Product Price"]
            if isinstance(price, str):
                price = price.replace("$", "").replace(",", "")
            try:
                price = float(price)
                return f"${price:.2f}" if price > 0 else "NA"
            except:
                return "NA"
    return "NA"

def get_latest_temu_price(df_temu, product_number):
    # 컬럼명 모두 소문자+strip, 일치하는 컬럼 찾기
    col_map = {c.strip().lower(): c for c in df_temu.columns}
    style_col = col_map.get("contribution sku")
    status_col = col_map.get("order item status")
    date_col = col_map.get("purchase date")
    price_col = col_map.get("base price total")
    if not all([style_col, status_col, date_col, price_col]):
        return "NA"

    # 모든 문자열, NaN 방지
    df_temu = df_temu.copy()
    df_temu[style_col] = df_temu[style_col].astype(str).fillna("").str.strip().str.upper()
    df_temu["temu_style"] = df_temu[style_col].str.split("-").str[0].str.strip().str.upper()
    df_temu[status_col] = df_temu[status_col].astype(str).fillna("").str.strip().str.lower()

    product_number = str(product_number).strip().upper()

    filtered = df_temu[
        (df_temu["temu_style"] == product_number) &
        (df_temu[status_col] != "cancelled")
    ]

    # --- 디버깅 ---
    # st.write("TEMU 스타일넘버 필터 결과:", filtered[[style_col, "temu_style", price_col, date_col]])

    if not filtered.empty:
        filtered["Order Date"] = pd.to_datetime(filtered[date_col], errors="coerce")
        filtered = filtered.dropna(subset=["Order Date"])
        if not filtered.empty:
            latest = filtered.sort_values("Order Date").iloc[-1]
            price = latest.get(price_col)
            if isinstance(price, str):
                price = price.replace("$", "").replace(",", "").strip()
            try:
                price = float(price)
                return f"${price:.2f}" if price > 0 else "NA"
            except:
                return "NA"
    return "NA"

def show_info_block(label, value):
    if value not in ("", None, float("nan")) and str(value).strip() != "":
        st.markdown(f"**{label}:** {value}")

# --- 스타일 정보 조회 페이지 ---
if page == "📖 스타일 정보 조회":
    try:
        df_info = load_google_sheet(PRODUCT_SHEET)
        df_img = load_images()
        df_shein = load_google_sheet(SHEIN_SHEET)
        df_temu = load_google_sheet(TEMU_SHEET)
    except Exception as e:
        st.error("❌ 데이터 로드 실패: " + str(e))
        st.stop()

    style_input = st.text_input("🔍 스타일 번호를 입력하세요:", "")
    if style_input:
        # 부분 검색 지원(BP3365, BP3365X 등)
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
                show_info_block("ERP PRICE", row.get("ERP PRICE", ""))
                # ★★★ 가격 항목 항상 표시(없으면 NA) ★★★
                shein_display = get_latest_shein_price(df_shein, selected)
                temu_display = get_latest_temu_price(df_temu, selected)
                st.markdown(f"**SHEIN PRICE:** {shein_display}")
                st.markdown(f"**TEMU PRICE:** {temu_display}")
                # 스타일 속성들 빈값만 생략
                for col, label in [
                    ("SLEEVE", "SLEEVE"), ("NECKLINE", "NECKLINE"), ("LENGTH", "LENGTH"),
                    ("FIT", "FIT"), ("DETAIL", "DETAIL"), ("STYLE MOOD", "STYLE MOOD"),
                    ("MODEL", "MODEL"), ("NOTES", "NOTES")
                ]:
                    val = row.get(col, "")
                    if pd.notna(val) and str(val).strip() not in ("", "nan", "NaN"):
                        st.markdown(f"**{label}:** {val}")

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
