# ==========================================
# File: pages/3_가격제안.py
# ==========================================
import streamlit as st
import pandas as pd
import numpy as np
from dateutil import parser

# -------------------- 기본 설정 --------------------
st.set_page_config(page_title="가격 제안 대시보드", layout="wide")
st.title("💡 가격 제안 대시보드")

TODAY = pd.Timestamp.today().normalize()
MATURITY_DAYS = 90  # 성숙 기준: 최근 3개월 고정
MATURITY_CUTOFF = TODAY - pd.Timedelta(days=MATURITY_DAYS)

# -------------------- 유틸 --------------------
@st.cache_data(show_spinner=False)
def load_google_sheet(sheet_name):
    import gspread
    from oauth2client.service_account import ServiceAccountCredentials
    import json
    GOOGLE_SHEET_URL = "https://docs.google.com/spreadsheets/d/1oyVzCgGK1Q3Qi_sbYwE-wKG6SArnfUDRe7rQfGOF-Eo"
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive",
    ]
    json_data = {k: str(v) for k, v in st.secrets["gcp_service_account"].items()}
    with open("/tmp/service_account.json", "w") as f:
        json.dump(json_data, f)
    creds = ServiceAccountCredentials.from_json_keyfile_name("/tmp/service_account.json", scope)
    client = gspread.authorize(creds)
    ws = client.open_by_url(GOOGLE_SHEET_URL).worksheet(sheet_name)
    df = pd.DataFrame(ws.get_all_records())
    df.columns = [c.lower().strip() for c in df.columns]
    return df

def parse_temudate(dt):
    try:
        s = str(dt).split("(")[0].strip()
        return parser.parse(s, fuzzy=True)
    except Exception:
        return pd.NaT

def parse_sheindate(dt):
    try:
        return pd.to_datetime(str(dt), errors="coerce", infer_datetime_format=True)
    except Exception:
        return pd.NaT

def money_to_float(series: pd.Series) -> pd.Series:
    """$ , 문자 등 제거 후 숫자 변환"""
    return pd.to_numeric(series.astype(str).str.replace(r"[^0-9.\-]", "", regex=True),
                         errors="coerce")

def show_price(val):
    try:
        x = float(val)
        if pd.isna(x):
            return "-"
        return f"${x:,.2f}"
    except Exception:
        return "-" if (val is None or val == "" or pd.isna(val)) else str(val)

def make_img_tag(url):
    if pd.notna(url) and str(url).startswith("http"):
        return f"<img src='{url}' style='width:56px;height:auto;border-radius:8px;'>"
    return ""

# -------------------- 데이터 로드 & 정규화 --------------------
df_info  = load_google_sheet("PRODUCT_INFO")
df_temu  = load_google_sheet("TEMU_SALES")
df_shein = load_google_sheet("SHEIN_SALES")

# style key & 이미지 맵
df_info["style_key"] = df_info.get("product number", "").astype(str)
IMG_MAP = dict(zip(df_info["style_key"], df_info.get("image", "")))

# LIVE DATE (사용자 시트에 TEMU_LIVE_DATE / SHEIN_LIVE_DATE 로 있다고 가정)
df_info["temu_live_date"]  = pd.to_datetime(df_info.get("temu_live_date"),  errors="coerce", infer_datetime_format=True)
df_info["shein_live_date"] = pd.to_datetime(df_info.get("shein_live_date"), errors="coerce", infer_datetime_format=True)

# 주문 일자
df_temu["order date"]  = df_temu["purchase date"].apply(parse_temudate)
df_shein["order date"] = df_shein["order processed on"].apply(parse_sheindate)

# 상태/수량/금액 숫자화
df_temu["order item status"]  = df_temu["order item status"].astype(str)
df_temu["quantity shipped"]   = pd.to_numeric(df_temu.get("quantity shipped", 0), errors="coerce").fillna(0)
df_temu["base price total"]   = money_to_float(df_temu.get("base price total", pd.Series(dtype=object))).fillna(0.0)

df_shein["order status"] = df_shein["order status"].astype(str)
df_shein["product price"] = money_to_float(df_shein.get("product price", pd.Series(dtype=object))).fillna(0.0)

# -------------------- 플랫폼 설정 & 추천가 로직 --------------------
PLATFORM_CFG = {
    "TEMU":  {"fee_rate":0.12, "extra_fee":0.0, "base_add":7, "min_add":2, "floor":9},
    "SHEIN": {"fee_rate":0.15, "extra_fee":0.0, "base_add":7, "min_add":2, "floor":9},
}

