# ==========================================
# File: pages/9_옵션_분석.py
# ==========================================
import re
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
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

def _money(s: pd.Series) -> pd.Series:
    return (s.astype(str).str.replace(r"[^0-9.\-]", "", regex=True)
            .replace("", pd.NA).astype(float))

# -------------------------
# Load & normalize
# -------------------------
info  = load_google_sheet("PRODUCT_INFO")
temu  = load_google_sheet("TEMU_SALES")
shein = load_google_sheet("SHEIN_SALES")

temu["order date"] = temu["purchase date"].apply(parse_temudate)
shein["order date"] = shein["order processed on"].apply(parse_sheindate)

temu["order item status"] = temu["order item status"].astype(str).str.lower()
temu["quantity shipped"]  = pd.to_numeric(temu.get("quantity shipped", 0), errors="coerce").fillna(0)
shein["order status"]     = shein["order status"].astype(str).str.lower()

# -------------------------
# Controls
# -------------------------
min_dt = pd.to_datetime(pd.concat([temu["order date"], shein["order date"]]).dropna()).min()
max_dt = pd.to_datetime(pd.concat([temu["order date"], shein["order date"]]).dropna()).max()

r1, r2 = st.columns([1.6, 1])
with r1:
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
with r2:
    platform = st.radio("플랫폼", ["BOTH", "TEMU", "SHEIN"], horizontal=True, index=0)

# -------------------------
# Category mapping
# -------------------------
TOP_TOKENS   = {"CROP TOP","WAIST TOP","LONG TOP"}
DRESS_TOKENS = {"MINI DRESS","MIDI DRESS","MAXI DRESS"}
SKIRT_TOKENS = {"MINI SKIRT","MIDI SKIRT","MAXI SKIRT"}
PANTS_TOKENS = {"SHORTS","KNEE","CAPRI","FULL"}

def detect_cat_from_length(length_str: str) -> str:
    items = [s.strip().upper() for s in str(length_str).split(",") if s.strip()]
    has_top   = any(x in TOP_TOKENS for x in items)
    has_dress = any(x in DRESS_TOKENS for x in items)
    has_skirt = any(x in SKIRT_TOKENS for x in items)
    has_pants = any(x in PANTS_TOKENS for x in items)

    # 세트: 옵션이 2개 이상이면서 Top+Skirt / Top+Pants 유형
    if len(items) >= 2 and has_top and (has_skirt or has_pants):
        return "SET"
    if has_dress: return "DRESS"
    if has_top:   return "TOP"
    if has_skirt: return "SKIRT"
    if has_pants: return "PANTS"
    return "OTHER"

# TEMU 상품명에 JUMPSUIT/ROMPER가 있으면 우선 반영
def detect_jr_from_temu_name(name: str) -> str|None:
    s = str(name).upper()
    if "JUMPSUIT" in s: return "JUMPSUIT"
    if "ROMPER"   in s: return "ROMPER"
    return None

# 제품별 기본 카테고리
info["_base_cat"] = info["length"].apply(detect_cat_from_length)

# -------------------------
# Build sold rows (기간/플랫폼 필터)
# -------------------------
T = temu[(temu["order date"]>=start)&(temu["order date"]<=end)].copy()
T = T[T["order item status"].isin(["shipped","delivered"])]
T["qty"] = T["quantity shipped"].astype(float)

S = shein[(shein["order date"]>=start)&(shein["order date"]<=end)].copy()
S = S[~S["order status"].eq("customer refunded")]
S["qty"] = 1.0

if platform == "TEMU":
    S = S.iloc[0:0]
elif platform == "SHEIN":
    T = T.iloc[0:0]

# TEMU: Jumpsuit/Romper 덮어쓰기
if not T.empty:
    # TEMU product name by customer order 칼럼 추정(여러 변형 대응)
    name_cols = [c for c in T.columns if "product name" in c and "customer" in c]
    if name_cols:
        t_name = T[name_cols[0]].astype(str)
        jr_cat = t_name.map(detect_jr_from_temu_name)
    else:
        jr_cat = pd.Series(index=T.index, dtype=object)

# 판매 레코드 → style 단위 카테고리 붙이기
key_info = info.set_index(info["product number"].astype(str).str.upper().str.replace(" ","",regex=False))["_base_cat"]
def to_key(s): return str(s).upper().replace(" ","")

if not T.empty:
    T["_key"] = T["product number"].map(to_key)
    T["_cat"] = T["_key"].map(key_info).fillna("OTHER")
    if name_cols:
        T.loc[jr_cat.notna(), "_cat"] = jr_cat[jr_cat.notna()]  # JUMPSUIT/ROMPER 우선
