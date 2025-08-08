# pages/3_디자인_제안.py
import streamlit as st
import pandas as pd
import numpy as np
from dateutil import parser
from collections import Counter
import re
import os

# ---------------------------
# 기본 세팅
# ---------------------------
st.set_page_config(page_title="AI 의류 디자인 제안", layout="wide")
st.title("🧠✨ AI 의류 디자인 제안")

# ---------------------------
# 공통 유틸
# ---------------------------
def parse_temudate(dt):
    try: return parser.parse(str(dt).split('(')[0].strip(), fuzzy=True)
    except: return pd.NaT

def parse_sheindate(dt):
    try: return pd.to_datetime(str(dt), errors="coerce", infer_datetime_format=True)
    except: return pd.NaT

@st.cache_data(show_spinner=False)
def load_google_sheet(sheet_name):
    import gspread
    from oauth2client.service_account import ServiceAccountCredentials
    import json
    GOOGLE_SHEET_URL = "https://docs.google.com/spreadsheets/d/1oyVzCgGK1Q3Qi_sbYwE-wKG6SArnfUDRe7rQfGOF-Eo"
    scope = ["https://spreadsheets.google.com/feeds","https://www.googleapis.com/auth/drive"]
    json_data = {k: str(v) for k,v in st.secrets["gcp_service_account"].items()}
    with open("/tmp/service_account.json","w") as f: json.dump(json_data, f)
    creds = ServiceAccountCredentials.from_json_keyfile_name("/tmp/service_account.json", scope)
    client = gspread.authorize(creds)
    ws = client.open_by_url(GOOGLE_SHEET_URL).worksheet(sheet_name)
    df = pd.DataFrame(ws.get_all_records())
    df.columns = [c.lower().strip() for c in df.columns]
    return df

def to_num(x):
    try:
        return float(str(x).replace("$","").replace(",",""))
    except:
        return np.nan

def mode_or_top(counter: Counter, default="-"):
    if not counter: return default
    return counter.most_common(1)[0][0]

def month_to_season(m: int, hemisphere="north"):
    # 간단 시즌 매핑
    if hemisphere=="north":
        if m in [12,1,2]: return "winter"
        if m in [3,4,5]:  return "spring"
        if m in [6,7,8]:  return "summer"
        return "fall"
    else:
        # south hemisphere 반대
        if m in [12,1,2]: return "summer"
        if m in [3,4,5]:  return "fall"
        if m in [6,7,8]:  return "winter"
        return "spring"

def clamp_text(s):
    s = str(s).strip()
    return s if s else "-"

# ---------------------------
# 데이터 로드
# ---------------------------
df_info  = load_google_sheet("PRODUCT_INFO")
df_temu  = load_google_sheet("TEMU_SALES")
df_shein = load_google_sheet("SHEIN_SALES")

# 날짜 컬럼 정리
df_temu["order date"]  = df_temu["purchase date"].apply(parse_temudate)
df_shein["order date"] = df_shein["order processed on"].apply(parse_sheindate)

# 상품 이미지 맵
IMG_MAP = dict(zip(df_info["product number"].astype(str), df_info.get("image","")))

# ---------------------------
# 사이드바 / 컨트롤
# ---------------------------
st.sidebar.header("⚙️ 설정")

# 기간 설정
today = pd.Timestamp.today().normalize()
default_start = (today - pd.Timedelta(days=60)).date()
default_end   = today.date()

date_range = st.sidebar.date_input("분석 기간", (default_start, default_end))
if isinstance(date_range, (list, tuple)) and len(date_range)==2:
    start_date, end_date = map(pd.to_datetime, date_range)
else:
    start_date = end_date = pd.to_datetime(date_range)

platform = st.sidebar.radio("플랫폼", ["TEMU","SHEIN","BOTH"], horizontal=True)
hemisphere = st.sidebar.selectbox("지역(계절 매핑)", ["north","south"], index=0)

# 타깃 시즌(자동/수동)
auto_season = st.sidebar.checkbox("시즌 자동 감지(최근 판매월)", value=True)
manual_season = st.sidebar.selectbox("수동 시즌", ["spring","summer","fall","winter"], index=1)

