import streamlit as st
import pandas as pd
import numpy as np
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

def safe_float(x):
    try:
        if pd.isna(x): return np.nan
        return float(str(x).replace("$", "").replace(",", ""))
    except:
        return np.nan

def show_price(val):
    try:
        x = float(val)
        if pd.isna(x): return "-"
        return f"${x:,.2f}"
    except:
        return "-" if (val is None or val == "" or pd.isna(val)) else str(val)

def make_img_tag(url):
    if pd.notna(url) and str(url).startswith("http"):
        return f"<img src='{url}' style='width:50px;height:auto;border-radius:6px;'>"
    return ""

# ------------------------------
# 데이터 불러오기
df_info = load_google_sheet("PRODUCT_INFO")
df_temu = load_google_sheet("TEMU_SALES")
df_shein = load_google_sheet("SHEIN_SALES")

df_info.columns = [c.strip().lower() for c in df_info.columns]
df_temu.columns = [c.strip().lower() for c in df_temu.columns]
df_shein.columns = [c.strip().lower() for c in df_shein.columns]

df_temu["order date"] = df_temu["purchase date"].apply(parse_temudate)
df_shein["order date"] = df_shein["order processed on"].apply(parse_sheindate)

# 이미지 dict
img_dict = dict(zip(df_info["product number"].astype(str), df_info["image"]))

# 스타일 넘버 리스트
all_styles = df_info["product number"].astype(str).tolist()

# ERP price 보정
def get_erp(row):
    try:
        return float(str(row["erp price"]).replace("$", "").replace(",", ""))
    except:
        return np.nan

df_info["erp price"] = df_info.apply(get_erp, axis=1)

# TEMU/SHEIN 현재가
def temu_now(style):
    vals = df_temu[df_temu["product number"] == style]["base price total"]
    vals = vals.apply(safe_float)
    vals = vals[vals > 0]
    return show_price(vals.mean()) if len(vals) > 0 else "-"

def shein_now(style):
    vals = df_shein[df_shein["product description"] == style]["product price"]
    vals = vals.apply(safe_float)
    vals = vals[vals > 0]
    return show_price(vals.mean()) if len(vals) > 0 else "-"

# --- 판매 집계 ---
def get_qty(df, style, days):
    now = pd.Timestamp.now()
    since = now - pd.Timedelta(days=days)
    if "order date" not in df.columns:
        return 0
    if "product number" in df.columns:
        target = df["product number"] == style
    else:
        target = df["product description"] == style
    df2 = df[target]
    if "order item status" in df2.columns: # temu
        df2 = df2[df2["order item status"].str.lower().isin(["shipped", "delivered"])]
        qty_col = "quantity shipped"
    else:
        df2 = df2[~df2["order status"].str.lower().isin(["customer refunded"])]
        qty_col = None # Shein: row = 1건
    df2 = df2[(df2["order date"] >= since) & (df2["order date"] <= now)]
    if qty_col:
        return pd.to_numeric(df2[qty_col], errors="coerce").fillna(0).sum()
    else:
        return df2.shape[0]

# --- AI 가격추천 로직 ---
def suggest_price(row, sim_avg, temu_price, shein_price, mode):
    erp = row["erp price"]
    base_min = erp*1.3 + 2
    base_norm = erp*1.3 + 7
    base_min = max(base_min, 9)
    base_norm = max(base_norm, 9)
    # 경쟁가(비슷한 스타일, temu, shein, sim_avg)
    ref_prices = [safe_float(temu_price), safe_float(shein_price)]
    if not pd.isna(sim_avg): ref_prices.append(sim_avg)
    ref_prices = [x for x in ref_prices if not pd.isna(x) and x > 0]
    if mode == "new":  # 신상/미판매: 너무 싸게는 말고, 동종평균/경쟁가 있으면 +조금 더
        if ref_prices:
            rec = max(base_min, np.mean(ref_prices))
        else:
            rec = base_min
    elif mode == "slow": # 1~2건밖에 없는 슬로우
        if ref_prices:
            rec = min(base_norm, np.mean(ref_prices))
        else:
            rec = base_min
    elif mode == "drop": # 판매 급감: (최소 기준, 경쟁가와 큰 차 없도록)
        if ref_prices:
            rec = min(base_norm, np.mean(ref_prices))
        else:
            rec = base_min
    elif mode == "hot": # 잘팔림: 경쟁가 있으면 평균, 최소가보다 1~2불 더 올려서
        if ref_prices:
            rec = max(base_norm, np.mean(ref_prices) + 2)
        else:
            rec = base_norm + 1
    else: # fallback
        rec = base_norm
    rec = round(max(9, rec), 2)
    return rec

