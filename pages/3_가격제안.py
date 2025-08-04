import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from dateutil import parser

# 1. 구글시트 데이터 불러오기 (utils 함수 예시)
@st.cache_data(show_spinner=False)
def load_google_sheet(sheet_name):
    import gspread
    from oauth2client.service_account import ServiceAccountCredentials
    import json
    GOOGLE_SHEET_URL = "https://docs.google.com/spreadsheets/d/1oyVzCgGK1Q3Qi_sbYwE-wKG6SArnfUDRe7rQfGOF-Eo"
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive"
    ]
    json_data = {k: str(v) for k, v in st.secrets["gcp_service_account"].items()}
    with open("/tmp/service_account.json", "w") as f:
        json.dump(json_data, f)
    creds = ServiceAccountCredentials.from_json_keyfile_name("/tmp/service_account.json", scope)
    client = gspread.authorize(creds)
    sheet = client.open_by_url(GOOGLE_SHEET_URL).worksheet(sheet_name)
    data = sheet.get_all_records()
    df = pd.DataFrame(data)
    df.columns = [c.lower().strip() for c in df.columns]
    return df

# 2. OpenAI API (gpt-4o 사용)
def get_ai_price_suggestion(prompt):
    api_key = st.secrets.get("openai_api_key", "")
    if not api_key:
        return "OpenAI API Key 미설정"
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        resp = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}]
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        return f"AI 추천 실패: {e}"

st.write("df_info 컬럼:", df_info.columns.tolist())

# 3. 데이터 불러오기
df_info = load_google_sheet("PRODUCT_INFO")
df_shein = load_google_sheet("SHEIN_SALES")
df_temu = load_google_sheet("TEMU_SALES")

# 날짜 파싱
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

df_temu["order date"] = df_temu["purchase date"].apply(parse_temudate)
df_shein["order date"] = df_shein["order processed on"].apply(parse_sheindate)

# 4. 가격 추천 대상 추출
today = pd.Timestamp.now().normalize()
date_30 = today - pd.Timedelta(days=30)
date_60 = today - pd.Timedelta(days=60)

# 스타일별 최근 30일 판매/지난 30일 판매
temu_30 = df_temu[(df_temu["order date"] >= date_30) & (df_temu["order item status"].str.lower().isin(["shipped", "delivered"]))]
shein_30 = df_shein[(df_shein["order date"] >= date_30) & (~df_shein["order status"].str.lower().isin(["customer refunded"]))]
temu_60 = df_temu[(df_temu["order date"] >= date_60) & (df_temu["order date"] < date_30) & (df_temu["order item status"].str.lower().isin(["shipped", "delivered"]))]
shein_60 = df_shein[(df_shein["order date"] >= date_60) & (df_shein["order date"] < date_30) & (~df_shein["order status"].str.lower().isin(["customer refunded"]))]

def get_qty(df, style_col, qty_col):
    return df.groupby(style_col)[qty_col].sum() if qty_col in df.columns else df.groupby(style_col).size()

# 스타일별 판매량 집계
temu_qty_30 = get_qty(temu_30, "product number", "quantity shipped")
shein_qty_30 = get_qty(shein_30, "product description", None)
temu_qty_60 = get_qty(temu_60, "product number", "quantity shipped")
shein_qty_60 = get_qty(shein_60, "product description", None)

# 가격 미지정/판매 없는 스타일
def is_na(val):
    try:
        # 빈값 또는 0이면 판매 없는 걸로 간주 (float 변환)
        return (pd.isna(val)) or (float(val) == 0)
    except:
        return True  # 변환 안되는 값(빈 문자열 등)은 True 처리

info_idx = df_info["product number"].astype(str)
# 1. TEMU 데이터 가격 숫자 변환
df_temu["base price total"] = pd.to_numeric(df_temu["base price total"], errors="coerce").fillna(0)
df_shein["product price"] = pd.to_numeric(df_shein["product price"], errors="coerce").fillna(0)

no_sale_mask = (
    info_idx.map(
        lambda x: is_na(df_temu[df_temu["product number"] == x]["base price total"].sum()) and
                  is_na(df_shein[df_shein["product description"] == x]["product price"].sum())
    )
)
df_no_sale = df_info[no_sale_mask]


# 판매 적은 스타일 (최근 30일 1~2개만 판매)
def get_sale_num(x):
    t = temu_qty_30.get(x, 0)
    s = shein_qty_30.get(x, 0)
    return t + s

df_info["recent_30d_sale"] = df_info["product number"].map(get_sale_num)
low_sale = df_info[(df_info["recent_30d_sale"] > 0) & (df_info["recent_30d_sale"] <= 2)]

# 잘 팔리는 스타일(최근 30일 10개 이상)
well_selling = df_info[df_info["recent_30d_sale"] >= 10]

# 지난달 대비 판매 급감(직전 30일 대비 -70% 이하)
def get_drop(x):
    n30 = df_info.loc[df_info["product number"] == x, "recent_30d_sale"].values[0]
    n60 = temu_qty_60.get(x, 0) + shein_qty_60.get(x, 0)
    if n60 == 0: return False
    return (n30 / n60) < 0.3

drop_list = df_info[df_info["product number"].apply(get_drop)]

# --------- AI 가격 추천 페이지 UI ---------
st.title("💡 AI 기반 가격 추천 (실험 기능)")

