# ==========================================
# File: pages/9_옵션_분석.py
# 옵션 · 카테고리 분석 (도넛 + 옵션 상세 테이블)
# ==========================================
import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
import re
from dateutil import parser

st.set_page_config(page_title="옵션 · 카테고리 분석", layout="wide")
st.title("🧩 옵션 · 카테고리 분석")

# -------------------------
# Helpers
# -------------------------
@st.cache_data(show_spinner=False)
def load_google_sheet(sheet_name: str) -> pd.DataFrame:
    import gspread
    from oauth2client.service_account import ServiceAccountCredentials
    import json
    GOOGLE_SHEET_URL = "https://docs.google.com/spreadsheets/d/1oyVzCgGK1Q3Qi_sbYwE-wKG6SArnfUDRe7rQfGOF-Eo"
    scope = ["https://spreadsheets.google.com/feeds","https://www.googleapis.com/auth/drive"]
    creds_json = {k: str(v) for k, v in st.secrets["gcp_service_account"].items()}
    with open("/tmp/service_account.json","w") as f:
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

def money_series(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s.astype(str).str.replace(r"[^0-9.\-]", "", regex=True), errors="coerce").fillna(0.0)

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
# Load & normalize
# -------------------------
info  = load_google_sheet("PRODUCT_INFO")
temu  = load_google_sheet("TEMU_SALES")
shein = load_google_sheet("SHEIN_SALES")

IMG_MAP = build_img_map(info)

# Dates
temu["order date"]  = temu["purchase date"].apply(parse_temudate)
shein["order date"] = shein["order processed on"].apply(parse_sheindate)

# Status & numerics
temu["order item status"] = temu["order item status"].astype(str)
temu["quantity shipped"]  = pd.to_numeric(temu.get("quantity shipped", 0), errors="coerce").fillna(0)
temu["base price total"]  = money_series(temu.get("base price total", pd.Series(dtype=str)))

shein["order status"]   = shein["order status"].astype(str)
shein["product price"]  = money_series(shein.get("product price", pd.Series(dtype=str)))

# robust column hooks
def find_col(cols, *cands):
    cols_low = {c.lower(): c for c in cols}
    for name in cands:
        if name.lower() in cols_low:
            return cols_low[name.lower()]
    # fallback: try contains
    low_list = list(cols_low.keys())
    for name in cands:
        for c in low_list:
            if name.lower() in c:
                return cols_low[c]
    return None

temu_color_col = find_col(temu.columns, "color")
temu_size_col  = find_col(temu.columns, "size")

shein_sku_col  = find_col(shein.columns, "seller sku", "sku", "seller_sku")

# -------------------------
# Size / Color normalization
# -------------------------
SIZE_MAP = {
    "SMALL":"S","SM":"S","S":"S",
    "MEDIUM":"M","MD":"M","M":"M",
    "LARGE":"L","LG":"L","L":"L",
    "XL":"1X","1XL":"1X","1X":"1X",
    "XXL":"2X","2XL":"2X","2X":"2X",
    "XXXL":"3X","3XL":"3X","3X":"3X",
}
def norm_size(x):
    s = str(x).strip().upper().replace(" ", "")
    return SIZE_MAP.get(s, s)

def norm_color(x):
    # UNDER_SCORE → space, Title Case
    s = str(x).strip().replace("_"," ").strip()
    if not s:
        return s
    return s.title()

# -------------------------
# Category mapping (reduce OTHER)
# -------------------------
def cat_from_info(style_key: str, temu_name_hint: str) -> str:
    # info row
    r = info[info["product number"].astype(str).str.upper().str.replace(" ","", regex=False).eq(style_key)]
    length = str(r["length"].iloc[0]).strip().lower() if not r.empty and "length" in r.columns else ""
    base   = str(r["default product name(en)"].iloc[0]).lower() if not r.empty and "default product name(en)" in r.columns else ""

    # set
    if length.startswith("sets") or "sets" in base:
        return "SET"
    # romper / jumpsuit from temu name hint
    hint = str(temu_name_hint).lower()
    if "romper" in hint:    return "ROMPER"
    if "jumpsuit" in hint:  return "JUMPSUIT"

    L = length.replace("_"," ").strip()
    if L in ["crop top","waist top","long top"]:
        return "TOP"
    if "dress" in L:
        return "DRESS"
    if "skirt" in L:
        return "SKIRT"
    if any(x in L for x in ["shorts","knee","capri","full"]):
        return "PANTS"
    # fallback
    return "OTHER"