# --- 유사 스타일 평균
def get_similar_avg(row):
    cols = ["sleeve", "length", "fit"]
    mask = (df_info["product number"] != row["product number"])
    for c in cols:
        if c in df_info.columns and c in row and not pd.isna(row[c]):
            mask &= (df_info[c] == row[c])
    # 최근 tem/shein 가격 평균
    temus = df_temu[df_temu["product number"].isin(df_info[mask]["product number"])]["base price total"].apply(safe_float)
    sheins = df_shein[df_shein["product description"].isin(df_info[mask]["product number"])]["product price"].apply(safe_float)
    vals = []
    if len(temus) > 0 and temus.mean()>0: vals.append(temus.mean())
    if len(sheins) > 0 and sheins.mean()>0: vals.append(sheins.mean())
    return np.mean(vals) if vals else np.nan

# --- 각 스타일별 정보/추천가
records = []
for _, row in df_info.iterrows():
    style = row["product number"]
    erp = row["erp price"]
    img = img_dict.get(str(style), "")
    t_now = temu_now(style)
    s_now = shein_now(style)
    sim_avg = get_similar_avg(row)
    qty30 = get_qty(df_temu, style, 30) + get_qty(df_shein, style, 30)
    qty30_prev = get_qty(df_temu, style, 60) + get_qty(df_shein, style, 60) - qty30
    qty_all = get_qty(df_temu, style, 9999) + get_qty(df_shein, style, 9999)
    # 상태별 추천 (mode)
    if qty30 == 0:
        mode = "new"
        why = "한 번도 팔리지 않음"
    elif qty30 <= 2:
        mode = "slow"
        why = "판매 1~2건 이하 (슬로우셀러)"
    elif qty30_prev >= 2*qty30 and qty30 > 0:
        mode = "drop"
        why = "판매 급감 (직전 30일대비 50%↓)"
    elif qty30 >= 10 and qty30 > qty30_prev:
        mode = "hot"
        why = "최근 30일 판매 급증, 가격 인상 추천"
    else:
        mode = ""
        why = ""
    # 추천가 산정
    rec_price = suggest_price(row, sim_avg, t_now, s_now, mode)
    records.append({
        "이미지": make_img_tag(img),
        "Style Number": style,
        "ERP Price": show_price(erp),
        "TEMU 가격": t_now,
        "SHEIN 가격": s_now,
        "추천가": show_price(rec_price),
        "30일판매": int(qty30),
        "이전30일": int(qty30_prev),
        "전체판매": int(qty_all),
        "사유": why,
        "mode": mode
    })

df_rec = pd.DataFrame(records)

# ----- Streamlit UI -----
st.markdown("""
<h1>💡 가격 제안 대시보드</h1>
<ul>
  <li>최근 30일간 판매량 0 (신상/미판매 스타일)</li>
  <li>지난달 대비 판매 급감</li>
  <li>판매가 1~2건 등 극히 적음 (slow seller)</li>
  <li>너무 잘 팔리는 아이템 (가격 인상 추천)</li>
  <li><b>기본 가격 제시: erp price × 1.3 + 7</b> (최소 erp×1.3+2, $9 미만 비추천)</li>
</ul>
""", unsafe_allow_html=True)

tabs = st.tabs([
    "🆕 판매 없음 (신상/미판매)",
    "🟠 판매 저조",
    "📉 판매 급감",
    "🔥 가격 인상 추천"
])

def display_table(df, comment):
    show = df[["이미지","Style Number","ERP Price","TEMU 가격","SHEIN 가격","추천가","30일판매","이전30일","전체판매","사유"]]
    st.markdown(f"<h4>{comment}</h4>", unsafe_allow_html=True)
    st.markdown(show.to_html(escape=False, index=False), unsafe_allow_html=True)

with tabs[0]:
    no_sales = df_rec[df_rec["mode"] == "new"]
    display_table(no_sales, "판매 기록 없는 신상/미판매 스타일의 최소가격 제시 (동종 평균가 반영)")
with tabs[1]:
    slow = df_rec[df_rec["mode"] == "slow"]
    display_table(slow, "판매가 1~2건 이하인 슬로우셀러 (가격/경쟁가/동종평균 참고)")
with tabs[2]:
    drop = df_rec[df_rec["mode"] == "drop"]
    display_table(drop, "판매 급감(직전30일대비 50%↓) 스타일의 가격 조정 추천")
with tabs[3]:
    hot = df_rec[df_rec["mode"] == "hot"]
    display_table(hot, "판매가 계속 증가중인 핫아이템 (가격 인상 가능)")
