# ==========================================
# File: pages/5_교차플랫폼_비교.py
# (라이브 여부 필터 포함 버전)
# ==========================================
import streamlit as st
import pandas as pd
import numpy as np
import re
from dateutil import parser

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

_money = lambda s: pd.to_numeric(pd.Series(s).astype(str).str.replace(r"[^0-9.\-]", "", regex=True), errors="coerce").fillna(0.0)

# -------------------------
# Load
# -------------------------
df_info  = load_google_sheet("PRODUCT_INFO")
df_temu  = load_google_sheet("TEMU_SALES")
df_shein = load_google_sheet("SHEIN_SALES")

IMG_MAP = build_img_map(df_info)

# 날짜 정규화
df_temu["order date"]  = df_temu["purchase date"].apply(parse_temudate)
df_shein["order date"] = df_shein["order processed on"].apply(parse_sheindate)

# 숫자/상태 정규화
df_temu["order item status"] = df_temu["order item status"].astype(str)
df_temu["quantity shipped"]  = pd.to_numeric(df_temu.get("quantity shipped", 0), errors="coerce").fillna(0)
if "base price total" in df_temu.columns:
    df_temu["base price total"] = _money(df_temu["base price total"])

df_shein["order status"] = df_shein["order status"].astype(str)
if "product price" in df_shein.columns:
    df_shein["product price"] = _money(df_shein["product price"])

# 라이브 날짜(등록 여부) 맵
live = df_info[["product number", "temu_live_date", "shein_live_date"]].copy()
live["style_key"] = live["product number"].astype(str).str.upper().str.replace(" ", "", regex=False)
live["temu_live_date"]  = pd.to_datetime(live.get("temu_live_date"),  errors="coerce")
live["shein_live_date"] = pd.to_datetime(live.get("shein_live_date"), errors="coerce")
live["temu_live"]  = live["temu_live_date" ].notna()
live["shein_live"] = live["shein_live_date"].notna()
live["등록상태"] = np.select(
    [
        live["temu_live"] & live["shein_live"],
        live["temu_live"] & ~live["shein_live"],
        ~live["temu_live"] & live["shein_live"],
    ],
    ["둘다 등록", "TEMU만 등록", "SHEIN만 등록"],
    default="미등록"
)

# -------------------------
# Date controls
# -------------------------
min_dt = pd.to_datetime(pd.concat([df_temu["order date"], df_shein["order date"]]).dropna()).min()
max_dt = pd.to_datetime(pd.concat([df_temu["order date"], df_shein["order date"]]).dropna()).max()

if pd.isna(min_dt) or pd.isna(max_dt):
    st.info("날짜 데이터가 없습니다. 시트를 확인하세요.")
    st.stop()

