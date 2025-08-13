# ==========================================
# File: pages/9_옵션_분석.py
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
        return m.group(1)
    return s_key

# -------------------------
# Load data
# -------------------------
info  = load_google_sheet("PRODUCT_INFO")
temu  = load_google_sheet("TEMU_SALES")
shein = load_google_sheet("SHEIN_SALES")

# parse dates
temu["order date"]  = temu["purchase date"].apply(parse_temudate)
shein["order date"] = shein["order processed on"].apply(parse_sheindate)

# status/qty
temu["order item status"] = temu["order item status"].astype(str)
temu["quantity shipped"]  = pd.to_numeric(temu.get("quantity shipped", 0), errors="coerce").fillna(0)

shein["order status"] = shein["order status"].astype(str)

# style keys
temu["style_key"]  = temu["product number"].astype(str).apply(style_key_from_label)
shein["style_key"] = shein["product description"].astype(str).apply(style_key_from_label)
info["style_key"]   = info["product number"].astype(str).apply(style_key_from_label)

# -------------------------
# 기간/플랫폼 컨트롤
# -------------------------
min_dt = pd.to_datetime(pd.concat([temu["order date"], shein["order date"]]).dropna()).min()
max_dt = pd.to_datetime(pd.concat([temu["order date"], shein["order date"]]).dropna()).max()

r1, r2 = st.columns([1.7,1])
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
    platform = st.radio("플랫폼", ["BOTH","TEMU","SHEIN"], horizontal=True)

# -------------------------
# 카테고리 매핑 (info.LENGTH + TEMU 제품명 보정)
# -------------------------
def calc_category(length_str: str) -> set:
    s = str(length_str).upper()
    parts = [p.strip() for p in s.split(",") if p.strip()]
    cats = set()
    for p in parts:
        if "TOP" in p:
            cats.add("TOP")
        elif "DRESS" in p:
            cats.add("DRESS")
        elif "SKIRT" in p:
            cats.add("SKIRT")
        elif any(x in p for x in ["SHORT", "KNEE", "CAPRI", "FULL", "PANTS"]):
            cats.add("PANTS")
    return cats

# 기본 카테고리
cat_map = {}
for _, r in info.iterrows():
    key = r["style_key"]
    cats = calc_category(r.get("length",""))
    if not cats:
        cat_map[key] = "PANTS"  # 기본값
    elif len(cats) >= 2:
        cat_map[key] = "SET"
    else:
        cat_map[key] = list(cats)[0]

# TEMU 제품명으로 ROMPER/JUMPSUIT 보정
if "product name by customer order" in temu.columns:
    tnames = temu[["style_key","product name by customer order"]].dropna()
    # 한 스타일에 여러 제품명 있을 수 있으니 가장 흔한 걸 사용
    tnames = tnames.groupby("style_key")["product name by customer order"].apply(lambda s: " ".join(map(str,s))).reset_index()
    for _, r in tnames.iterrows():
        name = str(r["product name by customer order"]).upper()
        if "ROMPER" in name:
            cat_map[r["style_key"]] = "ROMPER"
        elif "JUMPSUIT" in name:
            cat_map[r["style_key"]] = "JUMPSUIT"

# -------------------------
# 판매 집계 (기간/플랫폼 반영)
# -------------------------
frames = []
if platform in ["BOTH","TEMU"]:
    t = temu[(temu["order date"]>=start)&(temu["order date"]<=end)]
    t = t[t["order item status"].str.lower().isin(["shipped","delivered"])].copy()
    t["qty"] = t["quantity shipped"]
    frames.append(t[["style_key","qty","color","size"]])
if platform in ["BOTH","SHEIN"]:
    s = shein[(shein["order date"]>=start)&(shein["order date"]<=end)].copy()
    s = s[~s["order status"].str.lower().eq("customer refunded")]
    s["qty"] = 1
    # 색/사이즈 추출 (seller sku: STYLE-COLOR-SIZE)
    if "seller sku" in s.columns:
        parts = s["seller sku"].astype(str).str.split("-", n=2, expand=True)
        if parts.shape[1] >= 3:
            s["color"] = parts[1].str.replace("_"," ").str.title()
            s["size"]  = parts[2].str.upper().replace({"1XL":"1X","2XL":"2X","3XL":"3X","SMALL":"S","MEDIUM":"M","LARGE":"L"})
    frames.append(s[["style_key","qty","color","size"]])

if not frames:
    st.info("표시할 데이터가 없습니다.")
    st.stop()

sold = pd.concat(frames, ignore_index=True)
sold = sold.dropna(subset=["style_key"])
sold["cat"] = sold["style_key"].map(cat_map).fillna("PANTS")

