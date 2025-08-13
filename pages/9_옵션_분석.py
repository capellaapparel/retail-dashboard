# ==========================================
# File: pages/9_옵션_분석.py
# (도넛 라벨 outside + 좌우 배치 + 카테고리/옵션 Top)
# ==========================================
import streamlit as st
import pandas as pd
import re
from dateutil import parser
import plotly.express as px

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

def style_key_from_label(label: str, keys: set[str]) -> str | None:
    s = str(label).strip().upper()
    if not s:
        return None
    s_key = s.replace(" ", "")
    if s_key in keys:
        return s_key
    m = STYLE_RE.search(s)
    if m:
        cand = m.group(1).replace(" ", "")
        if cand in keys:
            return cand
    for k in keys:
        if k in s_key:
            return k
    return None

# -------------------------
# Load data
# -------------------------
info  = load_google_sheet("PRODUCT_INFO")
temu  = load_google_sheet("TEMU_SALES")
shein = load_google_sheet("SHEIN_SALES")

# normalize dates
temu["order date"]  = temu["purchase date"].apply(parse_temudate)
shein["order date"] = shein["order processed on"].apply(parse_sheindate)

# sold flags
temu["order item status"] = temu["order item status"].astype(str)
temu["quantity shipped"]  = pd.to_numeric(temu.get("quantity shipped", 0), errors="coerce").fillna(0)

shein["order status"] = shein["order status"].astype(str)

# PRODUCT_INFO key maps
info_keys = info.get("product number", pd.Series(dtype=str)).astype(str).str.upper().str.replace(" ", "", regex=False)
IMG_MAP   = dict(zip(info_keys, info.get("image","")))
LEN_MAP   = dict(zip(info_keys, info.get("length","")))

# -------------------------
# Date / Platform controls
# -------------------------
min_dt = pd.to_datetime(pd.concat([temu["order date"], shein["order date"]]).dropna()).min()
max_dt = pd.to_datetime(pd.concat([temu["order date"], shein["order date"]]).dropna()).max()

r1, r2 = st.columns([1.2,1])
with r1:
    dr = st.date_input(
        "조회 기간",
        value=(max_dt.date() - pd.Timedelta(days=29), max_dt.date()),
        min_value=min_dt.date(),
        max_value=max_dt.date(),
    )
    if isinstance(dr, (list, tuple)) and len(dr) == 2:
        start, end = dr
    else:
        start, end = dr, dr
    start = pd.to_datetime(start)
    end   = pd.to_datetime(end) + pd.Timedelta(hours=23, minutes=59, seconds=59)
with r2:
    platform = st.radio("플랫폼", ["BOTH","TEMU","SHEIN"], index=0, horizontal=True)

# -------------------------
# 카테고리 분류 규칙
# -------------------------
TOP_SET   = {"CROP TOP","WAIST TOP","LONG TOP"}
DRESS_SET = {"MINI DRESS","MIDI DRESS","MAXI DRESS"}
SKIRT_SET = {"MINI SKIRT","MIDI SKIRT","MAXI SKIRT"}
BOTTOM_SET= {"SHORTS","KNEE","CAPRI","FULL"}  # 바텀 계열 길이

def classify_category(length_text: str, temu_name: str = "") -> str:
    """LENGTH 조합으로 1차 분류. 바텀쪽이면 TEMU 상품명에서 ROMPER/JUMPSUIT 감지."""
    if not str(length_text).strip():
        # 길이 정보 없으면 TEMU 상품명으로만 추정
        t = str(temu_name).upper()
        if "ROMPER" in t: return "ROMPER"
        if "JUMPSUIT" in t: return "JUMPSUIT"
        return "OTHER"

    # 길이 토큰 분리
    raw = (str(length_text).upper()
           .replace("/", ",")
           .replace("|", ",")
           .replace(";", ","))
    tokens = [x.strip() for x in raw.split(",") if x.strip()]
    groups = set()

    for tk in tokens:
        if tk in TOP_SET: groups.add("TOP")
        elif tk in DRESS_SET: groups.add("DRESS")
        elif tk in SKIRT_SET: groups.add("SKIRT")
        elif tk in BOTTOM_SET: groups.add("BOTTOM")

    if len(groups) >= 2:
        return "SET"

    if not groups:
        # 길이 값이 있지만 규칙 밖 → TEMU 이름 보조판단
        t = str(temu_name).upper()
        if "ROMPER" in t: return "ROMPER"
        if "JUMPSUIT" in t: return "JUMPSUIT"
        return "OTHER"

    g = groups.pop()
    if g == "BOTTOM":
        t = str(temu_name).upper()
        if "ROMPER" in t: return "ROMPER"
        if "JUMPSUIT" in t: return "JUMPSUIT"
        return "PANTS"
    return g

# -------------------------
# 분석용 데이터 구축
# -------------------------
keys_set = set(info_keys)

# TEMU
T = temu[(temu["order date"]>=start)&(temu["order date"]<=end) &
         (temu["order item status"].str.lower().isin(["shipped","delivered"]))].copy()
T["style_key"] = T["product number"].astype(str).apply(lambda x: style_key_from_label(x, keys_set))
T = T.dropna(subset=["style_key"]).copy()
T["length_info"] = T["style_key"].map(LEN_MAP).fillna("")
T["cat"] = T.apply(lambda r: classify_category(r["length_info"], r.get("product name by customer order","")), axis=1)
T["qty"] = T["quantity shipped"]
T["platform"] = "TEMU"