target_season = None
if auto_season:
    # 최근 판매월 기반으로 가장 많은 시즌 선택
    sales_df = []
    if platform in ["TEMU","BOTH"]:
        s = df_temu[(df_temu["order date"]>=start_date)&(df_temu["order date"]<=end_date)]
        s = s[s["order item status"].astype(str).str.lower().isin(["shipped","delivered"])]
        sales_df.append(s[["order date"]])
    if platform in ["SHEIN","BOTH"]:
        s = df_shein[(df_shein["order date"]>=start_date)&(df_shein["order date"]<=end_date)]
        s = s[~s["order status"].astype(str).str.lower().isin(["customer refunded"])]
        sales_df.append(s[["order date"]])
    if sales_df:
        d = pd.concat(sales_df)
        seasons = d["order date"].dt.month.apply(lambda m: month_to_season(m, hemisphere))
        target_season = seasons.mode().iloc[0] if not seasons.empty else "summer"
    else:
        target_season = "summer"
else:
    target_season = manual_season

# 설계 옵션
goal = st.sidebar.selectbox("디자인 목적", [
    "리스크 적고 안전한 변형",
    "트렌드 반영(전진형)",
    "원가절감형(가성비)"
], index=0)

force_long_sleeve = st.sidebar.checkbox("긴팔 고정", value=False)
num_variants = st.sidebar.slider("디자인 수", 1, 6, 3)

st.sidebar.markdown("---")
st.sidebar.caption("※ 하단에서 이미지 생성 엔진/API를 선택할 수 있습니다. 키가 없으면 프롬프트만 출력됩니다.")

# ---------------------------
# 1) 베스트셀러 추출 + 속성 집계
# ---------------------------
def get_sold_subset():
    subsets = []
    if platform in ["TEMU","BOTH"]:
        t = df_temu[(df_temu["order date"]>=start_date)&(df_temu["order date"]<=end_date)]
        t = t[t["order item status"].astype(str).str.lower().isin(["shipped","delivered"])].copy()
        t["qty"] = pd.to_numeric(t["quantity shipped"], errors="coerce").fillna(0)
        t = t.groupby("product number")["qty"].sum().reset_index().rename(columns={"product number":"style"})
        t["platform"]="TEMU"
        subsets.append(t)
    if platform in ["SHEIN","BOTH"]:
        s = df_shein[(df_shein["order date"]>=start_date)&(df_shein["order date"]<=end_date)]
        s = s[~s["order status"].astype(str).str.lower().isin(["customer refunded"])].copy()
        s["qty"] = 1
        s = s.groupby("product description")["qty"].sum().reset_index().rename(columns={"product description":"style"})
        s["platform"]="SHEIN"
        subsets.append(s)
    if not subsets: 
        return pd.DataFrame(columns=["style","qty","platform"])
    return pd.concat(subsets, ignore_index=True)

sold = get_sold_subset()
if sold.empty:
    st.info("선택한 조건에 판매 데이터가 없습니다.")
    st.stop()

# info와 조인
info = df_info.copy()
info.rename(columns={"product number":"style"}, inplace=True)
merged = sold.merge(info, on="style", how="left")

# 상위 N 추출
topN = st.slider("분석할 상위 스타일 수", 10, 200, 50)
top_df = merged.sort_values("qty", ascending=False).head(topN)

# 속성 후보 컬럼
ATTR_COLS = ["sleeve","length","fit","neckline","closure","fabric","pattern"]

# 속성 카운트
attr_counts = {c: Counter() for c in ATTR_COLS}
for _, row in top_df.iterrows():
    for c in ATTR_COLS:
        if c in top_df.columns:
            val = str(row.get(c,"")).strip().lower()
            if val and val not in ["nan","none","-",""]:
                attr_counts[c][val]+=1

dominants = {c: mode_or_top(attr_counts[c]) for c in ATTR_COLS}

