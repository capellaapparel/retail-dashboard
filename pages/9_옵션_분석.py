# ==========================================
# File: pages/9_옵션_분석.py
# 옵션 · 카테고리 분석 (도넛 + 리더라인, 요약표, 색상/사이즈 Top)
# ==========================================
import math
import re
import numpy as np
import pandas as pd
import streamlit as st
import altair as alt
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

def parse_temudate(x):
    s = str(x)
    if "(" in s: s = s.split("(")[0].strip()
    try: return parser.parse(s, fuzzy=True)
    except Exception: return pd.NaT

def parse_sheindate(x):
    try: return pd.to_datetime(str(x), errors="coerce", infer_datetime_format=True)
    except Exception: return pd.NaT

def clean_money(s: pd.Series) -> pd.Series:
    return (s.astype(str).str.replace(r"[^0-9.\-]", "", regex=True)
            .replace("", pd.NA).astype(float)).fillna(0.0)

# -------------------------
# Load
# -------------------------
info  = load_google_sheet("PRODUCT_INFO")
temu  = load_google_sheet("TEMU_SALES")
shein = load_google_sheet("SHEIN_SALES")

# Dates
temu["order date"]  = temu["purchase date"].apply(parse_temudate)
shein["order date"] = shein["order processed on"].apply(parse_sheindate)

# Status & numeric
temu["order item status"] = temu["order item status"].astype(str)
temu["quantity shipped"]  = pd.to_numeric(temu.get("quantity shipped", 0), errors="coerce").fillna(0)
temu["base price total"]  = clean_money(temu.get("base price total", pd.Series(dtype=str)))

shein["order status"]   = shein["order status"].astype(str)
shein["product price"]  = clean_money(shein.get("product price", pd.Series(dtype=str)))
shein["seller sku"]     = shein.get("seller sku", "")

# -------------------------
# Controls
# -------------------------
min_dt = pd.to_datetime(pd.concat([temu["order date"], shein["order date"]]).dropna()).min()
max_dt = pd.to_datetime(pd.concat([temu["order date"], shein["order date"]]).dropna()).max()

c1, c2 = st.columns([1.2, 1])
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
    start = pd.to_datetime(start)
    end   = pd.to_datetime(end) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
with c2:
    platform = st.radio("플랫폼", ["BOTH","TEMU","SHEIN"], horizontal=True, index=0)

# -------------------------
# 판매 데이터 필터 (기간/상태)
# -------------------------
T = temu[(temu["order date"]>=start)&(temu["order date"]<=end)].copy()
T = T[T["order item status"].str.lower().isin(["shipped","delivered"])]
S = shein[(shein["order date"]>=start)&(shein["order date"]<=end)].copy()
S = S[~S["order status"].str.lower().isin(["customer refunded"])]

if platform == "TEMU":
    S = S.iloc[0:0]   # empty
elif platform == "SHEIN":
    T = T.iloc[0:0]

# -------------------------
# 카테고리 분류 로직
# -------------------------
def normalize_length_to_cat(length: str) -> str:
    s = (str(length) or "").upper()
    if not s or s == "NAN":
        return "OTHER"

    # 세트: 길이 문자열에 콤마가 있으면 (예: "CROP TOP, MINI SKIRT")
    if "," in s:
        return "SET"

    # TOP
    if "CROP TOP" in s or "WAIST TOP" in s or "LONG TOP" in s or s.strip() == "TOP":
        return "TOP"

    # DRESS
    if "DRESS" in s:
        return "DRESS"

    # SKIRT
    if "SKIRT" in s:
        return "SKIRT"

    # PANTS
    if "PANTS" in s or "PANT" in s:
        return "PANTS"

    return "OTHER"

# TEMU 상품명에서 ROMPER/JUMPSUIT 캐치
def detect_temuname_cat(series: pd.Series) -> str|None:
    name = str(series).upper()
    if "ROMPER" in name: return "ROMPER"
    if "JUMPSUIT" in name: return "JUMPSUIT"
    return None

# style 기준으로 LENGTH기반 카테고리 매핑
info_key = info.copy()
info_key["style_key"] = info_key.get("product number","").astype(str).str.upper().str.replace(" ","", regex=False)
info_key["base_cat"]  = info_key["length"].apply(normalize_length_to_cat)

