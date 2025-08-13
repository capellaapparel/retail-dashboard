# ==========================================
# File: pages/9_옵션_카테고리_분석.py
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
    if "(" in s: s = s.split("(")[0].strip()
    try: return parser.parse(s, fuzzy=True)
    except Exception: return pd.NaT

def parse_sheindate(x):
    try: return pd.to_datetime(str(x), errors="coerce", infer_datetime_format=True)
    except Exception: return pd.NaT

def style_key_from_label(label: str, valid_keys: set[str]) -> str | None:
    s = str(label).strip().upper()
    if not s: return None
    s_key = s.replace(" ", "")
    if s_key in valid_keys: return s_key
    m = STYLE_RE.search(s)
    if m:
        cand = m.group(1).replace(" ", "")
        if cand in valid_keys: return cand
    for k in valid_keys:
        if k in s_key: return k
    return None

def norm_color(c):
    s = str(c).strip().replace("_"," ").title()
    if s in ["Nan", "None", ""]: return None
    return s

SIZE_MAP = {
    "SMALL":"S", "MEDIUM":"M", "LARGE":"L",
    "XS":"XS", "S":"S", "M":"M", "L":"L", "XL":"XL",
    "1XL":"1X", "2XL":"2X", "3XL":"3X",
    "1X":"1X", "2X":"2X", "3X":"3X",
}
def norm_size(x):
    s = str(x).strip().upper().replace(" ", "")
    return SIZE_MAP.get(s, s if s not in ["", "NAN", "NONE"] else None)

# -------------------------
# Load data
# -------------------------
info  = load_google_sheet("PRODUCT_INFO")
temu  = load_google_sheet("TEMU_SALES")
shein = load_google_sheet("SHEIN_SALES")

# Keys for matching
valid_keys = set(info.get("product number", pd.Series(dtype=str)).astype(str).str.upper().str.replace(" ","", regex=False))

# Order dates
temu["order date"]  = temu["purchase date"].apply(parse_temudate)
shein["order date"] = shein["order processed on"].apply(parse_sheindate)

# Normalize status/qty/price
temu["order item status"] = temu["order item status"].astype(str)
temu["quantity shipped"]  = pd.to_numeric(temu.get("quantity shipped", 0), errors="coerce").fillna(0)

shein["order status"] = shein["order status"].astype(str)
shein["product price"] = pd.to_numeric(shein.get("product price", 0).astype(str).str.replace(r"[^0-9.\-]", "", regex=True), errors="coerce").fillna(0.0)

# -------------------------
# Controls
# -------------------------
min_dt = pd.to_datetime(pd.concat([temu["order date"], shein["order date"]]).dropna()).min()
max_dt = pd.to_datetime(pd.concat([temu["order date"], shein["order date"]]).dropna()).max()

c1, c2 = st.columns([1.4, 1])
with c1:
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
    start = pd.to_datetime(start); end = pd.to_datetime(end) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
with c2:
    platform = st.radio("플랫폼", ["BOTH","TEMU","SHEIN"], horizontal=True)

# -------------------------
# Category Mapper
# -------------------------
TOP_TOKENS   = ["CROP TOP", "WAIST TOP", "LONG TOP", "TOP"]
DRESS_TOKENS = ["MINI DRESS", "MIDI DRESS", "MAXI DRESS", "DRESS"]
SKIRT_TOKENS = ["MINI SKIRT", "MAXI SKIRT", "SKIRT"]

def map_category(length_val, temu_name, shein_desc):
    lv = str(length_val or "").upper()
    # 길이에 옵션 두 개(콤마)면 SET
    if "," in lv and any(t in lv for t in TOP_TOKENS + DRESS_TOKENS + SKIRT_TOKENS):
        return "SET"

    if any(t in lv for t in TOP_TOKENS): return "TOP"
    if any(t in lv for t in DRESS_TOKENS): return "DRESS"
    if any(t in lv for t in SKIRT_TOKENS): return "SKIRT"

    # 나머지 군: 팬츠/점프수트/롬퍼
    tname = str(temu_name or "").upper()
    sdesc = str(shein_desc or "").upper()
    text  = tname + " " + sdesc
    if "ROMPER" in text:    return "ROMPER"
    if "JUMPSUIT" in text:  return "JUMPSUIT"
    if "PANT" in text or "PANTS" in text or "TROUSER" in text:
        return "PANTS"
    # 안전망
    return "OTHER"

# PRODUCT_INFO (length) join 준비
info_key = info[["product number","length"]].copy()
info_key["style_key"] = info_key["product number"].astype(str).str.upper().str.replace(" ","", regex=False)
LEN_MAP = dict(zip(info_key["style_key"], info_key["length"]))

# -------------------------
# Build rows (platform by platform)
# -------------------------
rows = []

# TEMU rows
if platform in ["TEMU","BOTH"]:
    t = temu[(temu["order date"]>=start) & (temu["order date"]<=end)].copy()
    t = t[t["order item status"].str.lower().isin(["shipped","delivered"])].copy()
    t["style_key"] = t["product number"].astype(str).apply(lambda x: style_key_from_label(x, valid_keys))
    t = t.dropna(subset=["style_key"])
    t["qty"] = t["quantity shipped"].astype(float)

    # 색/사이즈
    t["color"] = t.get("color", np.nan).apply(norm_color)
    t["size"]  = t.get("size",  np.nan).apply(norm_size)

    # 카테고리
    t["cat"] = t.apply(
        lambda r: map_category(
            LEN_MAP.get(str(r["style_key"]), ""),
            r.get("product name by customer order", r.get("product description", "")),
            ""
        ), axis=1
    )

    rows.append(t[["style_key","color","size","qty","cat"]].assign(platform="TEMU"))

