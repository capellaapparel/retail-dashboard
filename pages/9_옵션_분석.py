# ==========================================
# File: pages/9_옵션_분석.py
# (Altair 도넛 + 바깥 라벨/리더라인, 옵션 TOP 바)
# ==========================================
import streamlit as st
import pandas as pd
import numpy as np
import re
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

# 사이즈 normalize
SIZE_MAP = {
    "1XL":"1X","1X":"1X","2XL":"2X","2X":"2X","3XL":"3X","3X":"3X",
    "SMALL":"S","S":"S","M":"M","MEDIUM":"M","L":"L","LARGE":"L",
    "XS":"XS","XL":"XL"
}
def norm_size(s):
    x = str(s).strip().upper()
    return SIZE_MAP.get(x, x)

# SHEIN Seller SKU → (style, color, size)
def parse_shein_sku(s):
    s = str(s)
    parts = s.split("-")
    if len(parts) < 3:
        return "", "", ""
    size = parts[-1]
    color = parts[-2].replace("_", " ")
    style = "-".join(parts[:-2])  # 스타일에 '-'가 있어도 안전
    return style, color, size

# LENGTH → 카테고리(SET 포함)
TOP_TAGS   = {"CROP TOP","WAIST TOP","LONG TOP"}
DRESS_TAGS = {"MINI DRESS","MIDI DRESS","MAXI DRESS"}
SKIRT_TAGS = {"MINI SKIRT","MIDI SKIRT","MAXI SKIRT"}
PANTS_TAGS = {"SHORTS","KNEE","CAPRI","FULL"}  # 하의 계열 (팬츠/점프수트/롬퍼 후보)

def length_to_cat(length_text: str) -> set:
    if not str(length_text).strip():
        return set()
    # "A, B" 형태를 안전하게 분리
    tokens = [t.strip().upper() for t in str(length_text).split(",") if t.strip()]
    cats = set()
    for t in tokens:
        if t in TOP_TAGS:   cats.add("TOP")
        if t in DRESS_TAGS: cats.add("DRESS")
        if t in SKIRT_TAGS: cats.add("SKIRT")
        if t in PANTS_TAGS: cats.add("PANTS")  # 기본은 PANTS로 분류(후보)
    # 조합이 TOP+SKIRT 또는 TOP+PANTS면 세트로 본다
    if ("TOP" in cats and "SKIRT" in cats) or ("TOP" in cats and "PANTS" in cats):
        return {"SET"}
    return cats or set()

# -------------------------
# Load
# -------------------------
info  = load_google_sheet("PRODUCT_INFO")
temu  = load_google_sheet("TEMU_SALES")
shein = load_google_sheet("SHEIN_SALES")

# 날짜/수치 정규화
temu["order date"]  = temu["purchase date"].apply(parse_temudate)
temu["order item status"] = temu["order item status"].astype(str)
temu["quantity shipped"]  = pd.to_numeric(temu.get("quantity shipped", 0), errors="coerce").fillna(0)

shein["order date"]  = shein["order processed on"].apply(parse_sheindate)
shein["order status"] = shein["order status"].astype(str)

# 기간/플랫폼 선택
min_dt = pd.to_datetime(pd.concat([temu["order date"], shein["order date"]]).dropna()).min()
max_dt = pd.to_datetime(pd.concat([temu["order date"], shein["order date"]]).dropna()).max()