# TEMU: 스타일별 이름 탐색해서 ROMPER/JUMPSUIT 보정
temu_names = (T[["product number","product name by customer order"]]
                .dropna()
                .assign(style_key=lambda d: d["product number"].astype(str).str.upper().str.replace(" ","", regex=False)))
temu_names["name_cat"] = temu_names["product name by customer order"].apply(detect_temuname_cat)
temu_name_cat = temu_names.dropna(subset=["name_cat"]).drop_duplicates("style_key")[["style_key","name_cat"]]

# 최종 카테고리 테이블
cat_map = info_key[["style_key","base_cat"]].merge(temu_name_cat, on="style_key", how="left")
cat_map["cat"] = cat_map["name_cat"].fillna(cat_map["base_cat"]).fillna("OTHER")
cat_map = cat_map[["style_key","cat"]].drop_duplicates("style_key")

# -------------------------
# 스타일키 매핑 (TEMU / SHEIN 각자)
# -------------------------
T["style_key"] = T["product number"].astype(str).str.upper().str.replace(" ","", regex=False)
S["style_key"] = S.get("product description","").astype(str).str.extract(r"([A-Z]{1,3}\d{3,5}[A-Z0-9]?)")[0].str.upper().fillna("")

# 판매량/매출
T["qty"]   = pd.to_numeric(T["quantity shipped"], errors="coerce").fillna(0)
T["sales"] = pd.to_numeric(T["base price total"], errors="coerce").fillna(0.0)
S["qty"]   = 1.0
S["sales"] = pd.to_numeric(S["product price"], errors="coerce").fillna(0.0)

sold = pd.concat([T[["style_key","qty","sales"]], S[["style_key","qty","sales"]]], ignore_index=True)
sold = sold.merge(cat_map, on="style_key", how="left")
sold["cat"] = sold["cat"].fillna("OTHER")

# 카테고리 요약
cat_summary = (sold.groupby("cat", as_index=False)
                    .agg(qty=("qty","sum"), sales=("sales","sum"))
                    .sort_values("qty", ascending=False))
total_qty = cat_summary["qty"].sum()
if total_qty > 0:
    cat_summary["pct"] = (cat_summary["qty"] / total_qty * 100).round(1)
else:
    cat_summary["pct"] = 0.0

# -------------------------
# 도넛 + 리더라인 레이블 (좌) / 표(우)
# -------------------------
st.markdown("### 📊 카테고리별 판매 비율 (도넛)")

# 도넛
donut = alt.Chart(cat_summary).mark_arc(innerRadius=70, outerRadius=120).encode(
    theta=alt.Theta("qty:Q", stack=True),
    color=alt.Color("cat:N", title="카테고리"),
    tooltip=[alt.Tooltip("cat:N", title="카테고리"),
             alt.Tooltip("qty:Q", title="판매수량", format=",.0f"),
             alt.Tooltip("pct:Q", title="비율(%)")]
).properties(height=420)

# 파이 조각 각도 기반 리더라인 좌표 계산 (파이썬으로 계산)
def build_leaderlines(df: pd.DataFrame, r0=120, r1=160):
    if df.empty: 
        return pd.DataFrame(columns=["cat","x0","y0","x1","y1","tx","ty","label"])
    d = df.copy()
    d["frac"] = d["qty"] / d["qty"].sum() if d["qty"].sum() > 0 else 0
    d["cum"]  = d["frac"].cumsum()
    d["cum0"] = d["cum"] - d["frac"]
    d["ang"]  = (d["cum0"] + d["frac"]/2.0) * 2*math.pi

    d["x0"] = r0 * np.cos(d["ang"])
    d["y0"] = r0 * np.sin(d["ang"])
    d["x1"] = r1 * np.cos(d["ang"])
    d["y1"] = r1 * np.sin(d["ang"])

    # 텍스트 위치는 끝점에서 조금 더 밀어내고 (좌우에 따라 dx만 바꿈)
    d["tx"] = (r1 + 2) * np.cos(d["ang"])
    d["ty"] = (r1 + 2) * np.sin(d["ang"])

    d["label"] = d.apply(lambda r: f"{r['cat']} ({r['pct']}%)", axis=1)
    # 좌우 카테고리별로 dx 부호 반대로(Altair에선 xOffset 사용)
    d["dx"] = d["tx"].apply(lambda v: 6 if v>=0 else -6)
    return d[["cat","x0","y0","x1","y1","tx","ty","dx","label"]]

