# ==========================================
# File: pages/5_교차플랫폼_비교.py
# (이미지 보이기 + 헤더 정렬 가능 버전)
# ==========================================
import streamlit as st
import pandas as pd
import re
from dateutil import parser

# -------------------------
# Page Config & Title
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
        import json as _json
        _json.dump(creds_json, f)
    creds = ServiceAccountCredentials.from_json_keyfile_name("/tmp/service_account.json", scope)
    client = gspread.authorize(creds)
    ws = client.open_by_url(GOOGLE_SHEET_URL).worksheet(sheet_name)
    df = pd.DataFrame(ws.get_all_records())
    df.columns = [c.lower().strip() for c in df.columns]
    return df

STYLE_RE = re.compile(r"\b([A-Z]{1,3}\d{3,5}[A-Z0-9]?)\b")

def parse_temudate(x):
    s = str(x)
    if "(" in s:
        s = s.split("(")[0].strip()
    try:
        return parser.parse(s, fuzzy=True)
    except Exception:
        return pd.NaT

def parse_sheindate(x):
    try:
        return pd.to_datetime(str(x), errors="coerce", infer_datetime_format=True)
    except Exception:
        return pd.NaT

def build_img_map(df_info: pd.DataFrame):
    keys = df_info.get("product number", pd.Series(dtype=str)).astype(str).str.upper().str.replace(" ", "", regex=False)
    return dict(zip(keys, df_info.get("image", "")))

def style_key_from_label(label: str, img_map: dict) -> str | None:
    s = str(label).strip().upper()
    if not s:
        return None
    s_key = s.replace(" ", "")
    if s_key in img_map:
        return s_key
    m = STYLE_RE.search(s)
    if m:
        cand = m.group(1).replace(" ", "")
        if cand in img_map:
            return cand
    for k in img_map.keys():
        if k in s_key:
            return k
    return None

# -------------------------
# Load & Normalize
# -------------------------
df_info  = load_google_sheet("PRODUCT_INFO")
df_temu  = load_google_sheet("TEMU_SALES")
df_shein = load_google_sheet("SHEIN_SALES")

IMG_MAP = build_img_map(df_info)

# Dates

df_temu["order date"]  = df_temu["purchase date"].apply(parse_temudate)
df_shein["order date"] = df_shein["order processed on"].apply(parse_sheindate)

# Status & numeric 정규화

df_temu["order item status"] = df_temu["order item status"].astype(str)
df_temu["quantity shipped"] = pd.to_numeric(df_temu.get("quantity shipped", 0), errors="coerce").fillna(0)

# 금액 컬럼을 안전하게 숫자로
_money = lambda s: pd.to_numeric(s.astype(str).str.replace(r"[^0-9.\-]", "", regex=True), errors="coerce").fillna(0.0)

df_shein["order status"] = df_shein["order status"].astype(str)
df_shein["product price"] = _money(df_shein["product price"])

# -------------------------
# Date controls
# -------------------------
min_dt = pd.to_datetime(pd.concat([df_temu["order date"], df_shein["order date"]]).dropna()).min()
max_dt = pd.to_datetime(pd.concat([df_temu["order date"], df_shein["order date"]]).dropna()).max()

if pd.isna(min_dt) or pd.isna(max_dt):
    st.info("날짜 데이터가 없습니다. 시트를 확인하세요.")
    st.stop()

# 기본: 최근 30일
dr = st.date_input(
    "조회 기간",
    value=(max_dt.date() - pd.Timedelta(days=29), max_dt.date()),
    min_value=min_dt.date(),
    max_value=max_dt.date(),
)
if isinstance(dr, (list, tuple)):
    start, end = dr
else:
    start, end = dr, dr
start = pd.to_datetime(start)
end   = pd.to_datetime(end) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)

# -------------------------
# Aggregate per platform
# -------------------------
# TEMU: shipped/delivered only
_t = df_temu[(df_temu["order date"] >= start) & (df_temu["order date"] <= end)].copy()
_t = _t[_t["order item status"].str.lower().isin(["shipped", "delivered"])].copy()
_t["style_key"] = _t["product number"].astype(str).apply(lambda x: style_key_from_label(x, IMG_MAP))
_t = _t.dropna(subset=["style_key"]) 

temu_grp = _t.groupby("style_key").agg(
    temu_qty=("quantity shipped", "sum"),
    temu_sales=("base price total", lambda s: _money(s).sum()),
)
# Qty는 정수화
temu_grp["temu_qty"] = temu_grp["temu_qty"].round().astype(int)
# AOV
temu_grp["temu_aov"] = temu_grp.apply(lambda r: (r["temu_sales"] / r["temu_qty"]) if r["temu_qty"] > 0 else 0.0, axis=1)