dr = st.date_input(
    "조회 기간 (주문일 기준)",
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

# 등록 상태 필터
status_choice = st.selectbox(
    "표시할 등록 상태",
    ["모두", "둘다 등록", "TEMU만 등록", "SHEIN만 등록"],
    index=0
)

# -------------------------
# Aggregate per platform (주문기간 내 판매 집계)
# -------------------------
# TEMU
_t = df_temu[(df_temu["order date"] >= start) & (df_temu["order date"] <= end)].copy()
_t = _t[_t["order item status"].str.lower().isin(["shipped", "delivered"])].copy()
_t["style_key"] = _t["product number"].astype(str).apply(lambda x: style_key_from_label(x, IMG_MAP))
_t = _t.dropna(subset=["style_key"])
temu_grp = _t.groupby("style_key").agg(
    temu_qty=("quantity shipped","sum"),
    temu_sales=("base price total","sum"),
)
temu_grp["temu_qty"] = temu_grp["temu_qty"].round().astype(int)
temu_grp["temu_aov"] = temu_grp.apply(lambda r: (r["temu_sales"] / r["temu_qty"]) if r["temu_qty"] > 0 else 0.0, axis=1)

# SHEIN
_s = df_shein[(df_shein["order date"] >= start) & (df_shein["order date"] <= end)].copy()
_s = _s[~_s["order status"].str.lower().isin(["customer refunded"])].copy()
_s["style_key"] = _s["product description"].astype(str).apply(lambda x: style_key_from_label(x, IMG_MAP))
_s = _s.dropna(subset=["style_key"])
shein_grp = _s.groupby("style_key").agg(
    shein_qty=("product description","count"),
    shein_sales=("product price","sum"),
)
shein_grp["shein_qty"] = shein_grp["shein_qty"].round().astype(int)
shein_grp["shein_aov"] = shein_grp.apply(lambda r: (r["shein_sales"] / r["shein_qty"]) if r["shein_qty"] > 0 else 0.0, axis=1)

# -------------------------
# Merge sales + live
# -------------------------
combined = pd.concat([temu_grp, shein_grp], axis=1).reset_index()  # style_key 컬럼 포함
combined = combined.merge(
    live[["style_key","temu_live_date","shein_live_date","temu_live","shein_live","등록상태"]],
    on="style_key", how="outer"
)

# NaN → 0/False
for c in ["temu_qty","temu_sales","temu_aov","shein_qty","shein_sales","shein_aov"]:
    if c not in combined.columns:
        combined[c] = 0.0
combined[["temu_qty","shein_qty"]] = combined[["temu_qty","shein_qty"]].fillna(0).round().astype(int)
combined[["temu_sales","temu_aov","shein_sales","shein_aov"]] = combined[["temu_sales","temu_aov","shein_sales","shein_aov"]].fillna(0.0)
for c in ["temu_live","shein_live"]:
    if c not in combined.columns:
        combined[c] = False
combined["등록상태"] = combined["등록상태"].fillna("미등록")

# 표시 키/이미지
combined = combined.rename(columns={"style_key":"Style Number"})
img_map = build_img_map(df_info)
combined["image_url"] = combined["Style Number"].apply(lambda x: img_map.get(str(x).upper(), ""))

# 등록 상태 필터 적용
if status_choice != "모두":
    if status_choice == "둘다 등록":
        mask = combined["temu_live"] & combined["shein_live"]
    elif status_choice == "TEMU만 등록":
        mask = combined["temu_live"] & ~combined["shein_live"]
    else:  # SHEIN만 등록
        mask = ~combined["temu_live"] & combined["shein_live"]
    combined = combined[mask]

# -------------------------
# KPI
# -------------------------
with st.container(border=True):
    st.markdown("**요약**")
    cols = st.columns(4)
    both_styles = ((combined["temu_qty"] > 0) & (combined["shein_qty"] > 0)).sum()
    temu_strong = ((combined["temu_qty"] >= (combined["shein_qty"] * 1.3)) & (combined["temu_qty"] >= 3)).sum()
    shein_strong = ((combined["shein_qty"] >= (combined["temu_qty"] * 1.3)) & (combined["shein_qty"] >= 3)).sum()
    total_styles = combined.shape[0]
    with cols[0]: st.metric("분석 스타일 수", f"{total_styles:,}")
    with cols[1]: st.metric("양 플랫폼 동시 판매", f"{both_styles:,}")
    with cols[2]: st.metric("TEMU 강세", f"{temu_strong:,}")
    with cols[3]: st.metric("SHEIN 강세", f"{shein_strong:,}")

# -------------------------
# Default sort: 총 매출 내림차순
# -------------------------
combined["총매출"] = combined["temu_sales"] + combined["shein_sales"]
combined = combined.sort_values("총매출", ascending=False)

# -------------------------
# 스타일링(CSS) & 출력 테이블
# -------------------------
THUMB = 144
st.markdown(f"""
<style>
[data-testid="stDataFrame"] img, [data-testid="stDataEditor"] img {{
    height: {THUMB}px !important;
    width: {THUMB}px !important;
    border-radius: 8px;
    max-width: none !important;
    max-height: none !important;
    object-fit: cover !important;
}}
[data-testid="stDataFrame"] [role="row"], [data-testid="stDataEditor"] [role="row"] {{
    min-height: {THUMB + 16}px !important;
}}
</style>
""", unsafe_allow_html=True)

show = combined[[
    "image_url","Style Number",
    "temu_qty","temu_sales","temu_aov",
    "shein_qty","shein_sales","shein_aov",
    "등록상태","temu_live_date","shein_live_date"
]].copy()

st.dataframe(
    show.rename(columns={
        "image_url": "이미지",
        "temu_qty": "TEMU Qty", "temu_sales": "TEMU Sales", "temu_aov": "TEMU AOV",
        "shein_qty": "SHEIN Qty", "shein_sales": "SHEIN Sales", "shein_aov": "SHEIN AOV",
        "temu_live_date": "TEMU Live Date", "shein_live_date": "SHEIN Live Date",
    }),
    use_container_width=True,
    hide_index=True,
    height=680,
    column_config={
        "이미지": st.column_config.ImageColumn("이미지", width="large"),
        "TEMU Qty":  st.column_config.NumberColumn("TEMU Qty",  format="%,d", step=1),
        "SHEIN Qty": st.column_config.NumberColumn("SHEIN Qty", format="%,d", step=1),
        "TEMU Sales":  st.column_config.NumberColumn("TEMU Sales",  format="$%,.2f", step=0.01),
        "SHEIN Sales": st.column_config.NumberColumn("SHEIN Sales", format="$%,.2f", step=0.01),
        "TEMU AOV":    st.column_config.NumberColumn("TEMU AOV",    format="$%,.2f", step=0.01),
        "SHEIN AOV":   st.column_config.NumberColumn("SHEIN AOV",   format="$%,.2f", step=0.01),
        "TEMU Live Date":  st.column_config.DatetimeColumn("TEMU Live Date", format="YYYY-MM-DD"),
        "SHEIN Live Date": st.column_config.DatetimeColumn("SHEIN Live Date", format="YYYY-MM-DD"),
    }
)

# -------------------------
# Download CSV
# -------------------------
st.download_button(
    "CSV 다운로드",
    data=combined.drop(columns=["총매출"], errors="ignore").to_csv(index=False),
    file_name="cross_platform_compare_with_live.csv",
    mime="text/csv",
)
