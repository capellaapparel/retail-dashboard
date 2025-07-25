import streamlit as st
import pandas as pd
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta

# --- Google Sheet URL & Settings ---
GOOGLE_SHEET_URL = "https://docs.google.com/spreadsheets/d/1oyVzCgGK1Q3Qi_sbYwE-wKG6SArnfUDRe7rQfGOF-Eo"
IMAGE_CSV = "product_images.csv"

st.set_page_config(page_title="Capella Dashboard", layout="wide")

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

# --- 플랫폼 선택에 따라 시트, 컬럼명 통일 ---
def get_sales_data(platform):
    if platform == "SHEIN":
        df_sales = load_google_sheet("Sheet2")
    elif platform == "TEMU":
        df_sales = load_google_sheet("Sheet3")
    else:  # Both
        df_shein = load_google_sheet("Sheet2")
        df_temu = load_google_sheet("Sheet3")
        df_sales = pd.concat([df_shein, df_temu], ignore_index=True)
    df_sales.columns = df_sales.columns.str.strip()
    return df_sales

# --- 메인탭 ---
page = st.sidebar.radio(
    "페이지 선택", [
        "스타일 정보 조회",
        "전체 세일즈 분석",
        "가격 제안"
    ]
)

# ========== 1. 스타일 정보 조회 ==========
if page == "스타일 정보 조회":
    st.title("스타일 정보 조회")
    try:
        df_info = load_google_sheet("Sheet1")
        df_img = load_images()
        df_info["Product Number"] = df_info["Product Number"].astype(str).str.strip()
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
                st.markdown(f"**SHEIN PRICE:** {row.get('SHEIN PRICE', '')}")
                st.markdown(f"**TEMU PRICE:** {row.get('TEMU PRICE', '')}")
                st.markdown(f"**SLEEVE:** {row.get('SLEEVE', '')}")
                st.markdown(f"**NECKLINE:** {row.get('NECKLINE', '')}")
                st.markdown(f"**LENGTH:** {row.get('LENGTH', '')}")
                st.markdown(f"**FIT:** {row.get('FIT', '')}")
                st.markdown(f"**DETAIL:** {row.get('DETAIL', '')}")
                st.markdown(f"**STYLE MOOD:** {row.get('STYLE MOOD', '')}")
                st.markdown(f"**MODEL:** {row.get('MODEL', '')}")
                st.markdown(f"**NOTES:** {row.get('NOTES', '')}")

            # 사이즈 차트 표
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

# ========== 2. 전체 세일즈 분석 ==========
elif page == "전체 세일즈 분석":
    st.title("전체 세일즈 분석")
    platform = st.radio("플랫폼 선택", ["SHEIN", "TEMU", "Both"], horizontal=True)
    try:
        df_info = load_google_sheet("Sheet1")
        df_info["Product Number"] = df_info["Product Number"].astype(str).str.strip()
        df_sales = get_sales_data(platform)
        df_sales["Product Description"] = df_sales["Product Description"].astype(str).str.strip()
        df_sales["Order Date"] = pd.to_datetime(df_sales["Order Processed On"], errors="coerce", infer_datetime_format=True)
        df_sales = df_sales.dropna(subset=["Order Date"])
    except Exception as e:
        st.error("❌ 데이터 로드 실패: " + str(e))
        st.stop()

    min_date, max_date = df_sales["Order Date"].dt.date.min(), df_sales["Order Date"].dt.date.max()
    date_range = st.date_input("📅 날짜 범위 선택", [min_date, max_date], format="YYYY-MM-DD", key="sales_range")
    # 날짜 필터
    if isinstance(date_range, list) and len(date_range) == 2:
        start, end = pd.to_datetime(date_range[0]), pd.to_datetime(date_range[1])
        mask = (df_sales["Order Date"].dt.date >= start.date()) & (df_sales["Order Date"].dt.date <= end.date())
        df_sales_filtered = df_sales[mask]
    else:
        df_sales_filtered = df_sales

    if df_sales_filtered.empty:
        st.info("선택된 날짜 범위에 해당하는 데이터가 없습니다.")
    else:
        # 1) 일자별 판매 그래프
        st.subheader("일자별 판매 추이")
        sales_by_date = df_sales_filtered.groupby("Order Date").size().reset_index(name="Orders")
        sales_by_date = sales_by_date.set_index("Order Date").sort_index()
        st.line_chart(sales_by_date)

        # 2) 베스트셀러 (판매 상위 10)
        st.subheader("베스트셀러 Top 10")
        best_items = df_sales_filtered["Product Description"].value_counts().head(10)
        st.table(best_items)

        # 3) 저조한 아이템 (판매 0~2건, 스타일정보 기준)
        st.subheader("판매 저조 아이템 (0~2건)")
        sale_counts = df_sales_filtered["Product Description"].value_counts()
        sale_counts = sale_counts.reset_index().rename(columns={"index": "Product Number", "Product Description": "판매건수"})
        merged = df_info.merge(sale_counts, how="left", left_on="Product Number", right_on="Product Number")
        merged["판매건수"] = merged["판매건수"].fillna(0).astype(int)
        low_sales = merged[merged["판매건수"] <= 2][["Product Number", "판매건수", "SLEEVE", "FIT", "STYLE MOOD"]]
        st.dataframe(low_sales, use_container_width=True)

        # 4) 스타일 속성별 트렌드(예: SLEEVE, STYLE MOOD)
        st.subheader("스타일 속성별 트렌드")
        with st.expander("SLEEVE별 판매"):
            sleeve_best = merged.groupby("SLEEVE")["판매건수"].sum().sort_values(ascending=False)
            st.bar_chart(sleeve_best)
        with st.expander("FIT별 판매"):
            fit_best = merged.groupby("FIT")["판매건수"].sum().sort_values(ascending=False)
            st.bar_chart(fit_best)
        with st.expander("STYLE MOOD별 판매"):
            style_best = merged.groupby("STYLE MOOD")["판매건수"].sum().sort_values(ascending=False)
            st.bar_chart(style_best)

