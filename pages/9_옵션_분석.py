# ==========================================
# File: pages/9_옵션_분석.py
# (처음 버전: 심플 도넛 + 카테고리 요약 + 옵션 요약)
# ==========================================
import streamlit as st
import pandas as pd
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
    with open("/tmp/service_account.json","w") as f:
        import json as _json
        _json.dump(creds_json, f)
    creds = ServiceAccountCredentials.from_json_keyfile_name("/tmp/service_account.json", scope)
    client = gspread.authorize(creds)
    ws = client.open_by_url(GOOGLE_SHEET_URL).worksheet(sheet_name)
    df = pd.DataFrame(ws.get_all_records())
    df.columns = [c.lower().strip() for c in df.columns]
    return df

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

STYLE_RE = re.compile(r"\b([A-Z]{1,3}\d{3,5}[A-Z0-9]?)\b")

def style_key_from_label(label: str) -> str | None:
    s = str(label).strip().upper()
    if not s:
        return None
    s_key = s.replace(" ", "")
    m = STYLE_RE.search(s)
    if m:
        return m.group(1).replace(" ", "")
    return None

# 색상/사이즈 정규화
def norm_color(s: str) -> str:
    t = str(s).strip().replace("_", " ").upper()
    return t

SIZE_MAP = {
    "SMALL":"S","MEDIUM":"M","LARGE":"L",
    "1XL":"1X","2XL":"2X","3XL":"3X",
    "XS":"XS","S":"S","M":"M","L":"L","XL":"XL","XXL":"2X","XXXL":"3X"
}
def norm_size(s: str) -> str:
    t = str(s).strip().upper().replace(" ", "")
    return SIZE_MAP.get(t, t)

# LENGTH → 카테고리 매핑
TOPS   = {"CROP TOP","WAIST TOP","LONG TOP"}
DRESS  = {"MINI DRESS","MIDI DRESS","MAXI DRESS"}
SKIRT  = {"MINI SKIRT","MIDI SKIRT","MAXI SKIRT"}
PANTS  = {"SHORTS","KNEE","CAPRI","FULL"}  # 팬츠 길이 표현

def map_length_to_cat(length: str) -> str | None:
    vals = [v.strip().upper() for v in str(length).split(",") if v.strip()]
    if not vals:
        return None
    cats = set()
    for v in vals:
        if v in TOPS: cats.add("TOP")
        elif v in DRESS: cats.add("DRESS")
        elif v in SKIRT: cats.add("SKIRT")
        elif v in PANTS: cats.add("PANTS")
    if len(cats) >= 2:
        return "SET"
    if cats:
        return list(cats)[0]
    return None

# -------------------------
# Load
# -------------------------
info  = load_google_sheet("PRODUCT_INFO")
temu  = load_google_sheet("TEMU_SALES")
shein = load_google_sheet("SHEIN_SALES")

# 공통 정규화
temu["order date"]  = temu["purchase date"].apply(parse_temudate)
shein["order date"] = shein["order processed on"].apply(parse_sheindate)

temu["order item status"] = temu["order item status"].astype(str)
temu["quantity shipped"]  = pd.to_numeric(temu.get("quantity shipped", 0), errors="coerce").fillna(0)

shein["order status"] = shein["order status"].astype(str)

# product number → length map
info_keys = info.get("product number", pd.Series(dtype=str)).astype(str).str.upper().str.replace(" ","", regex=False)
length_map = dict(zip(info_keys, info.get("length","")))

# -------------------------
# Controls
# -------------------------
min_dt = pd.to_datetime(pd.concat([temu["order date"], shein["order date"]]).dropna()).min()
max_dt = pd.to_datetime(pd.concat([temu["order date"], shein["order date"]]).dropna()).max()

a,b = st.columns([1.3,1])
with a:
    dr = st.date_input(
        "조회 기간",
        value=(max_dt.date()-pd.Timedelta(days=29), max_dt.date()),
        min_value=min_dt.date(),
        max_value=max_dt.date(),
    )
    if isinstance(dr,(list,tuple)):
        start, end = dr
    else:
        start, end = dr, dr
    start = pd.to_datetime(start); end = pd.to_datetime(end) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
with b:
    platform = st.radio("플랫폼", ["BOTH","TEMU","SHEIN"], horizontal=True)

# -------------------------
# Build dataset (qty 기반)
# -------------------------
rows = []

# TEMU
if platform in ["BOTH","TEMU"]:
    t = temu[(temu["order date"]>=start)&(temu["order date"]<=end)].copy()
    t = t[t["order item status"].str.lower().isin(["shipped","delivered"])]
    for _,r in t.iterrows():
        qty = float(r.get("quantity shipped",0))
        if qty<=0: 
            continue
        # 카테고리: 우선 텍스트(ROMPER/JUMPSUIT) → 없으면 PRODUCT_INFO length
        pn  = str(r.get("product number","")).upper().replace(" ","")
        txt = str(r.get("product name by customer order","")).upper()
        if "ROMPER" in txt:
            cat = "ROMPER"
        elif "JUMPSUIT" in txt:
            cat = "JUMPSUIT"
        else:
            cat = map_length_to_cat(length_map.get(pn, ""))
            if not cat: 
                continue
        rows.append({"platform":"TEMU","cat":cat,"qty":qty,
                     "color":norm_color(r.get("color","")),
                     "size":norm_size(r.get("size",""))})