left, right = st.columns([1.3, 1])
with left:
    dr = st.date_input(
        "조회 기간",
        value=(max_dt.date()-pd.Timedelta(days=29), max_dt.date()),
        min_value=min_dt.date(), max_value=max_dt.date()
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
# 판매라인 빌드 (스타일/색상/사이즈 포함)
# -------------------------
rows = []

if platform in ("TEMU","BOTH"):
    t = temu[
        (temu["order date"]>=start) & (temu["order date"]<=end) &
        (temu["order item status"].str.lower().isin(["shipped","delivered"]))
    ].copy()
    t["style"] = t.get("product number", "")
    t["color"] = t.get("color", "")
    t["size"]  = t.get("size", "")
    t["qty"]   = t["quantity shipped"]
    t["platform"] = "TEMU"
    rows.append(t[["platform","style","color","size","qty","product name by customer order"]])

if platform in ("SHEIN","BOTH"):
    s = shein[
        (shein["order date"]>=start) & (shein["order date"]<=end) &
        (~shein["order status"].str.lower().eq("customer refunded"))
    ].copy()
    # 1건 1개로 간주
    s["qty"] = 1.0
    style, color, size = [], [], []
    for sku in s.get("seller sku",""):
        st_, co_, si_ = parse_shein_sku(sku)
        style.append(st_); color.append(co_); size.append(si_)
    s["style"] = style
    s["color"] = color
    s["size"]  = size
    s["platform"] = "SHEIN"
    s["product name by customer order"] = ""  # 빈칸(분류 보조용 컬럼 맞추기)
    rows.append(s[["platform","style","color","size","qty","product name by customer order"]])

if not rows:
    st.info("표시할 데이터가 없습니다.")
    st.stop()

sold = pd.concat(rows, ignore_index=True)
sold["style_key"] = sold["style"].astype(str).str.upper().str.replace(" ", "", regex=False)
sold["size"] = sold["size"].apply(norm_size)
sold["color"] = sold["color"].astype(str).str.strip()

# -------------------------
# 카테고리 매핑
# -------------------------
# 1) LENGTH 기반 1차 분류
len_map = {}
for _, r in info[["product number","length"]].dropna().iterrows():
    k = str(r["product number"]).upper().replace(" ", "")
    len_map[k] = length_to_cat(r["length"])

sold["length_cats"] = sold["style_key"].map(len_map).apply(lambda v: v if isinstance(v,set) else set())

# 2) TEMU 주문명 기반(ROMPER/JUMPSUIT) 보정
name_col = sold["product name by customer order"].astype(str).str.upper()
sold["name_romper"]    = name_col.str.contains("ROMPER", na=False)
sold["name_jumpsuit"]  = name_col.str.contains("JUMPSUIT", na=False)

def decide_cat(row):
    cats = set(row["length_cats"])
    # 세트 우선
    if "SET" in cats:
        return "SET"
    # 드레스/탑/스커트 우선
    for c in ("DRESS","TOP","SKIRT"):
        if c in cats:
            return c
    # 하의 계열이면 ROMPER/JUMPSUIT 체크
    if "PANTS" in cats:
        if row["name_romper"]:
            return "ROMPER"
        if row["name_jumpsuit"]:
            return "JUMPSUIT"
        return "PANTS"
    # 아무것도 못 찾으면 기타 방지용으로 TOP 취급
    return "TOP"

sold["cat"] = sold.apply(decide_cat, axis=1)

# -------------------------
# 카테고리 도넛 데이터
# -------------------------
cat_summary = (sold.groupby("cat", as_index=False)["qty"].sum()
               .sort_values("qty", ascending=False))
total_qty = cat_summary["qty"].sum()
cat_summary["ratio"] = np.where(total_qty>0, cat_summary["qty"]/total_qty*100.0, 0.0)
cat_summary["label"] = cat_summary.apply(lambda r: f'{r["cat"]} ({r["ratio"]:.1f}%)', axis=1)

# -------------------------
# Donut with outside labels (Altair)
# -------------------------
outerR = 150
innerR = 80
labelR = outerR + 24
lineR1 = outerR + 6   # 라벨선 시작
lineR2 = outerR + 20  # 라벨선 끝

# 각 조각의 중간 각도 계산(라벨 위치용)
donut_src = cat_summary.copy()
sum_qty = float(donut_src["qty"].sum()) if donut_src.shape[0] else 1.0
donut_src["theta"] = donut_src["qty"].cumsum() - donut_src["qty"]/2.0
donut_src["theta"] = donut_src["theta"] / sum_qty * 2*np.pi
donut_src["x1"] = np.cos(donut_src["theta"]) * lineR1
donut_src["y1"] = np.sin(donut_src["theta"]) * lineR1
donut_src["x2"] = np.cos(donut_src["theta"]) * lineR2
donut_src["y2"] = np.sin(donut_src["theta"]) * lineR2
donut_src["lx"] = np.cos(donut_src["theta"]) * labelR
donut_src["ly"] = np.sin(donut_src["theta"]) * labelR

# Altair 차트 (좌: 도넛, 우: 요약표)
c_left, c_right = st.columns([1.1, 1])

with c_left:
    st.subheader("📊 카테고리별 판매 비율 (도넛)")

    base = alt.Chart(cat_summary).encode(theta=alt.Theta("qty:Q"), color=alt.Color("cat:N", title="카테고리"))

    donut = base.mark_arc(innerRadius=innerR, outerRadius=outerR)

    # 리더 라인 + 외부 라벨(검정 글자)
    line = alt.Chart(donut_src).mark_line(color="#555").encode(
        x="x1:Q", y="y1:Q", x2="x2:Q", y2="y2:Q"
    )
    labels = alt.Chart(donut_src).mark_text(
        fontSize=12, fontWeight="bold", color="#000"
    ).encode(
        x="lx:Q", y="ly:Q", text="label:N", align="center", baseline="middle"
    )

    st.altair_chart((donut + line + labels).properties(height=380), use_container_width=True)

with c_right:
    st.subheader("📁 카테고리 요약")
    st.dataframe(
        cat_summary[["cat","qty","ratio"]].rename(columns={"cat":"카테고리","qty":"판매수량","ratio":"비율(%)"}),
        use_container_width=True, hide_index=True
    )

st.markdown("---")

# -------------------------
# 옵션 요약 (색상/사이즈 TOP)
# -------------------------
st.subheader("🎨 옵션 요약 (색상/사이즈 Top)")

# 색상
top_colors = (sold.groupby("color", as_index=False)["qty"].sum()
              .sort_values("qty", ascending=False).head(12))

# 사이즈
top_sizes = (sold.assign(size_norm=sold["size"].apply(norm_size))
             .groupby("size_norm", as_index=False)["qty"].sum()
             .sort_values("qty", ascending=False))

col1, col2 = st.columns(2)
with col1:
    color_chart = alt.Chart(top_colors).mark_bar().encode(
        x=alt.X("qty:Q", title="판매수량"),
        y=alt.Y("color:N", sort="-x", title="색상"),
        tooltip=["color","qty"]
    ).properties(height=360)
    st.altair_chart(color_chart, use_container_width=True)
with col2:
    size_chart = alt.Chart(top_sizes).mark_bar().encode(
        x=alt.X("qty:Q", title="판매수량"),
        y=alt.Y("size_norm:N", sort="-x", title="사이즈"),
        tooltip=[alt.Tooltip("size_norm", title="사이즈"),"qty"]
    ).properties(height=360)
    st.altair_chart(size_chart, use_container_width=True)

st.caption("※ 도넛은 판매수량 기준 비율입니다. (색상/사이즈는 각각 Top 항목을 보여줍니다)")
