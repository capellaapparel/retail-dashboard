# ==========================================
# File: pages/3_가격제안.py
# (라이브 90일 미만 자동 제외 + 빈 후보 처리 보강)
# ==========================================
import streamlit as st
import pandas as pd
import numpy as np
from dateutil import parser

# -------------------------
# 기본 설정
# -------------------------
st.set_page_config(page_title="가격 제안 대시보드", layout="wide")
st.title("💡 가격 제안 대시보드")

MATURE_DAYS = 90  # 성숙 기준 고정: 등록 후 90일

# -------------------------
# 유틸
# -------------------------
def safe_float(x):
    try:
        if pd.isna(x):
            return np.nan
        return float(str(x).replace("$", "").replace(",", ""))
    except Exception:
        return np.nan

def money_to_float_series(s: pd.Series) -> pd.Series:
    return pd.to_numeric(
        s.astype(str).str.replace(r"[^0-9.\-]", "", regex=True),
        errors="coerce"
    ).fillna(0.0)

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

def parse_temudate(dt):
    try:
        return parser.parse(str(dt).split("(")[0].strip(), fuzzy=True)
    except Exception:
        return pd.NaT

def parse_sheindate(dt):
    try:
        return pd.to_datetime(str(dt), errors="coerce", infer_datetime_format=True)
    except Exception:
        return pd.NaT

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
    ws = client.open_by_url(GOOGLE_SHEET_URL).worksheet(sheet_name)
    df = pd.DataFrame(ws.get_all_records())
    df.columns = [c.lower().strip() for c in df.columns]
    return df

# ===================== 데이터 로드 =====================
df_info  = load_google_sheet("PRODUCT_INFO")
df_temu  = load_google_sheet("TEMU_SALES")
df_shein = load_google_sheet("SHEIN_SALES")

# 날짜 정규화
df_temu["order date"]  = df_temu["purchase date"].apply(parse_temudate)
df_shein["order date"] = df_shein["order processed on"].apply(parse_sheindate)

# 숫자/상태 정규화
df_temu["order item status"] = df_temu["order item status"].astype(str)
df_temu["quantity shipped"]  = pd.to_numeric(df_temu.get("quantity shipped", 0), errors="coerce").fillna(0.0)
if "base price total" in df_temu.columns:
    df_temu["base price total"] = money_to_float_series(df_temu["base price total"])

df_shein["order status"]   = df_shein["order status"].astype(str)
if "product price" in df_shein.columns:
    df_shein["product price"] = money_to_float_series(df_shein["product price"])

# 이미지 맵 & ERP
img_dict = dict(zip(df_info.get("product number", pd.Series(dtype=str)).astype(str), df_info.get("image", "")))

def to_erp(x):
    try:
        return float(str(x).replace("$", "").replace(",", ""))
    except Exception:
        return np.nan

df_info["erp price"] = df_info["erp price"].apply(to_erp)

# LIVE DATE (등록일) 컬럼 정리
for c in ["temu_live_date", "shein_live_date"]:
    if c not in df_info.columns:
        df_info[c] = None
df_info["temu_live_date"]  = pd.to_datetime(df_info["temu_live_date"],  errors="coerce", infer_datetime_format=True)
df_info["shein_live_date"] = pd.to_datetime(df_info["shein_live_date"], errors="coerce", infer_datetime_format=True)

# ===================== 분석 기간 (최근 30일 고정) =====================
now_ts = pd.Timestamp.today().normalize() + pd.Timedelta(hours=23, minutes=59, seconds=59)
start_30 = now_ts - pd.Timedelta(days=29)
prev_30_start = start_30 - pd.Timedelta(days=30)
prev_30_end   = start_30 - pd.Timedelta(seconds=1)

# ===================== 플랫폼 선택 =====================
platform_view = st.radio("플랫폼", options=["TEMU", "SHEIN"], horizontal=True)

