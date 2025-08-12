# ==========================================
# File: pages/5_교차플랫폼_비교.py
# (변형 단위 분석: 스타일 / 스타일+컬러 / 스타일+컬러+사이즈)
# ==========================================
import streamlit as st
import pandas as pd
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

# --- variant normalization ---
SIZE_MAP = {
    "1XL": "1X", "1X": "1X",
    "2XL": "2X", "2X": "2X",
    "3XL": "3X", "3X": "3X",
    "SMALL": "S", "S": "S",
    "MEDIUM": "M", "M": "M",
    "LARGE": "L", "L": "L",
}
def normalize_size(x: str | None) -> str | None:
    if x is None: return None
    s = str(x).strip().upper().replace(" ", "")
    return SIZE_MAP.get(s, s if s else None)

def normalize_color(x: str | None) -> str | None:
    if x is None: return None
    s = str(x).strip().replace("_", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s.upper() if s else None

def split_shein_sku(s: str):
    """
    SHEIN 'seller sku' → SKU-COLOR-SIZE
    COLOR 안의'-'도 있을 수 있어 split 후 마지막 토큰을 size로, 나머지 중간을 color로 묶음
    """
    t = str(s).strip()
    if not t or "-" not in t:
        return t, None, None
    parts = t.split("-")
    if len(parts) < 3:
        # 최소 3조각이 아닐 경우 안전하게 반환
        return parts[0], None, None
    style = parts[0]
    size = parts[-1]
    color = "-".join(parts[1:-1])  # 중간 모두가 컬러
    # 후처리
    return style, normalize_color(color), normalize_size(size)

# -------------------------
# Load & Normalize
# -------------------------
df_info  = load_google_sheet("PRODUCT_INFO")
df_temu  = load_google_sheet("TEMU_SALES")
df_shein = load_google_sheet("SHEIN_SALES")

IMG_MAP = build_img_map(df_info)

# dates
df_temu["order date"]  = df_temu["purchase date"].apply(parse_temudate)
df_shein["order date"] = df_shein["order processed on"].apply(parse_sheindate)

# numerics
_money = lambda s: pd.to_numeric(s.astype(str).str.replace(r"[^0-9.\-]", "", regex=True), errors="coerce").fillna(0.0)

df_temu["order item status"] = df_temu["order item status"].astype(str)
df_temu["quantity shipped"]  = pd.to_numeric(df_temu.get("quantity shipped", 0), errors="coerce").fillna(0)

df_shein["order status"]   = df_shein["order status"].astype(str)
df_shein["product price"]  = _money(df_shein["product price"])

# TEMU variant columns (if present)
df_temu["color_norm"] = df_temu.get("color", pd.Series([None]*len(df_temu))).apply(normalize_color)
df_temu["size_norm"]  = df_temu.get("size",  pd.Series([None]*len(df_temu))).apply(normalize_size)

# SHEIN variant columns from seller sku
if "seller sku" in df_shein.columns:
    shp = df_shein["seller sku"].apply(split_shein_sku)
    df_shein["style_from_sku"]  = shp.apply(lambda x: x[0])
    df_shein["color_norm"]      = shp.apply(lambda x: x[1])
    df_shein["size_norm"]       = shp.apply(lambda x: x[2])
else:
    # fallback: no seller sku → only style-level
    df_shein["style_from_sku"] = df_shein.get("product description", "")

# -------------------------
# Date controls
# -------------------------
min_dt = pd.to_datetime(pd.concat([df_temu["order date"], df_shein["order date"]]).dropna()).min()
max_dt = pd.to_datetime(pd.concat([df_temu["order date"], df_shein["order date"]]).dropna()).max()
if pd.isna(min_dt) or pd.isna(max_dt):
    st.info("날짜 데이터가 없습니다. 시트를 확인하세요.")
    st.stop()

# 기본 30일
dr = st.date_input(
    "조회 기간",
    value=(max_dt.date() - pd.Timedelta(days=29), max_dt.date()),
    min_value=min_dt.date(), max_value=max_dt.date(),
)
if isinstance(dr, (list, tuple)):
    start, end = dr
else:
    start, end = dr, dr
start = pd.to_datetime(start); end = pd.to_datetime(end) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)

# 분석 단위
gran = st.radio("분석 단위", ["스타일", "스타일+컬러", "스타일+컬러+사이즈"], horizontal=True)

# 어떤 key 컬럼으로 묶을지 결정
if gran == "스타일":
    key_cols = ["style_key"]
elif gran == "스타일+컬러":
    key_cols = ["style_key","color_norm"]
else:
    key_cols = ["style_key","color_norm","size_norm"]

# -------------------------
# Aggregate per platform (by selected granularity)
# -------------------------
# TEMU
t = df_temu[(df_temu["order date"].between(start, end)) &
            (df_temu["order item status"].str.lower().isin(["shipped","delivered"]))].copy()
