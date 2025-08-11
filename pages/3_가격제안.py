# ==========================================
# File: pages/3_가격제안.py
# ==========================================
import streamlit as st
import pandas as pd
import numpy as np
from dateutil import parser

# ============== 공통 유틸 ==============
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

def _key(s): return str(s).upper().replace(" ", "")

# ============== 데이터 로드 ==============
st.set_page_config(page_title="가격 제안 대시보드", layout="wide")
st.title("💡 가격 제안 대시보드")

df_info  = load_google_sheet("PRODUCT_INFO")
df_temu  = load_google_sheet("TEMU_SALES")
df_shein = load_google_sheet("SHEIN_SALES")

df_temu["order date"]  = df_temu["purchase date"].apply(parse_temudate)
df_shein["order date"] = df_shein["order processed on"].apply(parse_sheindate)

# style_key & LIVE DATE 맵
df_info["style_key"] = df_info["product number"].astype(str).map(_key)
temu_live_map  = dict(zip(df_info["style_key"], pd.to_datetime(df_info.get("temu_live_date"),  errors="coerce")))
shein_live_map = dict(zip(df_info["style_key"], pd.to_datetime(df_info.get("shein_live_date"), errors="coerce")))

img_dict = dict(zip(df_info["product number"].astype(str), df_info["image"]))

# ERP price 정규화
def to_erp(x):
    try: return float(str(x).replace("$","").replace(",",""))
    except: return np.nan
df_info["erp price"] = df_info["erp price"].apply(to_erp)

# ============== 플랫폼별 현재가 (등록일 이후만) ==============
def temu_now_num(style):
    key = _key(style)
    live = temu_live_map.get(key, pd.NaT)
    if pd.isna(live):   # 미등록 → 제외
        return np.nan
    d = df_temu[df_temu["product number"].astype(str)==str(style)].copy()
    d = d[d["order date"]>=live]
    vals = d["base price total"].apply(safe_float)
    vals = vals[vals>0]
    return float(vals.mean()) if len(vals)>0 else np.nan

def shein_now_num(style):
    key = _key(style)
    live = shein_live_map.get(key, pd.NaT)
    if pd.isna(live):
        return np.nan
    d = df_shein[df_shein["product description"].astype(str)==str(style)].copy()
    d = d[d["order date"]>=live]
    vals = d["product price"].apply(safe_float)
    vals = vals[vals>0]
    return float(vals.mean()) if len(vals)>0 else np.nan

# ============== 플랫폼별 판매 집계 (등록일 이후만) ==============
def get_qty_temu(style, days):
    key = _key(style)
    live = temu_live_map.get(key, pd.NaT)
    if pd.isna(live):      # 미등록 → 0 취급 (후에 필터에서 제외)
        return 0
    now = pd.Timestamp.now(); since = max(now - pd.Timedelta(days=days), live)
    d = df_temu[df_temu["product number"].astype(str)==str(style)].copy()
    d = d[d["order item status"].astype(str).str.lower().isin(["shipped","delivered"])]
    d = d[(d["order date"]>=since) & (d["order date"]<=now)]
    return pd.to_numeric(d["quantity shipped"], errors="coerce").fillna(0).sum()

def get_qty_shein(style, days):
    key = _key(style)
    live = shein_live_map.get(key, pd.NaT)
    if pd.isna(live):
        return 0
    now = pd.Timestamp.now(); since = max(now - pd.Timedelta(days=days), live)
    d = df_shein[df_shein["product description"].astype(str)==str(style)].copy()
    d = d[~d["order status"].astype(str).str.lower().isin(["customer refunded"])]
    d = d[(d["order date"]>=since) & (d["order date"]<=now)]
    return d.shape[0]

# ============== 추천가 로직 ==============
PLATFORM_CFG = {
    "TEMU":  {"fee_rate":0.12, "extra_fee":0.0, "base_add":7, "min_add":2, "floor":9},
    "SHEIN": {"fee_rate":0.15, "extra_fee":0.0, "base_add":7, "min_add":2, "floor":9},
}

