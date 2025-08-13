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
    return pd.to_numeric(s.astype(str).str.replace(r"[^0-9.\-]","", regex=True), errors="coerce").fillna(0.0)

# 컬러/사이즈 정규화
def norm_color(c):
    s = str(c).strip().replace("_"," ").strip()
    return s if s else None

SIZE_MAP = {
    "1XL":"1X","2XL":"2X","3XL":"3X",
    "XL":"XL","XS":"XS","S":"S","M":"M","L":"L",
    "SMALL":"S","MEDIUM":"M","LARGE":"L"
}
def norm_size(sz):
    s = str(sz).strip().upper()
    if s in SIZE_MAP: return SIZE_MAP[s]
    return s or None

# 카테고리 분류
TOP_TOK   = {"CROP TOP","WAIST TOP","LONG TOP"}
DRESS_TOK = {"MINI DRESS","MIDI DRESS","MAXI DRESS"}
SKIRT_TOK = {"MINI SKIRT","MIDI SKIRT","MAXI SKIRT"}
PANTS_TOK = {"SHORTS","KNEE","CAPRI","FULL"}

def detect_cat(length_str, temu_name=""):
    tokens = [t.strip().upper() for t in str(length_str).split(",") if str(t).strip()]
    # 두 가지 이상 옵션 → SET
    if len(tokens) >= 2:
        return "SET"
    tok = tokens[0] if tokens else ""
    if tok in TOP_TOK:   return "TOP"
    if tok in DRESS_TOK: return "DRESS"
    if tok in SKIRT_TOK: return "SKIRT"
    if tok in PANTS_TOK: 
        # 이름에 점프수트/롬퍼 단서 있으면 우선
        name = str(temu_name).upper()
        if "JUMPSUIT" in name: return "JUMPSUIT"
        if "ROMPER"   in name: return "ROMPER"
        return "PANTS"
    # TEMU 이름에서 JUMPSUIT/ROMPER 탐지
    name = str(temu_name).upper()
    if "JUMPSUIT" in name: return "JUMPSUIT"
    if "ROMPER"   in name: return "ROMPER"
    # 기본값
    return "TOP"

# -------------------------
# Load
# -------------------------
info  = load_google_sheet("PRODUCT_INFO")
temu  = load_google_sheet("TEMU_SALES")
shein = load_google_sheet("SHEIN_SALES")

# 날짜 정규화
temu["order date"]  = temu["purchase date"].apply(parse_temudate)
shein["order date"] = shein["order processed on"].apply(parse_sheindate)

# 정규화
temu["order item status"] = temu["order item status"].astype(str)
temu["quantity shipped"]  = pd.to_numeric(temu.get("quantity shipped", 0), errors="coerce").fillna(0)
if "base price total" in temu.columns:
    temu["base price total"] = money_series(temu["base price total"])

shein["order status"] = shein["order status"].astype(str)
if "product price" in shein.columns:
    shein["product price"] = money_series(shein["product price"])

# 옵션 정규화(색상/사이즈)
temu["color"] = temu.get("color", "").apply(norm_color)
temu["size"]  = temu.get("size", "").apply(norm_size)
shein["color"] = shein.get("color", "").apply(norm_color)
shein["size"]  = shein.get("size", "").apply(norm_size)

# -------------------------
# Controls
# -------------------------
min_dt = pd.to_datetime(pd.concat([temu["order date"], shein["order date"]]).dropna()).min()
max_dt = pd.to_datetime(pd.concat([temu["order date"], shein["order date"]]).dropna()).max()

c1, c2 = st.columns([1.6,1])
with c1:
    dr = st.date_input(
        "조회 기간",
        value=(max_dt.date() - pd.Timedelta(days=29), max_dt.date()),
        min_value=min_dt.date(),
        max_value=max_dt.date(),
    )
    if isinstance(dr,(list,tuple)):
        start, end = dr
    else:
        start, end = dr, dr
    start = pd.to_datetime(start)
    end   = pd.to_datetime(end) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
with c2:
    platform = st.radio("플랫폼", ["BOTH","TEMU","SHEIN"], horizontal=True)

# -------------------------
# 판매 데이터(기간/상태 필터)
# -------------------------
T = temu[(temu["order date"]>=start)&(temu["order date"]<=end)].copy()
T = T[T["order item status"].str.lower().isin(["shipped","delivered"])]
T["qty"] = T["quantity shipped"]

S = shein[(shein["order date"]>=start)&(shein["order date"]<=end)].copy()
S = S[~S["order status"].str.lower().eq("customer refunded")]
S["qty"] = 1.0

# 카테고리 붙이기
# PRODUCT_INFO의 length를 매칭(스타일 번호 기준). TEMU는 product number, SHEIN은 product description 안의 스타일코드가 섞여 있을 수 있어
info_idx = info.set_index(info["product number"].astype(str).str.upper().str.replace(" ","", regex=False))

def get_len_from_info(pn):
    key = str(pn).upper().replace(" ","")
    if key in info_idx.index:
        return info_idx.loc[key].get("length","")
    return ""

T["cat"] = [detect_cat(get_len_from_info(pn), tn) for pn, tn in zip(T.get("product number",""), T.get("product name by customer order",""))]
S["cat"] = [detect_cat(get_len_from_info(pn), "") for pn in S.get("seller sku","")]  # seller sku로 info 매칭

