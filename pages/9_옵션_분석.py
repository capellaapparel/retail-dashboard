# ==========================================
# File: pages/9_옵션_분석.py
# 옵션 · 카테고리 분석 (도넛 + 라벨 가이드라인, 표, 옵션 Top)
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

def style_key_from_info(s: str) -> str:
    return str(s).upper().replace(" ", "")

# -------------------------
# Load
# -------------------------
info  = load_google_sheet("PRODUCT_INFO")
temu  = load_google_sheet("TEMU_SALES")
shein = load_google_sheet("SHEIN_SALES")

# 날짜 정규화
temu["order date"]  = temu["purchase date"].apply(parse_temudate)
shein["order date"] = shein["order processed on"].apply(parse_sheindate)

# 상태/수치
temu["order item status"] = temu["order item status"].astype(str)
temu["quantity shipped"]  = pd.to_numeric(temu.get("quantity shipped", 0), errors="coerce").fillna(0)
if "base price total" in temu.columns:
    temu["base price total"] = pd.to_numeric(temu["base price total"].astype(str).str.replace(r"[^0-9.\-]", "", regex=True), errors="coerce").fillna(0.0)

shein["order status"] = shein["order status"].astype(str)
shein["qty"] = 1.0
if "product price" in shein.columns:
    shein["product price"] = pd.to_numeric(shein["product price"].astype(str).str.replace(r"[^0-9.\-]", "", regex=True), errors="coerce").fillna(0.0)

# -------------------------
# 기간/플랫폼
# -------------------------
min_dt = pd.to_datetime(pd.concat([temu["order date"], shein["order date"]]).dropna()).min()
max_dt = pd.to_datetime(pd.concat([temu["order date"], shein["order date"]]).dropna()).max()

left, right = st.columns([1.2, 1])
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
    platform = st.radio("플랫폼", ["BOTH", "TEMU", "SHEIN"], horizontal=True)

# -------------------------
# 카테고리 판별 (PRODUCT_INFO 기반 + 판매명 보정)
# -------------------------
def base_category_from_length(length_val: str) -> str | None:
    s = str(length_val).upper()
    if not s or s == "NAN":
        return None
    parts = [p.strip() for p in s.split(",") if p.strip()]
    has_top   = any("TOP" in p for p in parts)
    has_skirt = any("SKIRT" in p for p in parts)
    is_dress  = any("DRESS" in p for p in parts)
    # 하의 추정(팬츠 계열)
    bottom_words = ["SHORT", "KNEE", "CAPRI", "FULL", "PANTS", "BOTTOM", "LEG", "PANT"]
    has_pants = any(any(w in p for w in bottom_words) for p in parts)

    # 세트 조건: TOP과 SKIRT 또는 하의 조합
    if len(parts) >= 2 and has_top and (has_skirt or has_pants):
        return "SET"
    if is_dress:
        return "DRESS"
    if has_skirt:
        return "SKIRT"
    if has_top:
        return "TOP"
    if has_pants:
        return "PANTS"
    return None

# style_key
info["style_key"] = info["product number"].astype(str).apply(style_key_from_info)
base_cat = dict(zip(info["style_key"], info["length"].apply(base_category_from_length)))

# 판매명에서 ROMPER/JUMPSUIT 추정 (있으면 우선)
def detect_jump_romp(text: str) -> str | None:
    s = str(text).upper()
    if "ROMPER" in s:
        return "ROMPER"
    if "JUMPSUIT" in s:
        return "JUMPSUIT"
    return None

temu["style_key"] = temu["product number"].astype(str).apply(style_key_from_info)
shein["style_key"] = shein["product description"].astype(str).apply(
    lambda x: (STYLE_RE.search(str(x).upper()) or [None])[0] if STYLE_RE.search(str(x).upper()) else str(x).upper().replace(" ", "")
)

# 보정용 매핑
name_hint = {}
if "product name by customer order" in temu.columns:
    for sk, txt in zip(temu["style_key"], temu["product name by customer order"]):
        t = detect_jump_romp(txt)
        if t:
            name_hint[sk] = t
if "product description" in shein.columns:
    for sk, txt in zip(shein["style_key"], shein["product description"]):
        t = detect_jump_romp(txt)
        if t:
            name_hint[sk] = t

def final_category(sk: str) -> str:
    if sk in name_hint:
        return name_hint[sk]
    b = base_cat.get(sk)
    return b if b else "PANTS"  # 최종 디폴트

