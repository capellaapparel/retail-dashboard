# ==========================================
# File: pages/5_교차플랫폼_비교.py
# ==========================================
import streamlit as st
import pandas as pd
import re
from dateutil import parser

# -------------------------
# Page Config
# -------------------------
st.set_page_config(page_title="교차 플랫폼 비교", layout="wide")
st.title("🔁 교차 플랫폼 성과 비교 (TEMU vs SHEIN)")

# -------------------------
# Helpers
# -------------------------
@st.cache_data(show_spinner=False)
def load_google_sheet(sheet_name: str) -> pd.DataFrame:
    import gspread
    from oauth2client.service_account import ServiceAccountCredentials
    import json
    GOOGLE_SHEET_URL = "https://docs.google.com/spreadsheets/d/1oyVzCgGK1Q3Qi_sbYwE-wKG6SArnfUDRe7rQfGOF-Eo"
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_json = {k: str(v) for k, v in st.secrets["gcp_service_account"].items()}
    with open("/tmp/service_account.json", "w") as f:
        json.dump(creds_json, f)
    creds = ServiceAccountCredentials.from_json_keyfile_name("/tmp/service_account.json", scope)
    client = gspread.authorize(creds)
    ws = client.open_by_url(GOOGLE_SHEET_URL).worksheet(sheet_name)
    df = pd.DataFrame(ws.get_all_records())
    df.columns = [c.lower().strip() for c in df.columns]
    return df

STYLE_RE = re.compile(r"\b([A-Z]{1,3}\d{3,5}[A-Z0-9]?)\b")

def parse_temudate(x):
    s = str(x)
    if "(" in s: s = s.split("(")[0].strip()
    try: return parser.parse(s, fuzzy=True)
    except Exception: return pd.NaT

def parse_sheindate(x):
    try: return pd.to_datetime(str(x), errors="coerce", infer_datetime_format=True)
    except Exception: return pd.NaT

def build_img_map(df_info: pd.DataFrame):
    keys = df_info.get("product number", pd.Series(dtype=str)).astype(str).str.upper().str.replace(" ", "", regex=False)
    return dict(zip(keys, df_info.get("image", "")))

def style_key_from_label(label: str, img_map: dict) -> str | None:
    s = str(label).strip().upper()
    if not s: return None
    s_key = s.replace(" ", "")
    if s_key in img_map: return s_key
    m = STYLE_RE.search(s)
    if m:
        cand = m.group(1).replace(" ", "")
        if cand in img_map: return cand
    for k in img_map.keys():
        if k in s_key: return k
    return None

def usd(x):
    try:
        v = float(x)
        return f"${v:,.2f}"
    except Exception:
        return "-"

