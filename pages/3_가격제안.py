import streamlit as st
import pandas as pd
from dateutil import parser

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

st.title("AI 기반 가격 제안")

# 1. 데이터 불러오기
df_temu = load_google_sheet("TEMU_SALES")
df_info = load_google_sheet("PRODUCT_INFO")

# 2. purchase date 비정상값 제거
df_temu = df_temu[df_temu["purchase date"].apply(lambda x: isinstance(x, str))]
df_temu["order date"] = pd.to_datetime(df_temu["purchase date"], errors="coerce")
# 날짜 파싱 실패 row 제거
df_temu = df_temu[df_temu["order date"].notna()]

# 3. 스타일번호 선택
style_list = sorted(df_temu["product number"].unique())
style_selected = st.selectbox("스타일 번호 선택", style_list)
if not style_selected:
    st.info("스타일을 선택하세요.")
    st.stop()

# 4. 최근 30일 판매 데이터 필터링
end_date = df_temu["order date"].max()
start_date = end_date - pd.Timedelta(days=30)
df_style = df_temu[
    (df_temu["product number"] == style_selected) &
    (df_temu["order date"] >= start_date) &
    (df_temu["order date"] <= end_date) &
    (df_temu["order item status"].str.lower().isin(["shipped", "delivered"]))
]

st.markdown(f"### 최근 30일간 판매 내역")
st.dataframe(df_style[["order date", "base price total", "quantity shipped"]].sort_values("order date", ascending=False))

# 5. 간단한 통계
total_qty = pd.to_numeric(df_style["quantity shipped"], errors="coerce").fillna(0).sum()
total_sales = pd.to_numeric(df_style["base price total"], errors="coerce").fillna(0).sum()
avg_price = total_sales / total_qty if total_qty > 0 else 0

col1, col2, col3 = st.columns(3)
col1.metric("판매수량(30일)", int(total_qty))
col2.metric("총매출(30일)", f"${total_sales:,.2f}")
col3.metric("평균 판매가", f"${avg_price:,.2f}")

# 6. AI 가격 제안 (프롬프트 기반)
import openai

def ai_price_recommendation(sales, avg_price, qty, current_price):
    prompt = (
        f"지난 30일간 {qty}개 판매, 평균 판매가 ${avg_price:.2f}, "
        f"현재 판매가 ${current_price:.2f}입니다. "
        "판매량을 극대화할 수 있는 적정 권장가격을 1개 숫자로만 제안해주세요."
    )
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o",  # 또는 "gpt-3.5-turbo"
            messages=[{"role": "system", "content": "너는 숙련된 의류 판매 전략가야."},
                      {"role": "user", "content": prompt}],
            max_tokens=10,
            temperature=0.4,
        )
        ai_price = response.choices[0].message.content.strip()
        return ai_price
    except Exception as e:
        return f"AI 제안 실패: {e}"

current_price = avg_price
if st.button("AI 가격 제안 받기"):
    with st.spinner("AI가 가격을 분석 중..."):
        ai_price = ai_price_recommendation(total_sales, avg_price, total_qty, current_price)
    st.success(f"AI 추천가: ${ai_price}")

st.caption("※ AI 가격 제안은 참고용이며, 실제 판매가 결정은 데이터와 시장상황을 고려하여 최종 결정하세요.")

