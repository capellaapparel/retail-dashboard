# pages/4_디자인제안.py
import streamlit as st
import pandas as pd
import numpy as np
from dateutil import parser
from collections import Counter

# =========================
# 페이지 설정
# =========================
st.set_page_config(page_title="AI 의류 디자인 제안", layout="wide")
st.title("🧠✨ AI 의류 디자인 제안")

# =========================
# 유틸
# =========================
def parse_temudate(dt):
    try:
        return parser.parse(str(dt).split('(')[0].strip(), fuzzy=True)
    except Exception:
        return pd.NaT

def parse_sheindate(dt):
    try:
        return pd.to_datetime(str(dt), errors="coerce", infer_datetime_format=True)
    except Exception:
        return pd.NaT

@st.cache_data(show_spinner=False)
def load_google_sheet(sheet_name: str) -> pd.DataFrame:
    import gspread
    from oauth2client.service_account import ServiceAccountCredentials
    import json
    # ✅ 실제 사용 중인 시트 URL
    GOOGLE_SHEET_URL = "https://docs.google.com/spreadsheets/d/1oyVzCgGK1Q3Qi_sbYwE-wKG6SArnfUDRe7rQfGOF-Eo"
    scope = ["https://spreadsheets.google.com/feeds",
             "https://www.googleapis.com/auth/drive"]
    creds_json = {k: str(v) for k, v in st.secrets["gcp_service_account"].items()}
    with open("/tmp/service_account.json", "w") as f:
        json.dump(creds_json, f)
    creds = ServiceAccountCredentials.from_json_keyfile_name("/tmp/service_account.json", scope)
    client = gspread.authorize(creds)
    # ❗ URL이 바뀌면 여기만 수정
    ws = client.open_by_url(GOOGLE_SHEET_URL).worksheet(sheet_name)
    df = pd.DataFrame(ws.get_all_records())
    df.columns = [c.lower().strip() for c in df.columns]
    return df

def _clean_str(x):
    s = str(x).strip()
    return s if s and s.lower() not in ["nan", "none", "-", ""] else None

def month_to_season(m: int) -> str:
    # 미국만 고려: 북반구 기준
    if m in [12,1,2]: return "winter"
    if m in [3,4,5]:  return "spring"
    if m in [6,7,8]:  return "summer"
    return "fall"

# =========================
# 데이터 로드
# =========================
df_info  = load_google_sheet("PRODUCT_INFO")
df_temu  = load_google_sheet("TEMU_SALES")
df_shein = load_google_sheet("SHEIN_SALES")

# 날짜 파싱
df_temu["order date"]  = df_temu["purchase date"].apply(parse_temudate)
df_shein["order date"] = df_shein["order processed on"].apply(parse_sheindate)

# 이미지 맵
IMG_MAP = dict(zip(df_info.get("product number", pd.Series(dtype=str)).astype(str), df_info.get("image", "")))

# PRODUCT_INFO 실제 컬럼만 사용
ATTR_COLS = ["neckline", "length", "fit", "detail", "style mood"]

# =========================
# 사이드바 컨트롤
# =========================
st.sidebar.header("⚙️ 설정")

today = pd.Timestamp.today().normalize()
default_start = (today - pd.Timedelta(days=60)).date()
default_end   = today.date()
dr = st.sidebar.date_input("분석 기간", (default_start, default_end))
if isinstance(dr, (list, tuple)) and len(dr) == 2:
    start_date, end_date = map(pd.to_datetime, dr)
else:
    start_date = end_date = pd.to_datetime(dr)

platform = st.sidebar.radio("플랫폼", ["TEMU", "SHEIN", "BOTH"], horizontal=True)
auto_season = st.sidebar.checkbox("시즌 자동 감지(최근 판매월)", value=True)
manual_season = st.sidebar.selectbox("수동 시즌", ["spring","summer","fall","winter"], index=1)
topN = st.sidebar.slider("분석 상위 스타일 수", 10, 200, 50)

