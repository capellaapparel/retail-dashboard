import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

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

# 데이터 로드
df_info = load_google_sheet("PRODUCT_INFO")
df_temu = load_google_sheet("TEMU_SALES")
df_shein = load_google_sheet("SHEIN_SALES")

df_temu["order date"] = pd.to_datetime(df_temu["purchase date"], errors="coerce")
df_shein["order date"] = pd.to_datetime(df_shein["order processed on"], errors="coerce")
df_info["erp price"] = pd.to_numeric(df_info["erp price"], errors="coerce")

today = datetime.now()
start_30d = today - timedelta(days=30)
start_60d = today - timedelta(days=60)

# TEMU/SHEIN 평균가
def temu_avg_price(prodnum):
    vals = df_temu[df_temu["product number"] == prodnum]["base price total"]
    vals = pd.to_numeric(vals, errors="coerce")
    vals = vals[vals > 0]
    return np.nan if vals.empty else float(vals.mean())

def shein_avg_price(prodnum):
    vals = df_shein[df_shein["product description"] == prodnum]["product price"]
    vals = pd.to_numeric(vals, errors="coerce")
    vals = vals[vals > 0]
    return np.nan if vals.empty else float(vals.mean())

df_info["temu_avg"] = df_info["product number"].map(temu_avg_price)
df_info["shein_avg"] = df_info["product number"].map(shein_avg_price)

# 이미지 태그
def make_img_tag(url):
    if pd.notna(url) and str(url).startswith("http"):
        return f"<img src='{url}' style='width:60px;height:auto; border-radius:8px;'>"
    return ""

# 판매량 집계
def get_qty(df, col, prodnum, start, end):
    mask = (df["order date"] >= start) & (df["order date"] < end)
    if col == "product number":
        match = df["product number"] == prodnum
    else:
        match = df["product description"] == prodnum
    return int(df[mask & match].shape[0])

qty_30d, qty_prev30d, qty_all = [], [], []
for idx, row in df_info.iterrows():
    prodnum = row["product number"]
    qty_30d.append(get_qty(df_temu, "product number", prodnum, start_30d, today) + get_qty(df_shein, "product description", prodnum, start_30d, today))
    qty_prev30d.append(get_qty(df_temu, "product number", prodnum, start_60d, start_30d) + get_qty(df_shein, "product description", prodnum, start_60d, start_30d))
    qty_all.append(get_qty(df_temu, "product number", prodnum, pd.Timestamp('2000-01-01'), today) + get_qty(df_shein, "product description", prodnum, pd.Timestamp('2000-01-01'), today))
df_info["30d_qty"] = qty_30d
df_info["prev30d_qty"] = qty_prev30d
df_info["all_qty"] = qty_all

def suggest_price(row, similar_avg, temu_now, shein_now, mode="normal"):
    erp = float(row["erp price"]) if pd.notna(row["erp price"]) else 0
    min_sug = max(erp * 1.3 + 2, 9)
    base_sug = max(erp * 1.3 + 7, 9)
    avg = similar_avg if pd.notna(similar_avg) else base_sug
    # 판매급감/저조는 보수적으로 제안
    if mode == "drop" or mode == "slow":
        cand = [base_sug, avg]
        if pd.notna(temu_now): cand.append(temu_now * 0.92)  # TEMU 최근가보다 8%↓
        if pd.notna(shein_now): cand.append(shein_now * 0.92)
        rec = min([c for c in cand if c >= min_sug])
    elif mode == "inc":
        rec = max(base_sug, avg) + 1.0  # 인상은 기본가+1불
    else:
        rec = np.mean([base_sug, avg])
    if rec < min_sug:
        rec = min_sug
    return round(rec, 2)

# 동종 스타일 평균가 구하기
def similar_style_avg(row):
    mask = (
        (df_info["sleeve"] == row["sleeve"]) &
        (df_info["length"] == row["length"]) &
        (df_info["fit"] == row["fit"]) &
        (df_info["product number"] != row["product number"])
    )
    similar = df_info[mask]
    if similar.empty:
        return np.nan
    vals = pd.concat([similar["temu_avg"], similar["shein_avg"]]).dropna()
    return vals.mean() if not vals.empty else np.nan

