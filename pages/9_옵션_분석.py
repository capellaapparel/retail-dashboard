# ==========================================
# File: pages/9_옵션_분석.py
# (Altair만 사용 · 도넛 위에 카테고리 텍스트 표기)
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
    with open("/tmp/service_account.json","w") as f: json.dump(creds_json, f)
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

def normalize_size(x: str) -> str:
    s = str(x).strip().upper().replace(" ", "")
    mapping = {
        "1XL": "1X", "2XL": "2X", "3XL": "3X",
        "SMALL":"S", "MEDIUM":"M", "LARGE":"L"
    }
    return mapping.get(s, s)

def parse_shein_sku(sku: str):
    """
    SHEIN 'seller sku' 예) ABC123-HEATHER_GREY-1X
    색상은 _ 를 공백으로 바꿔 표기
    """
    s = str(sku)
    if "-" not in s:
        return None, None, None
    parts = s.split("-")
    if len(parts) < 3:
        return None, None, None
    style = parts[0]
    color = parts[1].replace("_", " ").title()
    size  = normalize_size(parts[2])
    return style, color, size

# 카테고리 판정 로직
TOP_TOKENS   = {"CROP TOP", "WAIST TOP", "LONG TOP"}
DRESS_TOKENS = {"MINI DRESS","MIDI DRESS","MAXI DRESS"}
SKIRT_TOKENS = {"MINI SKIRT","MIDI SKIRT","MAXI SKIRT"}

def infer_category(length_str: str, temu_name: str) -> str:
    name = str(temu_name).upper()
    if "ROMPER" in name:    return "ROMPER"
    if "JUMPSUIT" in name:  return "JUMPSUIT"

    tokens = [t.strip().upper() for t in str(length_str).split(",") if t.strip()]
    has_top   = any(t in TOP_TOKENS   for t in tokens)
    has_dress = any(t in DRESS_TOKENS for t in tokens)
    has_skirt = any(t in SKIRT_TOKENS for t in tokens)

    # 세트: TOP + (SKIRT 또는 PANTS류) 조합
    if has_top and (has_skirt or ("PANTS" in str(length_str).upper())):
        return "SET"
    if has_top:   return "TOP"
    if has_dress: return "DRESS"
    if has_skirt: return "SKIRT"
    # 기본값은 PANTS (OTHER 제거 요청 반영)
    return "PANTS"

# -------------------------
# Load
# -------------------------
info  = load_google_sheet("PRODUCT_INFO")
temu  = load_google_sheet("TEMU_SALES")
shein = load_google_sheet("SHEIN_SALES")

IMG_MAP = dict(zip(
    info.get("product number", pd.Series(dtype=str)).astype(str).str.upper().str.replace(" ", "", regex=False),
    info.get("image","")
))

temu["order date"]  = temu["purchase date"].apply(parse_temudate)
shein["order date"] = shein["order processed on"].apply(parse_sheindate)

# 날짜 컨트롤
min_dt = pd.to_datetime(pd.concat([temu["order date"], shein["order date"]]).dropna()).min()
max_dt = pd.to_datetime(pd.concat([temu["order date"], shein["order date"]]).dropna()).max()

left, right = st.columns([1.3, 1])
with left:
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
with right:
    platform = st.radio("플랫폼", ["BOTH","TEMU","SHEIN"], horizontal=True)

# -------------------------
# 판매 데이터(색상·사이즈 포함) 구축
# -------------------------
# TEMU: shipped/delivered & qty 사용
t = temu[(temu["order date"]>=start) & (temu["order date"]<=end)]
t = t[t["order item status"].astype(str).str.lower().isin(["shipped","delivered"])].copy()
t["qty"]   = pd.to_numeric(t.get("quantity shipped", 0), errors="coerce").fillna(0)
t["style"] = t["product number"].astype(str)
t["color"] = t.get("color", "")
t["size"]  = t.get("size", "")

# SHEIN: refunded 제외, 주문 한 건 = 1 qty
s = shein[(shein["order date"]>=start) & (shein["order date"]<=end)]
s = s[~s["order status"].astype(str).str.lower().eq("customer refunded")].copy()
style_, color_, size_ = [], [], []
for sku in s.get("seller sku", pd.Series([""]*len(s))):
    sty, col, siz = parse_shein_sku(sku)
    style_.append(sty); color_.append(col); size_.append(siz)
s["style"] = style_
s["color"] = color_
s["size"]  = size_
s["qty"]   = 1.0

if platform == "TEMU":
    sold = t.copy()
elif platform == "SHEIN":
    sold = s.copy()
