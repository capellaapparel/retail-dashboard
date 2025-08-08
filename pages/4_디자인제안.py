# pages/4_디자인제안.py
import streamlit as st
import pandas as pd
import numpy as np
from dateutil import parser
from collections import Counter
import os

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
    ws = client.open_by_url(GOOGLE_SHEET_URL).worksheet(sheet_name)
    df = pd.DataFrame(ws.get_all_records())
    df.columns = [c.lower().strip() for c in df.columns]
    return df

def _clean_str(x):
    s = str(x).strip()
    return s if s and s.lower() not in ["nan", "none", "-", ""] else None

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
# 사이드바 컨트롤 (수동 시즌)
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
topN = st.sidebar.slider("분석 상위 스타일 수", 10, 200, 50)

year = st.sidebar.number_input("예측 연도", min_value=2024, max_value=2030, value=2025, step=1)
season = st.sidebar.selectbox("타깃 시즌(수동)", ["Spring", "Summer", "Fall", "Winter"], index=1)

# (선택) OpenAI API 키 입력 → 있으면 트렌드 ‘예측’ 호출, 없으면 기본 리스트 사용
st.sidebar.markdown("---")
use_ai_trend = st.sidebar.checkbox("OpenAI로 시즌 트렌드 예측 사용", value=False)
api_key = None
if use_ai_trend:
    api_key = st.sidebar.text_input("OpenAI API Key (선택)", type="password")

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
# 트렌드 인사이트 (AI 예측 또는 기본 리스트)
# =========================
def curated_trends(year:int, season:str):
    season = season.lower()
    # 시즌별 "예측" 기본 리스트 (유지보수 쉬움)
    base = {
        "spring": [
            "소프트 파스텔 & 아이시 뉴트럴 팔레트",
            "라이트 레이어링: 얇은 니트/셔츠 드레스",
            "셔링·드레이핑 디테일 소폭 증가",
            "미디 길이의 슬림/레귤러 핏 상향",
            "미니멀 하드웨어, 실용 포켓/벨트 포인트"
        ],
        "summer": [
            "린넨/코튼 터치감의 경량 소재 선호",
            "슬림 핏 미디~맥시 길이 상향",
            "절제된 슬릿/컷아웃으로 통기성과 포인트",
            "무지/저채도 솔리드, 톤온톤 스타일링",
            "포켓/버튼 등 실용 디테일 결합"
        ],
        "fall": [
            "미디~롱 기장의 니트/저지 드레스 확대",
            "톤다운 뉴트럴·어스톤 포커스",
            "버튼·지퍼 대신 클린한 미니멀 클로징",
            "세미피트 혹은 살짝 릴랙스드 실루엣",
            "핀턱/와이드 립 등 텍스처 포인트"
        ],
        "winter": [
            "헤비게이지 니트·울 블렌드 소재",
            "하이넥·목선 커버 디자인 선호",
            "다크 뉴트럴 + 저채도 컬러 포인트",
            "롱 슬리브 & 맥시 길이 중심",
            "퀼팅/패치 포켓 등 실용성 강조"
        ],
    }
    # 연도 넣어 문구 강화
    return [f"{year} {season.title()} 예측: {t}" for t in base.get(season, [])]

def get_ai_trend(year:int, season:str, api_key:str|None):
    if not api_key:
        return curated_trends(year, season)
    try:
        # OpenAI SDK (>=1.x)
        from openai import OpenAI
        os.environ["OPENAI_API_KEY"] = api_key
        client = OpenAI()
        prompt = (
            f"Predict concise, actionable women's apparel trends for {year} {season}.\n"
            f"Return 5 bullets covering silhouettes, details, fabrics, and color directions, "
            f"optimised for mass-market dress design. No preamble."
        )
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role":"system","content":"You are a fashion trend forecaster for mass-market womenswear."},
                {"role":"user","content":prompt},
            ],
            temperature=0.7,
            max_tokens=300,
        )
        text = resp.choices[0].message.content.strip()
        # 줄 단위 → 리스트
        lines = [l.strip("-• \n\r") for l in text.splitlines() if l.strip()]
        if not lines:
            return curated_trends(year, season)
        return [f"{year} {season.title()} 예측: {l}" for l in lines[:5]]
    except Exception:
        # 실패 시 기본 리스트
        return curated_trends(year, season)

trend_bullets = get_ai_trend(year, season, api_key if use_ai_trend else None)

# =========================
# 시즌 보정(라이트) — 제공 컬럼만 활용
# =========================
def adjust_attrs_for_season(attrs:dict, season:str):
    a = attrs.copy()
    s = season.lower()
    if s == "summer":
        if not _clean_str(a.get("length")): a["length"] = "midi"
        if not _clean_str(a.get("fit")):    a["fit"]    = "slim"
    elif s == "spring":
        if not _clean_str(a.get("fit")):    a["fit"]    = "regular"
    elif s == "fall":
        if not _clean_str(a.get("fit")):    a["fit"]    = "regular"
    else:  # winter
        if not _clean_str(a.get("fit")):    a["fit"]    = "regular"
        if not _clean_str(a.get("length")): a["length"] = "midi"
    # 남은 None/빈값은 "-" 처리
    return {k:(v if _clean_str(v) else "-") for k,v in a.items()}

adj_attrs = adjust_attrs_for_season(dominant_now, season)

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
    desc = f"Design a {season.lower()} {attrs.get('fit','-')} {attrs.get('length','-')} dress"
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
prompts = [make_prompt(adj_attrs, season, i+1, ref_urls, goal) for i in range(num_variants)]

# =========================
# 출력
# =========================
left, right = st.columns([1.7, 1.3])

with left:
    st.subheader("📄 디자인 브리프")
    st.markdown(f"- 분석기간: **{start_date.date()} ~ {end_date.date()}**")
    st.markdown(f"- 플랫폼: **{platform}**")
    st.markdown(f"- 타깃 시즌(예측 연도 포함): **{season} {year}**")
    st.markdown("**핵심 속성(시즌 보정 반영):**")
    st.markdown(f"""
- neckline: **{adj_attrs.get('neckline','-')}**
- length: **{adj_attrs.get('length','-')}**
- fit: **{adj_attrs.get('fit','-')}**
- detail: **{adj_attrs.get('detail','-')}**
- style mood: **{adj_attrs.get('style mood','-')}**
    """)

    st.markdown("**트렌드 인사이트 (AI 예측 / 기본 리스트):**")
    for b in trend_bullets:
        st.markdown(f"- {b}")

    st.subheader("🎯 생성 프롬프트 (이미지 모델용)")
    st.caption("💡 아래 프롬프트를 **ChatGPT(이미지 생성 모델)**에 붙여넣으면 **DALL·E 3**로 바로 생성됩니다. Midjourney/Firefly/Leonardo에서도 사용 가능.")
    for i, p in enumerate(prompts, 1):
        st.markdown(f"**Prompt {i}**")
        st.code(p)

with right:
    st.subheader("🔎 레퍼런스(베스트셀러)")
    if ref_urls:
        st.image(ref_urls, width=160, caption=[f"ref{i+1}" for i in range(len(ref_urls))])
    else:
        st.info("레퍼런스 이미지가 없습니다 (PRODUCT_INFO.image 컬럼 확인).")