# ---------------------------
# 2) 시즌 규칙에 따른 보정
# ---------------------------
def adjust_by_season(attrs: dict, season: str, force_long: bool):
    a = attrs.copy()
    # 기본 보정 룰(원하는대로 틴팅 가능)
    if season == "summer":
        a["fabric"]   = a.get("fabric","lightweight knit")
        a["fit"]      = a.get("fit","relaxed")
        a["length"]   = a.get("length","mini") if a.get("length","-")=="-" else a["length"]
        a["neckline"] = a.get("neckline","v-neck")
        a["pattern"]  = a.get("pattern","solid")
        a["sleeve"]   = "long sleeve" if force_long else a.get("sleeve","short sleeve")
    elif season == "spring":
        a["fabric"]   = a.get("fabric","light cotton blend")
        a["fit"]      = a.get("fit","regular")
        a["neckline"] = a.get("neckline","square neck")
        a["pattern"]  = a.get("pattern","floral")
        a["sleeve"]   = "long sleeve" if force_long else a.get("sleeve","3/4 sleeve")
    elif season == "fall":
        a["fabric"]   = a.get("fabric","medium-weight knit")
        a["fit"]      = a.get("fit","regular")
        a["neckline"] = a.get("neckline","round neck")
        a["pattern"]  = a.get("pattern","solid")
        a["sleeve"]   = "long sleeve"  # 가을은 기본 롱슬리브
    else: # winter
        a["fabric"]   = a.get("fabric","thermal knit")
        a["fit"]      = a.get("fit","regular")
        a["neckline"] = a.get("neckline","mock neck")
        a["pattern"]  = a.get("pattern","solid")
        a["sleeve"]   = "long sleeve"

    # 클로저 기본값
    if a.get("closure","-") in ["-","none",""]:
        a["closure"] = "button front" if "button" in " ".join(attr_counts["closure"].keys()) else "pullover"

    # 안전장치
    for k,v in a.items():
        a[k] = clamp_text(v)
    return a

adj_attrs = adjust_by_season(dominants, target_season, force_long_sleeve)

# ---------------------------
# 3) 레퍼런스(영감) 이미지 수집
# ---------------------------
ref_imgs = []
for s in top_df["style"].astype(str).head(6):
    url = IMG_MAP.get(s, "")
    if isinstance(url,str) and url.startswith("http"):
        ref_imgs.append(url)

# ---------------------------
# 4) 디자인 브리프 + 프롬프트 생성
# ---------------------------
def make_brief(attrs, season, goal):
    bullets = []
    bullets.append(f"시즌: **{season}**")
    for k in ATTR_COLS:
        bullets.append(f"- {k}: **{attrs.get(k,'-')}**")
    # 목표별 가이드
    if goal == "리스크 적고 안전한 변형":
        bullets.append("- 실루엣은 기존 베스트셀러와 유사하게, 과도한 디테일 지양")
        bullets.append("- 원가 범위 내에서 소재/원단 변경 최소화")
    elif goal == "트렌드 반영(전진형)":
        bullets.append("- 톤온톤 대비/질감 미스매치 포인트 1개 추가")
        bullets.append("- 미세한 오버 핏 또는 크롭 비율로 실루엣 업데이트")
    else: # 원가절감형
        bullets.append("- 봉제 공정 수를 줄이는 디테일 선택")
        bullets.append("- 단추 수/지퍼/트림 최소화")
    return bullets

def make_prompt(attrs, season, goal, style_variant=1, refs=None):
    # 이미지 생성 프롬프트 (DALL·E/Firefly/Midjourney 공용 서술형)
    ref_part = ""
    if refs:
        ref_part = "Inspirations: " + ", ".join(refs[:4]) + ". "

    goal_hint = {
        "리스크 적고 안전한 변형": "commercial, mass-market ready, minimal risky details",
        "트렌드 반영(전진형)": "trend-forward, editorial touch, subtle fashion-forward silhouette",
        "원가절감형(가성비)": "cost-effective construction, minimal trims, simplified panels"
    }[goal]

    return (
        f"{ref_part}"
        f"Design a {season} {attrs.get('fit','regular')} {attrs.get('length','mini')} dress with "
        f"{attrs.get('sleeve','long sleeve')}, {attrs.get('neckline','round neck')}, "
        f"{attrs.get('closure','pullover')}. "
        f"Fabric: {attrs.get('fabric','lightweight knit')}. "
        f"Pattern/Surface: {attrs.get('pattern','solid')}. "
        f"Color: season-appropriate palette. "
        f"Photo-realistic studio shot, front view, flat background. "
        f"{goal_hint}. "
        f"Variant #{style_variant}."
    )