# -------------------------
# Page function
# -------------------------
def cross_platform_page():
    st.header("🔁 교차 플랫폼 성과 비교 (TEMU vs SHEIN)")

    # Load
    df_info  = load_google_sheet("PRODUCT_INFO")
    df_temu  = load_google_sheet("TEMU_SALES")
    df_shein = load_google_sheet("SHEIN_SALES")
    IMG_MAP  = build_img_map(df_info)

    # Normalize
    df_temu["order date"] = df_temu["purchase date"].apply(parse_temudate)
    df_temu["order item status"] = df_temu["order item status"].astype(str)
    df_temu["quantity shipped"] = pd.to_numeric(df_temu.get("quantity shipped", 0), errors="coerce").fillna(0)
    # ensure base price numeric when summing later
    def _money_series(s):
        return pd.to_numeric(s.astype(str).str.replace(r"[^0-9.\-]", "", regex=True), errors="coerce").fillna(0.0)

    df_shein["order date"] = df_shein["order processed on"].apply(parse_sheindate)
    df_shein["order status"] = df_shein["order status"].astype(str)
    df_shein["product price"] = _money_series(df_shein["product price"])

    # Date range
    dt_all = pd.to_datetime(pd.concat([df_temu["order date"], df_shein["order date"]]).dropna())
    if dt_all.empty:
        st.info("날짜 데이터가 없습니다. 시트를 확인하세요.")
        return
    min_dt, max_dt = dt_all.min().date(), dt_all.max().date()

    dr = st.date_input("조회 기간", value=(max_dt - pd.Timedelta(days=29), max_dt),
                       min_value=min_dt, max_value=max_dt)
    if isinstance(dr, (list, tuple)):
        start, end = dr
    else:
        start = end = dr
    start = pd.to_datetime(start)
    end   = pd.to_datetime(end) + pd.Timedelta(hours=23, minutes=59, seconds=59)

    # -------------------------
    # Aggregate per platform
    # -------------------------
    # TEMU: shipped/delivered only
    t = df_temu[(df_temu["order date"] >= start) & (df_temu["order date"] <= end)].copy()
    t = t[t["order item status"].str.lower().isin(["shipped", "delivered"])].copy()
    t["style_key"] = t["product number"].astype(str).apply(lambda x: style_key_from_label(x, IMG_MAP))
    t = t.dropna(subset=["style_key"])

    temu_grp = t.groupby("style_key").agg(
        temu_qty=("quantity shipped", "sum"),
        temu_sales=("base price total", lambda s: _money_series(s).sum()),
    )
    # 👉 Qty 정수화
    temu_grp["temu_qty"] = temu_grp["temu_qty"].round().astype(int)
    temu_grp["temu_aov"] = temu_grp.apply(
        lambda r: (r["temu_sales"] / r["temu_qty"]) if r["temu_qty"] > 0 else 0.0, axis=1
    )

    # SHEIN: exclude refunded
    s = df_shein[(df_shein["order date"] >= start) & (df_shein["order date"] <= end)].copy()
    s = s[~s["order status"].str.lower().isin(["customer refunded"])].copy()
    s["style_key"] = s["product description"].astype(str).apply(lambda x: style_key_from_label(x, IMG_MAP))
    s = s.dropna(subset=["style_key"])

    shein_grp = s.groupby("style_key").agg(
        shein_qty=("product description", "count"),
        shein_sales=("product price", "sum"),
    )
    # 👉 Qty 정수화
    shein_grp["shein_qty"] = shein_grp["shein_qty"].round().astype(int)
    shein_grp["shein_aov"] = shein_grp.apply(
        lambda r: (r["shein_sales"] / r["shein_qty"]) if r["shein_qty"] > 0 else 0.0, axis=1
    )

    # Merge
    combined = pd.concat([temu_grp, shein_grp], axis=1).fillna(0.0).reset_index()
    combined = combined.rename(columns={"index": "style_key", "style_key": "Style Number"})

    # Strength tag
    STR_Q = 1.3  # 30% 이상 차이
    def tag_strength(r):
        if r["temu_qty"] >= r["shein_qty"] * STR_Q and r["temu_qty"] >= 3:
            return "TEMU 강세"
        if r["shein_qty"] >= r["temu_qty"] * STR_Q and r["shein_qty"] >= 3:
            return "SHEIN 강세"
        return "균형"
    combined["태그"] = combined.apply(tag_strength, axis=1)

    # 액션 힌트
    def action_hint(row):
        if row["태그"] == "TEMU 강세":
            return "SHEIN 노출/가격 점검 (이미지·타이틀 개선 + 소폭 할인 검토)"
        if row["태그"] == "SHEIN 강세":
            return "TEMU 가격 재검토 또는 노출 강화 (키워드/이미지 개선)"
        return "두 플랫폼 동일 전략 유지"
    combined["액션"] = combined.apply(action_hint, axis=1)

    # KPI
    with st.container(border=True):
        st.markdown("**요약**")
        cols = st.columns(4)
        both_styles = ((combined["temu_qty"] > 0) & (combined["shein_qty"] > 0)).sum()
        temu_strong = (combined["태그"] == "TEMU 강세").sum()
        shein_strong = (combined["태그"] == "SHEIN 강세").sum()
        total_styles = combined.shape[0]
        with cols[0]:
            st.metric("분석 스타일 수", f"{total_styles:,}")
        with cols[1]:
            st.metric("양 플랫폼 동시 판매", f"{both_styles:,}")
        with cols[2]:
            st.metric("TEMU 강세", f"{temu_strong:,}")
        with cols[3]:
            st.metric("SHEIN 강세", f"{shein_strong:,}")

    # Sort options
    sort_opt = st.selectbox(
        "정렬 기준",
        ["총 판매수량", "플랫폼 격차(QTY)", "플랫폼 격차(AOV)", "플랫폼 격차(매출)", "Style Number"],
        index=0,
    )
    combined["총합_qty"] = (combined["temu_qty"] + combined["shein_qty"]).astype(int)
    combined["격차_qty"] = (combined["temu_qty"] - combined["shein_qty"]).abs().astype(int)
    combined["격차_aov"] = (combined["temu_aov"] - combined["shein_aov"]).abs()
    combined["격차_sales"] = (combined["temu_sales"] - combined["shein_sales"]).abs()

    if sort_opt == "총 판매수량":
        combined = combined.sort_values("총합_qty", ascending=False)
    elif sort_opt == "플랫폼 격차(QTY)":
        combined = combined.sort_values("격차_qty", ascending=False)
    elif sort_opt == "플랫폼 격차(AOV)":
        combined = combined.sort_values("격차_aov", ascending=False)
    elif sort_opt == "플랫폼 격차(매출)":
        combined = combined.sort_values("격차_sales", ascending=False)
    else:
        combined = combined.sort_values("Style Number")

    # Build display table
    img_map = IMG_MAP
    combined["이미지"] = combined["Style Number"].apply(
        lambda x: f"<img src='{img_map.get(str(x).upper(), '')}' class='thumb'>"
        if str(img_map.get(str(x).upper(), "")).startswith("http") else ""
    )

    show = combined[[
        "이미지", "Style Number",
        "temu_qty", "temu_sales", "temu_aov",
        "shein_qty", "shein_sales", "shein_aov",
        "태그", "액션"
    ]].copy()

    show.rename(columns={
        "temu_qty":"TEMU Qty","temu_sales":"TEMU Sales","temu_aov":"TEMU AOV",
        "shein_qty":"SHEIN Qty","shein_sales":"SHEIN Sales","shein_aov":"SHEIN AOV",
    }, inplace=True)

    # 👉 정수/통화 포맷
    show["TEMU Qty"]  = show["TEMU Qty"].astype(int).map(lambda x: f"{x:,}")
    show["SHEIN Qty"] = show["SHEIN Qty"].astype(int).map(lambda x: f"{x:,}")
    for col in ["TEMU Sales","TEMU AOV","SHEIN Sales","SHEIN AOV"]:
        show[col] = show[col].apply(usd)

    # CSS + render
    st.markdown("""
    <style>
    img.thumb { width:72px; height:auto; border-radius:10px; }
    .table-wrap table { width:100% !important; border-collapse:separate; border-spacing:0; }
    .table-wrap th, .table-wrap td { padding:10px 12px; font-size:0.95rem; }
    .table-wrap thead th { background:#fafafa; position:sticky; top:0; z-index:1; }
    </style>
    """, unsafe_allow_html=True)

    with st.container(border=True):
        st.markdown("**플랫폼별 성과 비교 테이블**")
        st.markdown(f"<div class='table-wrap'>{show.to_html(escape=False, index=False)}</div>", unsafe_allow_html=True)

    # Download
    st.download_button(
        "CSV 다운로드",
        data=combined.to_csv(index=False),
        file_name="cross_platform_compare.csv",
        mime="text/csv"
    )