else:
    T = pd.DataFrame(columns=["_cat","qty"])

if not S.empty:
    S["_key"] = S["product description"].astype(str).map(to_key)
    S["_cat"] = S["_key"].map(key_info).fillna("OTHER")
else:
    S = pd.DataFrame(columns=["_cat","qty"])

sold = pd.concat([T[["_cat","qty"]], S[["_cat","qty"]]], ignore_index=True)
sold["_cat"] = sold["_cat"].fillna("OTHER")

# -------------------------
# Category summary
# -------------------------
if sold.empty:
    st.info("데이터가 없습니다.")
    st.stop()

cat_summary = sold.groupby("_cat")["qty"].sum().sort_values(ascending=False).rename_axis("cat").reset_index()
cat_summary["ratio"] = cat_summary["qty"] / cat_summary["qty"].sum()

# -------------------------
# Donut with labels ON the slices (B/W friendly)
# -------------------------
st.subheader("📊 카테고리별 판매 비율 (도넛)")

labels = cat_summary["cat"].tolist()
values = cat_summary["qty"].tolist()
percs  = cat_summary["ratio"].tolist()

# 작은 조각은 바깥쪽 라벨 + 리더라인
positions = ["inside" if p >= 0.06 else "outside" for p in percs]

fig = go.Figure(
    go.Pie(
        labels=labels,
        values=values,
        hole=0.55,
        textinfo="label+percent",
        textposition=positions,           # per-slice
        textfont=dict(color="black", size=14),
        marker=dict(line=dict(color="#666", width=1)),
        pull=[0.04 if p < 0.04 else 0 for p in percs]  # 극소 조각 강조(살짝 분리)
    )
)
fig.update_layout(
    showlegend=False,                    # 범례 대신 조각 라벨 사용
    height=460,
    margin=dict(l=10, r=10, t=10, b=10),
    paper_bgcolor="white",
    plot_bgcolor="white"
)
st.plotly_chart(fig, use_container_width=True, theme=None)

# 오른쪽 표 요약
with st.container(border=True):
    st.markdown("**🗒 카테고리 요약**")
    view = cat_summary.copy()
    view["비율(%)"] = (view["ratio"]*100).round(1)
    view = view[["cat","qty","비율(%)"]].rename(columns={"cat":"카테고리","qty":"판매수량"})
    st.dataframe(view, use_container_width=True, hide_index=True)

# -------------------------
# 옵션 요약 (색상/사이즈 TOP)
# -------------------------
st.subheader("🎨 옵션 요약 (색상/사이즈 Top)")

# 색상 추정: SHEIN은 seller sku, TEMU는 color 컬럼 사용 (있으면)
def parse_shein_sku_for_color(x: str) -> str:
    # 예: ABCD-HEATHER_GREY-1X  -> HEATHER GREY
    parts = str(x).split("-")
    if len(parts) >= 3:
        color = parts[-2].replace("_"," ").strip()
        return color.title()
    return ""

def parse_shein_sku_for_size(x: str) -> str:
    sz = str(x).split("-")[-1].upper().strip()
    norm = {"1XL":"1X","2XL":"2X","3XL":"3X","SMALL":"S","MEDIUM":"M","LARGE":"L"}
    return norm.get(sz, sz)

colors = []
sizes  = []

# TEMU
if not T.empty:
    if "color" in T.columns:
        colors += [str(c).title() for c in T["color"] for _ in range(int(1))]  # 존재만 반영
    if "size" in T.columns:
        sizes  += [str(s).upper() for s in T["size"]]

# SHEIN
if not S.empty:
    sku_col = None
    for c in ["seller sku","seller_sku","seller sku id","seller-sku"]:
        if c in S.columns:
            sku_col = c; break
    if sku_col:
        colors += [parse_shein_sku_for_color(v) for v in S[sku_col]]
        sizes  += [parse_shein_sku_for_size(v)  for v in S[sku_col]]

# 상위 색상/사이즈 표
from collections import Counter
top_color = pd.DataFrame(Counter([c for c in colors if c]).most_common(12), columns=["color","qty"])
top_size  = pd.DataFrame(Counter([s for s in sizes  if s]).most_common(6),  columns=["size","qty"])

c1, c2 = st.columns(2)
with c1:
    st.markdown("**색상 Top 12**")
    if not top_color.empty:
        st.bar_chart(top_color.set_index("color")["qty"])
    else:
        st.caption("색상 데이터가 없습니다.")
with c2:
    st.markdown("**사이즈 Top 6**")
    if not top_size.empty:
        st.bar_chart(top_size.set_index("size")["qty"])
    else:
        st.caption("사이즈 데이터가 없습니다.")