# -------------------------
# 판매 데이터 필터
# -------------------------
T = temu[(temu["order date"] >= start) & (temu["order date"] <= end) &
         (temu["order item status"].str.lower().isin(["shipped", "delivered"]))].copy()
S = shein[(shein["order date"] >= start) & (shein["order date"] <= end) &
          (~shein["order status"].str.lower().eq("customer refunded"))].copy()

T["qty"] = T["quantity shipped"]
S["qty"] = 1.0

if platform == "TEMU":
    SOLD = T[["style_key", "qty", "base price total"]].copy()
elif platform == "SHEIN":
    SOLD = S[["style_key", "qty", "product price"]].copy()
else:
    SOLD = pd.concat([
        T[["style_key", "qty", "base price total"]].rename(columns={"base price total": "sales"}),
        S[["style_key", "qty", "product price"]].rename(columns={"product price": "sales"}),
    ], ignore_index=True)
    # TEMU/SHEIN 단독일 수 있으니 결측치 0
    SOLD["sales"] = pd.to_numeric(SOLD.get("sales", 0), errors="coerce").fillna(0.0)

if "sales" not in SOLD.columns:
    # 단일 플랫폼일 때 sales 생성
    if platform == "TEMU":
        SOLD["sales"] = pd.to_numeric(T.set_index("style_key").loc[SOLD["style_key"], "base price total"].values, errors="coerce").fillna(0.0)
    else:
        SOLD["sales"] = pd.to_numeric(S.set_index("style_key").loc[SOLD["style_key"], "product price"].values, errors="coerce").fillna(0.0)

SOLD["cat"] = SOLD["style_key"].astype(str).apply(final_category)

# 카테고리 집계
cat_sum = SOLD.groupby("cat").agg(qty=("qty", "sum"), sales=("sales", "sum")).reset_index()
cat_sum = cat_sum.sort_values("qty", ascending=False)
total_qty = cat_sum["qty"].sum()
if total_qty == 0:
    st.info("해당 기간에 판매 데이터가 없습니다.")
    st.stop()
cat_sum["pct"] = (cat_sum["qty"] / total_qty * 100).round(1)

# -------------------------
# 도넛 + 라벨 가이드(선) + 텍스트
# -------------------------
# 좌표 계산 (카테고리 라벨을 도넛 밖에 표시)
# 각 조각의 중앙각(라디안) → 라벨/가이드 시작점 좌표
R_INNER = 70
R_OUTER = 120
R_LABEL = 155   # 라벨 위치 반경
R_LINE  = 130   # 라벨 가이드 시작 반경 (도넛 끝 조금 바깥)

work = cat_sum.copy()
work["frac"] = work["qty"] / work["qty"].sum()
work["angle"] = work["frac"] * 2 * np.pi
work["cum"]   = work["angle"].cumsum()
work["mid"]   = work["cum"] - work["angle"] / 2.0
# 12시 방향(위)에서 시작하도록 -pi/2 오프셋
offset = -np.pi / 2
work["mid0"] = work["mid"] + offset

# 좌표
work["sx"] = np.cos(work["mid0"]) * R_LINE
work["sy"] = np.sin(work["mid0"]) * R_LINE
work["tx"] = np.cos(work["mid0"]) * R_LABEL
work["ty"] = np.sin(work["mid0"]) * R_LABEL
work["label"] = work["cat"] + " (" + work["pct"].astype(str) + "%)"

# 도넛
donut = alt.Chart(cat_sum).mark_arc(innerRadius=R_INNER, outerRadius=R_OUTER).encode(
    theta=alt.Theta("qty:Q"),
    color=alt.Color("cat:N", title="카테고리"),
    tooltip=["cat", "qty", alt.Tooltip("pct:Q", title="비율(%)")]
).properties(width=560, height=400)

# 가이드 라인
rule = alt.Chart(work).mark_rule(color="#999").encode(
    x=alt.X("sx:Q", scale=alt.Scale(domain=[-R_LABEL-30, R_LABEL+30]), axis=None),
    y=alt.Y("sy:Q", scale=alt.Scale(domain=[-R_LABEL-30, R_LABEL+30]), axis=None),
    x2="tx:Q", y2="ty:Q"
)

# 라벨 (좌표 고정, 텍스트만)
labels = alt.Chart(work).mark_text(fontSize=12, fontWeight="bold").encode(
    x=alt.X("tx:Q", scale=alt.Scale(domain=[-R_LABEL-30, R_LABEL+30]), axis=None),
    y=alt.Y("ty:Q", scale=alt.Scale(domain=[-R_LABEL-30, R_LABEL+30]), axis=None),
    text="label:N"
)

