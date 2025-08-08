# pages/4_디자인제안.py
import streamlit as st
import pandas as pd
import numpy as np
from dateutil import parser
from collections import Counter
from urllib.parse import quote

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

def season_sets(target: str):
    t = target.capitalize()
    if t == "Spring": return set([3,4,5]), set([2,6])
    if t == "Summer": return set([6,7,8]), set([5,9])
    if t == "Fall":   return set([9,10,11]), set([8,12])
    return set([12,1,2]), set([11,3])  # Winter

# =========================
# 데이터 로드
# =========================
df_info  = load_google_sheet("PRODUCT_INFO")
df_temu  = load_google_sheet("TEMU_SALES")
df_shein = load_google_sheet("SHEIN_SALES")

df_temu["order date"]  = df_temu["purchase date"].apply(parse_temudate)
df_shein["order date"] = df_shein["order processed on"].apply(parse_sheindate)

IMG_MAP = dict(zip(df_info.get("product number", pd.Series(dtype=str)).astype(str),
                   df_info.get("image","")))

# 우리가 갖고있는 속성
ATTR_COLS = ["neckline", "length", "fit", "detail", "style mood"]
for c in ATTR_COLS:
    if c not in df_info.columns:
        df_info[c] = None

# =========================
# 사이드바: 시즌/카테고리/목적
# =========================
st.sidebar.header("⚙️ 설정")
platform = st.sidebar.radio("플랫폼", ["TEMU", "SHEIN", "BOTH"], horizontal=True)
year = st.sidebar.number_input("예측 연도", min_value=2024, max_value=2030, value=2025, step=1)
season = st.sidebar.selectbox("타깃 시즌", ["Spring","Summer","Fall","Winter"], index=1)

category = st.sidebar.selectbox(
    "카테고리",
    [
        "dress",
        "pants",
        "shorts",
        "sets (top+skirt)",
        "sets (top+pants/shorts)",
        "sets (3pcs)",
        "jumpsuits",
        "rompers",
        "top",
    ],
    index=0
)

topN = st.sidebar.slider("분석 상위 스타일 수 (가중치 반영)", 10, 200, 50)
num_variants = st.sidebar.slider("생성 프롬프트 개수", 1, 6, 3)

goal = st.sidebar.selectbox(
    "디자인 목적",
    ["리스크 적고 안전한 변형","트렌드 반영(전진형)","원가절감형(가성비)"],
    index=0
)

# =========================
# 가중치 계산 (전체 데이터 + 시즌 치중)
# =========================
target_months, adjacent_months = season_sets(season)

def months_ago(ts: pd.Timestamp) -> int:
    today = pd.Timestamp.today()
    return max(0, (today.year - ts.year) * 12 + (today.month - ts.month)) if pd.notna(ts) else 999

def row_weight(order_dt: pd.Timestamp) -> float:
    if pd.isna(order_dt): return 0.0
    m = int(order_dt.month)
    y = int(order_dt.year)
    w_season = 1.0 if m in target_months else (0.7 if m in adjacent_months else 0.4)
    # 직전 타깃 시즌(연도 고려) 부스트
    prev_year_boost = 1.0
    if m in target_months and (y == year-1 or (season=="Winter" and ((y==year and m in [1,2]) or (y==year-1 and m==12)))):
        prev_year_boost = 1.3
    # 최근성 보정
    rec = months_ago(order_dt)
    w_recency = 1.0 if rec <= 18 else 0.7
    return w_season * prev_year_boost * w_recency

def build_weighted_sales():
    frames=[]
    if platform in ["TEMU","BOTH"]:
        t = df_temu.copy()
        t = t[t["order item status"].astype(str).str.lower().isin(["shipped","delivered"])]
        t["qty"] = pd.to_numeric(t["quantity shipped"], errors="coerce").fillna(0)
        t["w"] = t["order date"].apply(row_weight)
        t["wqty"] = t["qty"] * t["w"]
        t = t.groupby("product number", as_index=False)["wqty"].sum().rename(columns={"product number":"style"})
        frames.append(t)
    if platform in ["SHEIN","BOTH"]:
        s = df_shein.copy()
        s = s[~s["order status"].astype(str).str.lower().isin(["customer refunded"])]
        s["qty"] = 1.0
        s["w"] = s["order date"].apply(row_weight)
        s["wqty"] = s["qty"] * s["w"]
        s = s.groupby("product description", as_index=False)["wqty"].sum().rename(columns={"product description":"style"})
        frames.append(s)
    if not frames:
        return pd.DataFrame(columns=["style","wqty"])
    return pd.concat(frames, ignore_index=True)

w_sales = build_weighted_sales()
if w_sales.empty:
    st.info("데이터가 없습니다. 시트를 확인하세요.")
    st.stop()

top_styles = w_sales.sort_values("wqty", ascending=False).head(topN)["style"].astype(str).tolist()

