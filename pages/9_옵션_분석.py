# ==========================================
# File: pages/9_옵션_카테고리_분석.py
# 심플 버전: 옵션(색/사이즈) 요약 + 카테고리 도넛(판매 비율)
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
    scope = ["https://spreadsheets.google.com/feeds",
             "https://www.googleapis.com/auth/drive"]
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

# Size/Color normalize (사용자 규칙)
SIZE_MAP = {
    "SMALL": "S", "MEDIUM": "M", "LARGE": "L",
    "1XL": "1X", "2XL": "2X", "3XL": "3X",
}
def norm_size(x: str) -> str:
    s = str(x).strip().upper().replace(" ", "")
    s = SIZE_MAP.get(s, s)
    # XL 그대로, 2X/3X 유지
    return s

def norm_color(x: str) -> str:
    s = str(x).strip()
    if not s:
        return s
    s = s.replace("_", " ").strip()
    # 첫 글자만 대문자 (HEATHER GREY -> Heather grey → 전부 대문자 원하면 .upper())
    return " ".join([t.capitalize() for t in s.split()])

# -------------------------
# Load
# -------------------------
info  = load_google_sheet("PRODUCT_INFO")
temu  = load_google_sheet("TEMU_SALES")
shein = load_google_sheet("SHEIN_SALES")

IMG_MAP = build_img_map(info)

temu["order date"]  = temu["purchase date"].apply(parse_temudate)
shein["order date"] = shein["order processed on"].apply(parse_sheindate)

# numeric
temu["quantity shipped"] = pd.to_numeric(temu.get("quantity shipped", 0), errors="coerce").fillna(0)
temu["order item status"] = temu["order item status"].astype(str)
if "base price total" in temu.columns:
    temu["base price total"] = pd.to_numeric(temu["base price total"].astype(str).str.replace(r"[^0-9.\-]","", regex=True), errors="coerce").fillna(0.0)

shein["order status"] = shein["order status"].astype(str)
if "product price" in shein.columns:
    shein["product price"] = pd.to_numeric(shein["product price"].astype(str).str.replace(r"[^0-9.\-]","", regex=True), errors="coerce").fillna(0.0)

# -------------------------
# Controls
# -------------------------
min_dt = pd.to_datetime(pd.concat([temu["order date"], shein["order date"]]).dropna()).min()
max_dt = pd.to_datetime(pd.concat([temu["order date"], shein["order date"]]).dropna()).max()

if pd.isna(min_dt) or pd.isna(max_dt):
    st.info("날짜 데이터가 없습니다.")
    st.stop()

c1, c2 = st.columns([1.4, 1])
with c1:
    dr = st.date_input(
        "조회 기간",
        value=(max_dt.date() - pd.Timedelta(days=29), max_dt.date()),
        min_value=min_dt.date(), max_value=max_dt.date()
    )
    if isinstance(dr, (list, tuple)):
        start, end = dr
    else:
        start, end = dr, dr
    start = pd.to_datetime(start); end = pd.to_datetime(end) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
with c2:
    platform = st.radio("플랫폼", ["BOTH","TEMU","SHEIN"], horizontal=True, index=0)

# -------------------------
# Category rules
# -------------------------
def cat_from_info_and_text(length_val: str, text: str) -> str:
    """
    length 기준 + 텍스트 힌트로 카테고리 추론
    - length 기반:
      TOP: crop/waist/long top
      DRESS: mini/midi/maxi dress
      SKIRT: mini/midi/maxi skirt
      SET: 'sets (... )' 포함
      PANTS: shorts/knee/capri/full
    - text에서 'ROMPER','JUMPSUIT' 존재 시 각각 ROMPER/JUMPSUIT
    """
    l = str(length_val).strip().lower()
    t = str(text).strip().lower()
    if not l and not t:
        return "OTHER"

    # 세트 우선
    if "sets" in l:
        return "SET"

    # 텍스트로 점프수트/롬퍼 구분
    if "romper" in t:
        return "ROMPER"
    if "jumpsuit" in t:
        return "JUMPSUIT"

    # length 기반
    if any(x in l for x in ["crop top","waist top","long top","top "]):
        return "TOP"
    if "dress" in l:
        return "DRESS"
    if "skirt" in l:
        return "SKIRT"
    if any(x in l for x in ["shorts","knee","capri","full"]):
        return "PANTS"

    # 텍스트에서 보조 판정
    if "dress" in t:
        return "DRESS"
    if "skirt" in t:
        return "SKIRT"
    if any(w in t for w in ["pants","trouser","jeans","shorts","capri","wide leg","cargo"]):
        return "PANTS"
    if "top" in t:
        return "TOP"
    return "OTHER"