t["style_key"] = t["product number"].astype(str).apply(lambda x: style_key_from_label(x, IMG_MAP))
t = t.dropna(subset=["style_key"])
temu_grp = (
    t.groupby(key_cols)
     .agg(temu_qty=("quantity shipped","sum"),
          temu_sales=("base price total", lambda s: _money(s).sum()))
     .reset_index()
)
temu_grp["temu_qty"] = temu_grp["temu_qty"].round().astype(int)
temu_grp["temu_aov"] = temu_grp.apply(lambda r: (r["temu_sales"]/r["temu_qty"]) if r["temu_qty"]>0 else 0.0, axis=1)

# SHEIN
s = df_shein[(df_shein["order date"].between(start, end)) &
             (~df_shein["order status"].str.lower().eq("customer refunded"))].copy()
# style_key from seller sku (or fallback)
s["style_key"] = s["style_from_sku"].astype(str).apply(lambda x: style_key_from_label(x, IMG_MAP))
s = s.dropna(subset=["style_key"])
s["qty"] = 1
shein_grp = (
    s.groupby(key_cols)
     .agg(shein_qty=("qty","sum"),
          shein_sales=("product price","sum"))
     .reset_index()
)
shein_grp["shein_qty"] = shein_grp["shein_qty"].round().astype(int)
shein_grp["shein_aov"] = shein_grp.apply(lambda r: (r["shein_sales"]/r["shein_qty"]) if r["shein_qty"]>0 else 0.0, axis=1)

# -------------------------
# Merge & Tagging
# -------------------------
combined = pd.merge(temu_grp, shein_grp, on=key_cols, how="outer").fillna(0.0)

STR_Q = 1.3
def tag_strength(r):
    if r["temu_qty"] >= r["shein_qty"] * STR_Q and r["temu_qty"] >= 3: return "TEMU 강세"
    if r["shein_qty"] >= r["temu_qty"] * STR_Q and r["shein_qty"] >= 3: return "SHEIN 강세"
    return "균형"
combined["태그"] = combined.apply(tag_strength, axis=1)

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
    both = ((combined["temu_qty"]>0) & (combined["shein_qty"]>0)).sum()
    t_str = (combined["태그"].eq("TEMU 강세")).sum()
    s_str = (combined["태그"].eq("SHEIN 강세")).sum()
    tot   = combined.shape[0]
    cols[0].metric("분석 키 개수", f"{tot:,}")
    cols[1].metric("양 플랫폼 동시 판매", f"{both:,}")
    cols[2].metric("TEMU 강세", f"{t_str:,}")
    cols[3].metric("SHEIN 강세", f"{s_str:,}")

# 정렬 & 표시
combined["총매출"] = combined["temu_sales"] + combined["shein_sales"]
combined = combined.sort_values("총매출", ascending=False)

# 이미지 URL (스타일 기준)
combined["Style Number"] = combined["style_key"].astype(str)
combined["이미지"] = combined["Style Number"].apply(lambda x: IMG_MAP.get(x.upper(), ""))

# 출력 테이블 구성
cols_to_show = ["이미지", "Style Number"]
if "color_norm" in key_cols: cols_to_show.append("color_norm")
if "size_norm"  in key_cols: cols_to_show.append("size_norm")
cols_to_show += ["temu_qty","temu_sales","temu_aov","shein_qty","shein_sales","shein_aov","태그","액션"]

show = combined[cols_to_show].rename(columns={
    "color_norm": "Color",
    "size_norm":  "Size",
    "temu_qty":   "TEMU Qty",
    "temu_sales": "TEMU Sales",
    "temu_aov":   "TEMU AOV",
    "shein_qty":  "SHEIN Qty",
    "shein_sales":"SHEIN Sales",
    "shein_aov":  "SHEIN AOV",
})

# 이미지 크게
THUMB = 144
st.markdown(f"""
<style>
[data-testid="stDataFrame"] img, [data-testid="stDataEditor"] img {{
    height:{THUMB}px !important; width:{THUMB}px !important;
    border-radius:8px; object-fit:cover !important;
}}
[data-testid="stDataFrame"] [role="row"], [data-testid="stDataEditor"] [role="row"] {{
    min-height:{THUMB + 16}px !important;
}}
</style>
""", unsafe_allow_html=True)

st.dataframe(
    show,
    use_container_width=True, hide_index=True, height=680,
    column_config={
        "이미지": st.column_config.ImageColumn("이미지", width="large"),
        "TEMU Qty":  st.column_config.NumberColumn("TEMU Qty",  format="%,d", step=1),
        "SHEIN Qty": st.column_config.NumberColumn("SHEIN Qty", format="%,d", step=1),
        "TEMU Sales":  st.column_config.NumberColumn("TEMU Sales",  format="$%,.2f", step=0.01),
        "SHEIN Sales": st.column_config.NumberColumn("SHEIN Sales", format="$%,.2f", step=0.01),
        "TEMU AOV":    st.column_config.NumberColumn("TEMU AOV",    format="$%,.2f", step=0.01),
        "SHEIN AOV":   st.column_config.NumberColumn("SHEIN AOV",   format="$%,.2f", step=0.01),
    }
)

st.download_button(
    "CSV 다운로드",
    data=combined.drop(columns=["총매출"], errors="ignore").to_csv(index=False),
    file_name="cross_platform_compare_variant.csv",
    mime="text/csv",
)