info = df_info.copy()
info.rename(columns={"product number":"style"}, inplace=True)
info["style"] = info["style"].astype(str)
top_df = info[info["style"].isin(top_styles)].copy()

style_w = dict(zip(w_sales["style"].astype(str), w_sales["wqty"]))

# =========================
# 속성 집계 (가중 카운트)
# =========================
attr_counts = {c: Counter() for c in ATTR_COLS}
for _, r in top_df.iterrows():
    sw = style_w.get(str(r["style"]), 0.0)
    for c in ATTR_COLS:
        v = _clean(r.get(c))
        if v and sw>0:
            attr_counts[c][v] += sw

dominant = {c: (attr_counts[c].most_common(1)[0][0] if attr_counts[c] else "-") for c in ATTR_COLS}

# =========================
# 시즌 보정(라이트)
# =========================
def adjust_attrs_for_season(attrs:dict, season:str):
    a = attrs.copy()
    s = season.lower()
    if s == "summer":
        if not _clean(a.get("length")): a["length"] = "midi"
        if not _clean(a.get("fit")):    a["fit"]    = "slim"
    elif s in ["spring","fall"]:
        if not _clean(a.get("fit")):    a["fit"]    = "regular"
    else:  # winter
        if not _clean(a.get("fit")):    a["fit"]    = "regular"
        if not _clean(a.get("length")): a["length"] = "midi"
    return {k:(v if _clean(v) else "-") for k,v in a.items()}

adj_attrs = adjust_attrs_for_season(dominant, season)

# =========================
# 트렌드 인사이트 (예측)
# =========================
def forecast_trends(year:int, season:str, attr_counts:dict) -> list[str]:
    s = season.lower()
    bullets = []
    top_attr_lines = []
    for col in ["fit","length","neckline","detail","style mood"]:
        if attr_counts.get(col) and len(attr_counts[col])>0:
            v, amt = attr_counts[col].most_common(1)[0]
            top_attr_lines.append(f"{col}: `{v}` 상향")
    if top_attr_lines:
        bullets.append(f"{year} {season} 예측(내부 데이터 가중): " + "; ".join(top_attr_lines[:3]))
    if s == "summer":
        bullets += [
            f"{year} {season} 예측: 경량감·절제된 슬릿/컷아웃, 저채도 솔리드/톤온톤",
            f"{year} {season} 예측: 슬림 핏 미디~맥시, 실용 디테일(포켓) 유지",
        ]
    elif s == "spring":
        bullets += [
            f"{year} {season} 예측: 파스텔/아이시 뉴트럴, 셔링/드레이핑 완만한 증가",
            f"{year} {season} 예측: 미디 길이 레귤러~슬림, 미니멀 하드웨어",
        ]
    elif s == "fall":
        bullets += [
            f"{year} {season} 예측: 니트/저지 드레스 확대, 세미핏·릴랙스드",
            f"{year} {season} 예측: 톤다운 뉴트럴, 텍스처(립/핀턱) 포인트",
        ]
    else:
        bullets += [
            f"{year} {season} 예측: 하이넥/목선 커버·롱 슬리브 전환",
            f"{year} {season} 예측: 맥시 길이 선호·실용 디테일(패치 포켓 등)",
        ]
    if s in ["fall","winter"]:
        bullets.append(f"{year} {season} 예측: 여름 인기 ‘슬릿/포켓/미니멀’ 유지하되 긴팔·높은 넥라인으로 계절 적합화")
    return bullets[:5]

trend_bullets = forecast_trends(year, season, attr_counts)

# =========================
# 레퍼런스 이미지
# =========================
ref_urls = []
top_styles_sorted = w_sales.sort_values("wqty", ascending=False)["style"].astype(str)
for sid in top_styles_sorted.head(6):
    u = IMG_MAP.get(sid, "")
    if isinstance(u, str) and u.startswith("http"):
        ref_urls.append(u)

# =========================
# 목적별 톤 차별화 + 카테고리 템플릿
# =========================
SAFE_TONE = (
    "commercial, mass‑market ready, conservative coverage, no risky cutouts, "
    "clean construction, minimal hardware, safe palette."
)
TREND_TONE = (
    "trend‑forward with controlled experimentation: subtle asymmetry or drape, "
    "light shirring/pleats, localized texture contrast, optional color pop accent, "
    "still mass‑market safe."
)
COST_TONE = (
    "cost‑effective construction: simplified panels, reduced seams and hardware, "
    "efficient fabric usage, maintain commercial appeal."
)

def goal_tone(goal:str)->str:
    return {"리스크 적고 안전한 변형": SAFE_TONE,
            "트렌드 반영(전진형)": TREND_TONE,
            "원가절감형(가성비)": COST_TONE}[goal]

