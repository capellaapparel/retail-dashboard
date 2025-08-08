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
PLATFORM_CFG = {
    "TEMU":  {"fee_rate":0.12, "extra_fee":0.0, "base_add":7, "min_add":2, "floor":9},
    "SHEIN": {"fee_rate":0.15, "extra_fee":0.0, "base_add":7, "min_add":2, "floor":9},
}

def suggest_price_platform(erp, cur_price, comp_prices, mode, cfg):
    """
    erp: float
    cur_price: 현재 우리 플랫폼가(숫자, NaN 가능)
    comp_prices: 경쟁 후보들(타플랫폼 현재가, 유사 평균 등) 숫자 리스트
    mode: "new"|"slow"|"drop"|"hot"|"" 
    cfg: {"fee_rate","min_add","base_add","floor"}
    """
    base_min  = max(erp*(1+cfg["fee_rate"]) + cfg["min_add"], cfg["floor"])
    base_norm = max(erp*(1+cfg["fee_rate"]) + cfg["base_add"], cfg["floor"])

    p_cur = cur_price if (cur_price is not None and not pd.isna(cur_price) and cur_price > 0) else None
    comps = [x for x in comp_prices if x is not None and not pd.isna(x) and x > 0]
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

    def _floor(x): return max(base_min, x)

    if mode in ["new", "slow"]:
        # 하향만(=상승 금지)
        cands = []
        if p_cur:     cands.append(p_cur * (1 - DISC_SLOW))
        if best_comp: cands.append(best_comp - BEAT_BY_SLOW)
        cands.append(base_norm)
        rec = min([c for c in cands if c and c > 0])
        rec = _floor(rec)
        if p_cur and rec > p_cur:   # 절대 인상 금지
            rec = p_cur

    elif mode == "drop":
        # 더 강한 하향, 상승 금지
        cands = []
        if p_cur:     cands.append(p_cur * (1 - DISC_DROP))
        if best_comp: cands.append(best_comp - BEAT_BY_DROP)
        cands.append(base_norm)
        rec = min([c for c in cands if c and c > 0])
        rec = _floor(rec)
        if p_cur and rec > p_cur:
            rec = p_cur

    elif mode == "hot":
        # ✅ 인상 강제: 절대 현재가 미만으로 내려가지 않음
        targets = []
        if p_cur:
            targets.append(p_cur * (1 + UPLIFT_HOT_PCT))
            targets.append(p_cur + UPLIFT_HOT_ABS)
        if worst_comp:
            targets.append(worst_comp + BEAT_UPWARDS)
        targets.append(base_norm)

        rec = max([t for t in targets if t and t > 0])
        rec = _floor(rec)

        # 혹시라도 계산상 하향이 나오면 현재가보다 조금이라도 올려서 강제 인상
        if p_cur and rec < p_cur:
            rec = _floor(max(p_cur + UPLIFT_HOT_ABS, p_cur*(1+UPLIFT_HOT_PCT)))

    else:
        # 보통: 상향 금지, 경쟁가 살짝 하회
        cands = []
        if p_cur:     cands.append(p_cur)
        if best_comp: cands.append(best_comp - BEAT_BY_SLOW)
        cands.append(base_norm)
        rec = min([c for c in cands if c and c > 0])
        rec = _floor(rec)
        if p_cur and rec > p_cur:
            rec = p_cur

    return round(rec, 2)

# ===================== 유사 스타일 평균가(간단) =====================
def similar_avg(style):
    tem = df_temu[df_temu["product number"].astype(str)!=str(style)]["base price total"].apply(safe_float)
    sh  = df_shein[df_shein["product description"].astype(str)!=str(style)]["product price"].apply(safe_float)
    pool = []
    if tem.notna().mean()>0: pool.append(tem.mean())
    if sh.notna().mean()>0:  pool.append(sh.mean())
    return np.nanmean(pool) if pool else np.nan

# ===================== 레코드 빌드 =====================
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

    rec_temu  = suggest_price_platform(erp, t_cur, [s_cur, sim], mode, PLATFORM_CFG["TEMU"])
    rec_shein = suggest_price_platform(erp, s_cur, [t_cur, sim], mode, PLATFORM_CFG["SHEIN"])

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

# ===================== 보기: TEMU / SHEIN =====================
platform_view = st.radio("플랫폼", options=["TEMU","SHEIN"], horizontal=True)

# 추천가 하이라이트 스타일
def highlight_price(val):
    if val not in ["-", None, ""] and not pd.isna(val):
        return 'background-color:#d4edda; color:#155724; font-weight:700;'
    return ''

def display_table(df, comment, platform_view):
    if platform_view == "TEMU":
        show = df[["이미지","Style Number","ERP Price","TEMU 현재가","추천가_TEMU","30일판매","이전30일","전체판매","사유"]]
        styled = show.style.applymap(highlight_price, subset=["추천가_TEMU"])
    else:
        show = df[["이미지","Style Number","ERP Price","SHEIN 현재가","추천가_SHEIN","30일판매","이전30일","전체판매","사유"]]
        styled = show.style.applymap(highlight_price, subset=["추천가_SHEIN"])

    st.markdown(f"**{comment}**")
    st.write(styled.to_html(escape=False, index=False), unsafe_allow_html=True)

# ===================== 탭 (선택된 플랫폼만 출력) =====================
tabs = st.tabs(["🆕 판매 없음", "🟠 판매 저조", "📉 판매 급감", "🔥 가격 인상 추천"])

with tabs[0]:
    display_table(df_rec[df_rec["mode"]=="new"],  "판매 기록 없는 신상/미판매 스타일 (동종 평균가 반영해 최소선 제시)", platform_view)
with tabs[1]:
    display_table(df_rec[df_rec["mode"]=="slow"], "판매 1~2건 이하 슬로우셀러 (경쟁가 하회 + 현재가 인상 금지)", platform_view)
with tabs[2]:
    display_table(df_rec[df_rec["mode"]=="drop"], "판매 급감(직전30일대비 50%↓) 스타일 (강한 할인, 인상 금지)", platform_view)
with tabs[3]:
    display_table(df_rec[df_rec["mode"]=="hot"],  "판매 증가 핫아이템 (최소 5% 또는 $0.5 인상, 경쟁가+α)", platform_view)