# info에서 길이/속성 매핑 용
INFO_COL_LENGTH = info.get("length")
if INFO_COL_LENGTH is None:
    info["length"] = None

# style key 매핑
info["style_key"] = info.get("product number", pd.Series(dtype=str)).astype(str).str.upper().str.replace(" ","", regex=False)
STYLE_TO_LENGTH = dict(zip(info["style_key"], info["length"]))

def length_for_style(style_key: str) -> str:
    return STYLE_TO_LENGTH.get(str(style_key).upper().replace(" ",""), "")

# TEMU rows
T = temu[(temu["order date"]>=start)&(temu["order date"]<=end)
         &(temu["order item status"].str.lower().isin(["shipped","delivered"]))].copy()
T["qty"]   = T["quantity shipped"]
T["sales"] = temu.get("base price total", 0.0)
# 텍스트 컬럼 후보
temu_text = None
for c in ["product name by customer order", "product description", "product title"]:
    if c in T.columns:
        temu_text = c; break
if temu_text is None:
    T["text"] = ""
else:
    T["text"] = T[temu_text].astype(str)

# style key
T["style_key"] = T["product number"].astype(str).apply(lambda x: style_key_from_label(x, IMG_MAP))
T = T.dropna(subset=["style_key"]).copy()

# 색상/사이즈
T["color_norm"] = T.get("color","").apply(norm_color) if "color" in T.columns else ""
T["size_norm"]  = T.get("size","").apply(norm_size) if "size" in T.columns else ""

# 카테고리
T["cat"] = T.apply(lambda r: cat_from_info_and_text(length_for_style(r["style_key"]), r["text"]), axis=1)
T["platform"] = "TEMU"

# SHEIN rows
S = shein[(shein["order date"]>=start)&(shein["order date"]<=end)
          &(~shein["order status"].str.lower().eq("customer refunded"))].copy()
S["qty"]   = 1.0
S["sales"] = shein.get("product price", 0.0)

# 텍스트(설명)
shein_text = None
for c in ["product description","product title"]:
    if c in S.columns:
        shein_text = c; break
if shein_text is None:
    S["text"] = ""
else:
    S["text"] = S[shein_text].astype(str)

# Seller SKU → style, color, size 파싱 (SKU-COLOR-SIZE)
def parse_shein_sku(x: str):
    s = str(x).strip()
    if not s:
        return ("","","")
    parts = s.split("-")
    if len(parts) >= 3:
        style = parts[0]
        color = norm_color(parts[1])
        size  = norm_size(parts[2])
        return (style, color, size)
    return (parts[0], "", "")

if "seller sku" in S.columns:
    parsed = S["seller sku"].apply(parse_shein_sku)
    S["sku_style"] = parsed.apply(lambda x: x[0])
    S["color_norm"] = parsed.apply(lambda x: x[1])
    S["size_norm"]  = parsed.apply(lambda x: x[2])
else:
    S["sku_style"] = ""
    S["color_norm"] = ""
    S["size_norm"]  = ""

# 스타일 키: description에서 추출 → info 매칭
S["style_key"] = S["product description"].astype(str).apply(lambda x: style_key_from_label(x, IMG_MAP))
S = S.dropna(subset=["style_key"]).copy()
S["cat"] = S.apply(lambda r: cat_from_info_and_text(length_for_style(r["style_key"]), r["text"]), axis=1)
S["platform"] = "SHEIN"

