# pages/4_디자인제안.py
import streamlit as st
import pandas as pd
import numpy as np
from dateutil import parser
from collections import Counter
from math import ceil

# =========================
# 기본 설정
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

def _clean(x):
    s = str(x).strip()
    return s if s and s.lower() not in ["nan","none","-",""] else None

def season_of_month(m: int) -> str:
    if m in [3,4,5]: return "Spring"
    if m in [6,7,8]: return "Summer"
    if m in [9,10,11]: return "Fall"
    return "Winter"  # 12,1,2

def months_ago(ts: pd.Timestamp) -> int:
    today = pd.Timestamp.today()
    return max(0, (today.year - ts.year) * 12 + (today.month - ts.month))

def season_sets(target: str):
    target = target.capitalize()
    if target == "Spring":
        return set([3,4,5]), set([2,6])
    if target == "Summer":
        return set([6,7,8]), set([5,9])
    if target == "Fall":
        return set([9,10,11]), set([8,12])
    return set([12,1,2]), set([11,3])  # Winter

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
IMG_MAP = dict(zip(df_info.get("product number", pd.Series(dtype=str)).astype(str), df_info.get("image","")))

# 실제 사용하는 속성
ATTR_COLS = ["neckline", "length", "fit", "detail", "style mood"]
for c in ATTR_COLS:
    if c not in df_info.columns:
        df_info[c] = None  # 안전

# =========================
# 사이드바: 수동 시즌/연도 & 기타
# =========================
st.sidebar.header("⚙️ 설정")
platform = st.sidebar.radio("플랫폼", ["TEMU", "SHEIN", "BOTH"], horizontal=True)
year = st.sidebar.number_input("예측 연도", min_value=2024, max_value=2030, value=2025, step=1)
season = st.sidebar.selectbox("타깃 시즌", ["Spring","Summer","Fall","Winter"], index=1)
topN = st.sidebar.slider("분석 상위 스타일 수 (가중치 반영)", 10, 200, 50)
num_variants = st.sidebar.slider("생성 프롬프트 개수", 1, 6, 3)
goal = st.sidebar.selectbox("디자인 목적", ["리스크 적고 안전한 변형","트렌드 반영(전진형)","원가절감형(가성비)"], index=0)

# =========================
# (핵심) 가중치 계산: 전체 데이터 기반 + 시즌/연도 치중
# =========================
target_months, adjacent_months = season_sets(season)

def row_weight(order_dt: pd.Timestamp) -> float:
    if pd.isna(order_dt): return 0.0
    m = int(order_dt.month)
    y = int(order_dt.year)
    w_season = 1.0 if m in target_months else (0.7 if m in adjacent_months else 0.4)
    # 타깃 연도의 직전 시즌(예: 2025 Winter → 2024 Dec/2025 Jan/Feb) 가중치 +
    prev_year_boost = 1.0
    if m in target_months and (y == year-1 or (season=="Winter" and ((y==year and m in [1,2]) or (y==year-1 and m==12)))):
        prev_year_boost = 1.3
    # 최신 데이터 가중(최근 18개월 1.0, 그 외 0.7)
    rec = months_ago(order_dt)
    w_recency = 1.0 if rec <= 18 else 0.7
    return w_season * prev_year_boost * w_recency

# =========================
# 판매 집계(전체 데이터) + 가중치 적용
# =========================
def build_weighted_sales():
    frames=[]
    if platform in ["TEMU","BOTH"]:
        t = df_temu.copy()
        t = t[t["order item status"].astype(str).str.lower().isin(["shipped","delivered"])]
        t["qty"] = pd.to_numeric(t["quantity shipped"], errors="coerce").fillna(0)
        t["w"] = t["order date"].apply(row_weight)
        t["wqty"] = t["qty"] * t["w"]
        t = t.groupby("product number", as_index=False)["wqty"].sum()
        t = t.rename(columns={"product number":"style"})
        frames.append(t)
    if platform in ["SHEIN","BOTH"]:
        s = df_shein.copy()
        s = s[~s["order status"].astype(str).str.lower().isin(["customer refunded"])]
        s["qty"] = 1.0
        s["w"] = s["order date"].apply(row_weight)
        s["wqty"] = s["qty"] * s["w"]
        s = s.groupby("product description", as_index=False)["wqty"].sum()
        s = s.rename(columns={"product description":"style"})
        frames.append(s)
    if not frames:
        return pd.DataFrame(columns=["style","wqty"])
    return pd.concat(frames, ignore_index=True)

