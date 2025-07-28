import streamlit as st
import pandas as pd
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from dateutil import parser

def parse_temudate(dt):
    try:
        return parser.parse(str(dt).split('(')[0].strip(), fuzzy=True)
    except Exception as ex:
        return pd.NaT

PRODUCT_SHEET = "PRODUCT_INFO"
SHEIN_SHEET = "SHEIN_SALES"
TEMU_SHEET = "TEMU_SALES"
GOOGLE_SHEET_URL = "https://docs.google.com/spreadsheets/d/1oyVzCgGK1Q3Qi_sbYwE-wKG6SArnfUDRe7rQfGOF-Eo"

st.set_page_config(page_title="Capella Product Dashboard", layout="wide")
page = st.sidebar.radio("페이지 선택", ["📖 스타일 정보 조회", "📊 세일즈 대시보드"])

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

def parse_sheindate(dt):
    try:
        return pd.to_datetime(str(dt), errors="coerce", infer_datetime_format=True)
    except Exception:
        return pd.NaT

def show_price_block(label, value):
    if value not in ("", None, float("nan")) and str(value).strip() not in ("", "nan", "NaN"):
        try:
            v = str(value).strip()
            if v.startswith("$"):
                price = v
            else:
                price = f"${v}"
            st.markdown(f"**{label}:** {price}")
        except:
            st.markdown(f"**{label}:** {value}")

def get_latest_shein_price(df_sales, product_number):
    filtered = df_sales[
        df_sales["product description"].astype(str).str.strip().str.upper() == str(product_number).strip().upper()
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
    filtered = df_temu[
        df_temu["product number"].astype(str).str.strip().str.upper() == str(product_number).strip().upper()
    ]
    if not filtered.empty:
        filtered = filtered.copy()
        filtered["order date"] = filtered["purchase date"].apply(parse_temudate)
        filtered = filtered.dropna(subset=["order date"])
        if not filtered.empty:
            latest = filtered.sort_values("order date").iloc[-1]
            price = latest["base price total"]
            try:
                price = float(str(price).replace("$", "").replace(",", ""))
                return f"${price:.2f}"
            except:
                return "NA"
    return "NA"

# =========================
#  스타일 정보 조회 페이지
# =========================
if page == "📖 스타일 정보 조회":
    try:
        df_info = load_google_sheet(PRODUCT_SHEET)
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
            image_url = str(row.get("image", "")).strip()

            st.markdown("---")
            col1, col2 = st.columns([1, 2])
            with col1:
    image_url = row.get("image", "")
    if pd.notna(image_url) and isinstance(image_url, str) and image_url.strip().lower().startswith("http"):
        st.image(image_url.strip(), width=300)
    else:
        st.caption("이미지 없음")
            with col2:
                st.subheader(row.get("default product name(en)", ""))
                st.markdown(f"**Product Number:** {row['product number']}")
                show_price_block("ERP PRICE", row.get("erp price", ""))
                latest_temu = get_latest_temu_price(df_temu, selected)
                latest_shein = get_latest_shein_price(df_shein, selected)
                st.markdown(f"**TEMU PRICE:** {latest_temu}")
                st.markdown(f"**SHEIN PRICE:** {latest_shein}")
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

# =========================
#     세일즈 대시보드
# =========================
if page == "📊 세일즈 대시보드":
    try:
        df_shein = load_google_sheet(SHEIN_SHEET)
        df_temu = load_google_sheet(TEMU_SHEET)
    except Exception as e:
        st.error("❌ 데이터 로드 실패: " + str(e))
        st.stop()

    df_shein["order date"] = df_shein["order processed on"].apply(parse_sheindate)
    df_temu["order date"] = df_temu["purchase date"].apply(parse_temudate)

    shein_sales = df_shein.rename(columns={
        "product description": "product number",
        "qty": "qty",
        "product price": "unit price"
    }).copy()
    shein_sales["platform"] = "SHEIN"
    shein_sales["qty"] = pd.to_numeric(shein_sales["qty"], errors="coerce").fillna(0)
    shein_sales["sales"] = shein_sales["qty"] * pd.to_numeric(shein_sales["unit price"], errors="coerce").fillna(0)

    temu_sales = df_temu.rename(columns={
        "product number": "product number",
        "qty": "qty",
        "base price total": "unit price"
    }).copy()
    temu_sales["platform"] = "TEMU"
    temu_sales["qty"] = pd.to_numeric(temu_sales["qty"], errors="coerce").fillna(0)
    temu_sales["sales"] = temu_sales["qty"] * pd.to_numeric(temu_sales["unit price"], errors="coerce").fillna(0)

    df_all = pd.concat([shein_sales, temu_sales], ignore_index=True)
    df_all = df_all[df_all["order date"].notna()]

    st.sidebar.subheader("플랫폼")
    platform_filter = st.sidebar.radio("플랫폼", ["BOTH", "SHEIN", "TEMU"], horizontal=True)
    st.sidebar.subheader("조회 기간")
    min_date = df_all["order date"].min()
    max_date = df_all["order date"].max()
    date_range = st.sidebar.date_input("기간", (min_date, max_date))

    df_view = df_all.copy()
    if platform_filter != "BOTH":
        df_view = df_view[df_view["platform"] == platform_filter]
    df_view = df_view[(df_view["order date"] >= pd.to_datetime(date_range[0])) & (df_view["order date"] <= pd.to_datetime(date_range[1]))]

    total_qty = int(df_view["qty"].sum())
    total_sales = df_view["sales"].sum()
    order_count = df_view.shape[0]

    colA, colB, colC = st.columns(3)
    colA.metric("총 판매수량", f"{total_qty:,}")
    colB.metric("총 매출", f"${total_sales:,.2f}")
    colC.metric("주문건수", f"{order_count:,}")

    st.subheader("일별 판매 추이")
    daily = df_view.groupby("order date").agg({"qty": "sum", "sales": "sum"}).reset_index()
    st.line_chart(daily.set_index("order date")[["qty", "sales"]])

    st.subheader("베스트셀러 TOP10")
    best = df_view.groupby("product number").agg({"qty": "sum", "sales": "sum"}).reset_index()
    best = best.sort_values("qty", ascending=False).head(10)
    st.dataframe(best)

    st.subheader("플랫폼별 매출 비율")
    platform_stats = df_view.groupby("platform")["sales"].sum()
    st.bar_chart(platform_stats)