# TEMU name hint map
name_col = find_col(temu.columns, "product name by customer order", "product name", "title")
temu_name_map = {}
if name_col:
    _tmp = temu.copy()
    _tmp["style_key"] = _tmp["product number"].astype(str).apply(lambda x: style_key_from_label(x, IMG_MAP))
    _tmp = _tmp.dropna(subset=["style_key"])
    temu_name_map = _tmp.groupby("style_key")[name_col].first().to_dict()

# -------------------------
# Date controls
# -------------------------
min_dt = pd.to_datetime(pd.concat([temu["order date"], shein["order date"]]).dropna()).min()
max_dt = pd.to_datetime(pd.concat([temu["order date"], shein["order date"]]).dropna()).max()
dr = st.date_input(
    "조회 기간",
    value=(max_dt.date() - pd.Timedelta(days=29), max_dt.date()),
    min_value=min_dt.date(),
    max_value=max_dt.date(),
)
start, end = (dr if isinstance(dr, (list,tuple)) else (dr,dr))
start = pd.to_datetime(start); end = pd.to_datetime(end) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)

platform = st.radio("플랫폼", ["BOTH","TEMU","SHEIN"], horizontal=True, index=0)

# -------------------------
# Build row-level option data
# -------------------------
rows = []

# TEMU rows
T = temu[(temu["order item status"].str.lower().isin(["shipped","delivered"])) &
         (temu["order date"]>=start) & (temu["order date"]<=end)].copy()
T["qty"]   = pd.to_numeric(T.get("quantity shipped",0), errors="coerce").fillna(0)
T["sales"] = money_series(T.get("base price total", pd.Series(dtype=str)))
T["style_key"] = T["product number"].astype(str).apply(lambda x: style_key_from_label(x, IMG_MAP))
T = T.dropna(subset=["style_key"])

if temu_color_col: T["color"] = T[temu_color_col].apply(norm_color)
else:             T["color"] = ""
if temu_size_col:  T["size"]  = T[temu_size_col].apply(norm_size)
else:              T["size"]  = ""

if platform in ["BOTH","TEMU"]:
    for _, r in T.iterrows():
        rows.append({
            "platform":"TEMU",
            "style": r["style_key"],
            "color": r["color"],
            "size":  r["size"],
            "qty":   r["qty"],
            "sales": r["sales"]
        })

# SHEIN rows
S = shein[(~shein["order status"].str.lower().eq("customer refunded")) &
          (shein["order date"]>=start) & (shein["order date"]<=end)].copy()
S["qty"]   = 1.0
S["sales"] = money_series(S.get("product price", pd.Series(dtype=str)))
S["style_key"] = S["product description"].astype(str).apply(lambda x: style_key_from_label(x, IMG_MAP))
S = S.dropna(subset=["style_key"])

def parse_shein_sku(s):
    if not shein_sku_col:
        return ("","")
    raw = str(s)
    parts = raw.split("-")
    if len(parts) >= 3:
        # SKU-COLOR-SIZE...  (여분 파트가 있으면 뒤는 버림)
        color = norm_color(parts[1])
        size  = norm_size(parts[2])
        return (color, size)
    return ("","")

if shein_sku_col:
    colors, sizes = [], []
    for v in S[shein_sku_col]:
        c, z = parse_shein_sku(v)
        colors.append(c); sizes.append(z)
    S["color"] = colors
    S["size"]  = sizes
else:
    S["color"] = ""
    S["size"]  = ""

if platform in ["BOTH","SHEIN"]:
    for _, r in S.iterrows():
        rows.append({
            "platform":"SHEIN",
            "style": r["style_key"],
            "color": r["color"],
            "size":  r["size"],
            "qty":   r["qty"],
            "sales": r["sales"]
        })