# 분류
no_sales, slow, drop, inc = [], [], [], []
for idx, row in df_info.iterrows():
    prodnum = row["product number"]
    sim_avg = similar_style_avg(row)
    sug = suggest_price(row, sim_avg, temu_now, shein_now, mode)
    temu_now = row["temu_avg"]
    shein_now = row["shein_avg"]
    img = make_img_tag(row.get("image", ""))
    # 분류
    if row["30d_qty"] == 0 and row["all_qty"] == 0:
        no_sales.append({
            "이미지": img,
            "Style Number": prodnum,
            "ERP Price": row["erp price"],
            "TEMU가": f"${temu_now:.2f}" if pd.notna(temu_now) else "-",
            "SHEIN가": f"${shein_now:.2f}" if pd.notna(shein_now) else "-",
            "추천가": f"${sug:.2f}",
            "30일 판매": row["30d_qty"],
            "이전30일": row["prev30d_qty"],
            "전체판매": row["all_qty"],
            "사유": "한 번도 팔린적 없음(신상/미판매)",
        })
    elif row["30d_qty"] == 0 and row["all_qty"] > 0:
        no_sales.append({
            "이미지": img,
            "Style Number": prodnum,
            "ERP Price": row["erp price"],
            "TEMU가": f"${temu_now:.2f}" if pd.notna(temu_now) else "-",
            "SHEIN가": f"${shein_now:.2f}" if pd.notna(shein_now) else "-",
            "추천가": f"${sug:.2f}",
            "30일 판매": row["30d_qty"],
            "이전30일": row["prev30d_qty"],
            "전체판매": row["all_qty"],
            "사유": "최근 30일 미판매 (이전 판매는 있음)",
        })
    elif row["30d_qty"] <= 2 and row["all_qty"] > 0:
        slow.append({
            "이미지": img,
            "Style Number": prodnum,
            "ERP Price": row["erp price"],
            "TEMU가": f"${temu_now:.2f}" if pd.notna(temu_now) else "-",
            "SHEIN가": f"${shein_now:.2f}" if pd.notna(shein_now) else "-",
            "추천가": f"${sug:.2f}",
            "30일 판매": row["30d_qty"],
            "이전30일": row["prev30d_qty"],
            "전체판매": row["all_qty"],
            "사유": "판매 저조 (최근 30일 1~2건)",
        })
    elif row["30d_qty"] < row["prev30d_qty"] / 2 and row["prev30d_qty"] > 0:
        drop.append({
            "이미지": img,
            "Style Number": prodnum,
            "ERP Price": row["erp price"],
            "TEMU가": f"${temu_now:.2f}" if pd.notna(temu_now) else "-",
            "SHEIN가": f"${shein_now:.2f}" if pd.notna(shein_now) else "-",
            "추천가": f"${sug:.2f}",
            "30일 판매": row["30d_qty"],
            "이전30일": row["prev30d_qty"],
            "전체판매": row["all_qty"],
            "사유": "판매 급감 (이전30일대비 50%↓)",
        })
    elif row["30d_qty"] >= 10 or row["all_qty"] > 30:
        sug_high = round(sug + 1.5, 2)
        inc.append({
            "이미지": img,
            "Style Number": prodnum,
            "ERP Price": row["erp price"],
            "TEMU가": f"${temu_now:.2f}" if pd.notna(temu_now) else "-",
            "SHEIN가": f"${shein_now:.2f}" if pd.notna(shein_now) else "-",
            "추천가": f"${sug_high:.2f}",
            "30일 판매": row["30d_qty"],
            "이전30일": row["prev30d_qty"],
            "전체판매": row["all_qty"],
            "사유": "판매호조/가격 인상 제안",
        })

def display_html_table(lst, title):
    st.markdown(f"#### {title}")
    if not lst:
        st.info("추천되는 스타일이 없습니다.")
        return
    df = pd.DataFrame(lst)
    st.markdown(
        df.to_html(escape=False, index=False), unsafe_allow_html=True
    )

st.title("💡 가격 제안 대시보드")
st.markdown("""
- 최근 30일간 판매량 0 (신상/미판매 스타일)
- 지난달 대비 판매 급감
- 판매가 1~2건 등 극히 적음 (slow seller)
- 너무 잘 팔리는 아이템 (가격 인상 추천)
- 기본 가격 제시: <b>erp price × 1.3 + 7</b> (최소 erp×1.3+2, $9 미만 비추천)
""", unsafe_allow_html=True)

tabs = st.tabs(
    ["🆕 판매 없음 (신상/미판매)", "🟠 판매 저조", "📉 판매 급감", "🔥 가격 인상 추천"]
)

with tabs[0]:
    display_html_table(no_sales, "판매 기록 없는 신상/미판매 스타일 추천가")

with tabs[1]:
    display_html_table(slow, "판매 저조 스타일 추천가")

with tabs[2]:
    display_html_table(drop, "판매 급감 스타일 추천가")

with tabs[3]:
    display_html_table(inc, "판매호조(가격 인상) 스타일 추천가")