# SHEIN rows
if platform in ["SHEIN","BOTH"]:
    s = shein[(shein["order date"]>=start) & (shein["order date"]<=end)].copy()
    s = s[~s["order status"].str.lower().eq("customer refunded")].copy()
    s["qty"] = 1.0

    # seller sku → SKU-COLOR-SIZE
    def parse_seller_sku(v):
        s = str(v)
        parts = s.split("-")
        if len(parts) >= 3:
            sku = parts[0]
            size = parts[-1]
            color = parts[-2]
            return sku, norm_color(color), norm_size(size)
        return None, None, None

    s["sku"], s["color"], s["size"] = zip(*s.get("seller sku", pd.Series(["--"]*len(s))).map(parse_seller_sku))
    # style 키 추출 (seller sku 우선, 실패 시 product description)
    s["style_key"] = s["sku"].apply(lambda x: style_key_from_label(x, valid_keys))
    mask_missing = s["style_key"].isna()
    if mask_missing.any():
        s.loc[mask_missing, "style_key"] = s.loc[mask_missing, "product description"].apply(lambda x: style_key_from_label(x, valid_keys))
    s = s.dropna(subset=["style_key"])

    # 카테고리
    s["cat"] = s.apply(
        lambda r: map_category(
            LEN_MAP.get(str(r["style_key"]), ""),
            "",
            r.get("product description", "")
        ), axis=1
    )

    rows.append(s[["style_key","color","size","qty","cat"]].assign(platform="SHEIN"))

if not rows:
    st.info("해당 기간/플랫폼에 데이터가 없습니다.")
    st.stop()

data = pd.concat(rows, ignore_index=True)

# 색/사이즈 정리
data["color"] = data["color"].fillna("—")
data["size"]  = data["size"].fillna("—")
data["cat"]   = data["cat"].replace({"OTHER":"PANTS"})  # OTHER 최대한 제거(안전망)

# -------------------------
# 1) 카테고리 도넛 + 요약
# -------------------------
# cat_summary 예시는 다음과 같은 형태라고 가정합니다:
# cat_summary = DataFrame([{"cat":"TOP","qty":413,"sales":...}, ...])
# value_col 은 비율 계산에 쓸 컬럼 (판매수량 기준이면 "qty")
value_col = "qty"

donut_src = cat_summary.copy()
donut_src = donut_src.rename(columns={"cat": "카테고리", value_col: "count"})
total = float(donut_src["count"].sum() or 1.0)
donut_src["pct"] = (donut_src["count"] / total * 100).round(1)
donut_src["label"] = donut_src["카테고리"] + " " + donut_src["pct"].astype(str) + "%"

# 도넛(링) 본체
base = alt.Chart(donut_src).encode(
    theta=alt.Theta("count:Q", stack=True),
    # 색상 범례는 흑백 프린트에선 큰 의미가 없으니 숨겨도 됩니다 (legend=None)
    color=alt.Color("카테고리:N", legend=None)
).properties(width=520, height=380)

ring = base.mark_arc(
    innerRadius=110,        # 도넛 두께 조절
    outerRadius=180,
    stroke="#444",          # 경계선 넣어서 흑백에서도 구분
    strokeWidth=1
)

# 라벨(카테고리명 + %). 작은 조각(3% 미만)은 숨김
labels = base.transform_calculate(
    midAngle="(datum.startAngle + datum.endAngle)/2"
).mark_text(
    radius=145,             # 도넛 안쪽 반지름(라벨 위치)
    size=12,
    fontWeight="bold",
    fill="#000"
).encode(
    theta="midAngle:Q",
    text="label:N",
    opacity=alt.condition(alt.datum.pct >= 3, alt.value(1), alt.value(0))
)

st.altair_chart(ring + labels, use_container_width=True)

# -------------------------
# 2) 옵션 Top (색상/사이즈)
# -------------------------
st.subheader("🎨 옵션 요약 (색상/사이즈 Top)")
c1, c2 = st.columns(2)

# 색상 Top N
topN = 12
color_grp = data.groupby("color").agg(qty=("qty","sum")).reset_index()
color_grp = color_grp[color_grp["color"]!="—"].sort_values("qty", ascending=False).head(topN)

with c1:
    bar_color = alt.Chart(color_grp).mark_bar().encode(
        x=alt.X("qty:Q", title="판매수량"),
        y=alt.Y("color:N", sort="-x", title="색상"),
        tooltip=[alt.Tooltip("color:N", title="색상"),
                 alt.Tooltip("qty:Q", title="판매수량", format=",.0f")]
    ).properties(height=420)
    st.altair_chart(bar_color, use_container_width=True)

# 사이즈 Top N
size_grp = data.groupby("size").agg(qty=("qty","sum")).reset_index()
size_grp = size_grp[size_grp["size"]!="—"].sort_values("qty", ascending=False).head(topN)

with c2:
    bar_size = alt.Chart(size_grp).mark_bar().encode(
        x=alt.X("qty:Q", title="판매수량"),
        y=alt.Y("size:N", sort="-x", title="사이즈"),
        tooltip=[alt.Tooltip("size:N", title="사이즈"),
                 alt.Tooltip("qty:Q", title="판매수량", format=",.0f")]
    ).properties(height=420)
    st.altair_chart(bar_size, use_container_width=True)

st.caption("· 도넛은 판매수량 기준 비율입니다. (색상/사이즈는 Top 12 기준)")