def suggest_price_platform(erp, cur_price, comp_prices, mode, cfg):
    """
    erp: float
    cur_price: 현재가(숫자)
    comp_prices: 경쟁 후보들(리스트)
    mode: "new"|"slow"|"drop"|"hot"|"" 
    """
    base_min  = max(erp*(1+cfg["fee_rate"]) + cfg["min_add"], cfg["floor"])
    base_norm = max(erp*(1+cfg["fee_rate"]) + cfg["base_add"], cfg["floor"])

    p_cur = cur_price if (cur_price is not None and not pd.isna(cur_price) and cur_price > 0) else None
    comps = [x for x in comp_prices if x is not None and not pd.isna(x) and x > 0]
    best_comp  = min(comps) if comps else None
    worst_comp = max(comps) if comps else None

    BEAT_BY_SLOW = 0.20
    BEAT_BY_DROP = 0.50
    DISC_SLOW    = 0.03
    DISC_DROP    = 0.10

    UPLIFT_HOT_PCT  = 0.05
    UPLIFT_HOT_ABS  = 0.50
    BEAT_UPWARDS    = 1.00

    def _floor(x): return max(base_min, x)

    if mode in ["new", "slow"]:
        cands = []
        if p_cur:     cands.append(p_cur * (1 - DISC_SLOW))
        if best_comp: cands.append(best_comp - BEAT_BY_SLOW)
        cands.append(base_norm)
        rec = min([c for c in cands if c and c > 0])
        rec = _floor(rec)
        if p_cur and rec > p_cur:
            rec = p_cur

    elif mode == "drop":
        cands = []
        if p_cur:     cands.append(p_cur * (1 - DISC_DROP))
        if best_comp: cands.append(best_comp - BEAT_BY_DROP)
        cands.append(base_norm)
        rec = min([c for c in cands if c and c > 0])
        rec = _floor(rec)
        if p_cur and rec > p_cur:
            rec = p_cur

    elif mode == "hot":
        targets = []
        if p_cur:
            targets.append(p_cur * (1 + UPLIFT_HOT_PCT))
            targets.append(p_cur + UPLIFT_HOT_ABS)
        if worst_comp:
            targets.append(worst_comp + BEAT_UPWARDS)
        targets.append(base_norm)

        rec = max([t for t in targets if t and t > 0])
        rec = _floor(rec)
        if p_cur and rec < p_cur:
            rec = _floor(max(p_cur + UPLIFT_HOT_ABS, p_cur*(1+UPLIFT_HOT_PCT)))

    else:
        cands = []
        if p_cur:     cands.append(p_cur)
        if best_comp: cands.append(best_comp - BEAT_BY_SLOW)
        cands.append(base_norm)
        rec = min([c for c in cands if c and c > 0])
        rec = _floor(rec)
        if p_cur and rec > p_cur:
            rec = p_cur

    return round(rec, 2)

# -------------------- 판매 집계 함수 --------------------
def qty_last_n_days(df, style_col, style, days, status_col=None, shipped_values=None):
    now  = TODAY + pd.Timedelta(hours=23, minutes=59, seconds=59)
    since = TODAY - pd.Timedelta(days=days)
    d = df[df[style_col].astype(str) == str(style)].copy()
    if status_col and shipped_values:
        d = d[d[status_col].astype(str).str.lower().isin([s.lower() for s in shipped_values])]
    d = d[(d["order date"] >= since) & (d["order date"] <= now)]
    if "quantity shipped" in d.columns:
        return pd.to_numeric(d["quantity shipped"], errors="coerce").fillna(0).sum()
    else:
        return len(d)  # SHEIN 건수

def total_qty(df, style_col, style, status_col=None, shipped_values=None):
    d = df[df[style_col].astype(str) == str(style)].copy()
    if status_col and shipped_values:
        d = d[d[status_col].astype(str).str.lower().isin([s.lower() for s in shipped_values])]
    if "quantity shipped" in d.columns:
        return pd.to_numeric(d["quantity shipped"], errors="coerce").fillna(0).sum()
    else:
        return len(d)

def current_price_mean(df, style_col, style, price_col):
    ser = df[df[style_col].astype(str) == str(style)][price_col]
    ser = pd.to_numeric(ser, errors="coerce")
    ser = ser[ser > 0]
    return float(ser.mean()) if not ser.empty else np.nan

# -------------------- 플랫폼 라디오 --------------------
platform_view = st.radio("플랫폼", options=["TEMU","SHEIN"], horizontal=True)

# -------------------- 성숙 90일 고정 안내 --------------------
with st.expander("진단", expanded=True):
    if platform_view == "TEMU":
        cnt_mature = df_info["temu_live_date"].notna().sum()
        st.caption(f"TEMU 라이브 입력 수: {cnt_mature:,}")
    else:
        cnt_mature = df_info["shein_live_date"].notna().sum()
        st.caption(f"SHEIN 라이브 입력 수: {cnt_mature:,}")
    st.caption(f"성숙 기준: 등록 후 **{MATURITY_DAYS}일** 경과 상품만 분석")