ann = build_leaderlines(cat_summary)

# 리더라인: rule (x0,y0) -> (x1,y1)
lines = alt.Chart(ann).mark_rule(color="#666").encode(
    x=alt.X("x0:Q", scale=alt.Scale(domain=[-200,200]), axis=None),
    y=alt.Y("y0:Q", scale=alt.Scale(domain=[-200,200]), axis=None),
    x2="x1:Q",
    y2="y1:Q",
)

# 텍스트 라벨 (xOffset으로 좌우 보정)
labels = alt.Chart(ann).mark_text(fontSize=12, fontWeight="bold").encode(
    x=alt.X("tx:Q", scale=alt.Scale(domain=[-200,200]), axis=None),
    y=alt.Y("ty:Q", scale=alt.Scale(domain=[-200,200]), axis=None),
    text="label:N",
    dx="dx:Q"
)

left, right = st.columns([1.1, 1])
with left:
    st.altair_chart(donut + lines + labels, use_container_width=True, theme=None)
with right:
    st.markdown("### 🗂️ 카테고리 요약")
    st.dataframe(
        cat_summary[["cat","qty","pct","sales"]]
        .rename(columns={"cat":"카테고리","qty":"판매수량","pct":"비율(%)","sales":"매출"}),
        use_container_width=True, hide_index=True
    )

# -------------------------
# 옵션 요약 (색상/사이즈 Top)
# -------------------------
st.markdown("### 🎨 옵션 요약 (색상/사이즈 Top)")

# 색상 & 사이즈 추출
def norm_size(x: str) -> str:
    s = str(x).upper().strip()
    if s in ["1XL","1X"]: return "1X"
    if s in ["2XL","2X"]: return "2X"
    if s in ["3XL","3X"]: return "3X"
    if s in ["SMALL","S"]: return "S"
    if s in ["MEDIUM","M"]: return "M"
    if s in ["LARGE","L"]: return "L"
    return s or ""

def from_shein_sku_color(sku: str) -> str:
    s = str(sku)
    parts = re.split(r"[-/]", s)
    if len(parts) >= 2:
        col = parts[1].replace("_"," ").strip()
        return col.upper()
    return ""

def from_shein_sku_size(sku: str) -> str:
    s = str(sku)
    parts = re.split(r"[-/]", s)
    if len(parts) >= 3:
        return norm_size(parts[2])
    return ""

# TEMU color/size
temu_colors = T.get("color","").astype(str).str.upper().replace("NAN","")
temu_sizes  = T.get("size","").astype(str).apply(norm_size)

# SHEIN color/size from seller sku
shein_colors = S["seller sku"].apply(from_shein_sku_color)
shein_sizes  = S["seller sku"].apply(from_shein_sku_size)

opt = pd.DataFrame({
    "color": pd.concat([temu_colors, shein_colors], ignore_index=True),
    "size":  pd.concat([temu_sizes,  shein_sizes],  ignore_index=True),
    "qty":   1.0
})
opt = opt.replace("","NaN").query('color!="NaN" or size!="NaN"')

# Top 색상
top_color = (opt.groupby("color", as_index=False)["qty"].sum()
               .sort_values("qty", ascending=False).head(12))
# Top 사이즈
top_size  = (opt[opt["size"]!="NaN"].groupby("size", as_index=False)["qty"].sum()
               .sort_values("qty", ascending=False))

c1, c2 = st.columns(2)
with c1:
    st.altair_chart(
        alt.Chart(top_color).mark_bar().encode(
            x=alt.X("qty:Q", title="판매수량"),
            y=alt.Y("color:N", sort="-x", title="색상"),
            tooltip=["color","qty"]
        ).properties(height=340),
        use_container_width=True
    )
with c2:
    st.altair_chart(
        alt.Chart(top_size).mark_bar().encode(
            x=alt.X("qty:Q", title="판매수량"),
            y=alt.Y("size:N", sort="-x", title="사이즈"),
            tooltip=["size","qty"]
        ).properties(height=340),
        use_container_width=True
    )

st.caption("※ 도넛은 판매수량 기준 비율입니다. (오른쪽 표의 '판매수량/비율/매출'과 함께 해석하세요.)")
