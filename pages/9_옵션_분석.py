# ==========================================
# File: pages/9_옵션_분석.py
# (도넛 조각 라벨 + 카테고리/컬러/사이즈 분석)
# ==========================================
import streamlit as st
import pandas as pd
import altair as alt
import re
from dateutil import parser

st.set_page_config(page_title="옵션 · 카테고리 분석", layout="wide")
st.title("❎ 옵션 · 카테고리 분석")

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

def money_clean(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series.astype(str).str.replace(r"[^0-9.\-]", "", regex=True), errors="coerce").fillna(0.0)

def build_img_map(info: pd.DataFrame) -> dict:
    keys = info.get("product number", pd.Series(dtype=str)).astype(str).str.upper().str.replace(" ", "", regex=False)
    return dict(zip(keys, info.get("image", "")))

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
    # 느슨한 포함 매칭
    for k in img_map.keys():
        if k in s_key:
            return k
    return None

# -------------------------
# Load
# -------------------------
info  = load_google_sheet("PRODUCT_INFO")
temu  = load_google_sheet("TEMU_SALES")
shein = load_google_sheet("SHEIN_SALES")

IMG_MAP = build_img_map(info)

# normalize dates
temu["order date"]  = temu["purchase date"].apply(parse_temudate)
shein["order date"] = shein["order processed on"].apply(parse_sheindate)

# normalize numerics
temu["order item status"] = temu["order item status"].astype(str)
temu["quantity shipped"]  = pd.to_numeric(temu.get("quantity shipped", 0), errors="coerce").fillna(0)
if "base price total" in temu.columns:
    temu["base price total"] = money_clean(temu["base price total"])

shein["order status"]   = shein["order status"].astype(str)
if "product price" in shein.columns:
    shein["product price"] = money_clean(shein["product price"])

# -------------------------
# Controls
# -------------------------
min_dt = pd.to_datetime(pd.concat([temu["order date"], shein["order date"]]).dropna()).min()
max_dt = pd.to_datetime(pd.concat([temu["order date"], shein["order date"]]).dropna()).max()

cL, cR = st.columns([1.3, 1])
with cL:
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
with cR:
    platform = st.radio("플랫폼", ["BOTH", "TEMU", "SHEIN"], horizontal=True, index=0)

# -------------------------
# Style → Category mapping
# LENGTH 값을 이용한 1차 분류 + TEMU 상품명에서 JUMPSUIT/ROMPER 보정
# SET 규칙: LENGTH에 TOP + (SKIRT or PANTS) 조합이거나 항목 2개 이상이면 SET
# -------------------------
TOP_KEYS   = {"CROP TOP","WAIST TOP","LONG TOP"}
DRESS_KEYS = {"MINI DRESS","MIDI DRESS","MAXI DRESS"}
SKIRT_KEYS = {"MINI SKIRT","MIDI SKIRT","MAXI SKIRT"}
# 바텀 길이 키워드(팬츠/점프/롬퍼 길이로 공용)
BOTTOM_KEYS = {"SHORTS","KNEE","CAPRI","FULL"}

def normalize_length_tokens(s):
    toks = []
    for p in re.split(r"[;,/]|(?<!\w)\s{2,}", str(s).upper()):
        p = p.strip()
        if not p:
            continue
        toks.append(p)
    # 콤마 기반 분리도 추가
    if len(toks) == 1 and "," in str(s):
        toks = [x.strip().upper() for x in str(s).split(",")]
    return [t for t in toks if t]

# TEMU 상품명(주문기준)에서 점프/롬퍼 힌트
temu_title_map = {}
if "product name by customer order" in temu.columns:
    tmap = temu.groupby(temu["product number"].astype(str))["product name by customer order"] \
               .agg(lambda x: " ".join([str(v) for v in x if pd.notna(v)])[:300]) \
               .to_dict()
    # 키 표준화
    temu_title_map = {str(k).upper().replace(" ",""): str(v).upper() for k,v in tmap.items()}