# -------------------- 레코드 빌드 --------------------
records = []
for _, row in df_info.iterrows():
    style = str(row.get("style_key"))
    erp   = pd.to_numeric(str(row.get("erp price", "")).replace("$","").replace(",",""), errors="coerce")
    img   = IMG_MAP.get(style, "")

    # 플랫폼별 live date 확인 + 등록 90일 경과 필터 (등록 안됨/90일 미만이면 제외)
    if platform_view == "TEMU":
        live_dt = row.get("temu_live_date")
        if pd.isna(live_dt) or (live_dt > MATURITY_CUTOFF):
            continue  # 제외
        # 판매 집계
        qty30      = qty_last_n_days(df_temu, "product number", style, 30,
                                     status_col="order item status", shipped_values=["shipped","delivered"])
        qty30_prev = qty_last_n_days(df_temu, "product number", style, 60,
                                     status_col="order item status", shipped_values=["shipped","delivered"]) - qty30
        qty_all    = total_qty(df_temu, "product number", style,
                               status_col="order item status", shipped_values=["shipped","delivered"])
        cur_price  = current_price_mean(df_temu, "product number", style, "base price total")
        comp_price = current_price_mean(df_shein, "product description", style, "product price")

    else:  # SHEIN
        live_dt = row.get("shein_live_date")
        if pd.isna(live_dt) or (live_dt > MATURITY_CUTOFF):
            continue  # 제외
        qty30      = qty_last_n_days(df_shein, "product description", style, 30)
        qty30_prev = qty_last_n_days(df_shein, "product description", style, 60) - qty30
        qty_all    = total_qty(df_shein, "product description", style)
        cur_price  = current_price_mean(df_shein, "product description", style, "product price")
        comp_price = current_price_mean(df_temu, "product number", style, "base price total")

    # 분류
    if qty30 == 0 and qty_all == 0:
        mode, why = "new", "등록 90일 경과했지만 판매 기록 없음"
    elif qty30 <= 2:
        mode, why = "slow", "최근 30일 판매 1~2건 이하 (슬로우셀러)"
    elif qty30_prev >= 2*qty30 and qty30 > 0:
        mode, why = "drop", "최근 30일 판매 급감 (직전 30일 대비 50%↓)"
    elif qty30 >= 10 and qty30 > qty30_prev:
        mode, why = "hot", "최근 30일 판매 증가 (가격 인상 후보)"
    else:
        mode, why = "", ""

    # 추천가 계산(동일 플랫폼 기준, 경쟁가는 반대 플랫폼 평균가로 사용)
    cfg = PLATFORM_CFG[platform_view]
    rec_price = suggest_price_platform(erp, cur_price, [comp_price], mode, cfg)

    records.append({
        "이미지": make_img_tag(img),
        "Style Number": style,
        "ERP Price": show_price(erp),
        f"{platform_view} 현재가": show_price(cur_price),
        f"추천가_{platform_view}": show_price(rec_price),
        "30일판매": int(qty30),
        "이전30일": int(qty30_prev),
        "전체판매": int(qty_all),
        "사유": why,
        "mode": mode
    })

df_rec = pd.DataFrame(records)

# -------------------- 표 렌더 --------------------
def highlight_price(val):
    if val not in ["-", None, ""] and not pd.isna(val):
        return 'background-color:#d4edda; color:#155724; font-weight:700;'
    return ''

def display_table(df, comment):
    cols = ["이미지","Style Number","ERP Price",
            f"{platform_view} 현재가", f"추천가_{platform_view}",
            "30일판매","이전30일","전체판매","사유"]
    if df.empty:
        st.info("표시할 데이터가 없습니다.")
        return
    styled = df[cols].style.applymap(
        highlight_price, subset=[f"추천가_{platform_view}"]
    )
    st.markdown(f"**{comment}**")
    st.write(styled.to_html(escape=False, index=False), unsafe_allow_html=True)

st.markdown("""
<style>
[data-testid="stMarkdownContainer"] table { width: 100% !important; }
</style>
""", unsafe_allow_html=True)

tabs = st.tabs(["🟥 미판매(등록 90일↑)", "🟠 판매 저조", "📉 판매 급감", "🔥 가격 인상 추천"])

with tabs[0]:
    display_table(df_rec[df_rec["mode"]=="new"],   "등록 90일 경과 & 판매 0건 (노출/카테고리/키워드 전면 점검)")
with tabs[1]:
    display_table(df_rec[df_rec["mode"]=="slow"],  "최근 30일 1~2건 이하 (경쟁가 하회 + 현재가 인상 금지)")
with tabs[2]:
    display_table(df_rec[df_rec["mode"]=="drop"],  "직전 30일 대비 50%↓ (강한 할인, 인상 금지)")
with tabs[3]:
    display_table(df_rec[df_rec["mode"]=="hot"],   "판매 증가 핫아이템 (최소 5% 또는 $0.5 인상, 경쟁가+α)")