w_sales = build_weighted_sales()
if w_sales.empty:
    st.info("데이터가 없습니다. 시트를 확인하세요.")
    st.stop()

# 상위 N 스타일
top_styles = w_sales.sort_values("wqty", ascending=False).head(topN)["style"].astype(str).tolist()

# 상위 N 상세 조인
info = df_info.copy()
info.rename(columns={"product number":"style"}, inplace=True)
info["style"] = info["style"].astype(str)
top_df = info[info["style"].isin(top_styles)].copy()

# =========================
# 속성 집계 (가중 카운트)
# =========================
# 스타일별 가중치 합을 다시 매핑하여 속성에 곱함
style_w = dict(zip(w_sales["style"].astype(str), w_sales["wqty"]))
attr_counts = {c: Counter() for c in ATTR_COLS}
for _, r in top_df.iterrows():
    sw = style_w.get(str(r["style"]), 0.0)
    for c in ATTR_COLS:
        v = _clean(r.get(c))
        if v and sw>0:
            attr_counts[c][v] += sw

dominant = {c: (attr_counts[c].most_common(1)[0][0] if attr_counts[c] else "-") for c in ATTR_COLS}

# =========================
# 시즌 보정(라이트) — 제공 컬럼만 활용
# =========================
def adjust_attrs_for_season(attrs:dict, season:str):
    a = attrs.copy()
    s = season.lower()
    # 결측만 보정; 과도한 변형 없이 시즌 정합성만 채움
    if s == "summer":
        if not _clean(a.get("length")): a["length"] = "midi"
        if not _clean(a.get("fit")):    a["fit"]    = "slim"
    elif s == "spring":
        if not _clean(a.get("fit")):    a["fit"]    = "regular"
    elif s == "fall":
        if not _clean(a.get("fit")):    a["fit"]    = "regular"
    else:  # winter
        if not _clean(a.get("fit")):    a["fit"]    = "regular"
        if not _clean(a.get("length")): a["length"] = "midi"
    return {k:(v if _clean(v) else "-") for k,v in a.items()}

adj_attrs = adjust_attrs_for_season(dominant, season)

# =========================
# 트렌드 인사이트 (예측) — 시즌/연도별, 내부 데이터 기반 가중 + 규칙
# =========================
def forecast_trends(year:int, season:str, attr_counts:dict) -> list[str]:
    s = season.lower()
    bullets = []

    # 1) 내부 데이터 기반 상위 속성 3개(시즌 가중 반영)
    top_attr_lines = []
    for col in ["fit","length","neckline","detail","style mood"]:
        if attr_counts.get(col) and len(attr_counts[col])>0:
            v, amt = attr_counts[col].most_common(1)[0]
            top_attr_lines.append(f"{col}: `{v}` 상향")
    if top_attr_lines:
        bullets.append(f"{year} {season} 예측(내부 데이터 가중): " + "; ".join(top_attr_lines[:3]))

    # 2) 시즌별 규칙적 제안(휴리스틱)
    if s == "summer":
        bullets += [
            f"{year} {season} 예측: 경량 소재 감성의 슬림 실루엣 유지, 과한 컷아웃 대신 절제된 슬릿 포인트",
            f"{year} {season} 예측: 저채도 솔리드/톤온톤 팔레트, 실용 디테일(포켓) 수요 지속",
        ]
    elif s == "spring":
        bullets += [
            f"{year} {season} 예측: 소프트 파스텔·아이시 뉴트럴, 셔링/드레이핑 완만한 증가",
            f"{year} {season} 예측: 미디 길이의 레귤러~슬림 핏, 미니멀 하드웨어",
        ]
    elif s == "fall":
        bullets += [
            f"{year} {season} 예측: 니트/저지 드레스 비중 확대, 세미핏 또는 살짝 릴랙스드",
            f"{year} {season} 예측: 톤다운 뉴트럴 중심, 텍스처(립/핀턱) 포인트",
        ]
    else:  # winter
        bullets += [
            f"{year} {season} 예측: 하이넥/목선 커버 실루엣, 롱 슬리브 전환 제안",
            f"{year} {season} 예측: 맥시 길이 선호와 실용 디테일(패치 포켓 등) 유지",
        ]

    # 3) 교차시즌 캐리오버 제안(예: 여름 인기 디테일을 겨울에 장착하되 긴팔로 변환)
    if s in ["fall","winter"]:
        bullets.append(f"{year} {season} 예측: 여름 인기 ‘슬릿/포켓/미니멀 디테일’을 유지하되 긴팔·높은 넥라인으로 계절 적합화")
    return bullets[:5]

