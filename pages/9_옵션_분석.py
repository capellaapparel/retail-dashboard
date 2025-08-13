# ==========================================
# File: pages/9_옵션_분석.py
# 옵션 · 카테고리 분석 (도넛 라벨 겹침 방지 + 긴 리더 라인)
# ==========================================
import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
import math
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

# 색/사이즈 정규화
def normalize_color(c: str) -> str:
    if pd.isna(c): return ""
    c = str(c).replace("_", " ").strip()
    return c.title()

SIZE_MAP = {
    "1XL":"1X","2XL":"2X","3XL":"3X",
    "SMALL":"S","MEDIUM":"M","LARGE":"L"
}
def normalize_size(s: str) -> str:
    s = str(s).strip().upper()
    return SIZE_MAP.get(s, s)

# 카테고리 매핑
TOP_KEYS    = ["CROP TOP","WAIST TOP","LONG TOP","TOP"]
DRESS_KEYS  = ["MINI DRESS","MIDI DRESS","MAXI DRESS","DRESS"]
SKIRT_KEYS  = ["MINI SKIRT","MIDI SKIRT","MAXI SKIRT","SKIRT"]
BOTTOM_KEYS = ["SHORTS","KNEE","CAPRI","FULL","BOTTOM","PANTS","JEANS","LEGGINGS"]

STYLE_RE = re.compile(r"\b([A-Z]{1,3}\d{3,5}[A-Z0-9]?)\b")

def pick_category(length_str: str, title_str: str) -> str:
    """PRODUCT_INFO.length 와 판매 데이터의 상품명으로 상위 카테고리 추론"""
    length = str(length_str or "").upper()
    title  = str(title_str or "").upper()

    # TEMU 제목에 ROMPER/JUMPSUIT 표시가 있으면 우선
    if "ROMPER" in title: return "ROMPER"
    if "JUMPSUIT" in title: return "JUMPSUIT"

    # LENGTH 조합으로 SET 판별
    parts = [p.strip().upper() for p in length.split(",") if p.strip()]
    has_top   = any(p in TOP_KEYS    for p in parts)
    has_skirt = any(p in SKIRT_KEYS  for p in parts)
    has_bottom= any(p in BOTTOM_KEYS for p in parts)
    has_dress = any(p in DRESS_KEYS  for p in parts)

    if (has_top and (has_skirt or has_bottom)): return "SET"
    if has_dress:  return "DRESS"
    if has_skirt:  return "SKIRT"
    if has_top:    return "TOP"
    if has_bottom: return "PANTS"

    # 그래도 못 찾으면 제목으로 추정
    if "DRESS" in title: return "DRESS"
    if "SKIRT" in title: return "SKIRT"
    if "TOP" in title:   return "TOP"
    if any(k in title for k in ["PANTS","JEANS","SHORTS","LEGGINGS","BOTTOM"]): return "PANTS"
    return "OTHER"

# -------------------------
# Load
# -------------------------
info  = load_google_sheet("PRODUCT_INFO")
temu  = load_google_sheet("TEMU_SALES")
shein = load_google_sheet("SHEIN_SALES")

temu["order date"]  = temu["purchase date"].apply(parse_temudate)
shein["order date"] = shein["order processed on"].apply(parse_sheindate)

temu["order item status"] = temu["order item status"].astype(str)
temu["quantity shipped"]  = pd.to_numeric(temu.get("quantity shipped", 0), errors="coerce").fillna(0)
temu["base price total"]  = money_series(temu.get("base price total", 0))

shein["order status"] = shein["order status"].astype(str)
shein["product price"] = money_series(shein.get("product price", 0))

# -------------------------
# Controls
# -------------------------
min_dt = pd.to_datetime(pd.concat([temu["order date"], shein["order date"]]).dropna()).min()
max_dt = pd.to_datetime(pd.concat([temu["order date"], shein["order date"]]).dropna()).max()

c_left, c_right = st.columns([1.6, 1])
with c_left:
    dr = st.date_input(
        "조회 기간",
        value=(max_dt.date() - pd.Timedelta(days=29), max_dt.date()),
        min_value=min_dt.date(), max_value=max_dt.date()
    )
    if isinstance(dr, (list, tuple)):
        start, end = dr
    else:
        start, end = dr, dr
    start = pd.to_datetime(start); end = pd.to_datetime(end) + pd.Timedelta(hours=23, minutes=59, seconds=59)
with c_right:
    platform = st.radio("플랫폼", ["BOTH","TEMU","SHEIN"], horizontal=True)

# -------------------------
# Build sold rows & category
# -------------------------
# PRODUCT_INFO 에서 style -> length 매핑
len_map = dict(zip(
    info.get("product number", pd.Series(dtype=str)).astype(str).str.upper().str.replace(" ", "", regex=False),
    info.get("length","")
))

def style_key(s):
    return str(s).upper().replace(" ", "")

# TEMU (shipped/delivered)
T = temu[(temu["order item status"].str.lower().isin(["shipped","delivered"])) &
         (temu["order date"]>=start) & (temu["order date"]<=end)].copy()