brief_lines = make_brief(adj_attrs, target_season, goal)

# 여러 변형 프롬프트 생성
prompts = [make_prompt(adj_attrs, target_season, goal, i+1, ref_imgs) for i in range(num_variants)]

# ---------------------------
# 5) 출력 (브리프/프롬프트/레퍼런스)
# ---------------------------
left, right = st.columns([1.6, 1.4])
with left:
    st.subheader("📝 디자인 브리프")
    st.markdown(f"- 분석기간: **{start_date.date()} ~ {end_date.date()}**")
    st.markdown(f"- 플랫폼: **{platform}**, 지역: **{hemisphere}**, 타깃 시즌: **{target_season}**")
    st.markdown("**핵심 속성(시즌 보정 반영):**")
    st.markdown("\n".join(brief_lines))

    st.subheader("🎯 생성 프롬프트 (이미지 모델용)")
    for i, p in enumerate(prompts, 1):
        st.markdown(f"**Prompt {i}**")
        st.code(p)

with right:
    st.subheader("🔎 레퍼런스(베스트셀러)")
    if ref_imgs:
        st.image(ref_imgs, width=160, caption=[f"ref{i+1}" for i in range(len(ref_imgs))])
    else:
        st.info("레퍼런스 이미지가 없습니다 (PRODUCT_INFO.image 컬럼 확인).")

# ---------------------------
# 6) (선택) 이미지 생성 실행
# ---------------------------
st.markdown("---")
st.subheader("🖼️ 이미지 생성 (선택)")

engine = st.radio("엔진", ["사용 안 함","OpenAI Images(DALL·E)","Stability SDXL"], horizontal=True)

if engine != "사용 안 함":
    api_key = st.text_input("API Key", type="password")
    idx = st.number_input("생성할 Prompt 번호", 1, len(prompts), 1, step=1)
    go = st.button("이미지 생성")
    if go:
        if not api_key:
            st.error("API Key를 입력하세요.")
        else:
            try:
                prompt = prompts[idx-1]
                if engine == "OpenAI Images(DALL·E)":
                    # OpenAI Images API 샘플 (pip install openai>=1.3.0)
                    from openai import OpenAI
                    os.environ["OPENAI_API_KEY"] = api_key
                    client = OpenAI()
                    img = client.images.generate(model="gpt-image-1", prompt=prompt, size="1024x1024")
                    url = img.data[0].url
                    st.image(url, caption="Generated (OpenAI)", use_column_width=True)
                    st.markdown(f"[원본 보기]({url})")

                elif engine == "Stability SDXL":
                    # Stability SDK 예시 (pip install stability-sdk)
                    import base64
                    import io
                    import stability_sdk.interfaces.gooseai.generation.generation_pb2 as generation
                    from stability_sdk import client as stab
                    os.environ["STABILITY_KEY"] = api_key
                    stability_api = stab.StabilityInference(
                        key=api_key,
                        engine="stable-diffusion-xl-1024-v1-0",
                        verbose=False,
                    )
                    answers = stability_api.generate(
                        prompt=prompt,
                        cfg_scale=7.0,
                        width=1024, height=1024,
                        sampler=generation.SAMPLER_K_DPMPP_2M
                    )
                    for rsp in answers:
                        for art in rsp.artifacts:
                            if art.type == generation.ARTIFACT_IMAGE:
                                img_bytes = art.binary
                                st.image(img_bytes, caption="Generated (SDXL)", use_column_width=True)
                else:
                    st.warning("엔진 선택이 올바르지 않습니다.")
            except Exception as e:
                st.exception(e)

# ---------------------------
# 끝
# ---------------------------