# SHEIN
S = shein[(shein["order date"]>=start)&(shein["order date"]<=end) &
          (~shein["order status"].str.lower().eq("customer refunded"))].copy()
S["style_key"] = S["product description"].astype(str).apply(lambda x: style_key_from_label(x, keys_set))
S = S.dropna(subset=["style_key"]).copy()
S["length_info"] = S["style_key"].map(LEN_MAP).fillna("")
S["cat"] = S["length_info"].apply(lambda x: classify_category(x, ""))
S["qty"] = 1
S["platform"] = "SHEIN"

if platform == "TEMU":
    base = T
elif platform == "SHEIN":
    base = S
else:
    base = pd.concat([T, S], ignore_index=True)

if base.empty:
    st.info("해당 기간/플랫폼에 데이터가 없습니다.")
    st.stop()

# 카테고리 요약
cat_summary = (base.groupby("cat", as_index=False)["qty"]
               .sum()
               .sort_values("qty", ascending=False))
cat_summary["비율(%)"] = (cat_summary["qty"] / cat_summary["qty"].sum() * 100).round(1)

# -------------------------
# 도넛 + 요약 테이블 (좌/우 배치)
# -------------------------
st.markdown("### 📊 카테고리별 판매 비율 (도넛)")

c1, c2 = st.columns([1.2, 1])
with c1:
    if cat_summary.shape[0] == 1:
        # 카테고리가 1개일 때는 라벨 겹침 이슈가 없지만, 도넛 외곽 라벨 유지
        hole = 0.55
    else:
        hole = 0.55

    fig = px.pie(
        cat_summary,
        names="cat",
        values="qty",
        hole=hole,
        color="cat",
        color_discrete_sequence=px.colors.qualitative.Set2,
    )
    # 라벨을 바깥쪽으로, 겹치면 자동으로 leader line 생성
    fig.update_traces(
        textposition="outside",
        texttemplate="%{label} (%{percent})",
        showlegend=False,
        marker_line_color="white",
        marker_line_width=1.2,
    )
    fig.update_layout(
        margin=dict(l=0, r=0, t=10, b=10),
        uniformtext_minsize=8,
        uniformtext_mode="hide",
        # 흑백 프린트 대비(명확한 선, 충분한 여백)
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(fig, use_container_width=True)

with c2:
    st.markdown("### 📁 카테고리 요약")
    st.dataframe(
        cat_summary.rename(columns={"cat":"카테고리","qty":"판매수량"}),
        use_container_width=True,
        hide_index=True,
    )

# -------------------------
# 옵션 요약 (색상/사이즈 Top)
# -------------------------
st.markdown("### 🎯 옵션 요약 (색상/사이즈 Top)")

# 사이즈 표준화
SIZE_NORM = {
    "SMALL": "S", "S": "S",
    "MEDIUM":"M", "M":"M",
    "LARGE":"L", "L":"L",
    "1XL":"1X", "1X":"1X",
    "2XL":"2X", "2X":"2X",
    "3XL":"3X", "3X":"3X",
}
def norm_size(x: str) -> str:
    s = str(x).strip().upper().replace(" ", "")
    return SIZE_NORM.get(s, s)

def norm_color(x: str) -> str:
    # SHEIN은 COLOR가 HEATHER_GREY 형태 → HEATHER GREY
    s = str(x).strip().upper().replace("_", " ")
    return s

# TEMU 색/사이즈
T_color = (T.assign(color=lambda d: d.get("color","").astype(str).str.upper(),
                    size=lambda d: d.get("size","").astype(str).map(norm_size))
             .groupby("color", as_index=False)["qty"].sum())
T_size  = (T.assign(size=lambda d: d.get("size","").astype(str).map(norm_size))
             .groupby("size", as_index=False)["qty"].sum())

# SHEIN 색/사이즈 (seller sku = SKU-COLOR-SIZE)
def split_shein_sku(s: str):
    parts = str(s).split("-")
    if len(parts) >= 3:
        return parts[-2], parts[-1]
    return "", ""

S_cols = S.copy()
if "seller sku" in S_cols.columns:
    colors, sizes = zip(*S_cols["seller sku"].astype(str).map(split_shein_sku))
    S_cols["color"] = [norm_color(c) for c in colors]
    S_cols["size"]  = [norm_size(s)  for s in sizes]
else:
    S_cols["color"] = ""
    S_cols["size"]  = ""

S_color = S_cols.groupby("color", as_index=False)["qty"].sum()
S_size  = S_cols.groupby("size",  as_index=False)["qty"].sum()

if platform == "TEMU":
    color_top = T_color
    size_top  = T_size
elif platform == "SHEIN":
    color_top = S_color
    size_top  = S_size
else:
    color_top = (pd.concat([T_color, S_color]).groupby("color", as_index=False)["qty"].sum())
    size_top  = (pd.concat([T_size,  S_size ]).groupby("size",  as_index=False)["qty"].sum())

color_top = color_top[color_top["color"].ne("")].sort_values("qty", ascending=False).head(12)
size_top  = size_top[size_top["size"].ne("")].sort_values("qty", ascending=False).head(8)

b1, b2 = st.columns(2)
with b1:
    st.bar_chart(color_top.set_index("color")["qty"], height=360, use_container_width=True)
with b2:
    st.bar_chart(size_top.set_index("size")["qty"], height=360, use_container_width=True)

st.caption("· 도넛은 판매수량 기준 비율입니다. (라벨은 바깥쪽에 표시되며, 흑백 출력에 대비해 리더 라인이 표시됩니다.)")