T["qty"]   = pd.to_numeric(T.get("quantity shipped", 0), errors="coerce").fillna(0)
T["price"] = T.get("base price total", 0.0)
T["style_key"] = T.get("product number","").astype(str).apply(style_key)
T["length"] = T["style_key"].map(len_map).fillna("")
T["cat"] = [pick_category(l, t) for l, t in zip(T["length"], T.get("product name by customer order",""))]

# SHEIN (exclude refunded)
S = shein[(~shein["order status"].str.lower().eq("customer refunded")) &
          (shein["order date"]>=start) & (shein["order date"]<=end)].copy()
S["qty"]   = 1.0
S["price"] = S.get("product price", 0.0)
S["style_key"] = S.get("product description","").astype(str)
S["length"]    = S["style_key"].apply(lambda x: "")
S["cat"]       = S["style_key"].apply(lambda _: "OTHER")  # 카테고리 추정 어렵다면 OTHER 처리(원하면 더 정교화)

# 플랫폼 선택
if platform == "TEMU":
    SOLD = T
elif platform == "SHEIN":
    SOLD = S
else:
    SOLD = pd.concat([T, S], ignore_index=True)

# -------------------------
# 카테고리 요약 (도넛 데이터)
# -------------------------
cat_summary = (SOLD.groupby("cat")["qty"].sum()
               .sort_values(ascending=False)
               .reset_index())
cat_summary = cat_summary[cat_summary["qty"] > 0].copy()
if cat_summary.empty:
    st.info("표시할 데이터가 없습니다.")
    st.stop()

cat_summary["pct"] = cat_summary["qty"] / cat_summary["qty"].sum() * 100.0
cat_summary["label"] = cat_summary.apply(lambda r: f"{r['cat']} ({r['pct']:.1f}%)", axis=1)

# -------------------------
# Donut + Anti-overlap Leader
# -------------------------
# 도넛 반지름/라벨 반경/격자 범위
R_OUT   = 100     # 도넛 바깥 반경
R_IN    = 55      # 도넛 안쪽 반경
R_PT    = R_OUT   # 라인 시작점(도넛 바깥 원)
R_ELBOW = R_OUT + 30   # 엘보(꺾임) x 위치
R_TEXT  = R_OUT + 105  # 라벨 x 위치
GAP_Y   = 13      # 라벨 상하 최소 간격(px처럼 동작)
DOM_X   = R_OUT + 130
DOM_Y   = R_OUT + 40
TEXT_PAD = 6      # 라인 끝과 텍스트 사이 여백

# 각도 계산
tmp = cat_summary.copy()
tmp["frac"] = tmp["qty"] / tmp["qty"].sum()
tmp["theta"] = tmp["frac"] * 2*np.pi
tmp["theta_cum"] = tmp["theta"].cumsum()
tmp["theta_mid"] = tmp["theta_cum"] - tmp["theta"]/2

# 원 위 점(도넛 바깥) 좌표
tmp["px"] = (R_PT * np.cos(tmp["theta_mid"]))
tmp["py"] = (R_PT * np.sin(tmp["theta_mid"]))

# 좌/우 측 구분
tmp["side"] = np.where(np.cos(tmp["theta_mid"]) >= 0, "R", "L")
tmp["sign"] = np.where(tmp["side"].eq("R"), 1, -1)

# y 기준 정렬 후 라벨 y 좌표를 서로 겹치지 않게 보정
def spread_y(df_side: pd.DataFrame) -> pd.DataFrame:
    df = df_side.sort_values("py").copy()
    last_y = -1e9
    rows = []
    for _, r in df.iterrows():
        y = r["py"]
        if y - last_y < GAP_Y:
            y = last_y + GAP_Y
        last_y = y
        rows.append({**r.to_dict(), "ly": y})  # label y
    # 너무 위/아래로 쏠리면 도메인에 맞춰 클램프
    for row in rows:
        row["ly"] = float(np.clip(row["ly"], -R_OUT, R_OUT))
    return pd.DataFrame(rows)

ann = pd.concat([spread_y(tmp[tmp["side"].eq("L")]),
                 spread_y(tmp[tmp["side"].eq("R")])], ignore_index=True)

# 엘보 x/y, 라벨 x/y, 라인 끝점 x(텍스트 전)
ann["ex"] = ann["sign"] * R_ELBOW     # elbow x
ann["ey"] = ann["ly"]                # elbow y
ann["tx"] = ann["sign"] * R_TEXT     # text x
ann["ty"] = ann["ly"]                # text y
ann["tx2"]= ann["tx"] - ann["sign"] * TEXT_PAD   # 라인이 닿는 텍스트 직전 x
ann["align"] = np.where(ann["side"].eq("R"), "left", "right")

# 도넛 차트
color_order = ["TOP","DRESS","PANTS","SET","JUMPSUIT","ROMPER","SKIRT","OTHER"]
color_range = ["#1f77b4","#ff4136","#ff851b","#2ecc71","#7fdbff","#ffdc00","#b10dc9","#aaaaaa"]