# SHEIN: exclude refunded
_s = df_shein[(df_shein["order date"] >= start) & (df_shein["order date"] <= end)].copy()
_s = _s[~_s["order status"].str.lower().isin(["customer refunded"])].copy()
_s["style_key"] = _s["product description"].astype(str).apply(lambda x: style_key_from_label(x, IMG_MAP))
_s = _s.dropna(subset=["style_key"]).copy()

shein_grp = _s.groupby("style_key").agg(
    shein_qty=("product description", "count"),
    shein_sales=("product price", "sum"),
)
# Qty는 정수화
shein_grp["shein_qty"] = shein_grp["shein_qty"].round().astype(int)
# AOV
shein_grp["shein_aov"] = shein_grp.apply(lambda r: (r["shein_sales"] / r["shein_qty"]) if r["shein_qty"] > 0 else 0.0, axis=1)

# -------------------------
# Merge & Tags
# -------------------------
combined = pd.concat([temu_grp, shein_grp], axis=1).fillna(0.0).reset_index().rename(columns={"index": "style_key", "style_key": "Style Number"})

STR_Q = 1.3  # 30% 이상 우위면 강세

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

# -------------------------
# KPI Summary (원래 형식 유지)
# -------------------------
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

# -------------------------
# Table (이미지 보이면서 헤더 정렬 가능)
# -------------------------
# 👉 썸네일 실제 크기 키우기(CSS). 컬럼 폭이 아니라 이미지 높이를 늘려야 커집니다.
THUMB_H = 144  # px (원하면 120, 144 등으로 변경)
st.markdown(f"""
<style>
/* DataFrame/Editor 안의 이미지 크기 강제 */
[data-testid="stDataFrame"] td img,
[data-testid="stDataEditor"] td img {{
    width: {THUMB}px !important;
    height: {THUMB}px !important;
    max-width: none !important;
    max-height: none !important;
    object-fit: cover !important;
    border-radius: 10px;
    display: block !important;
}}
/* 행 높이 확보 */
[data-testid="stDataFrame"] [role="row"],
[data-testid="stDataEditor"] [role="row"] {{
    min-height: {THUMB + 16}px !important;
}}
</style>
""", unsafe_allow_html=True)
# URL 컬럼 생성 (ImageColumn용)
combined["image_url"] = combined["Style Number"].apply(lambda x: IMG_MAP.get(str(x).upper(), ""))

# 표시 컬럼 구성 (숫자 타입 유지)
show = combined[[
    "image_url", "Style Number",
    "temu_qty", "temu_sales", "temu_aov",
    "shein_qty", "shein_sales", "shein_aov",
    "태그", "액션"
]].copy()

# Qty 정수 보장
show["temu_qty"] = show["temu_qty"].round().astype(int)
show["shein_qty"] = show["shein_qty"].round().astype(int)

st.dataframe(
    show.rename(columns={
        "image_url": "이미지",
        "temu_qty": "TEMU Qty", "temu_sales": "TEMU Sales", "temu_aov": "TEMU AOV",
        "shein_qty": "SHEIN Qty", "shein_sales": "SHEIN Sales", "shein_aov": "SHEIN AOV",
    }),
    use_container_width=True,
    hide_index=True,
    height=700,
    column_config={
        # ▶ 숫자 픽셀로 지정해야 실제 썸네일 렌더 크기를 계산합니다.
        "이미지": st.column_config.ImageColumn("이미지", width=THUMB),
        "TEMU Qty":  st.column_config.NumberColumn("TEMU Qty",  format="%,d", step=1),
        "SHEIN Qty": st.column_config.NumberColumn("SHEIN Qty", format="%,d", step=1),
        "TEMU Sales":  st.column_config.NumberColumn("TEMU Sales",  format="$%,.2f", step=0.01),
        "SHEIN Sales": st.column_config.NumberColumn("SHEIN Sales", format="$%,.2f", step=0.01),
        "TEMU AOV":    st.column_config.NumberColumn("TEMU AOV",    format="$%,.2f", step=0.01),
        "SHEIN AOV":   st.column_config.NumberColumn("SHEIN AOV",   format="$%,.2f", step=0.01),
    }
)
# -------------------------
# Download CSV (원자료)
# -------------------------
st.download_button(
    "CSV 다운로드",
    data=combined.to_csv(index=False),
    file_name="cross_platform_compare.csv",
    mime="text/csv",
)