def infer_category(style_key: str, length_val: str) -> str:
    # 1) length 기반
    toks = set(normalize_length_tokens(length_val))
    has_top   = len(TOP_KEYS & toks)   > 0
    has_dress = len(DRESS_KEYS & toks) > 0
    has_skirt = len(SKIRT_KEYS & toks) > 0
    has_bottom_len = len(BOTTOM_KEYS & toks) > 0

    # SET: (TOP + (SKIRT 또는 바텀)) 이거나 토큰 2개 이상
    if has_top and (has_skirt or has_bottom_len) or len(toks) >= 2:
        return "SET"

    if has_dress:
        return "DRESS"
    if has_skirt:
        return "SKIRT"
    if has_top:
        return "TOP"

    # 바텀 길이인데 점프/롬퍼인지 판정
    if has_bottom_len:
        # TEMU 상품명에서 보정
        title = temu_title_map.get(style_key, "")
        if "ROMPER" in title:
            return "ROMPER"
        if "JUMPSUIT" in title:
            return "JUMPSUIT"
        return "PANTS"

    # 기본은 OTHER → 집계에선 거의 없도록
    return "PANTS"

# style → category dict
style_to_cat = {}
info_keys = info.get("product number", pd.Series(dtype=str)).astype(str).str.upper().str.replace(" ","",regex=False)
for style_key, length_val in zip(info_keys, info.get("length","")):
    style_to_cat[style_key] = infer_category(style_key, length_val)

# -------------------------
# 판매 행 만들기 (플랫폼/기간/상태 필터)
# 컬러/사이즈 정규화
# -------------------------
SIZE_MAP = {
    "SMALL":"S", "MEDIUM":"M", "LARGE":"L",
    "1XL":"1X", "2XL":"2X", "3XL":"3X",
}
def norm_size(s):
    t = str(s).upper().strip()
    t = t.replace(" ", "")
    t = SIZE_MAP.get(t, t)
    if t in {"1XL","2XL","3XL"}:
        t = t.replace("XL","X")
    return t

def norm_color(s):
    t = str(s).strip().replace("_"," ").title()
    return t

rows = []

# TEMU
if platform in ["BOTH","TEMU"]:
    t = temu[(temu["order date"]>=start) & (temu["order date"]<=end)].copy()
    t = t[t["order item status"].str.lower().isin(["shipped","delivered"])]
    t["qty"] = t["quantity shipped"].fillna(0)
    t["style_key"] = t["product number"].astype(str).str.upper().str.replace(" ","",regex=False)

    # 컬러/사이즈 컬럼 명칭 보정 (있을 때만)
    col_color = "color" if "color" in t.columns else None
    col_size  = "size"  if "size"  in t.columns else None
    for _, r in t.iterrows():
        style = r["style_key"]
        cat   = style_to_cat.get(style, "PANTS")
        color = norm_color(r[col_color]) if col_color else ""
        size  = norm_size(r[col_size])   if col_size  else ""
        qty   = float(r["qty"] or 0)
        sales = float(r.get("base price total", 0.0) or 0.0)
        rows.append(("TEMU", style, cat, color, size, qty, sales))

# SHEIN
if platform in ["BOTH","SHEIN"]:
    s = shein[(shein["order date"]>=start) & (shein["order date"]<=end)].copy()
    s = s[~s["order status"].str.lower().eq("customer refunded")]
    s["qty"] = 1.0
    # 스타일 매칭
    s["style_key"] = s["product description"].apply(lambda x: style_key_from_label(x, IMG_MAP))

    # Seller SKU 파싱: SKU-COLOR-SIZE
    seller_col = "seller sku" if "seller sku" in s.columns else None
    def parse_seller(x):
        if pd.isna(x):
            return ("","")
        parts = str(x).split("-")
        if len(parts) >= 3:
            color = norm_color(parts[-2])
            size  = norm_size(parts[-1])
            return (color, size)
        return ("","")

    if seller_col:
        tmp = s[s["style_key"].notna()].copy()
        cs = tmp[seller_col].apply(parse_seller)
        tmp["color"] = [c for c,_ in cs]
        tmp["size"]  = [z for _,z in cs]
    else:
        tmp = s[s["style_key"].notna()].copy()
        tmp["color"] = ""
        tmp["size"]  = ""

    for _, r in tmp.iterrows():
        style = str(r["style_key"])
        cat   = style_to_cat.get(style, "PANTS")
        color = r["color"]
        size  = r["size"]
        qty   = float(r["qty"] or 0)
        sales = float(r.get("product price", 0.0) or 0.0)
        rows.append(("SHEIN", style, cat, color, size, qty, sales))