def suggest_price_platform(erp, cur_price, comp_prices, mode, cfg):
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
        if p_cur and rec > p_cur:   # 상향 금지
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

def similar_avg(style):
    tem = df_temu[df_temu["product number"].astype(str)!=str(style)]["base price total"].apply(safe_float)
    sh  = df_shein[df_shein["product description"].astype(str)!=str(style)]["product price"].apply(safe_float)
    pool = []
    if tem.notna().mean()>0: pool.append(tem.mean())
    if sh.notna().mean()>0:  pool.append(sh.mean())
    return np.nanmean(pool) if pool else np.nan

def classify(q30, q30_prev):
    if q30 == 0:
        return "new", "한 번도 팔리지 않음"
    elif q30 <= 2:
        return "slow", "판매 1~2건 이하 (슬로우셀러)"
    elif q30_prev >= 2*q30 and q30 > 0:
        return "drop", "판매 급감 (직전 30일대비 50%↓)"
    elif q30 >= 10 and q30 > q30_prev:
        return "hot", "최근 30일 판매 급증, 가격 인상 추천"
    else:
        return "", ""

# ============== 레코드 빌드 (플랫폼 분리 & 미등록 제외 플래그) ==============
records = []
now_ts = pd.Timestamp.now().normalize()
for _, row in df_info.iterrows():
    style = str(row["product number"])
    s_key = _key(style)
    erp   = row["erp price"]
    img   = img_dict.get(style, "")

    temu_live  = temu_live_map.get(s_key, pd.NaT)
    shein_live = shein_live_map.get(s_key, pd.NaT)
    temu_registered  = pd.notna(temu_live)
    shein_registered = pd.notna(shein_live)

    days_since_temu  = int((now_ts - temu_live).days)  if temu_registered  else None
    days_since_shein = int((now_ts - shein_live).days) if shein_registered else None

    # TEMU (등록일 이후 데이터만)
    t_cur  = temu_now_num(style) if temu_registered else np.nan
    t_30   = int(get_qty_temu(style, 30)) if temu_registered else 0
    t_60   = int(get_qty_temu(style, 60)) if temu_registered else 0
    t_30p  = t_60 - t_30
    t_all  = int(get_qty_temu(style, 9999)) if temu_registered else 0
    mode_t, why_t = classify(t_30, t_30p) if temu_registered else ("", "")

    # SHEIN (등록일 이후 데이터만)
    s_cur  = shein_now_num(style) if shein_registered else np.nan
    s_30   = int(get_qty_shein(style, 30)) if shein_registered else 0
    s_60   = int(get_qty_shein(style, 60)) if shein_registered else 0
    s_30p  = s_60 - s_30
    s_all  = int(get_qty_shein(style, 9999)) if shein_registered else 0
    mode_s, why_s = classify(s_30, s_30p) if shein_registered else ("", "")

    sim   = similar_avg(style)

    rec_t = suggest_price_platform(erp, t_cur, [s_cur, sim], mode_t, PLATFORM_CFG["TEMU"])  if temu_registered else np.nan
    rec_s = suggest_price_platform(erp, s_cur, [t_cur, sim], mode_s, PLATFORM_CFG["SHEIN"]) if shein_registered else np.nan

    records.append({
        "이미지": make_img_tag(img),
        "Style Number": style,
        "ERP Price": show_price(erp),

        # 등록/경과일
        "temu_registered": temu_registered,
        "shein_registered": shein_registered,
        "temu_live_date": temu_live,
        "shein_live_date": shein_live,
        "days_since_temu": days_since_temu,
        "days_since_shein": days_since_shein,

        # TEMU
        "TEMU 현재가": show_price(t_cur),
        "추천가_TEMU": show_price(rec_t),
        "30일판매_TEMU": t_30,
        "이전30일_TEMU": t_30p,
        "전체판매_TEMU": t_all,
        "사유_TEMU": why_t,
        "mode_TEMU": mode_t,

        # SHEIN
        "SHEIN 현재가": show_price(s_cur),
        "추천가_SHEIN": show_price(rec_s),
        "30일판매_SHEIN": s_30,
        "이전30일_SHEIN": s_30p,
        "전체판매_SHEIN": s_all,
        "사유_SHEIN": why_s,
        "mode_SHEIN": mode_s,
    })

