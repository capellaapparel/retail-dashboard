import streamlit as st
import pandas as pd
import re
from dateutil import parser

st.set_page_config(page_title="교차 플랫폼 비교", layout="wide")
st.title("🔁 교차 플랫폼 성과 비교 (TEMU vs SHEIN)")

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

def usd(x):
    try:
        v = float(x)
        return f"${v:,.2f}"
    except Exception:
        return "-"

df_info = load_google_sheet("PRODUCT_INFO")
df_temu = load_google_sheet("TEMU_SALES")
df_shein = load_google_sheet("SHEIN_SALES")

IMG_MAP = build_img_map(df_info)

df_temu["order date"] = df_temu["purchase date"].apply(parse_temudate)
df_shein["order date"] = df_shein["order processed on"].apply(parse_sheindate)

df_temu["order item status"] = df_temu["order item status"].astype(str)
df_temu["quantity shipped"] = pd.to_numeric(df_temu.get("quantity shipped", 0), errors="coerce").fillna(0)

df_shein["order status"] = df_shein["order status"].astype(str)
df_shein["product price"] = (
    df_shein["product price"].astype(str).str.replace(r"[^0-9.\-]", "", regex=True).replace("", pd.NA).astype(float)
)

min_dt = pd.to_datetime(pd.concat([
    df_temu["order date"], df_shein["order date"]
]).dropna()).min()
max_dt = pd.to_datetime(pd.concat([
    df_temu["order date"], df_shein["order date"]
]).dropna()).max()

if pd.isna(min_dt) or pd.isna(max_dt):
    st.info("날짜 데이터가 없습니다. 시트를 확인하세요.")
    st.stop()

dr = st.date_input(
    "조회 기간",
    value=(max_dt.date() - pd.Timedelta(days=29), max_dt.date()),
    min_value=min_dt.date(),
    max_value=max_dt.date()
)
if isinstance(dr, (list, tuple)):
    start, end = dr
else:
    start, end = dr, dr
start = pd.to_datetime(start)
end = pd.to_datetime(end) + pd.Timedelta(hours=23, minutes=59, seconds=59)

_t = df_temu[(df_temu["order date"] >= start) & (df_temu["order date"] <= end)]
_t = _t[_t["order item status"].str.lower().isin(["shipped", "delivered"])]
_t["style_key"] = _t["product number"].astype(str).apply(lambda x: style_key_from_label(x, IMG_MAP))
_t = _t.dropna(subset=["style_key"])

temu_grp = _t.groupby("style_key").agg(
    temu_qty=("quantity shipped", "sum"),
    temu_sales=("base price total", lambda s: pd.to_numeric(s.astype(str).str.replace(r"[^0-9.\-]", "", regex=True), errors="coerce").fillna(0).sum()),
)
temu_grp["temu_qty"] = temu_grp["temu_qty"].round().astype(int)
temu_grp["temu_aov"] = temu_grp.apply(lambda r: (r["temu_sales"] / r["temu_qty"]) if r["temu_qty"] > 0 else 0.0, axis=1)

_s = df_shein[(df_shein["order date"] >= start) & (df_shein["order date"] <= end)]
_s = _s[~_s["order status"].str.lower().isin(["customer refunded"])]
_s["style_key"] = _s["product description"].astype(str).apply(lambda x: style_key_from_label(x, IMG_MAP))
_s = _s.dropna(subset=["style_key"])

shein_grp = _s.groupby("style_key").agg(
    shein_qty=("product description", "count"),
    shein_sales=("product price", "sum"),
)
shein_grp["shein_qty"] = shein_grp["shein_qty"].round().astype(int)
shein_grp["shein_aov"] = shein_grp.apply(lambda r: (r["shein_sales"] / r["shein_qty"]) if r["shein_qty"] > 0 else 0.0, axis=1)

combined = pd.concat([temu_grp, shein_grp], axis=1).fillna(0.0).reset_index().rename(columns={"index": "style_key", "style_key": "Style Number"})

STR_Q = 1.3
def tag_strength(r):
    if r["temu_qty"] >= r["shein_qty"] * STR_Q and r["temu_qty"] >= 3:
        return "TEMU 강세"
    if r["shein_qty"] >= r["temu_qty"] * STR_Q and r["shein_qty"] >= 3:
        return "SHEIN 강세"
    return "균형"
combined["태그"] = combined.apply(tag_strength, axis=1)

combined["이미지"] = combined["Style Number"].apply(lambda x: f"<img src='{IMG_MAP.get(str(x).upper(), '')}' class='thumb'>" if str(IMG_MAP.get(str(x).upper(), '')).startswith("http") else "")

def action_hint(row):
    if row["태그"] == "TEMU 강세":
        return "SHEIN 노출/가격 점검 (이미지·타이틀 개선 + 소폭 할인 검토)"
    if row["태그"] == "SHEIN 강세":
        return "TEMU 가격 재검토 또는 노출 강화 (키워드/이미지 개선)"
    return "두 플랫폼 동일 전략 유지"
combined["액션"] = combined.apply(action_hint, axis=1)

# Use st.data_editor for filter/sort with HTML rendering for images
st.data_editor(
    combined.rename(columns={
        "temu_qty": "TEMU Qty",
        "temu_sales": "TEMU Sales",
        "temu_aov": "TEMU AOV",
        "shein_qty": "SHEIN Qty",
        "shein_sales": "SHEIN Sales",
        "shein_aov": "SHEIN AOV",
    }),
    use_container_width=True,
    hide_index=True,
    column_config={
        "이미지": st.column_config.Column("이미지", help="상품 이미지", width="small")
    },
    height=600,
    disabled=True
)