# SHEIN
if platform in ["BOTH","SHEIN"]:
    s = shein[(shein["order date"]>=start)&(shein["order date"]<=end)].copy()
    s = s[~s["order status"].str.lower().eq("customer refunded")]
    for _,r in s.iterrows():
        qty = 1.0
        desc = str(r.get("product description",""))
        up   = desc.upper()
        if "ROMPER" in up:
            cat = "ROMPER"
        elif "JUMPSUIT" in up:
            cat = "JUMPSUIT"
        else:
            sk = style_key_from_label(desc)
            cat = map_length_to_cat(length_map.get((sk or ""), ""))
            if not cat:
                continue
        # 색상/사이즈: SELLER SKU = SKU-COLOR-SIZE
        seller = str(r.get("seller sku",""))
        parts  = seller.split("-")
        cval   = norm_color(parts[-2]) if len(parts)>=3 else ""
        sval   = norm_size(parts[-1])  if len(parts)>=2 else ""
        rows.append({"platform":"SHEIN","cat":cat,"qty":qty,"color":cval,"size":sval})

df = pd.DataFrame(rows)
if df.empty:
    st.info("표시할 데이터가 없습니다.")
    st.stop()

# -------------------------
# Category summary (qty 비율)
# -------------------------
cat_sum = (df.groupby(["platform","cat"])["qty"].sum()
           .reset_index().rename(columns={"qty":"sold_qty"}))

def make_donut(_df):
    # 카테고리 비율 계산
    tot = _df["sold_qty"].sum()
    _df = _df.sort_values("sold_qty", ascending=False).copy()
    _df["비율(%)"] = (_df["sold_qty"]/tot*100).round(1)
    return _df, tot

# 플랫폼 선택
if platform == "BOTH":
    # 전체 합산
    cat_all = df.groupby("cat")["qty"].sum().reset_index().rename(columns={"qty":"sold_qty"})
    donut_src, tot_qty = make_donut(cat_all)
else:
    donut_src, tot_qty = make_donut(cat_sum[cat_sum["platform"].eq(platform)][["cat","sold_qty"]])

# -------------------------
# Layout: 도넛(왼쪽) + 요약표(오른쪽)
# -------------------------
st.subheader("📊 카테고리별 판매 비율 (도넛)")
cL, cR = st.columns([1.2,1])

with cL:
    donut = alt.Chart(donut_src).mark_arc(innerRadius=90, outerRadius=150).encode(
        theta=alt.Theta("sold_qty:Q", stack=True),
        color=alt.Color("cat:N", title="카테고리"),
        tooltip=[alt.Tooltip("cat:N", title="카테고리"),
                 alt.Tooltip("sold_qty:Q", title="판매수량"),
                 alt.Tooltip("비율(%):Q")]
    ).properties(height=380)
    st.altair_chart(donut, use_container_width=True)

with cR:
    st.subheader("📁 카테고리 요약")
    show = donut_src.rename(columns={"cat":"카테고리","sold_qty":"판매수량"})
    st.dataframe(show, hide_index=True, use_container_width=True)

# -------------------------
# 옵션 요약 (색상/사이즈 Top)
# -------------------------
st.subheader("🎨 옵션 요약 (색상/사이즈 Top)")
# 색상 Top 12
col_cnt = (df.groupby("color")["qty"].sum().sort_values(ascending=False)
           .reset_index().rename(columns={"color":"색상","qty":"판매수량"})).head(12)
# 사이즈 Top 10
size_cnt = (df.groupby("size")["qty"].sum().sort_values(ascending=False)
            .reset_index().rename(columns={"size":"사이즈","qty":"판매수량"})).head(10)

b1, b2 = st.columns(2)
with b1:
    if not col_cnt.empty:
        cbar = alt.Chart(col_cnt).mark_bar().encode(
            x=alt.X("판매수량:Q", title="판매수량"),
            y=alt.Y("색상:N", sort="-x", title=None),
            tooltip=["색상","판매수량"]
        ).properties(height=320)
        st.altair_chart(cbar, use_container_width=True)
    else:
        st.info("색상 데이터가 없습니다.")
with b2:
    if not size_cnt.empty:
        sbar = alt.Chart(size_cnt).mark_bar().encode(
            x=alt.X("판매수량:Q", title="판매수량"),
            y=alt.Y("사이즈:N", sort="-x", title=None),
            tooltip=["사이즈","판매수량"]
        ).properties(height=320)
        st.altair_chart(sbar, use_container_width=True)
    else:
        st.info("사이즈 데이터가 없습니다.")

st.caption("· 도넛은 판매수량 기준 비율입니다. (색상/사이즈는 Top N)")