df_rec = pd.DataFrame(records)

# ============== 보기: TEMU / SHEIN (미등록 제외 + 3개월 경과 필터) ==============
platform_view = st.radio("플랫폼", options=["TEMU","SHEIN"], horizontal=True)

MATURITY_DAYS = 90  # 업로드 후 3개월

def highlight_price(val):
    if val not in ["-", None, ""] and not pd.isna(val):
        return 'background-color:#d4edda; color:#155724; font-weight:700;'
    return ''

def display_table(df, comment, platform_view, cols):
    st.markdown(f"**{comment}**")
    if platform_view == "TEMU":
        styled = df[cols].style.applymap(highlight_price, subset=["추천가_TEMU"])
    else:
        styled = df[cols].style.applymap(highlight_price, subset=["추천가_SHEIN"])
    st.write(styled.to_html(escape=False, index=False), unsafe_allow_html=True)

if platform_view == "TEMU":
    base_cols = ["이미지","Style Number","ERP Price","TEMU 현재가","추천가_TEMU","30일판매_TEMU","이전30일_TEMU","전체판매_TEMU","사유_TEMU"]
    view = df_rec[df_rec["temu_registered"]].copy()

    # ▶ 판매없음/저조 탭에는 '등록 후 90일 경과' 조건 적용
    mature_mask = view["days_since_temu"].fillna(0) >= MATURITY_DAYS

    tabs = st.tabs(["🆕 판매 없음", "🟠 판매 저조", "📉 판매 급감", "🔥 가격 인상 추천"])
    with tabs[0]:
        display_table(view[(view["mode_TEMU"]=="new") & mature_mask],  "TEMU 미판매/신규 (등록 90일 경과만 표시)", "TEMU", base_cols)
    with tabs[1]:
        display_table(view[(view["mode_TEMU"]=="slow") & mature_mask], "TEMU 슬로우셀러 (등록 90일 경과만 표시)", "TEMU", base_cols)
    with tabs[2]:
        display_table(view[view["mode_TEMU"]=="drop"], "TEMU 판매 급감", "TEMU", base_cols)
    with tabs[3]:
        display_table(view[view["mode_TEMU"]=="hot"],  "TEMU 핫아이템", "TEMU", base_cols)

else:
    base_cols = ["이미지","Style Number","ERP Price","SHEIN 현재가","추천가_SHEIN","30일판매_SHEIN","이전30일_SHEIN","전체판매_SHEIN","사유_SHEIN"]
    view = df_rec[df_rec["shein_registered"]].copy()

    mature_mask = view["days_since_shein"].fillna(0) >= MATURITY_DAYS

    tabs = st.tabs(["🆕 판매 없음", "🟠 판매 저조", "📉 판매 급감", "🔥 가격 인상 추천"])
    with tabs[0]:
        display_table(view[(view["mode_SHEIN"]=="new") & mature_mask],  "SHEIN 미판매/신규 (등록 90일 경과만 표시)", "SHEIN", base_cols)
    with tabs[1]:
        display_table(view[(view["mode_SHEIN"]=="slow") & mature_mask], "SHEIN 슬로우셀러 (등록 90일 경과만 표시)", "SHEIN", base_cols)
    with tabs[2]:
        display_table(view[view["mode_SHEIN"]=="drop"], "SHEIN 판매 급감", "SHEIN", base_cols)
    with tabs[3]:
        display_table(view[view["mode_SHEIN"]=="hot"],  "SHEIN 핫아이템", "SHEIN", base_cols)