st.caption(f"성숙 기준: 등록 후 **{MATURE_DAYS}일** 경과된 상품만 분석 (등록일은 PRODUCT_INFO 시트의 TEMU_LIVE_DATE / SHEIN_LIVE_DATE 사용)")

# ===================== 플랫폼별 현재가 =====================
def temu_now_num(style):
    vals = df_temu[df_temu["product number"].astype(str) == str(style)]["base price total"]
    vals = vals[vals > 0]
    return float(vals.mean()) if len(vals) > 0 else np.nan

def shein_now_num(style):
    vals = df_shein[df_shein["product description"].astype(str) == str(style)]["product price"]
    vals = vals[vals > 0]
    return float(vals.mean()) if len(vals) > 0 else np.nan

# ===================== 판매 집계(최근/직전 30일) =====================
def get_qty(df, style, s, e, platform):
    """플랫폼별 수량 집계 (TEMU는 quantity shipped, SHEIN은 건수 1)"""
    if platform == "TEMU":
        d = df[(df["product number"].astype(str) == str(style)) &
               (df["order date"] >= s) & (df["order date"] <= e) &
               (df["order item status"].str.lower().isin(["shipped", "delivered"]))].copy()
        return pd.to_numeric(d["quantity shipped"], errors="coerce").fillna(0).sum()
    else:
        d = df[(df["product description"].astype(str) == str(style)) &
               (df["order date"] >= s) & (df["order date"] <= e) &
               (~df["order status"].str.lower().eq("customer refunded"))].copy()
        return d.shape[0]

# ===================== 추천가 로직 =====================
PLATFORM_CFG = {
    "TEMU":  {"fee_rate": 0.12, "extra_fee": 0.0, "base_add": 7, "min_add": 2, "floor": 9},
    "SHEIN": {"fee_rate": 0.15, "extra_fee": 0.0, "base_add": 7, "min_add": 2, "floor": 9},
}

def suggest_price_platform(erp, cur_price, comp_prices, mode, cfg):
    """
    erp: float
    cur_price: 현재 우리 플랫폼가(숫자, NaN 가능)
    comp_prices: 경쟁 후보들(타플랫폼 현재가, 유사 평균 등) 숫자 리스트
    mode: "new"|"slow"|"drop"|"hot"|"" 
    cfg: {"fee_rate","min_add","base_add","floor"}
    """
    # 최소 기준
    base_min  = max((erp or 0.0) * (1 + cfg["fee_rate"]) + cfg["min_add"], cfg["floor"])
    base_norm = max((erp or 0.0) * (1 + cfg["fee_rate"]) + cfg["base_add"], cfg["floor"])

    p_cur = None
    try:
        if cur_price is not None and not pd.isna(cur_price) and float(cur_price) > 0:
            p_cur = float(cur_price)
    except Exception:
        p_cur = None

    comps = []
    for x in comp_prices:
        try:
            if x is not None and not pd.isna(x) and float(x) > 0:
                comps.append(float(x))
        except Exception:
            continue

    best_comp  = min(comps) if comps else None
    worst_comp = max(comps) if comps else None

    # 튜닝값
    BEAT_BY_SLOW = 0.20     # 경쟁가보다 이만큼 싸게(슬로우/보통)
    BEAT_BY_DROP = 0.50     # 급감은 더 크게
    DISC_SLOW    = 0.03     # 현재가 대비 3% 인하(슬로우)
    DISC_DROP    = 0.10     # 현재가 대비 10% 인하(급감)

    UPLIFT_HOT_PCT  = 0.05  # 핫: 최소 5% 인상
    UPLIFT_HOT_ABS  = 0.50  # 핫: 혹은 최소 +$0.5 인상
    BEAT_UPWARDS    = 1.00  # 핫: 경쟁가를 +$1 넘겨서 적정가 앵커링

    def _floor(x):
        try:
            z = float(x)
        except Exception:
            z = base_norm
        return max(base_min, z)

    # 각 모드별 후보 가격 산출(빈 리스트 방지)
    cands = []

    if mode in ["new", "slow"]:
        if p_cur:     cands.append(p_cur * (1 - DISC_SLOW))
        if best_comp: cands.append(best_comp - BEAT_BY_SLOW)
        cands.append(base_norm)
        # 하한 보정
        cands = [_floor(c) for c in cands if c and c > 0]
        if not cands:
            return round(_floor(base_norm), 2)
        rec = min(cands)
        if p_cur and rec > p_cur:   # 절대 인상 금지
            rec = p_cur

    elif mode == "drop":
        if p_cur:     cands.append(p_cur * (1 - DISC_DROP))
        if best_comp: cands.append(best_comp - BEAT_BY_DROP)
        cands.append(base_norm)
        cands = [_floor(c) for c in cands if c and c > 0]
        if not cands:
            return round(_floor(base_norm), 2)
        rec = min(cands)
        if p_cur and rec > p_cur:
            rec = p_cur

    elif mode == "hot":
        if p_cur:
            cands.append(p_cur * (1 + UPLIFT_HOT_PCT))
            cands.append(p_cur + UPLIFT_HOT_ABS)
        if worst_comp:
            cands.append(worst_comp + BEAT_UPWARDS)
        cands.append(base_norm)
        cands = [_floor(c) for c in cands if c and c > 0]
        if not cands:
            return round(_floor(base_norm if not p_cur else max(p_cur + UPLIFT_HOT_ABS, p_cur*(1+UPLIFT_HOT_PCT))), 2)
        rec = max(cands)
        if p_cur and rec < p_cur:  # 혹시라도 하향되면 강제 인상
            rec = _floor(max(p_cur + UPLIFT_HOT_ABS, p_cur*(1+UPLIFT_HOT_PCT)))

    else:
        if p_cur:     cands.append(p_cur)
        if best_comp: cands.append(best_comp - BEAT_BY_SLOW)
        cands.append(base_norm)
        cands = [_floor(c) for c in cands if c and c > 0]
        if not cands:
            return round(_floor(base_norm), 2)
        rec = min(cands)
        if p_cur and rec > p_cur:
            rec = p_cur

    return round(_floor(rec), 2)