opt_df = pd.DataFrame(rows)
if opt_df.empty:
    st.info("해당 기간에 데이터가 없습니다.")
    st.stop()

opt_df["aov"] = opt_df.apply(lambda r: (r["sales"]/r["qty"]) if r["qty"]>0 else 0.0, axis=1)

# -------------------------
# 카테고리 도넛 + 표
# -------------------------
# style → category
cat_rows = []
for style in opt_df["style"].unique():
    hint = temu_name_map.get(style, "")
    cat = cat_from_info(style, hint)
    cat_rows.append((style, cat))
cat_df = pd.DataFrame(cat_rows, columns=["style","cat"])

opt_df = opt_df.merge(cat_df, on="style", how="left")

cat_sum = (opt_df.groupby("cat", as_index=False)
                  .agg(qty=("qty","sum"), sales=("sales","sum")))
cat_sum["ratio"] = (cat_sum["qty"] / cat_sum["qty"].sum() * 100.0).round(1)

left, right = st.columns([1.2,1.1])
with left:
    st.subheader("📊 카테고리별 판매 비율 (도넛)")
    donut = alt.Chart(cat_sum).mark_arc(outerRadius=180, innerRadius=90).encode(
        theta=alt.Theta("qty:Q", title="판매수량"),
        color=alt.Color("cat:N", title="카테고리"),
        tooltip=[alt.Tooltip("cat:N", title="카테고리"),
                 alt.Tooltip("qty:Q", title="수량", format=",.0f"),
                 alt.Tooltip("ratio:Q", title="비율(%)"),
                 alt.Tooltip("sales:Q", title="매출", format="$, .2f")]
    ).properties(height=380)
    st.altair_chart(donut, use_container_width=True)

with right:
    st.subheader("📑 카테고리 요약")
    st.dataframe(cat_sum.rename(columns={"cat":"카테고리","qty":"판매수량","ratio":"비율(%)","sales":"매출($)"}),
                 use_container_width=True, hide_index=True)

st.divider()

# -------------------------
# 옵션 상세 분석 (원래 방식)
# -------------------------
st.subheader("🔎 옵션 상세 분석 (변형별 성과)")

# 필터: 스타일(선택), 그룹 기준
style_choices = sorted(opt_df["style"].unique().tolist())
sel_styles = st.multiselect("분석할 스타일(선택 없음 = 전체)", style_choices, default=[])

group_mode = st.radio("그룹 기준", ["Color", "Size", "Color+Size"], horizontal=True)

df2 = opt_df.copy()
if sel_styles:
    df2 = df2[df2["style"].isin(sel_styles)].copy()

if group_mode == "Color":
    grp_cols = ["platform","style","color"]
elif group_mode == "Size":
    grp_cols = ["platform","style","size"]
else:
    grp_cols = ["platform","style","color","size"]

g = (df2.groupby(grp_cols, as_index=False)
         .agg(qty=("qty","sum"), sales=("sales","sum")))
g["aov"] = g.apply(lambda r: (r["sales"]/r["qty"]) if r["qty"]>0 else 0.0, axis=1)

# 이미지 URL
img_map = IMG_MAP
g["image"] = g["style"].apply(lambda x: img_map.get(str(x).upper(), ""))

# 보여주기
st.dataframe(
    g.rename(columns={
        "platform":"플랫폼", "style":"Style Number",
        "color":"Color", "size":"Size",
        "qty":"판매수량", "sales":"매출", "aov":"AOV"
    }).sort_values(["판매수량","매출"], ascending=[False,False]),
    use_container_width=True,
    hide_index=True,
    column_config={
        "image": st.column_config.ImageColumn("이미지", width="medium"),
        "판매수량": st.column_config.NumberColumn("판매수량", format="%,.0f"),
        "매출":     st.column_config.NumberColumn("매출", format="$%,.2f"),
        "AOV":     st.column_config.NumberColumn("AOV", format="$%,.2f"),
    }
)
