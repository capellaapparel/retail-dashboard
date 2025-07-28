import streamlit as st
import pandas as pd
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# 시트명/파일명
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
    df = pd.DataFrame(data)
    df.columns = [c.lower().strip() for c in df.columns]
    return df

@st.cache_data(show_spinner=False)
def load_images():
    df = pd.read_csv(IMAGE_CSV)
    df.columns = [c.lower().strip() for c in df.columns]
    return df

def show_info_block(label, value):
    if value not in ("", None, float("nan")) and str(value).strip() != "":
        st.markdown(f"**{label}:** {value}")

def get_latest_shein_price(df_shein, product_number):
    filtered = df_shein[
        df_shein["product description"].astype(str).str.strip().str.upper() == str(product_number).strip().upper()
    ]
    if not filtered.empty:
        filtered = filtered.copy()
        filtered["order date"] = pd.to_datetime(filtered["order processed on"], errors="coerce")
        filtered = filtered.dropna(subset=["order date"])
        if not filtered.empty:
            latest = filtered.sort_values("order date").iloc[-1]
            price = latest["product price"]
            try:
                price = float(str(price).replace("$", "").replace(",", ""))
                return f"${price:.2f}"
            except:
                return "NA"
    return "NA"

def get_latest_temu_price(df_temu, product_number):
    st.write("==[ TEMU 전체 product number ]==", df_temu['product number'].unique())
    st.write("==[ 입력값 ]==", product_number)
    filtered = df_temu[
        df_temu['product number'].astype(str).str.strip().str.upper() == str(product_number).strip().upper()
    ]
    st.write("==[ 필터 후 row 수 ]==", len(filtered))
    st.write("==[ 필터 후 데이터 샘플 dict ]==", filtered.head(3).to_dict())  # 여기만 to_dict() 추가!

    if filtered.empty:
        return "NA"

    filtered = filtered.copy()
    filtered["order date"] = pd.to_datetime(filtered["purchase date"], errors="coerce")
    filtered = filtered.dropna(subset=["order date"])
    if filtered.empty:
        st.write("==[ order date drop 후 empty ]==")
        return "NA"

    latest = filtered.sort_values("order date").iloc[-1]
    st.write("==[ 가장 최신 row dict ]==", latest.to_dict())   # to_dict()로 안전하게
    price = latest["base price total"]
    st.write("==[ 최신 price 값 ]==", price)
    try:
        price = float(str(price).replace("$", "").replace(",", ""))
        st.write("==[ 최종 TEMU PRICE ]==", f"${price:.2f}")
        return f"${price:.2f}"
    except Exception as ex:
        st.write("==[ 가격 변환 에러 ]==", price, ex)
        return "NA"

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
        matched = df_info[df_info["product number"].astype(str).str.contains(style_input, case=False, na=False)]
        if matched.empty:
            st.warning("❌ 해당 스타일을 찾을 수 없습니다.")
        else:
            selected = st.selectbox("스타일 선택", matched["product number"].astype(str))
            row = df_info[df_info["product number"] == selected].iloc[0]
            img_row = df_img[df_img["product number"] == selected] if 'product number' in df_img.columns else None
            image_url = img_row.iloc[0]["first image"] if (img_row is not None and not img_row.empty) else None

            st.markdown("---")
            col1, col2 = st.columns([1, 2])
            with col1:
                if image_url:
                    st.image(image_url, width=300)
                else:
                    st.caption("이미지 없음")
            with col2:
                st.subheader(row.get("default product name(en)", ""))
                st.markdown(f"**Product Number:** {row['product number']}")
                show_info_block("ERP PRICE", row.get("erp price", ""))
                # 가격: Temu → Shein 순서, 값 없으면 NA
                latest_temu = get_latest_temu_price(df_temu, selected)
                latest_shein = get_latest_shein_price(df_shein, selected)
                st.markdown(f"**TEMU PRICE:** {latest_temu}")
                st.markdown(f"**SHEIN PRICE:** {latest_shein}")
                # 빈 정보 생략
                for col, label in [
                    ("sleeve", "SLEEVE"), ("neckline", "NECKLINE"), ("length", "LENGTH"),
                    ("fit", "FIT"), ("detail", "DETAIL"), ("style mood", "STYLE MOOD"),
                    ("model", "MODEL"), ("notes", "NOTES")
                ]:
                    val = row.get(col, "")
                    if pd.notna(val) and str(val).strip() not in ("", "nan", "NaN"):
                        st.markdown(f"**{label}:** {val}")

            st.markdown("---")
            st.subheader("📏 Size Chart")
            def has_size_data(*args):
                return any(str(v).strip() not in ["", "0", "0.0"] for v in args)
            top1_vals = (row.get("top1_chest", ""), row.get("top1_length", ""), row.get("top1_sleeve", ""))
            top2_vals = (row.get("top2_chest", ""), row.get("top2_length", ""), row.get("top2_sleeve", ""))
            bottom_vals = (row.get("bottom_waist", ""), row.get("bottom_hip", ""), row.get("bottom_length", ""), row.get("bottom_inseam", ""))
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
