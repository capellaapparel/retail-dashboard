import streamlit as st
import pandas as pd
from dateutil import parser
import openai
openai.api_key = OPENAI_API_KEY
openai.ChatCompletion.create(
    model="gpt-4o",
    messages=[{"role":"user", "content": prompt}]
)

# --- (필요시 LLM 활용을 위해) OpenAI Key 셋팅 ---
OPENAI_API_KEY = st.secrets.get("openai_api_key", "")
def get_ai_reason(prompt):
    if not OPENAI_API_KEY:
        return ""
    try:
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY)
        resp = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}]
        )
        return resp.choices[0].message.content.strip()
    except ImportError:
        try:
            import openai
            openai.api_key = OPENAI_API_KEY
            resp = openai.ChatCompletion.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}]
            )
            return resp["choices"][0]["message"]["content"].strip()
        except Exception as e:
            return "AI 사유 생성에 실패했습니다."
    except Exception as e:
        return "AI 사유 생성에 실패했습니다."

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

# --- 데이터 불러오기 ---
df_info = load_google_sheet("PRODUCT_INFO")
df_temu = load_google_sheet("TEMU_SALES")
df_shein = load_google_sheet("SHEIN_SALES")

df_temu["order date"] = df_temu["purchase date"].apply(parse_temudate)
df_shein["order date"] = df_shein["order processed on"].apply(parse_sheindate)

# ---- 가격 제안 함수 ----
def ai_price_suggestion(row, df_info, df_temu, df_shein):
    erp = float(row.get("erp price", 0))
    style = row.get("product number", "")
    style_cat = row.get("length", "") + "/" + row.get("sleeve", "") + "/" + row.get("fit", "")
    base_price = max(round(erp*1.3 + 7, 2), 9)

    # 유사 스타일(카테고리/핏 등 일치) 최근 판매가 평균
    filters = (
        (df_info["length"] == row.get("length")) &
        (df_info["sleeve"] == row.get("sleeve")) &
        (df_info["fit"] == row.get("fit"))
    )
    similar_styles = df_info[filters & (df_info["product number"] != style)]
    similar_nums = similar_styles["product number"].unique()
    temu_prices = []
    shein_prices = []
    # 각 스타일별 최근 판매가격(판매 기록 있는 것만)
    for s in similar_nums:
        temu_p = df_temu[df_temu["product number"] == s]
        if not temu_p.empty:
            price = pd.to_numeric(temu_p["base price total"], errors="coerce").mean()
            if not pd.isna(price):
                temu_prices.append(price)
        shein_p = df_shein[df_shein["product description"] == s]
        if not shein_p.empty:
            price = pd.to_numeric(shein_p["product price"], errors="coerce").mean()
            if not pd.isna(price):
                shein_prices.append(price)
    # 평균 계산
    all_prices = temu_prices + shein_prices
    similar_avg = round(sum(all_prices)/len(all_prices), 2) if all_prices else 0

    # 최근 30/14/7일 판매량 집계
    today = pd.Timestamp.today().normalize()
    temu_sales = df_temu[df_temu["product number"] == style]
    shein_sales = df_shein[df_shein["product description"] == style]
    recent_30 = (
        (temu_sales["order date"] > today - pd.Timedelta(days=30)).sum() +
        (shein_sales["order date"] > today - pd.Timedelta(days=30)).sum()
    )
    recent_14 = (
        (temu_sales["order date"] > today - pd.Timedelta(days=14)).sum() +
        (shein_sales["order date"] > today - pd.Timedelta(days=14)).sum()
    )
    recent_7 = (
        (temu_sales["order date"] > today - pd.Timedelta(days=7)).sum() +
        (shein_sales["order date"] > today - pd.Timedelta(days=7)).sum()
    )
    # AOV, 급증/급감 판단
    all_sales = pd.concat([temu_sales, shein_sales])
    all_prices2 = pd.to_numeric(all_sales["base price total"].fillna(0), errors="coerce")
    sales_count = all_sales.shape[0]
    aov = round(all_prices2.sum()/sales_count,2) if sales_count else 0

    # --- AI/Rule 기반 추천가 산정 ---
    if sales_count == 0:
        # 한 번도 팔린 적 없음: 공격적 가격 인하
        rec_price = max(round(erp*1.3+2, 2), 9)
        reason = "한 번도 판매된 적 없는 스타일입니다. ERP/유사 스타일 평균을 참고해 공격적 인하가 필요합니다."
    elif recent_30 == 0 and sales_count > 0:
        # 예전엔 팔렸는데 최근 30일 0: 추가 인하
        rec_price = max(round(erp*1.3+3, 2), 9)
        reason = "최근 한 달간 판매가 없어 가격 인하가 필요합니다."
    elif recent_7 > 10:
        # 최근 7일 10건 이상: 인상 가능
        rec_price = max(round(base_price + 2, 2), 9)
        reason = "최근 1주일 내 판매가 많아 가격 인상을 고려해볼 수 있습니다."
    elif 1 <= sales_count <= 2:
        # 단일 판매: 추가 인하 유도
        rec_price = max(round(erp*1.3+3, 2), 9)
        reason = "판매 이력이 거의 없으므로 추가 인하 추천"
    elif similar_avg > 0:
        # 유사 스타일 평균이 존재 → 그 근처로
        rec_price = max(round((base_price+similar_avg)/2, 2), 9)
        reason = f"유사 스타일 평균({similar_avg}) 및 ERP를 반영해 추천"
    else:
        rec_price = base_price
        reason = "ERP 기반 기본 가격 추천"
    # AI 설명 추가 (LLM 사용 가능)
    if client:
        prompt = f"""You're an AI pricing expert for a fashion wholesaler. 
        Given: ERP={erp}, Similar styles avg price={similar_avg}, Recent 30/14/7 sales={recent_30}/{recent_14}/{recent_7}, Base price={base_price}
        Suggest a new price and give reasoning in Korean for a manager. Minimum 9불. (1 sentence, 100자 이내)
        """
        ai_resp = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role":"user", "content": prompt}]
        )
        reason = ai_resp.choices[0].message.content.strip()

    return rec_price, reason, f"{recent_30}/{recent_14}/{recent_7}", similar_avg

