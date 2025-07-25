import streamlit as st
import pandas as pd
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- 구글시트 시트명 변경 ---
PRODUCT_SHEET = "PRODUCT_INFO"
SHEIN_SHEET = "SHEIN_SALES"
TEMU_SHEET = "TEMU_SALES"
IMAGE_CSV = "product_images.csv"

GOOGLE_SHEET_URL = "https://docs.google.com/spreadsheets/d/1oyVzCgGK1Q3Qi_sbYwE-wKG6SArnfUDRe7rQfGOF-Eo"
st.set_page_config(page_title="Capella Product Dashboard", layout="wide")
page = st.sidebar.radio("페이지 선택", ["📖 스타일 정보 조회", "📊 세일즈 데이터 분석"])

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

def get_latest_shein_price(df_sales, style_num):
    filtered = df_sales[df_sales["Product Description"].astype(str).str.strip() == style_num]
    if not filtered.empty:
        filtered = filtered.copy()
        filtered["Order Date"] = pd.to_datetime(filtered["Order Processed On"], errors="coerce")
        filtered = filtered.dropna(subset=["Order Date"])
        if not filtered.empty:
            latest = filtered.sort_values("Order Date").iloc[-1]
            return latest["Product Price"]
    return None

import re

def get_latest_temu_price(df_temu, style_num):
    # 컬럼 소문자화 및 공백제거
    df_temu = df_temu.rename(columns={c: c.lower().strip() for c in df_temu.columns})
    style_col = "contribution sku"
    status_col = "order item status"
    date_col = "purchase date"
    price_col = "base price total"

    style_num = str(style_num).strip().upper()
    # TEMU contribution sku에서 스타일넘버 추출
    df_temu["스타일넘버"] = df_temu[style_col].apply(
        lambda x: re.split(r'[-_]', str(x).strip().upper())[0] if pd.notna(x) else "")

    # style_num이 TEMU 스타일넘버의 끝부분/일부에라도 "포함"되면 매칭
    filtered = df_temu[
        (df_temu["스타일넘버"].str.contains(style_num, na=False)) &
        (df_temu[status_col].str.lower() != "cancelled")
    ]

    # st.write("TEMU DEBUG", style_num, filtered[["스타일넘버", price_col, date_col]].head(2))  # 디버깅용

    if not filtered.empty and date_col in filtered.columns:
        filtered["Order Date"] = pd.to_datetime(filtered["purchase date"], errors="coerce")
        filtered = filtered.dropna(subset=["Order Date"])
        if not filtered.empty:
            latest = filtered.sort_values("Order Date").iloc[-1]
            price = latest.get(price_col)
            if isinstance(price, str):
                price = price.replace("$", "").replace(",", "")
            try:
                price = float(price)
                return f"${price:.2f}"
            except:
                return None
    return None



def show_info_block(label, value):
    if value not in ("", None, float("nan")):
        st.markdown(f"**{label}:** {value}")

# --- 스타일 정보 조회 ---
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
                # 최신 가격 동적 표시
                latest_shein = get_latest_shein_price(df_shein, selected)
                latest_temu = get_latest_temu_price(df_temu, selected)
                if latest_shein:
                    st.markdown(f"**SHEIN PRICE:** ${latest_shein}")
                if latest_temu:
                    st.markdown(f"**TEMU PRICE:** {latest_temu}")
                # 빈 정보 자동 생략
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

# (세일즈 분석/추가 기능 필요시 이 아래에 이어서 구현)