# ========== 3. 가격 제안 페이지 ==========
elif page == "가격 제안":
    st.title("가격 제안")
    platform = st.radio("플랫폼 선택", ["SHEIN", "TEMU"], horizontal=True)
    try:
        df_info = load_google_sheet("Sheet1")
        df_info["Product Number"] = df_info["Product Number"].astype(str).str.strip()
        df_sales = get_sales_data(platform)
        df_sales["Product Description"] = df_sales["Product Description"].astype(str).str.strip()
        df_sales["Order Date"] = pd.to_datetime(df_sales["Order Processed On"], errors="coerce", infer_datetime_format=True)
        df_sales = df_sales.dropna(subset=["Order Date"])
    except Exception as e:
        st.error("❌ 데이터 로드 실패: " + str(e))
        st.stop()

    # 최근 3개월 필터
    recent_cut = datetime.today() - timedelta(days=90)
    df_sales_recent = df_sales[df_sales["Order Date"] >= recent_cut]

    # 집계
    latest_prices = df_sales_recent.sort_values("Order Date").drop_duplicates("Product Description", keep="last")
    sales_summary = df_sales_recent.groupby("Product Description").size().reset_index(name="판매 건수")
    sales_summary = sales_summary.merge(
        latest_prices[["Product Description", "Product Price"]],
        on="Product Description", how="left"
    )
    sales_summary = sales_summary.rename(columns={"Product Price": "최근 판매가"})

    df_info = df_info.merge(
        sales_summary, how="left",
        left_on="Product Number", right_on="Product Description"
    )
    df_info["판매 건수"] = df_info["판매 건수"].fillna(0).astype(int)
    df_info["최근 판매가"] = pd.to_numeric(df_info["최근 판매가"], errors="coerce")

    # 권장 가격 로직 (플랫폼별 조정 가능)
    def recommend_price(row):
        erp = row["ERP PRICE"]
        recent = row["최근 판매가"]
        sales = row["판매 건수"]
        if pd.isna(recent):
            return erp + 3
        if sales == 0:
            return max(erp + 1, min(recent - 1, erp + 3))
        if sales <= 2:
            return max(erp + 2, recent - 0.5)
        if sales >= 20:
            return max(recent + 0.5, erp + 7)
        return recent
    df_info["권장 가격"] = df_info.apply(recommend_price, axis=1)

    st.subheader("⬇️ 가격 인하 제안")
    lower_table = df_info[df_info["판매 건수"] <= 2].sort_values("판매 건수")[
        ["Product Number", "판매 건수", "ERP PRICE", "최근 판매가", "권장 가격", "SLEEVE", "STYLE MOOD"]]
    st.dataframe(lower_table.style.apply(lambda r: ["background-color: #ffe6e6"] * len(r), axis=1),
                 use_container_width=True)

    st.subheader("⬆️ 가격 인상 제안")
    raise_table = df_info[df_info["판매 건수"] >= 20].sort_values("판매 건수", ascending=False)[
        ["Product Number", "판매 건수", "ERP PRICE", "최근 판매가", "권장 가격", "SLEEVE", "STYLE MOOD"]]
    st.dataframe(raise_table.style.apply(lambda r: ["background-color: #e6ffe6"] * len(r), axis=1),
                 use_container_width=True)