else:
    sold = pd.concat([t, s], ignore_index=True)

# 사이즈 표준화
sold["size"] = sold["size"].apply(normalize_size)

# -------------------------
# 카테고리 매핑 (스타일별)
# -------------------------
# TEMU 상품명 텍스트 확보해 카테고리 보정에 사용
temu_name_by_style = (
    temu.groupby(temu["product number"].astype(str))["product name by customer order"]
        .agg(lambda x: next((v for v in x if str(v).strip()), ""))
        .to_dict()
)

cat_map = {}
for _, r in info.iterrows():
    key = str(r.get("product number", "")).upper().replace(" ", "")
    length_str = str(r.get("length",""))
    temu_name = temu_name_by_style.get(str(r.get("product number","")), "")
    cat_map[key] = infer_category(length_str, temu_name)

# sold에 카테고리 부여
def stykey(x: str) -> str:
    return str(x).upper().replace(" ", "")

sold["style_key"] = sold["style"].astype(str).apply(stykey)
sold["cat"] = sold["style_key"].map(cat_map).fillna("PANTS")

# -------------------------
# 1) 도넛: 카테고리별 판매 비율 (흑백 출력 대비 라벨 직접 표기)
# -------------------------
cat_summary = (sold.groupby("cat")["qty"].sum().reset_index()
                    .rename(columns={"qty":"cnt"})
               )
if cat_summary["cnt"].sum() == 0:
    st.info("해당 기간에 판매 데이터가 없습니다.")
    st.stop()

cat_summary["pct"] = cat_summary["cnt"] / cat_summary["cnt"].sum()
cat_summary = cat_summary.sort_values("cnt", ascending=False)

# Altair 도넛
arc = alt.Chart(cat_summary).mark_arc(innerRadius=90, outerRadius=160).encode(
    theta=alt.Theta("cnt:Q", stack=True),
    color=alt.Color("cat:N", legend=None),  # 프린트(흑백)용으로 범례 숨김
    order=alt.Order("cnt:Q", sort="descending")
)

# 라벨(카테고리명 + %). 흑백 프린트 대비 검은 글씨로 크게
cat_summary["label"] = cat_summary.apply(
    lambda r: f"{r['cat']} ({r['pct']*100:.1f}%)", axis=1
)
labels = alt.Chart(cat_summary).mark_text(radius=190, size=14, color="black").encode(
    theta=alt.Theta("cnt:Q", stack=True),
    text="label:N",
    order=alt.Order("cnt:Q", sort="descending")
)

left_block = st.container()
with left_block:
    st.markdown("### 📊 카테고리별 판매 비율 (도넛)")
    st.altair_chart((arc + labels).properties(height=420), use_container_width=True)

# 오른쪽에 간단 요약 테이블
right_block = st.container()
with right_block:
    st.markdown("### 🗂️ 카테고리 요약")
    show = cat_summary[["cat","cnt","pct"]].copy()
    show["비율(%)"] = (show["pct"]*100).round(1)
    show = show.drop(columns=["pct"]).rename(columns={"cat":"카테고리","cnt":"판매수량"})
    st.dataframe(show, use_container_width=True, hide_index=True)

st.markdown("---")

# -------------------------
# 2) 옵션 요약 (색상 Top, 사이즈 Top) — 처음 스타일 느낌으로 단순히 Top만
# -------------------------
st.subheader("🎨 옵션 요약 (색상/사이즈 Top)")

colA, colB = st.columns(2)

# 색상 Top
with colA:
    color_top = (sold.dropna(subset=["color"])
                     .groupby("color")["qty"].sum()
                     .sort_values(ascending=False)
                     .head(12).reset_index())
    color_chart = alt.Chart(color_top).mark_bar().encode(
        y=alt.Y("color:N", sort='-x', title="색상"),
        x=alt.X("qty:Q", title="판매수량"),
        tooltip=["color","qty"]
    ).properties(height=360)
    st.altair_chart(color_chart, use_container_width=True)

# 사이즈 Top
with colB:
    size_top = (sold.dropna(subset=["size"])
                    .groupby("size")["qty"].sum()
                    .sort_values(ascending=False)
                    .reset_index())
    size_chart = alt.Chart(size_top).mark_bar().encode(
        y=alt.Y("size:N", sort='-x', title="사이즈"),
        x=alt.X("qty:Q", title="판매수량"),
        tooltip=["size","qty"]
    ).properties(height=360)
    st.altair_chart(size_chart, use_container_width=True)

st.caption("· 도넛은 '판매수량' 기준 비율입니다. (색상/사이즈는 Top만 표시)")