# ===================== 유사 스타일 평균가(간단) =====================
def similar_avg(style):
    tem = df_temu[df_temu["product number"].astype(str) != str(style)]["base price total"]
    sh  = df_shein[df_shein["product description"].astype(str) != str(style)]["product price"]
    pool = []
    if tem.notna().mean() > 0:
        pool.append(tem.mean())
    if sh.notna().mean() > 0:
        pool.append(sh.mean())
    return float(np.nanmean(pool)) if pool else np.nan

# ===================== 레코드 빌드 (성숙 90일 이후만) =====================
def build_records_for_platform(platform: str):
    today = pd.Timestamp.today().normalize()
    live_col = "temu_live_date" if platform == "TEMU" else "shein_live_date"

    records = []
    for _, row in df_info.iterrows():
        style = str(row.get("product number", "")).strip()
        if not style:
            continue

        live_dt = row.get(live_col)
        if pd.isna(live_dt):
            # 해당 플랫폼에 등록 안된 상품은 스킵
            continue

        # 성숙 기준 적용
        if (today - pd.to_datetime(live_dt)).days < MATURE_DAYS:
            # 90일 미만은 분석 제외
            continue

        erp   = row.get("erp price", np.nan)
        img   = img_dict.get(style, "")

        # 최근/직전 30일 판매 수량 (플랫폼별)
        if platform == "TEMU":
            qty30      = get_qty(df_temu,  style, start_30, now_ts, "TEMU")
            qty30_prev = get_qty(df_temu,  style, prev_30_start, prev_30_end, "TEMU")
            cur_price  = temu_now_num(style)
            comp_price = shein_now_num(style)  # 타플랫폼 평균가
        else:
            qty30      = get_qty(df_shein, style, start_30, now_ts, "SHEIN")
            qty30_prev = get_qty(df_shein, style, prev_30_start, prev_30_end, "SHEIN")
            cur_price  = shein_now_num(style)
            comp_price = temu_now_num(style)

        qty_all = qty30 + qty30_prev  # 총 판매(최근60일)

        # 모드 판정
        if qty30 == 0:
            mode, why = "new", "최근 30일 판매 없음 (성숙 90일 경과)"
        elif qty30 <= 2:
            mode, why = "slow", "최근 30일 판매 1~2건 (저조)"
        elif qty30_prev > 0 and qty30 <= 0.5 * qty30_prev:
            mode, why = "drop", "판매 급감 (직전 30일 대비 50%↓)"
        elif qty30 >= 10 and qty30 > qty30_prev:
            mode, why = "hot", "판매 증가 (가격 인상 추천)"
        else:
            mode, why = "", ""

        sim   = similar_avg(style)
        rec   = suggest_price_platform(erp, cur_price, [comp_price, sim], mode, PLATFORM_CFG[platform])

        rec_row = {
            "이미지": make_img_tag(img),
            "Style Number": style,
            "ERP Price": show_price(erp),
            f"{platform} 현재가": show_price(cur_price),
            f"추천가_{platform}": show_price(rec),
            "30일판매": int(qty30),
            "이전30일": int(qty30_prev),
            "최근60일": int(qty_all),
            "사유": why,
            "mode": mode
        }
        records.append(rec_row)

    return pd.DataFrame(records)

