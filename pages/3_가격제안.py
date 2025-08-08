import streamlit as st
import pandas as pd
import numpy as np
from dateutil import parser

# ===================== 공통 유틸 =====================
def safe_float(x):
    try:
        if pd.isna(x): return np.nan
        return float(str(x).replace("$","").replace(",",""))
    except:
        return np.nan

def show_price(val):
    try:
        x = float(val)
        if pd.isna(x): return "-"
        return f"${x:,.2f}"
    except:
        return "-" if (val is None or val=="" or pd.isna(val)) else str(val)

def make_img_tag(url):
    if pd.notna(url) and str(url).startswith("http"):
        return f"<img src='{url}' style='width:56px;height:auto;border-radius:8px;'>"
    return ""

def parse_temudate(dt):
    try: return parser.parse(str(dt).split('(')[0].strip(), fuzzy=True)
    except Exception: return pd.NaT

def parse_sheindate(dt):
    try: return pd.to_datetime(str(dt), errors="coerce", infer_datetime_format=True)
    except Exception: return pd.NaT

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
    with open("/tmp/service_account.json","w") as f: json.dump(json_data, f)
    creds = ServiceAccountCredentials.from_json_keyfile_name("/tmp/service_account.json", scope)
    client = gspread.authorize(creds)
    ws = client.open_by_url(GOOGLE_SHEET_URL).worksheet(sheet_name)
    df = pd.DataFrame(ws.get_all_records())
    df.columns = [c.lower().strip() for c in df.columns]
    return df

# ===================== 데이터 로드 =====================
st.set_page_config(page_title="가격 제안 대시보드", layout="wide")
st.title("💡 가격 제안 대시보드")

df_info  = load_google_sheet("PRODUCT_INFO")
df_temu  = load_google_sheet("TEMU_SALES")
df_shein = load_google_sheet("SHEIN_SALES")

df_temu["order date"]  = df_temu["purchase date"].apply(parse_temudate)
df_shein["order date"] = df_shein["order processed on"].apply(parse_sheindate)

img_dict = dict(zip(df_info["product number"].astype(str), df_info["image"]))

# ERP price 정규화
def to_erp(x):
    try: return float(str(x).replace("$","").replace(",",""))
    except: return np.nan
df_info["erp price"] = df_info["erp price"].apply(to_erp)

# ===================== 플랫폼별 현재가 (숫자) =====================
def temu_now_num(style):
    vals = df_temu[df_temu["product number"].astype(str)==str(style)]["base price total"].apply(safe_float)
    vals = vals[vals>0]
    return float(vals.mean()) if len(vals)>0 else np.nan

def shein_now_num(style):
    vals = df_shein[df_shein["product description"].astype(str)==str(style)]["product price"].apply(safe_float)
    vals = vals[vals>0]
    return float(vals.mean()) if len(vals)>0 else np.nan

# ===================== 판매 집계 =====================
def get_qty(df, style, days):
    now = pd.Timestamp.now()
    since = now - pd.Timedelta(days=days)
    if "order date" not in df.columns: return 0
    if "product number" in df.columns:
        target = df["product number"].astype(str)==str(style)
    else:
        target = df["product description"].astype(str)==str(style)
    d = df[target]
    if "order item status" in d.columns:  # TEMU
        d = d[d["order item status"].astype(str).str.lower().isin(["shipped","delivered"])]
        qty_col = "quantity shipped"
    else:
        d = d[~d["order status"].astype(str).str.lower().isin(["customer refunded"])]
        qty_col = None
    d = d[(d["order date"]>=since) & (d["order date"]<=now)]
    if qty_col:
        return pd.to_numeric(d[qty_col], errors="coerce").fillna(0).sum()
    else:
        return d.shape[0]

# ===================== 플랫폼 설정 & 추천가 로직 =====================
# 필요 시 자유롭게 튜닝
PLATFORM_CFG = {
    "TEMU":  {"fee_rate":0.12, "extra_fee":0.0, "base_add":7, "min_add":2, "floor":9},
    "SHEIN": {"fee_rate":0.15, "extra_fee":0.0, "base_add":7, "min_add":2, "floor":9},
}

def suggest_price_platform(erp, ref_prices, mode, cfg):
    """
    erp: float
    ref_prices: 경쟁가 후보 리스트(숫자)
    mode: "new"|"slow"|"drop"|"hot"|"" (판매 상태)
    cfg: PLATFORM_CFG 하위 dict
    """
    base_min  = max(erp*(1+cfg["fee_rate"]) + cfg["min_add"], cfg["floor"])
    base_norm = max(erp*(1+cfg["fee_rate"]) + cfg["base_add"], cfg["floor"])

    refs = [x for x in ref_prices if not pd.isna(x) and x>0]
    rec = base_norm

    if mode in ["new","slow","drop"]:
        rec = min(base_norm, min(refs)) if refs else base_min
    elif mode == "hot":
        rec = max(base_norm, (max(refs)+1) if refs else (base_norm+1))

    return round(max(cfg["floor"], rec), 2)