# 플랫폼 필터
if platform == "TEMU":
    SOLD = T.copy()
elif platform == "SHEIN":
    SOLD = S.copy()
else:
    SOLD = pd.concat([T, S], ignore_index=True)

# -------------------------
# 1) 카테고리 요약(테이블)
# -------------------------
cat_summary = (SOLD.groupby("cat")
               .agg(qty=("qty","sum"),
                    sales=("base price total", lambda s: money_series(s).sum() if "base price total" in SOLD.columns else 0.0))
               .reset_index())
cat_summary = cat_summary.sort_values("qty", ascending=False)

st.subheader("📂 카테고리 요약")
st.dataframe(
    cat_summary.assign(비율=lambda d: d["qty"]/d["qty"].sum()*100)[["cat","qty","비율","sales"]]
        .rename(columns={"cat":"카테고리","qty":"판매수량","sales":"매출"}),
    use_container_width=True, hide_index=True
)

# -------------------------
# 2) 도넛 + 라벨(리더 라인) — 겹침 최소화
# -------------------------
st.subheader("📈 카테고리별 판매 비율 (도넛)")

if cat_summary["qty"].sum() == 0:
    st.info("표시할 데이터가 없습니다.")
else:
    # Arc(도넛) 자체는 Altair의 mark_arc 사용(데이터는 qty)
    color_domain = list(cat_summary["cat"])
    color_scale  = alt.Scale(domain=color_domain, scheme='tableau10')

    donut = alt.Chart(cat_summary).mark_arc(innerRadius=70, outerRadius=130).encode(
        theta=alt.Theta("qty:Q"),
        color=alt.Color("cat:N", scale=color_scale, title="카테고리"),
        tooltip=[alt.Tooltip("cat:N", title="카테고리"),
                 alt.Tooltip("qty:Q", title="판매수량", format=",.0f"),
                 alt.Tooltip("pct:Q", title="비율(%)", format=".1f")]
    ).transform_calculate(
        pct="datum.qty / datum.qty.sum() * 100"
    ).properties(height=420)

    # ----- 라벨 위치/리더 라인 데이터(파이 각도 직접 계산)
    d = cat_summary.copy()
    d["val"] = d["qty"].astype(float)
    d["f"]   = d["val"] / d["val"].sum()
    d["cum"] = d["f"].cumsum()
    d["start"] = 2*np.pi*(d["cum"] - d["f"])
    d["end"]   = 2*np.pi*d["cum"]
    d["mid"]   = (d["start"] + d["end"]) / 2

    R_OUT = 130
    R_LAB = 175  # 라벨 반지름(조금 멀리)
    # 조각 바깥쪽 점(리더 라인 시작점)
    d["lx"] = R_OUT * np.sin(d["mid"])
    d["ly"] = -R_OUT * np.cos(d["mid"])
    # 라벨 위치(좌우로 길게)
    d["tx"] = R_LAB * np.sin(d["mid"])
    d["ty"] = -R_LAB * np.cos(d["mid"])
    d["label"] = d["cat"] + " (" + (d["f"]*100).round(1).astype(str) + "%)"
    ann = d[["cat","lx","ly","tx","ty","label"]]

    # 리더 라인
    lines = alt.Chart(ann).mark_rule(color="#9aa0a6").encode(
        x="lx:Q", y="ly:Q", x2="tx:Q", y2="ty:Q"
    )

    # 라벨을 좌/우로 나눠 정렬(align)만 마크 속성으로 고정
    left_labels = alt.Chart(ann[ann["tx"] < 0]).mark_text(
        align="right", baseline="middle", fontSize=12, fontWeight="bold"
    ).encode(
        x="tx:Q", y="ty:Q", text="label:N"
    )

    right_labels = alt.Chart(ann[ann["tx"] >= 0]).mark_text(
        align="left", baseline="middle", fontSize=12, fontWeight="bold"
    ).encode(
        x="tx:Q", y="ty:Q", text="label:N"
    )

    st.altair_chart(donut + lines + left_labels + right_labels, use_container_width=True)

# -------------------------
# 3) 옵션 요약 (색상/사이즈 Top)
# -------------------------
st.subheader("🎨 옵션 요약 (색상/사이즈 Top)")

# 색상 TOP
col_left, col_right = st.columns(2)
with col_left:
    color_cnt = SOLD.dropna(subset=["color"]).groupby("color")["qty"].sum().sort_values(ascending=False).head(12)
    if color_cnt.empty:
        st.info("색상 데이터가 없습니다.")
    else:
        st.bar_chart(color_cnt, height=300)

with col_right:
    size_cnt = SOLD.dropna(subset=["size"]).groupby("size")["qty"].sum().sort_values(ascending=False).head(10)
    if size_cnt.empty:
        st.info("사이즈 데이터가 없습니다.")
    else:
        # 보기 좋게 사이즈 순서 정렬
        pref = ["XS","S","M","L","XL","1X","2X","3X"]
        order = [s for s in pref if s in size_cnt.index] + [s for s in size_cnt.index if s not in pref]
        size_cnt = size_cnt.reindex(order)
        st.bar_chart(size_cnt, height=300)
