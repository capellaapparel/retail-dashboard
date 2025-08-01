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

st.title("AI 기반 가격 변경 필요 스타일 추천")

# 데이터 불러오기
df_temu = load_google_sheet("TEMU_SALES")
df_temu = df_temu[df_temu["purchase date"].apply(lambda x: isinstance(x, str))]
df_temu["order date"] = pd.to_datetime(df_temu["purchase date"], errors="coerce")
df_temu = df_temu[df_temu["order date"].notna()]
df_temu["quantity shipped"] = pd.to_numeric(df_temu["quantity shipped"], errors="coerce").fillna(0)
df_temu["base price total"] = pd.to_numeric(df_temu["base price total"], errors="coerce").fillna(0)

today = df_temu["order date"].max()
last_month = today - pd.Timedelta(days=30)
prev_month = last_month - pd.Timedelta(days=30)

# [1] 최근 30일 / 그 이전 30일 판매량, 매출, AOV
sold_status = ["shipped", "delivered"]
recent = df_temu[
    (df_temu["order date"] >= last_month) &
    (df_temu["order date"] <= today) &
    (df_temu["order item status"].str.lower().isin(sold_status))
]
prev = df_temu[
    (df_temu["order date"] >= prev_month) &
    (df_temu["order date"] < last_month) &
    (df_temu["order item status"].str.lower().isin(sold_status))
]

grp_recent = recent.groupby("product number").agg(
    recent_qty = ("quantity shipped", "sum"),
    recent_sales = ("base price total", "sum"),
    recent_order = ("order id", "nunique")
)
grp_recent["recent_aov"] = grp_recent["recent_sales"] / grp_recent["recent_order"].replace(0,1)

grp_prev = prev.groupby("product number").agg(
    prev_qty = ("quantity shipped", "sum"),
    prev_sales = ("base price total", "sum"),
    prev_order = ("order id", "nunique")
)
grp_prev["prev_aov"] = grp_prev["prev_sales"] / grp_prev["prev_order"].replace(0,1)

# [2] 전체 평균 AOV (경쟁제품 평균)
overall_aov = grp_recent["recent_aov"].mean()

# [3] 합치기
summary = pd.concat([grp_recent, grp_prev], axis=1).fillna(0)

summary["판매량 증감률(%)"] = summary.apply(
    lambda row: ((row["recent_qty"] - row["prev_qty"]) / row["prev_qty"] * 100)
    if row["prev_qty"] > 0 else (100 if row["recent_qty"] > 0 else 0), axis=1
)

# [4] “지속적으로 잘 팔리는 상품” 정의: 최근 30일/이전 30일 모두 판매 > 10
summary["steady_seller"] = (summary["recent_qty"] >= 10) & (summary["prev_qty"] >= 10)

# [5] AOV 경쟁 비교
summary["aov_compared"] = summary["recent_aov"] - overall_aov

# [6] 가격조정 ‘필요’ 추정
def price_recommend(row):
    if row["recent_qty"] == 0 and row["prev_qty"] > 0:
        return "▼ 가격 인하 추천 (판매 중단)"
    elif row["recent_qty"] > 0 and row["판매량 증감률(%)"] < -50:
        return "▼ 가격 인하 검토 (판매 급감)"
    elif row["steady_seller"]:
        return "▲ 가격 인상 고려 (지속 인기)"
    elif row["recent_qty"] > 0 and row["aov_compared"] < -2:
        return "▲ 가격 인상 고려 (AOV 낮음)"
    elif row["recent_qty"] > 0 and row["aov_compared"] > 2:
        return "▼ 가격 인하 검토 (AOV 높음, 경쟁보다 비쌈)"
    else:
        return ""
summary["가격조정 추천"] = summary.apply(price_recommend, axis=1)

recommend = summary[summary["가격조정 추천"] != ""]

st.markdown("### 🔥 아래 스타일은 가격 조정이 필요할 수 있습니다")
if recommend.empty:
    st.info("가격 조정 필요 스타일이 없습니다. (모든 스타일이 정상 판매 중)")
else:
    show_cols = [
        "recent_qty", "prev_qty", "판매량 증감률(%)", "recent_aov", "aov_compared", "가격조정 추천"
    ]
    pretty_names = [
        "최근 30일 판매량", "이전 30일 판매량", "판매량 증감률(%)", "최근 AOV", "AOV-경쟁평균", "추천"
    ]
    show_df = recommend[show_cols]
    show_df.columns = pretty_names
    st.dataframe(show_df.style.format({
        "최근 AOV": "${:,.2f}",
        "AOV-경쟁평균": "${:,.2f}",
        "판매량 증감률(%)": "{:.1f}%"
    }))

st.caption(
    "기준 설명:\n"
    "- 최근 30일간 판매량 0: 판매 중단, 가격 인하 추천\n"
    "- 지난달 대비 판매량 급감: 가격 인하 검토\n"
    "- 두 달 연속 판매량 10개↑: 가격 인상 고려\n"
    "- AOV(평균 판매가)가 경쟁 제품보다 2달러 이상 낮거나 높음: 인상/인하 추천"
)