# ===================== 유사 스타일 평균가(간단) =====================
def similar_avg(style):
    tem = df_temu[df_temu["product number"].astype(str)!=str(style)]["base price total"].apply(safe_float)
    sh  = df_shein[df_shein["product description"].astype(str)!=str(style)]["product price"].apply(safe_float)
    pool = []
    if tem.notna().mean()>0: pool.append(tem.mean())
    if sh.notna().mean()>0:  pool.append(sh.mean())
    return np.nanmean(pool) if pool else np.nan

# ===================== 레코드 빌드 (두 플랫폼 추천가 모두 계산해두고, 화면에서 선택) =====================
records = []
for _, row in df_info.iterrows():
    style = str(row["product number"])
    erp   = row["erp price"]
    img   = img_dict.get(style, "")

    qty30      = get_qty(df_temu, style, 30) + get_qty(df_shein, style, 30)
    qty30_prev = (get_qty(df_temu, style, 60) + get_qty(df_shein, style, 60)) - qty30
    qty_all    = get_qty(df_temu, style, 9999) + get_qty(df_shein, style, 9999)

    if qty30 == 0:
        mode, why = "new", "한 번도 팔리지 않음"
    elif qty30 <= 2:
        mode, why = "slow", "판매 1~2건 이하 (슬로우셀러)"
    elif qty30_prev >= 2*qty30 and qty30 > 0:
        mode, why = "drop", "판매 급감 (직전 30일대비 50%↓)"
    elif qty30 >= 10 and qty30 > qty30_prev:
        mode, why = "hot", "최근 30일 판매 급증, 가격 인상 추천"
    else:
        mode, why = "", ""

    t_cur = temu_now_num(style)
    s_cur = shein_now_num(style)
    sim   = similar_avg(style)

    rec_temu  = suggest_price_platform(erp, [s_cur, sim], mode, PLATFORM_CFG["TEMU"])
    rec_shein = suggest_price_platform(erp, [t_cur, sim], mode, PLATFORM_CFG["SHEIN"])

    records.append({
        "이미지": make_img_tag(img),
        "Style Number": style,
        "ERP Price": show_price(erp),
        "TEMU 현재가": show_price(t_cur),
        "SHEIN 현재가": show_price(s_cur),
        "추천가_TEMU": show_price(rec_temu),
        "추천가_SHEIN": show_price(rec_shein),
        "30일판매": int(qty30),
        "이전30일": int(qty30_prev),
        "전체판매": int(qty_all),
        "사유": why,
        "mode": mode
    })

df_rec = pd.DataFrame(records)

# ===================== 보기: TEMU / SHEIN (BOTH 제거) =====================
platform_view = st.segmented_control("플랫폼", options=["TEMU","SHEIN"], default="TEMU")

def display_table(df, comment, platform_view):
    if platform_view == "TEMU":
        show = df[["이미지","Style Number","ERP Price","TEMU 현재가","추천가_TEMU","30일판매","이전30일","전체판매","사유"]]
    else:
        show = df[["이미지","Style Number","ERP Price","SHEIN 현재가","추천가_SHEIN","30일판매","이전30일","전체판매","사유"]]
    st.markdown(f"**{comment}**")
    st.markdown(show.to_html(escape=False, index=False), unsafe_allow_html=True)

# ===================== 탭 (선택된 플랫폼 독립 출력) =====================
tabs = st.tabs(["🆕 판매 없음", "🟠 판매 저조", "📉 판매 급감", "🔥 가격 인상 추천"])

with tabs[0]:
    display_table(df_rec[df_rec["mode"]=="new"],  "판매 기록 없는 신상/미판매 스타일의 최소가격 제시 (동종 평균가 반영)", platform_view)
with tabs[1]:
    display_table(df_rec[df_rec["mode"]=="slow"], "판매가 1~2건 이하인 슬로우셀러 (가격/경쟁가/동종평균 참고)", platform_view)
with tabs[2]:
    display_table(df_rec[df_rec["mode"]=="drop"], "판매 급감(직전30일대비 50%↓) 스타일의 가격 조정 추천", platform_view)
with tabs[3]:
    display_table(df_rec[df_rec["mode"]=="hot"],  "판매가 증가 중인 핫아이템 (가격 인상 가능)", platform_view)