def category_sentence(category:str, attrs:dict, season:str)->str:
    fit  = attrs.get("fit","-")
    leng = attrs.get("length","-")
    neck = attrs.get("neckline","-")
    det  = attrs.get("detail","-")
    mood = attrs.get("style mood","-")

    s = season.lower()
    parts = []

    if category == "dress":
        base = f"Design a {s} {fit} {leng} dress"
        if _clean(neck): base += f" with {neck} neckline"
        parts.append(base)
    elif category == "top":
        base = f"Design a {s} {fit} top"
        if _clean(neck): base += f" with {neck} neckline"
        parts.append(base)
    elif category == "pants":
        parts.append(f"Design {s} {fit} pants, ankle to full length")
    elif category == "shorts":
        parts.append(f"Design {s} {fit} shorts, mid to high rise")
    elif category == "jumpsuits":
        base = f"Design a {s} {fit} {leng} jumpsuit"
        if _clean(neck): base += f" with {neck} neckline"
        parts.append(base)
    elif category == "rompers":
        base = f"Design a {s} {fit} {leng} romper"
        if _clean(neck): base += f" with {neck} neckline"
        parts.append(base)
    elif category == "sets (top+skirt)":
        top_line   = f"a {fit} top" + (f" with {neck} neckline" if _clean(neck) else "")
        skirt_line = f"a {fit} {leng} skirt"
        parts.append(f"Design a {s} two‑piece set: {top_line} paired with {skirt_line}. Ensure modest overlap (no bare midriff).")
    elif category == "sets (top+pants/shorts)":
        top_line = f"a {fit} top" + (f" with {neck} neckline" if _clean(neck) else "")
        bottom   = "pants" if ("winter" in s or "fall" in s) else "shorts"
        parts.append(f"Design a {s} two‑piece set: {top_line} paired with {fit} {bottom}.")
    elif category == "sets (3pcs)":
        top_line = f"a {fit} top" + (f" with {neck} neckline" if _clean(neck) else "")
        third    = "light jacket" if s in ["spring","fall"] else ("cardigan" if s=="winter" else "shirt overlay")
        bottom   = "pants" if s in ["fall","winter"] else "skirt"
        parts.append(f"Design a {s} three‑piece set: {top_line}, {fit} {bottom}, and a {third}.")

    if _clean(det):
        parts.append(f"Detail: {det}.")
    if _clean(mood):
        parts.append(f"Style mood: {mood}.")
    return " ".join(parts)

# 이미지 강제 지시 헤더(텍스트 답변 방지)
IMAGE_HEADER = (
    "CREATE EXACTLY ONE IMAGE.\n"
    "Use the image-generation tool to render a single photo‑realistic studio product image.\n"
    "Canvas: 768x1152 (vertical), PNG. Plain flat background, even soft lighting.\n"
    "Do not write any text or captions—return the image only.\n"
    "Model‑free mannequin or clean flat‑lay. Garment centered, full‑length. No hands, props, or overlays.\n"
)

def make_prompt(attrs:dict, season:str, variant:int, refs:list, goal:str, category:str):
    parts = [IMAGE_HEADER]
    if refs:
        parts.append("Inspirations: " + ", ".join(refs[:2]) + ". ")
    parts.append(category_sentence(category, attrs, season) + " ")
    parts.append("Fabric grain and seams visible. ")
    parts.append(goal_tone(goal) + " ")
    parts.append(f"Variant #{variant}.")
    return "".join(parts)

def chatgpt_link(prompt: str) -> str:
    return f"[🖼️ ChatGPT에서 이미지 생성하기](https://chat.openai.com/?model=gpt-4o&input={quote(prompt)})"

prompts = [make_prompt(adj_attrs, season, i+1, ref_urls, goal, category) for i in range(num_variants)]

# =========================
# 출력
# =========================
left, right = st.columns([1.65, 1.35])

with left:
    st.subheader("📄 디자인 브리프")
    st.markdown(f"- 플랫폼: **{platform}**")
    st.markdown(f"- 타깃 시즌/연도: **{season} {year}**")
    st.markdown(f"- 카테고리: **{category}**")
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
    st.caption("👇 **클릭하면 ChatGPT(DALL·E 3)** 가 열리고 프롬프트가 자동 입력됩니다. (다른 이미지툴은 텍스트를 복사해 사용)")
    for i, p in enumerate(prompts, 1):
        st.markdown(f"**Prompt {i}**")
        st.code(p)
        st.markdown(chatgpt_link(p), unsafe_allow_html=True)
        st.divider()

with right:
    st.subheader("🔎 레퍼런스(베스트셀러·가중치 반영)")
    if ref_urls:
        st.image(ref_urls, width=160, caption=[f"ref{i+1}" for i in range(len(ref_urls))])
    else:
        st.info("레퍼런스 이미지가 없습니다 (PRODUCT_INFO.image 컬럼 확인).")
