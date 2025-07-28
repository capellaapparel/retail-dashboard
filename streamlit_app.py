import streamlit as st
import pandas as pd
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from dateutil import parser

def parse_temudate(dt):
    try:
        return parser.parse(str(dt).split('(')[0].strip(), fuzzy=True)
    except Exception:
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

def try_float(x):
    try: return float(str(x).replace("$","").replace(",","").strip())
    except: return 0

def show_price_block(label, value):
    if value not in ("", None, float("nan")) and str(value).strip() not in ("", "nan", "NaN"):
        try:
            # 이미 $로 시작하면 그대로, 아니면 붙임
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
            image_url = str(row.get("image", "")).strip()  # 소문자 "image"로!

            st.markdown("---")
            col1, col2 = st.columns([1, 2])
            with col1:
                if image_url:
                    st.image(image_url, width=400)
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


# --- 세일즈 대시보드 페이지 ---
if page == "📊 세일즈 대시보드":
    st.title("세일즈 대시보드")

    # 데이터 불러오기
    try:
        df_shein = load_google_sheet(SHEIN_SHEET)
        df_temu = load_google_sheet(TEMU_SHEET)
    except Exception as e:
        st.error("❌ 데이터 로드 실패: " + str(e))
        st.stop()

    # 날짜 컬럼 표준화
    df_shein["order date"] = pd.to_datetime(df_shein["order processed on"], errors="coerce")
    df_temu["order date"] = df_temu["purchase date"].apply(parse_temudate)

    # 통합
    df_shein["platform"] = "SHEIN"
    df_temu["platform"] = "TEMU"
    df_shein["product number"] = df_shein["product description"].astype(str).str.strip().str.upper()
    df_temu["product number"] = df_temu["product number"].astype(str).str.strip().str.upper()

    # 판매수량/매출 표준화
    df_shein["qty"] = df_shein["quantity"].apply(try_float) if "quantity" in df_shein.columns else 1
    df_temu["qty"] = df_temu["quantity purchased"].apply(try_float) if "quantity purchased" in df_temu.columns else 1
    df_shein["sales"] = df_shein["product price"].apply(try_float) * df_shein["qty"]
    df_temu["sales"] = df_temu["base price total"].apply(try_float) * df_temu["qty"]

    # 필터 UI
    platform_opt = st.sidebar.radio("플랫폼", options=["BOTH", "SHEIN", "TEMU"], index=0)
    mindate = min(
        df_shein["order date"].min(),
        df_temu["order date"].min()
    )
    maxdate = max(
        df_shein["order date"].max(),
        df_temu["order date"].max()
    )
    date_range = st.sidebar.date_input("조회 기간", [mindate, maxdate])

    # 데이터 필터링
    if platform_opt == "BOTH":
        df_all = pd.concat([df_shein, df_temu], ignore_index=True)
    elif platform_opt == "SHEIN":
        df_all = df_shein.copy()
    else:
        df_all = df_temu.copy()

    df_all = df_all[
        (df_all["order date"] >= pd.to_datetime(date_range[0])) &
        (df_all["order date"] <= pd.to_datetime(date_range[1]))
    ]

    # KPI
    col1, col2, col3 = st.columns(3)
    col1.metric("총 판매수량", int(df_all["qty"].sum()))
    col2.metric("총 매출", f"${df_all['sales'].sum():,.2f}")
    col3.metric("주문건수", len(df_all))

    # ---- 일별 판매량/매출 추이
    st.markdown("### 일별 판매 추이")
    daily = df_all.groupby(df_all["order date"].dt.date).agg({
        "qty":"sum",
        "sales":"sum"
    }).reset_index()
    st.line_chart(daily.set_index("order date")[["qty","sales"]])

    # ---- 베스트셀러 TOP10
    st.markdown("### 베스트셀러 TOP10")
    best = (
        df_all.groupby("product number")
        .agg({"qty":"sum","sales":"sum"})
        .sort_values("qty", ascending=False)
        .head(10)
        .reset_index()
    )
    st.dataframe(best, use_container_width=True)

    # ---- 플랫폼별 breakdown (비율 파이차트)
    st.markdown("### 플랫폼별 매출 비율")
    platform_summary = df_all.groupby("platform").agg({"sales":"sum", "qty":"sum"})
    st.bar_chart(platform_summary["sales"])

    # ---- 상품별 상세 (옵션)
    with st.expander("상품별 상세 데이터 보기"):
        st.dataframe(df_all, use_container_width=True)