pie = alt.Chart(cat_summary).mark_arc(outerRadius=R_OUT, innerRadius=R_IN).encode(
    theta=alt.Theta("qty:Q"),
    color=alt.Color("cat:N", legend=None, scale=alt.Scale(domain=color_order, range=color_range))
).properties(height=420)

# 리더 라인 (wedge → elbow)
leader1 = alt.Chart(ann).mark_rule(color="#667085", strokeWidth=1.0).encode(
    x=alt.X("px:Q",  scale=alt.Scale(domain=[-DOM_X, DOM_X]), axis=None),
    y=alt.Y("py:Q",  scale=alt.Scale(domain=[-DOM_Y, DOM_Y]), axis=None),
    x2=alt.X("ex:Q"),
    y2=alt.Y("ey:Q"),
)

# 리더 라인 (elbow → label)
leader2 = alt.Chart(ann).mark_rule(color="#667085", strokeWidth=1.0).encode(
    x=alt.X("ex:Q",  scale=alt.Scale(domain=[-DOM_X, DOM_X]), axis=None),
    y=alt.Y("ey:Q",  scale=alt.Scale(domain=[-DOM_Y, DOM_Y]), axis=None),
    x2=alt.X("tx2:Q"),
    y2=alt.Y("ty:Q"),
)

# 라벨 텍스트
labels = alt.Chart(ann).mark_text(fontSize=12, fontWeight="bold", dy=0).encode(
    x=alt.X("tx:Q", scale=alt.Scale(domain=[-DOM_X, DOM_X]), axis=None),
    y=alt.Y("ty:Q", scale=alt.Scale(domain=[-DOM_Y, DOM_Y]), axis=None),
    text="label:N",
    align="align:N"
)

# 도넛 + 라인 + 라벨
donut = (pie + leader1 + leader2 + labels)

# 오른쪽 요약 테이블
sum_tbl = cat_summary[["cat","qty","pct"]].rename(columns={"cat":"카테고리","qty":"판매수량","pct":"비율(%)"})
sum_tbl["비율(%)"] = sum_tbl["비율(%)"].map(lambda v: f"{v:.1f}")

sec1_left, sec1_right = st.columns([1.6,1])
with sec1_left:
    st.subheader("📊 카테고리별 판매 비율 (도넛)")
    st.altair_chart(donut, use_container_width=True)
with sec1_right:
    st.subheader("📁 카테고리 요약")
    st.dataframe(sum_tbl, use_container_width=True, hide_index=True)

# -------------------------
# 옵션 요약 (색상/사이즈 TOP)
# -------------------------
st.subheader("🎨 옵션 요약 (색상/사이즈 Top)")

# 색상
if "color" in temu.columns:
    T_colors = temu[(temu["order item status"].str.lower().isin(["shipped","delivered"])) &
                    (temu["order date"]>=start) & (temu["order date"]<=end)].copy()
    T_colors["qty"]   = pd.to_numeric(T_colors.get("quantity shipped", 0), errors="coerce").fillna(0)
    T_colors["color"] = T_colors["color"].apply(normalize_color)
else:
    T_colors = pd.DataFrame(columns=["color","qty"])

if "product options" in shein.columns:
    # 색상은 SHEIN 원천 구조에 맞춰 추가로 파싱하고 싶다면 여기에 보강
    S_colors = pd.DataFrame(columns=["color","qty"])
else:
    S_colors = pd.DataFrame(columns=["color","qty"])

COLORS = pd.concat([T_colors[["color","qty"]], S_colors[["color","qty"]]], ignore_index=True)
COLORS = COLORS.groupby("color")["qty"].sum().sort_values(ascending=False).head(12).reset_index()
COLORS = COLORS[COLORS["color"].astype(str).str.strip()!=""]

# 사이즈
T_size = temu[(temu["order item status"].str.lower().isin(["shipped","delivered"])) &
              (temu["order date"]>=start) & (temu["order date"]<=end)].copy()
T_size["qty"]  = pd.to_numeric(T_size.get("quantity shipped", 0), errors="coerce").fillna(0)
T_size["size"] = T_size.get("size","").astype(str).apply(normalize_size)

S_size = shein[(~shein["order status"].str.lower().eq("customer refunded")) &
               (shein["order date"]>=start) & (shein["order date"]<=end)].copy()
S_size["qty"]  = 1.0
S_size["size"] = S_size.get("variant size","").astype(str).apply(normalize_size) if "variant size" in S_size.columns else ""

SIZES = pd.concat([T_size[["size","qty"]], S_size[["size","qty"]]], ignore_index=True)
SIZES = SIZES.groupby("size")["qty"].sum().sort_values(ascending=False).head(12).reset_index()
SIZES = SIZES[SIZES["size"].astype(str).str.strip()!=""]

cA, cB = st.columns(2)
with cA:
    st.bar_chart(COLORS.set_index("color")["qty"], height=320)
with cB:
    st.bar_chart(SIZES.set_index("size")["qty"], height=320)

st.caption("· 도넛은 판매수량 기준 비율입니다. (라벨은 좌우로 길게 끌어당겨 겹치지 않게 배치)")