# 도넛 + (선+글자) 레이어
donut_block = (donut + rule + labels)

# 우측 요약 테이블
with st.container():
    st.markdown("### 📊 카테고리 요약")
    c1, c2 = st.columns([1.2, 1])
    with c1:
        st.markdown("#### 📈 카테고리별 판매 비율 (도넛)")
        st.altair_chart(donut_block, use_container_width=True)
    with c2:
        show = cat_sum.rename(columns={"cat":"카테고리", "qty":"판매수량", "pct":"비율(%)", "sales":"매출"})
        st.dataframe(show[["카테고리","판매수량","비율(%)","매출"]], use_container_width=True, hide_index=True)

# -------------------------
# 옵션 요약 (색상/사이즈 Top)
# -------------------------
st.markdown("### 🎨 옵션 요약 (색상/사이즈 Top)")

# TEMU: 컬러/사이즈 컬럼 사용 (있을 때)
def norm_color(c: str) -> str:
    s = str(c).replace("_", " ").strip()
    if not s or s.lower() in ["nan", "none"]:
        return ""
    return s.title()

def norm_size(s: str) -> str:
    m = str(s).strip().upper().replace(" ", "")
    repl = {
        "1XL": "1X", "2XL": "2X", "3XL": "3X",
        "SMALL": "S", "MEDIUM": "M", "LARGE": "L"
    }
    return repl.get(m, m)

# TEMU 옵션
opt_T = T.copy()
opt_T["color_norm"] = opt_T.get("color", "").apply(norm_color)
opt_T["size_norm"]  = opt_T.get("size", "").apply(norm_size)

# SHEIN 옵션(Seller SKU: SKU-COLOR-SIZE)
def split_shein_sku(x: str):
    s = str(x)
    if "-" not in s:
        return "", ""
    parts = s.split("-")
    if len(parts) < 3:
        return "", ""
    color = norm_color(parts[-2])
    size  = norm_size(parts[-1])
    return color, size

opt_S = S.copy()
if "seller sku" in opt_S.columns:
    cols, sizs = [], []
    for v in opt_S["seller sku"]:
        c, sz = split_shein_sku(v)
        cols.append(c); sizs.append(sz)
    opt_S["color_norm"] = cols
    opt_S["size_norm"]  = sizs
else:
    opt_S["color_norm"] = ""
    opt_S["size_norm"]  = ""

opt_all = []
if platform in ["BOTH", "TEMU"]:
    opt_all.append(opt_T[["qty", "color_norm", "size_norm"]])
if platform in ["BOTH", "SHEIN"]:
    opt_all.append(opt_S[["qty", "color_norm", "size_norm"]])

opts = pd.concat(opt_all, ignore_index=True) if opt_all else pd.DataFrame(columns=["qty","color_norm","size_norm"])
opts["qty"] = pd.to_numeric(opts["qty"], errors="coerce").fillna(0)

top_colors = (opts[opts["color_norm"].ne("")]
              .groupby("color_norm")["qty"].sum()
              .sort_values(ascending=False).head(12).reset_index())

top_sizes  = (opts[opts["size_norm"].ne("")]
              .groupby("size_norm")["qty"].sum()
              .sort_values(ascending=False).reset_index())

bc, bs = st.columns(2)
with bc:
    st.markdown("**색상 Top 12 (판매수량)**")
    if top_colors.empty:
        st.info("색상 데이터가 없습니다.")
    else:
        cchart = alt.Chart(top_colors).mark_bar().encode(
            x=alt.X("qty:Q", title="판매수량"),
            y=alt.Y("color_norm:N", sort="-x", title="색상")
        ).properties(height=420)
        st.altair_chart(cchart, use_container_width=True)

with bs:
    st.markdown("**사이즈 Top (판매수량)**")
    if top_sizes.empty:
        st.info("사이즈 데이터가 없습니다.")
    else:
        schart = alt.Chart(top_sizes).mark_bar().encode(
            x=alt.X("qty:Q", title="판매수량"),
            y=alt.Y("size_norm:N", sort="-x", title="사이즈")
        ).properties(height=420)
        st.altair_chart(schart, use_container_width=True)

st.caption("※ 도넛 라벨은 도넛 중심에서 해당 조각의 중앙각을 따라 밖으로 끌어내어 표시하고, 얇은 선으로 조각과 연결해 가독성을 높였습니다.")
