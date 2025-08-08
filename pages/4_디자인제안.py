import streamlit as st
import pandas as pd
import numpy as np
from dateutil import parser
from collections import Counter
import requests
from bs4 import BeautifulSoup

# =========================
# 페이지 설정
# =========================
st.set_page_config(page_title="AI 의류 디자인 제안", layout="wide")
st.title("🧠✨ AI 의류 디자인 제안")

# =========================
# 유틸 함수
# =========================
def parse_date(dt):
    try:
        return parser.parse(str(dt).split('(')[0].strip(), fuzzy=True)
    except:
        return pd.NaT

@st.cache_data(show_spinner=False)
def load_sheet(sheet):
    import gspread
    from oauth2client.service_account import ServiceAccountCredentials
    import json
    URL = "https://docs.google.com/spreadsheets/d/.../edit"
    scope = ["https://spreadsheets.google.com/feeds","https://www.googleapis.com/auth/drive"]
    creds_json = {k: str(v) for k,v in st.secrets["gcp_service_account"].items()}
    with open("/tmp/sa.json","w") as f: json.dump(creds_json, f)
    creds = ServiceAccountCredentials.from_json_keyfile_name("/tmp/sa.json", scope)
    client = gspread.authorize(creds)
    ws = client.open_by_url(URL).worksheet(sheet)
    df = pd.DataFrame(ws.get_all_records())
    df.columns = [c.lower().strip() for c in df.columns]
    return df

def _clean(x):
    s = str(x).strip()
    return None if s.lower() in ["nan","none","-",""] else s

# 외부 트렌드 수집
def fetch_trends():
    trends = []
    res = requests.get("https://www.whowhatwear.com/fashion/summer/summer-2025-dress-trends")
    if res.ok:
        soup = BeautifulSoup(res.text, "html.parser")
        items = soup.select("li")[:5]
        for li in items:
            txt = li.get_text().strip()
            if txt:
                trends.append(txt)
    if not trends:
        trends = ["Polka dots revival", "Drop-waist silhouettes", "Meaningful minimalism"]
    return trends

# =========================
# 데이터 로드 및 설정
# =========================
df_info = load_sheet("PRODUCT_INFO")
df_temu = load_sheet("TEMU_SALES")
df_shein = load_sheet("SHEIN_SALES")

df_info_cols = ["neckline","length","fit","detail","style mood"]
IMG_MAP = dict(zip(df_info["product number"].astype(str), df_info.get("image","")))

# 날짜 입력
st.sidebar.header("필터 설정")
dr = st.sidebar.date_input("분석 기간", value=(pd.to_datetime("2025-06-01"), pd.to_datetime("2025-08-01")))
if isinstance(dr, (list,tuple)) and len(dr)==2:
    start_date, end_date = dr
else:
    st.error("기간을 시작 날짜와 종료 날짜로 설정하세요.")
    st.stop()

platform = st.sidebar.selectbox("플랫폼", ["TEMU", "SHEIN", "BOTH"])

topN = st.sidebar.slider("상위 스타일 수", 10, 100, 30)

season = st.sidebar.selectbox("시즌 설정", ["summer"], index=0)

# =========================
# 판매 집계
# =========================
def aggregate_sales(df, date_col, qty_col, style_col):
    df2 = df[(df[date_col]>=start_date)&(df[date_col]<=end_date)]
    df2 = df2[df2[qty_col].notna()]
    return df2.groupby(style_col)[qty_col].sum().reset_index().rename(columns={style_col:"style", qty_col:"qty"})

frames = []
if platform in ["TEMU","BOTH"]:
    t = df_temu.copy()
    t["order date"] = t["purchase date"].apply(parse_date)
    t = t[t["order date"].between(start_date, end_date)]
    t = t[t["order item status"].str.lower().isin(["shipped","delivered"])]
    t["quantity shipped"] = pd.to_numeric(t["quantity shipped"], errors="coerce").fillna(0)
    frames.append(aggregate_sales(t, "order date", "quantity shipped", "product number"))
if platform in ["SHEIN","BOTH"]:
    s = df_shein.copy()
    s["order date"] = s["order processed on"].apply(parse_date)
    s = s[s["order date"].between(start_date, end_date)]
    s = s[~s["order status"].str.lower().isin(["customer refunded"])]
    s["qty"] = 1
    frames.append(aggregate_sales(s, "order date", "qty", "product description"))

if not frames:
    st.error("판매 데이터가 없습니다.")
    st.stop()

sales = pd.concat(frames, ignore_index=True)
sales = sales.sort_values("qty", ascending=False).head(topN)
merged = sales.merge(df_info, left_on="style", right_on="product number", how="left")

# =========================
# 속성 요약
# =========================
attr_counts = {c: Counter(merged[c].dropna().astype(str)) for c in df_info_cols}
dominant = {c: attr_counts[c].most_common(1)[0][0] if attr_counts[c] else "-" for c in df_info_cols}

# =========================
# 디자인 브리프 & 트렌드 섹션
# =========================
trend_list = fetch_trends()

st.subheader("디자인 브리프 & 트렌드 인사이트")

st.markdown(f"""
- **분석 기간**: `{start_date.date()} ~ {end_date.date()}`
- **플랫폼**: **{platform}**
- **시즌**: **{season}**

**핵심 속성 (상위 스타일 기반)**:
- neckline: **{dominant.get('neckline','-')}**
- length: **{dominant.get('length','-')}**
- fit: **{dominant.get('fit','-')}**
- detail: **{dominant.get('detail','-')}**
- style mood: **{dominant.get('style mood','-')}**

**2025 여름 패션 유행 트렌드 참고**:
""", unsafe_allow_html=True)

for t in trend_list:
    st.markdown(f"- {t}")

st.subheader("생성 프롬프트 안내")
st.markdown("아래 디자인 프롬프트를 **ChatGPT (DALL·E 3 모델)**에 붙여넣으면 유사한 이미지 디자인을 바로 생성할 수 있습니다.")