tab1, tab2, tab3, tab4 = st.tabs([
    "판매기록 없음", "판매 적은 스타일", "판매 급감", "베스트셀러/가격 인상 추천"
])

# 1. 판매기록 없음
with tab1:
    st.subheader("최근 판매 없는 스타일 – AI 가격 추천")
    if df_no_sale.empty:
        st.info("모든 스타일이 최소 1건 이상 판매되었습니다.")
    else:
        for idx, row in df_no_sale.iterrows():
            # 유사 카테고리/핏/길이 등에서 평균 판매가/ERP 찾기
            erp = row.get("erp price", 0)
            category = row.get("category", "")
            fit = row.get("fit", "")
            length = row.get("length", "")
            similar = df_info[(df_info["category"] == category) & (df_info["fit"] == fit) & (df_info["length"] == length)]
            similar = similar[similar["product number"] != row["product number"]]
            if similar.empty:
                avg_price = ""
            else:
                avg_price = similar["erp price"].mean()
            # AI 프롬프트 구성
            prompt = f"""
ERP: {erp}
카테고리: {category}, 핏: {fit}, 길이: {length}
비슷한 스타일 평균 ERP: {avg_price}
이 스타일은 아직 판매 기록이 없습니다.
ERP, 비슷한 스타일, 최소판매가(ERP*1.3+3, 최소 9불), 트렌드를 참고해 Temu/Shein 판매가를 추천하고, 간단한 이유를 1줄로 말해줘.
"""
            ai_rec = get_ai_price_suggestion(prompt)
            st.markdown(f"""
            <div style="border:1px solid #eee; border-radius:12px; padding:10px 18px; margin-bottom:14px;">
                <b>{row['product number']} — {row.get('default product name(en)', '')}</b><br>
                <span style="color:#999;">ERP: {erp}, CATEGORY: {category}, FIT: {fit}, LENGTH: {length}</span><br>
                <b>추천가:</b> {ai_rec}
            </div>
            """, unsafe_allow_html=True)

# 2. 판매적음
with tab2:
    st.subheader("판매 적은 스타일 – AI 가격 추천")
    if low_sale.empty:
        st.info("최근 30일간 판매 적은 스타일이 없습니다.")
    else:
        for idx, row in low_sale.iterrows():
            erp = row.get("erp price", 0)
            category = row.get("category", "")
            fit = row.get("fit", "")
            length = row.get("length", "")
            prompt = f"""
ERP: {erp}
카테고리: {category}, 핏: {fit}, 길이: {length}
최근 30일간 판매량: {row['recent_30d_sale']}
지난달 대비 판매량: {temu_qty_60.get(row['product number'], 0) + shein_qty_60.get(row['product number'], 0)}
ERP*1.3+3 이상, 최소 9불 이상 기준으로 Temu/Shein에 판매 추천가와 이유를 1줄로 알려줘.
"""
            ai_rec = get_ai_price_suggestion(prompt)
            st.markdown(f"""
            <div style="border:1px solid #eee; border-radius:12px; padding:10px 18px; margin-bottom:14px;">
                <b>{row['product number']} — {row.get('default product name(en)', '')}</b><br>
                <span style="color:#999;">ERP: {erp}, CATEGORY: {category}, FIT: {fit}, LENGTH: {length}</span><br>
                <b>추천가:</b> {ai_rec}
            </div>
            """, unsafe_allow_html=True)

# 3. 판매급감
with tab3:
    st.subheader("판매 급감 스타일 – AI 가격 추천")
    if drop_list.empty:
        st.info("최근 판매량이 급감한 스타일이 없습니다.")
    else:
        for idx, row in drop_list.iterrows():
            erp = row.get("erp price", 0)
            prompt = f"""
ERP: {erp}
최근 30일 판매: {row['recent_30d_sale']}
이전 30일 판매: {temu_qty_60.get(row['product number'], 0) + shein_qty_60.get(row['product number'], 0)}
판매량이 70%이상 급감했습니다. 가격을 내릴지, 유지할지 추천해줘. 근거도 1줄로.
"""
            ai_rec = get_ai_price_suggestion(prompt)
            st.markdown(f"""
            <div style="border:1px solid #eee; border-radius:12px; padding:10px 18px; margin-bottom:14px;">
                <b>{row['product number']} — {row.get('default product name(en)', '')}</b><br>
                <span style="color:#999;">ERP: {erp}</span><br>
                <b>추천가:</b> {ai_rec}
            </div>
            """, unsafe_allow_html=True)

# 4. 잘 팔리는 스타일
with tab4:
    st.subheader("베스트셀러 – 가격 인상 추천")
    if well_selling.empty:
        st.info("잘 팔리는 스타일이 없습니다.")
    else:
        for idx, row in well_selling.iterrows():
            erp = row.get("erp price", 0)
            prompt = f"""
ERP: {erp}
최근 30일 판매: {row['recent_30d_sale']}
베스트셀러(10개 이상 팔림). 가격을 인상해도 괜찮을지, 추천가와 근거를 1줄로 알려줘.
"""
            ai_rec = get_ai_price_suggestion(prompt)
            st.markdown(f"""
            <div style="border:1px solid #eee; border-radius:12px; padding:10px 18px; margin-bottom:14px;">
                <b>{row['product number']} — {row.get('default product name(en)', '')}</b><br>
                <span style="color:#999;">ERP: {erp}</span><br>
                <b>추천가:</b> {ai_rec}
            </div>
            """, unsafe_allow_html=True)
