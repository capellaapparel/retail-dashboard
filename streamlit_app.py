import streamlit as st
import pandas as pd
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import re

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
            return latest["Product Price"]
    return None

def get_latest_temu_price(df_temu, product_number):
    # 컬럼명 소문자화 및 공백제거 (혹시라도 컬럼명이 살짝 다를 경우도 대비)
    df_temu = df_temu.rename(columns=lambda x: x.lower().strip())
    style_col = "contribution sku"
    status_col = "order item status"
    date_col = "purchase date"
    price_col = "base price total"
    
    # 모든 텍스트 컬럼 공백·대소문자 정리
    df_temu[style_col] = df_temu[style_col].astype(str).str.strip().str.upper()
    df_temu[status_col] = df_temu[status_col].astype(str).str.strip().str.lower()
    df_temu[date_col] = df_temu[date_col].astype(str).str.strip()
    
    # Product Number도 깔끔하게
    product_number = str(product_number).strip().upper()
    
    # TEMU contribution sku에서 스타일넘버만 추출
    df_temu["temu_style"] = df_temu[style_col].str.split("-").str[0].str.strip().str.upper()

    # **디버그: 스타일넘버 매칭 샘플 출력**
    st.write("TEMU 전체 스타일넘버 5개:", df_temu["temu_style"].head())
    st.write("찾는 Product Number:", product_number)

    # Cancelled 제외, 매칭만
    filtered = df_temu[
        (df_temu["temu_style"] == product_number) &
        (df_temu[status_col] != "cancelled")
    ]
    # **디버그: 필터된 데이터**
    st.write("TEMU 필터결과:", filtered[[style_col, "temu_style", price_col, date_col]].head(5))

    if not filtered.empty:
        filtered["Order Date"] = pd.to_datetime(filtered[date_col], errors="coerce")
        filtered = filtered.dropna(subset=["Order Date"])
        if not filtered.empty:
            latest = filtered.sort_values("Order Date").iloc[-1]
            price = latest.get(price_col)
            if isinstance(price, str):
                price = price.replace("$", "").replace(",", "")
            try:
                price = float(price)
                return f"${price:.2f}"
            except Exception as ex:
                st.write("가격 변환 에러:", price, ex)
                return None
    return None


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
        # ex: 3365 입력하면 BP3365, BP3365X, BTP3365 등 모두 결과에 포함
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

                # 가격: 정확한 Product Number만 매칭!
                latest_shein = get_latest_shein_price(df_shein, selected)
                latest_temu = get_latest_temu_price(df_temu, selected)
                if latest_shein is not None and str(latest_shein).strip() != "":
                    st.markdown(f"**SHEIN PRICE:** ${latest_shein}")
                if latest_temu is not None and str(latest_temu).strip() != "":
                    st.markdown(f"**TEMU PRICE:** ${latest_temu}")

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