# 시즌 결정 (미국 기준)
if auto_season:
    frames = []
    if platform in ["TEMU", "BOTH"]:
        t = df_temu[(df_temu["order date"] >= start_date) & (df_temu["order date"] <= end_date)]
        t = t[t["order item status"].astype(str).str.lower().isin(["shipped","delivered"])]
        frames.append(t[["order date"]])
    if platform in ["SHEIN", "BOTH"]:
        s = df_shein[(df_shein["order date"] >= start_date) & (df_shein["order date"] <= end_date)]
        s = s[~s["order status"].astype(str).str.lower().isin(["customer refunded"])]
        frames.append(s[["order date"]])
    if frames:
        d = pd.concat(frames, ignore_index=True)
        if d.empty:
            target_season = manual_season
        else:
            seasons = d["order date"].dt.month.apply(month_to_season)
            target_season = seasons.mode().iloc[0] if not seasons.empty else manual_season
    else:
        target_season = manual_season
else:
    target_season = manual_season

# =========================
# 판매 집계 + 상위 N
# =========================
def get_sales_by_style():
    frames=[]
    if platform in ["TEMU","BOTH"]:
        t = df_temu[(df_temu["order date"]>=start_date)&(df_temu["order date"]<=end_date)].copy()
        t = t[t["order item status"].astype(str).str.lower().isin(["shipped","delivered"])]
        t["qty"] = pd.to_numeric(t["quantity shipped"], errors="coerce").fillna(0)
        t = t.groupby("product number")["qty"].sum().reset_index().rename(columns={"product number":"style"})
        frames.append(t)
    if platform in ["SHEIN","BOTH"]:
        sh = df_shein[(df_shein["order date"]>=start_date)&(df_shein["order date"]<=end_date)].copy()
        sh = sh[~sh["order status"].astype(str).str.lower().isin(["customer refunded"])]
        sh["qty"] = 1
        sh = sh.groupby("product description")["qty"].sum().reset_index().rename(columns={"product description":"style"})
        frames.append(sh)
    if not frames:
        return pd.DataFrame(columns=["style","qty"])
    return pd.concat(frames, ignore_index=True)

sales = get_sales_by_style()
if sales.empty:
    st.info("선택한 기간/플랫폼에 판매 데이터가 없습니다.")
    st.stop()

info = df_info.copy()
info.rename(columns={"product number":"style"}, inplace=True)
merged = sales.merge(info, on="style", how="left")
top_df = merged.sort_values("qty", ascending=False).head(topN).copy()

# =========================
# 속성 집계 (현재 기간)
# =========================
attr_counts = {c: Counter() for c in ATTR_COLS}
for _, r in top_df.iterrows():
    for c in ATTR_COLS:
        if c in top_df.columns:
            v = _clean_str(r.get(c))
            if v: attr_counts[c][v] += 1

dominant_now = {c: (attr_counts[c].most_common(1)[0][0] if attr_counts[c] else "-") for c in ATTR_COLS}

# =========================
# 트렌드 인사이트 (고정 리스트; 필요시 업데이트)
# =========================
def curated_trends_for_2025_summer():
    # 인터넷 크롤링 없이, 운영 중 깨지지 않게 유지하는 고정 인사이트
    return [
        "버블/버룬 헴라인과 드레이핑 실루엣이 주목",
        "슬림 핏 미디 길이의 미니멀 드레스 상향",
        "셔링/주름(플리츠) 포인트와 컷아웃의 절제된 사용",
        "깨끗한 솔리드 컬러 + 저채도의 파스텔 팔레트",
        "실용 디테일(포켓 등)과 캐주얼 무드의 결합 증가",
    ]

trend_bullets = curated_trends_for_2025_summer()

# =========================
# 시즌 보정(라이트) — 제공 컬럼만 활용
# =========================
def adjust_attrs_for_season(attrs:dict, season:str):
    a = attrs.copy()
    if season == "summer":
        if not _clean_str(a.get("length")): a["length"] = "midi"
        if not _clean_str(a.get("fit")):    a["fit"]    = "slim"
    elif season == "spring":
        if not _clean_str(a.get("fit")):    a["fit"]    = "regular"
    elif season == "fall":
        if not _clean_str(a.get("fit")):    a["fit"]    = "regular"
    else:  # winter
        if not _clean_str(a.get("fit")):    a["fit"]    = "regular"
        if not _clean_str(a.get("length")): a["length"] = "midi"
    # 남은 None/빈값은 "-" 처리
    return {k:(v if _clean_str(v) else "-") for k,v in a.items()}