# 플랫폼 필터
frames = []
if platform in ["BOTH","TEMU"]:
    frames.append(T[["platform","style_key","qty","sales","color_norm","size_norm","cat"]])
if platform in ["BOTH","SHEIN"]:
    frames.append(S[["platform","style_key","qty","sales","color_norm","size_norm","cat"]])

if not frames:
    st.info("데이터가 없습니다.")
    st.stop()

ALL = pd.concat(frames, ignore_index=True)

# -------------------------
# 1) 카테고리 도넛 그래프 (판매수량 비율)
# -------------------------
st.subheader("📊 카테고리별 판매 비율 (도넛)")
cat_df = ALL.groupby("cat", as_index=False).agg(qty=("qty","sum"), sales=("sales","sum"))
cat_df = cat_df[cat_df["qty"] > 0].sort_values("qty", ascending=False).reset_index(drop=True)
if cat_df.empty:
    st.info("카테고리 집계 결과가 없습니다.")
else:
    cat_df["pct"] = (cat_df["qty"] / cat_df["qty"].sum()) * 100.0
    c1, c2 = st.columns([1,1])
    with c1:
        donut = alt.Chart(cat_df).mark_arc(innerRadius=70).encode(
            theta=alt.Theta("qty:Q", stack=True),
            color=alt.Color("cat:N", title="카테고리"),
            tooltip=[alt.Tooltip("cat:N", title="카테고리"),
                     alt.Tooltip("qty:Q", title="판매수량", format=",.0f"),
                     alt.Tooltip("pct:Q", title="비율(%)", format=".1f")]
        ).properties(height=360)
        st.altair_chart(donut, use_container_width=True)
    with c2:
        st.markdown("**카테고리 요약**")
        st.dataframe(cat_df[["cat","qty","pct","sales"]]
                     .rename(columns={"cat":"카테고리","qty":"판매수량","pct":"비율(%)","sales":"매출"})
                     .style.format({"판매수량":"{:,}","비율(%)":"{:.1f}","매출":"${:,.2f}"}),
                     use_container_width=True, hide_index=True)

# -------------------------
# 2) 옵션(색상/사이즈) 간단 요약
# -------------------------
st.subheader("🎨 옵션 요약 (색상/사이즈 Top)")
opt_left, opt_right = st.columns(2)

# Color Top
with opt_left:
    color_df = (ALL.assign(color_norm=ALL["color_norm"].astype(str).str.strip())
                  .query("color_norm != ''")
                  .groupby("color_norm", as_index=False).agg(qty=("qty","sum"))
                  .sort_values("qty", ascending=False).head(12))
    if color_df.empty:
        st.info("색상 데이터가 없습니다.")
    else:
        bar = alt.Chart(color_df).mark_bar().encode(
            x=alt.X("qty:Q", title="판매수량"),
            y=alt.Y("color_norm:N", title="색상", sort="-x")
        ).properties(height=340)
        st.altair_chart(bar, use_container_width=True)

# Size Top
with opt_right:
    size_df = (ALL.assign(size_norm=ALL["size_norm"].astype(str).str.strip())
                 .query("size_norm != ''")
                 .groupby("size_norm", as_index=False).agg(qty=("qty","sum"))
                 .sort_values("qty", ascending=False).head(12))
    if size_df.empty:
        st.info("사이즈 데이터가 없습니다.")
    else:
        bar2 = alt.Chart(size_df).mark_bar().encode(
            x=alt.X("qty:Q", title="판매수량"),
            y=alt.Y("size_norm:N", title="사이즈", sort="-x")
        ).properties(height=340)
        st.altair_chart(bar2, use_container_width=True)

st.caption("• 도넛은 ‘판매수량’ 기준 비율입니다. (막대는 Top 12 색상/사이즈)")