df_rec = build_records_for_platform(platform_view)

# ===================== 보기: 추천가 하이라이트 =====================
def highlight_price(val):
    if val not in ["-", None, ""] and not pd.isna(val):
        return 'background-color:#d4edda; color:#155724; font-weight:700;'
    return ''

def display_table(df, comment, platform_view):
    if df.empty:
        st.info("표시할 데이터가 없습니다.")
        return

    cols = ["이미지", "Style Number", "ERP Price",
            f"{platform_view} 현재가", f"추천가_{platform_view}",
            "30일판매", "이전30일", "최근60일", "사유"]
    show = df[cols].copy()
    styled = show.style.applymap(highlight_price, subset=[f"추천가_{platform_view}"])

    st.markdown(f"**{comment}**")
    st.write(styled.to_html(escape=False, index=False), unsafe_allow_html=True)

# ===================== 탭 =====================
tabs = st.tabs(["🆕 미판매/신규 (성숙 90일↑)", "🟠 판매 저조 (성숙 90일↑)", "📉 판매 급감 (성숙 90일↑)", "🔥 가격 인상 추천"])

with tabs[0]:
    display_table(df_rec[df_rec["mode"] == "new"],  "최근 30일 판매 없음 (등록 후 90일 경과 상품)", platform_view)
with tabs[1]:
    display_table(df_rec[df_rec["mode"] == "slow"], "최근 30일 판매 1~2건 저조 (등록 후 90일 경과)", platform_view)
with tabs[2]:
    display_table(df_rec[df_rec["mode"] == "drop"], "직전 30일 대비 50% 이상 급감 (등록 후 90일 경과)", platform_view)
with tabs[3]:
    display_table(df_rec[df_rec["mode"] == "hot"],  "판매 증가 핫아이템 (최소 5% 또는 $0.5 인상 + 경쟁가+α)", platform_view)

# ===================== 상단 요약(디버깅/확인용) =====================
with st.expander("진단"):
    live_col = "temu_live_date" if platform_view == "TEMU" else "shein_live_date"
    today = pd.Timestamp.today().normalize()
    live_age = (today - pd.to_datetime(df_info[live_col], errors="coerce")).dt.days
    st.write(f"{platform_view} 라이브 입력 수:", int(df_info[live_col].notna().sum()))
    st.write(f"성숙 기준: 등록 후 {MATURE_DAYS}일 경과 상품만 분석")
    st.write("라이브 컬럼 null:", int(df_info[live_col].isna().sum()))
    st.write("평균 live age(fyi):", float(live_age.dropna().mean()) if live_age.notna().any() else "N/A")