adj_attrs = adjust_attrs_for_season(dominant_now, target_season)

# =========================
# 레퍼런스 이미지(상위 몇 개)
# =========================
ref_urls=[]
for s in top_df["style"].astype(str).head(6):
    u = IMG_MAP.get(s, "")
    if isinstance(u, str) and u.startswith("http"):
        ref_urls.append(u)

# =========================
# 프롬프트 생성 (이미지 모델용)
# =========================
def make_prompt(attrs:dict, season:str, variant:int, refs:list, goal:str):
    goal_hint = {
        "리스크 적고 안전한 변형": "commercial, mass-market ready, minimal risky details",
        "트렌드 반영(전진형)": "trend-forward, subtle editorial touch",
        "원가절감형(가성비)": "cost-effective construction, simplified detail",
    }[goal]
    parts=[]
    if refs:
        parts.append("Inspirations: " + ", ".join(refs[:4]) + ". ")
    desc = f"Design a {season} {attrs.get('fit','-')} {attrs.get('length','-')} dress"
    if _clean_str(attrs.get("neckline")):
        desc += f" with {attrs['neckline']} neckline"
    if _clean_str(attrs.get("detail")):
        desc += f", detail: {attrs['detail']}"
    if _clean_str(attrs.get('style mood')):
        desc += f", style mood: {attrs['style mood']}"
    desc += ". "
    parts.append(desc)
    parts.append("Photo-realistic studio shot, front view, full-length, flat background, even soft lighting. ")
    parts.append(goal_hint + ". ")
    parts.append(f"Variant #{variant}.")
    return "".join(parts)

goal = st.selectbox("디자인 목적", ["리스크 적고 안전한 변형","트렌드 반영(전진형)","원가절감형(가성비)"], index=0)
num_variants = st.slider("프롬프트 개수", 1, 6, 3)
prompts = [make_prompt(adj_attrs, target_season, i+1, ref_urls, goal) for i in range(num_variants)]

# =========================
# 출력
# =========================
left, right = st.columns([1.7, 1.3])

with left:
    st.subheader("📄 디자인 브리프")
    st.markdown(f"- 분석기간: **{start_date.date()} ~ {end_date.date()}**")
    st.markdown(f"- 플랫폼: **{platform}**")
    st.markdown(f"- 타깃 시즌: **{target_season}**")
    st.markdown("**핵심 속성(시즌 보정 반영):**")
    st.markdown(f"""
- neckline: **{adj_attrs.get('neckline','-')}**
- length: **{adj_attrs.get('length','-')}**
- fit: **{adj_attrs.get('fit','-')}**
- detail: **{adj_attrs.get('detail','-')}**
- style mood: **{adj_attrs.get('style mood','-')}**
    """)
    st.markdown("**트렌드 인사이트(레퍼런스 & 내부 데이터 요약):**")
    for b in trend_bullets:
        st.markdown(f"- {b}")

    st.subheader("🎯 생성 프롬프트 (이미지 모델용)")
    st.caption("💡 아래 프롬프트를 **ChatGPT**(이미지 생성 모델) 에 붙여넣으면 **DALL·E 3**로 바로 생성됩니다. Midjourney/Firefly/Leonardo에서도 사용 가능.")
    for i, p in enumerate(prompts, 1):
        st.markdown(f"**Prompt {i}**")
        st.code(p)

with right:
    st.subheader("🔎 레퍼런스(베스트셀러)")
    if ref_urls:
        st.image(ref_urls, width=160, caption=[f"ref{i+1}" for i in range(len(ref_urls))])
    else:
        st.info("레퍼런스 이미지가 없습니다 (PRODUCT_INFO.image 컬럼 확인).")