# -------------------------
# 도넛 데이터 (카테고리)
# -------------------------
cat_summary = sold.groupby("cat")["qty"].sum().reset_index().rename(columns={"qty":"count"})
cat_summary = cat_summary.sort_values("count", ascending=False).reset_index(drop=True)
total_cnt = cat_summary["count"].sum()
cat_summary["ratio"] = (cat_summary["count"] / total_cnt * 100).round(1)
cat_summary["label"] = cat_summary.apply(lambda r: f"{r['cat']} ({r['ratio']}%)", axis=1)

# 라벨 좌표(리더라인용) 계산
# 각 조각의 중심각도(mid) 계산
angles = (cat_summary["count"] / total_cnt) * 2*np.pi
cat_summary["end"] = angles.cumsum()
cat_summary["start"] = cat_summary["end"] - angles
cat_summary["mid"] = (cat_summary["start"] + cat_summary["end"])/2.0
# 도넛 반지름
innerR, outerR = 70, 120
# 조각 외곽 좌표(라인 시작) / 라벨 좌표(라인 끝)
cat_summary["ox"] = outerR*np.cos(cat_summary["mid"])
cat_summary["oy"] = outerR*np.sin(cat_summary["mid"])
cat_summary["lx"] = (outerR+24)*np.cos(cat_summary["mid"])
cat_summary["ly"] = (outerR+24)*np.sin(cat_summary["mid"])
# 좌/우 분리
cat_right = cat_summary[cat_summary["ox"] >= 0].copy()
cat_left  = cat_summary[cat_summary["ox"] <  0].copy()

# -------------------------
# 레이아웃: 도넛(왼쪽) + 요약(오른쪽)
# -------------------------
st.markdown("### 📊 카테고리별 판매 비율 (도넛)")
c_l, c_r = st.columns([1.1, 1])

with c_l:
    # 도넛 본체
    pie = alt.Chart(cat_summary).mark_arc(innerRadius=innerR, outerRadius=outerR, stroke='white').encode(
        theta=alt.Theta("count:Q", stack=True, title=None),
        color=alt.Color("cat:N", title="카테고리"),
        tooltip=["cat:N","count:Q","ratio:Q"]
    ).properties(width=520, height=380)

    # 리더라인
    lines = alt.Chart(cat_summary).mark_rule(color="#888").encode(
        x="ox:Q", y="oy:Q", x2="lx:Q", y2="ly:Q"
    )

    # 라벨(오른쪽: left align)
    text_right = alt.Chart(cat_right).mark_text(align="left", baseline="middle", dx=6).encode(
        x="lx:Q", y="ly:Q", text="label:N", color=alt.value("#111")
    )
    # 라벨(왼쪽: right align)
    text_left = alt.Chart(cat_left).mark_text(align="right", baseline="middle", dx=-6).encode(
        x="lx:Q", y="ly:Q", text="label:N", color=alt.value("#111")
    )

    st.altair_chart(pie + lines + text_right + text_left, use_container_width=True)

with c_r:
    st.markdown("### 📁 카테고리 요약")
    st.dataframe(
        cat_summary[["cat","count","ratio"]].rename(columns={"cat":"카테고리","count":"판매수량","ratio":"비율(%)"}),
        use_container_width=True, hide_index=True
    )

# -------------------------
# 옵션 요약 (색상 / 사이즈 Top)
# -------------------------
st.markdown("### 🎨 옵션 요약 (색상/사이즈 Top)")
left, right = st.columns(2)

# 색상 TOP
color_top = (sold.dropna(subset=["color"])
                 .assign(color=lambda d: d["color"].astype(str).str.strip())
                 .query("color != ''")
                 .groupby("color")["qty"].sum()
                 .sort_values(ascending=False).head(12).reset_index())
with left:
    if not color_top.empty:
        cbar = alt.Chart(color_top).mark_bar().encode(
            y=alt.Y("color:N", sort='-x', title=None),
            x=alt.X("qty:Q", title="판매수량"),
            tooltip=["color","qty"]
        ).properties(height=320)
        st.altair_chart(cbar, use_container_width=True)
    else:
        st.caption("색상 데이터가 없습니다.")

# 사이즈 TOP (표준화)
size_fix = {"1XL":"1X","2XL":"2X","3XL":"3X","SMALL":"S","MEDIUM":"M","LARGE":"L"}
sold["size"] = sold["size"].astype(str).str.upper().replace(size_fix)

size_top = (sold.dropna(subset=["size"])
                .assign(size=lambda d: d["size"].astype(str).str.strip())
                .query("size != ''")
                .groupby("size")["qty"].sum()
                .sort_values(ascending=False).reset_index())
with right:
    if not size_top.empty:
        sbar = alt.Chart(size_top).mark_bar().encode(
            y=alt.Y("size:N", sort='-x', title=None),
            x=alt.X("qty:Q", title="판매수량"),
            tooltip=["size","qty"]
        ).properties(height=320)
        st.altair_chart(sbar, use_container_width=True)
    else:
        st.caption("사이즈 데이터가 없습니다.")