trend_bullets = forecast_trends(year, season, attr_counts)

# =========================
# 레퍼런스 이미지(가중 상위 몇 개)
# =========================
ref_urls = []
top_styles_sorted = w_sales.sort_values("wqty", ascending=False)["style"].astype(str)
for s_id in top_styles_sorted.head(6):
    url = IMG_MAP.get(s_id, "")
    if isinstance(url, str) and url.startswith("http"):
        ref_urls.append(url)

# =========================
# 프롬프트 생성 (이미지 모델용) — closure/fabric/pattern 제거
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
    if _clean(attrs.get("neckline")):
        desc += f" with {attrs['neckline']} neckline"
    if _clean(attrs.get("detail")):
        desc += f", detail: {attrs['detail']}"
    if _clean(attrs.get('style mood')):
        desc += f", style mood: {attrs['style mood']}"
    desc += ". "
    parts.append(desc)
    parts.append("Photo-realistic studio shot, front view, full-length, flat background, even soft lighting. ")
    parts.append(goal_hint + ". ")
    parts.append(f"Variant #{variant}.")
    return "".join(parts)

prompts = [make_prompt(adj_attrs, season, i+1, ref_urls, goal) for i in range(num_variants)]

# =========================
# 출력
# =========================
left, right = st.columns([1.7, 1.3])

with left:
    st.subheader("📄 디자인 브리프")
    st.markdown(f"- 플랫폼: **{platform}**")
    st.markdown(f"- 타깃 시즌/연도: **{season} {year}**")
    st.markdown("**핵심 속성(시즌 보정 반영):**")
    st.markdown(f"""
- neckline: **{adj_attrs.get('neckline','-')}**
- length: **{adj_attrs.get('length','-')}**
- fit: **{adj_attrs.get('fit','-')}**
- detail: **{adj_attrs.get('detail','-')}**
- style mood: **{adj_attrs.get('style mood','-')}**
    """)

    st.markdown("**트렌드 인사이트(예측)**")
    for b in trend_bullets:
        st.markdown(f"- {b}")

    st.subheader("🎯 생성 프롬프트 (이미지 모델용)")
    st.caption("💡 아래 프롬프트를 **ChatGPT(이미지 생성 모델)**에 붙여넣으면 **DALL·E 3**로 바로 생성됩니다. Midjourney/Firefly/Leonardo에서도 사용 가능.")
    for i, p in enumerate(prompts, 1):
        st.markdown(f"**Prompt {i}**")
        st.code(p)

with right:
    st.subheader("🔎 레퍼런스(베스트셀러·가중치 반영)")
    if ref_urls:
        st.image(ref_urls, width=160, caption=[f"ref{i+1}" for i in range(len(ref_urls))])
    else:
        st.info("레퍼런스 이미지가 없습니다 (PRODUCT_INFO.image 컬럼 확인).")