sold = pd.DataFrame(rows, columns=["platform","style_key","cat","color","size","qty","sales"])

if sold.empty:
    st.info("해당 조건의 판매 데이터가 없습니다.")
    st.stop()

# -------------------------
# 1) 카테고리 요약 (도넛 + 표)
# -------------------------
cat_summary = (sold.groupby("cat")
                   .agg(qty=("qty","sum"), sales=("sales","sum"))
                   .sort_values("qty", ascending=False)
                   .reset_index())

left, right = st.columns([1.1, 1.1])

with left:
    st.markdown("### 📊 카테고리별 판매 비율 (도넛)")

    donut_src = cat_summary.rename(columns={"cat":"카테고리","qty":"count"}).copy()
    total = float(donut_src["count"].sum() or 1.0)
    donut_src["pct"] = (donut_src["count"] / total * 100).round(1)
    donut_src["label"] = donut_src["카테고리"] + " " + donut_src["pct"].astype(str) + "%"

    base = alt.Chart(donut_src).encode(
        theta=alt.Theta("count:Q", stack=True),
        color=alt.Color("카테고리:N", legend=None)
    ).properties(width=520, height=380)

    ring = base.mark_arc(
        innerRadius=110,
        outerRadius=180,
        stroke="#444",
        strokeWidth=1
    )

    labels = base.transform_calculate(
        midAngle="(datum.startAngle + datum.endAngle)/2"
    ).mark_text(
        radius=145,
        size=12,
        fontWeight="bold",
        fill="#000"
    ).encode(
        theta="midAngle:Q",
        text="label:N",
        opacity=alt.condition(alt.datum.pct >= 3, alt.value(1), alt.value(0))
    )

    st.altair_chart(ring + labels, use_container_width=True)

with right:
    st.markdown("### 🧾 카테고리 요약")
    cat_tbl = cat_summary.copy()
    cat_tbl["비율(%)"] = (cat_tbl["qty"] / cat_tbl["qty"].sum() * 100).round(1)
    cat_tbl = cat_tbl.rename(columns={"cat":"카테고리","qty":"판매수량","sales":"매출"})
    st.dataframe(cat_tbl, use_container_width=True, hide_index=True)

# -------------------------
# 2) 옵션 요약 (컬러/사이즈 TOP)
# -------------------------
st.markdown("---")
st.markdown("### 🎨 옵션 요약 (색상/사이즈 Top)")

topN = 12

c1, c2 = st.columns(2)
with c1:
    color_top = (sold.groupby("color")["qty"].sum().sort_values(ascending=False).head(topN)
                    .rename_axis("색상").reset_index(name="판매수량"))
    color_chart = alt.Chart(color_top).mark_bar().encode(
        x=alt.X("판매수량:Q"),
        y=alt.Y("색상:N", sort="-x"),
        tooltip=["색상","판매수량"]
    ).properties(height=320)
    st.altair_chart(color_chart, use_container_width=True)

with c2:
    size_top = (sold.groupby("size")["qty"].sum().sort_values(ascending=False).head(topN)
                   .rename_axis("사이즈").reset_index(name="판매수량"))
    size_chart = alt.Chart(size_top).mark_bar().encode(
        x=alt.X("판매수량:Q"),
        y=alt.Y("사이즈:N", sort="-x"),
        tooltip=["사이즈","판매수량"]
    ).properties(height=320)
    st.altair_chart(size_chart, use_container_width=True)

st.caption("※ 도넛 비율은 판매수량 기준입니다. (색상/사이즈 Top 그래프는 상위 12개)")
