import streamlit as st
import pandas as pd
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
from sklearn.cluster import KMeans

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
    # (생략: 기존 스타일 정보 조회 그대로 유지)
    pass

# --- 세일즈 데이터 분석 페이지 ---
elif page == "📊 세일즈 데이터 분석 (Shein)":
    st.title("📊 Shein 세일즈 데이터 분석")
    try:
        df_info = load_google_sheet("Sheet1")
        df_sales = load_google_sheet("Sheet2")
    except Exception as e:
        st.error("❌ 데이터 로드 실패: " + str(e))
        st.stop()

    df_sales.columns = df_sales.columns.str.strip()
    df_sales["Order Date"] = pd.to_datetime(df_sales["Order Processed On"], errors="coerce")
    df_sales["Style"] = df_sales["Product Description"].astype(str)
    df_sales["Price"] = pd.to_numeric(df_sales["Product Price"], errors="coerce")

    # 날짜 필터 추가
    st.markdown("### 📆 날짜 필터")
    min_date = df_sales["Order Date"].min()
    max_date = df_sales["Order Date"].max()
    date_range = st.date_input("날짜 범위 선택", [min_date, max_date])
    if len(date_range) == 2:
        start_date, end_date = date_range
        df_sales = df_sales[(df_sales["Order Date"] >= pd.to_datetime(start_date)) & (df_sales["Order Date"] <= pd.to_datetime(end_date))]

    # 일일 매출
    st.markdown("### 📅 날짜별 매출 추이")
    df_daily = df_sales.groupby("Order Date")["Price"].sum().reset_index()
    st.line_chart(df_daily.set_index("Order Date"))

    # 판매건수 계산
    sales_counts = df_sales["Style"].value_counts().to_dict()
    df_info["판매 건수"] = df_info["Product Number"].astype(str).map(sales_counts).fillna(0).astype(int)
    df_info["ERP PRICE"] = pd.to_numeric(df_info["ERP PRICE"], errors="coerce")
    shein_prices = df_sales.dropna(subset=["Order Date"])
    latest_price = shein_prices.sort_values("Order Date").drop_duplicates("Style", keep="last")[["Style", "Price"]].set_index("Style")["Price"]
    df_info["SHEIN PRICE"] = df_info["Product Number"].astype(str).map(latest_price)

    # 권장 가격 로직
    def suggest_price(erp, current_price, sales_count):
        if pd.isna(erp): return "-"
        if sales_count == 0:
            return round(min(erp + 3, current_price) if current_price else erp + 3, 2)
        elif sales_count <= 2:
            return round(min(erp + 4.5, current_price) if current_price else erp + 4.5, 2)
        elif sales_count >= 20:
            return round(max(erp + 7.5, current_price + 1 if current_price else erp + 7), 2)
        return "-"

    df_info["권장 가격"] = df_info.apply(lambda row: suggest_price(row["ERP PRICE"], row["SHEIN PRICE"], row["판매 건수"]), axis=1)

    st.markdown("### ⬇️ 가격 인하 제안")
    lower_table = df_info[df_info["판매 건수"] <= 2][["Product Number", "판매 건수", "ERP PRICE", "SHEIN PRICE", "권장 가격"]]
    st.dataframe(lower_table.style.apply(lambda r: ["background-color: #ffe6e6"]*len(r), axis=1), use_container_width=True)

    st.markdown("### ⬆️ 가격 인상 제안")
    raise_table = df_info[df_info["판매 건수"] >= 20][["Product Number", "판매 건수", "ERP PRICE", "SHEIN PRICE", "권장 가격"]]
    st.dataframe(raise_table.style.apply(lambda r: ["background-color: #e6ffe6"]*len(r), axis=1), use_container_width=True)
