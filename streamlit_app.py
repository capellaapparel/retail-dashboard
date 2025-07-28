import streamlit as st
import pandas as pd
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials

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
            try:
                price = float(str(price).replace("$", "").replace(",", ""))
                return f"${price:.2f}"
            except:
                return "NA"
    return "NA"

def get_latest_temu_price(df_temu, product_number):
    df_temu = df_temu.rename(columns=lambda x: x.lower().strip())
    style_col = "contribution sku"
    status_col = "order item status"
    date_col = "purchase date"
    price_col = "base price total"
    if style_col not in df_temu.columns or status_col not in df_temu.columns or price_col not in df_temu.columns:
        return "NA"
    product_number = str(product_number).strip().upper()
    df_temu[style_col] = df_temu[style_col].astype(str).str.strip().str.upper()
    df_temu[status_col] = df_temu[status_col].astype(str).str.strip().str.lower()
    df_temu[date_col] = df_temu[date_col].astype(str).str.strip()
    filtered = df_temu[
        df_temu[style_col].str.startswith(product_number)
        & (df_temu[status_col] != "cancelled")
    ]
    st.write("====TEMU 필터 rows 수:", len(filtered))
    st.write("====TEMU 샘플 rows:", filtered[[style_col, price_col, date_col]].head(5))
    if not filtered.empty:
        filtered = filtered.copy()
        filtered["Order Date"] = pd.to_datetime(filtered[date_col], errors="coerce")
        filtered = filtered.dropna(subset=["Order Date", price_col])
        if not filtered.empty:
            latest = filtered.sort_values("Order Date").iloc[-1]
            price = latest.get(price_col)
            st.write("====TEMU 최종 row 샘플:", latest)
            try:
                if pd.isna(price) or price in ("", "NA", "nan"):
                    return "NA"
                return f"${float(str(price).replace('$', '').replace(',', '')):.2f}"
            except Exception as ex:
                st.write("TEMU price 변환 실패", price, ex)
                return "NA"
    return "NA"




    for idx, row in filtered.iterrows():
        price = row.get(price_col)
        st.write(f"TEMU row idx={idx}, price_raw={price!r}")
        try:
            if price is None:
                continue
            price_str = str(price).replace("$", "").replace(",", "").strip()
            if price_str == "" or price_str.lower() == "na":
                continue
            price_f = float(price_str)
            st.write(f"▶︎ TEMU price_f: {price_f}")
            return f"${price_f:.2f}"
        except Exception as ex:
            st.write(f"✖︎ 변환에러: {price!r} → {ex}")
            continue
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
                # 가격: TEMU → SHEIN 순서, 값 없으면 NA
                latest_temu = get_latest_temu_price(df_temu, selected)
                latest_shein = get_latest_shein_price(df_shein, selected)
                st.markdown(f"**TEMU PRICE:** {latest_temu}")
                st.markdown(f"**SHEIN PRICE:** {latest_shein}")
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