# --- Streamlit UI ---
st.title("🤖 AI 기반 가격 제안")
st.caption("판매이력/유사 스타일/ERP/최소가/최근 트렌드까지 종합 분석")

# [1] 판매량/가격 데이터 없는 스타일/저판매/고판매 모두 추천 대상
def need_price_suggestion(row):
    style = row["product number"]
    temu_sales = df_temu[df_temu["product number"] == style]
    shein_sales = df_shein[df_shein["product description"] == style]
    recent_30 = (
        (temu_sales["order date"] > pd.Timestamp.today() - pd.Timedelta(days=30)).sum() +
        (shein_sales["order date"] > pd.Timestamp.today() - pd.Timedelta(days=30)).sum()
    )
    total_sales = temu_sales.shape[0] + shein_sales.shape[0]
    if total_sales == 0 or recent_30 == 0 or total_sales < 5 or recent_30 > 15:
        return True
    return False

df_info = df_info[df_info["erp price"].notnull()]
price_df = df_info[df_info.apply(need_price_suggestion, axis=1)].copy()

suggestions = []
for _, row in price_df.iterrows():
    price, reason, sales_recent, similar_avg = ai_price_suggestion(row, df_info, df_temu, df_shein)
    suggestions.append({
        "Product Number": row["product number"],
        "Name": row.get("default product name(en)", ""),
        "ERP Price": row["erp price"],
        "유사 스타일 평균": similar_avg,
        "최근 30/14/7일 판매량": sales_recent,
        "추천가격": price,
        "사유": reason
    })

result_df = pd.DataFrame(suggestions)
st.markdown("#### 🧠 가격 조정/추천 필요한 스타일")
st.dataframe(
    result_df,
    use_container_width=True,
    height=600
)
st.caption("""
- 가격은 ERP*1.3+7 기준, 유사 스타일 평균, 최근 트렌드, AI 설명 등 반영
- 판매이력 없음/저판매/고판매(최근 7일 10건↑) 모두 분석
- 최소가 9불, 최근 데이터 자동 분석+추천가+AI사유(설명) 모두 표시
""")
