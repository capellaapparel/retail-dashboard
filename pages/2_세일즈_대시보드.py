# pages/2_세일즈_대시보드.py
import streamlit as st
import pandas as pd
import re
from dateutil import parser

# =========================
# Page & CSS
# =========================
st.set_page_config(page_title="세일즈 대시보드", layout="wide")
st.title("세일즈 대시보드")

st.markdown("""
<style>
/* 공통 카드 */
.cap-card { border:1px solid #e9e9ef; border-radius:12px; padding:16px; background:#fff; }
.cap-card + .cap-card { margin-top:14px; }

/* KPI 박스(외곽 네모만, 내부는 native metric 사용) */
.kpi-wrap { display:grid; grid-template-columns: repeat(4, minmax(240px, 1fr)); gap:16px; }
.kpi-cell { border:1px solid #f0f0f5; border-radius:12px; padding:14px 16px; background:#fff; }

/* 인사이트 */
.insight-title { font-weight:700; margin-bottom:8px; font-size:1.05rem; }
.insight-list { margin:0; padding-left:18px; }
.insight-list li { margin:4px 0; line-height:1.45; }

/* 섹션 제목 */
.block-title { margin:18px 0 8px 0; font-weight:700; font-size:1.05rem; }

/* Best Seller 테이블 크게 */
.best-card .table-wrap { width:100%; }
.best-card table { width:100% !important; table-layout:fixed; border-collapse:separate; border-spacing:0; }
.best-card th, .best-card td { padding:12px 14px; font-size:0.96rem; }
.best-card th { background:#fafafa; }
.best-card td { vertical-align:middle; }
.best-card table thead th:nth-child(1),
.best-card table tbody td:nth-child(1) { width:120px; }
.best-card table thead th:nth-child(2),
.best-card table tbody td:nth-child(2) { width:auto; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.best-card table thead th:nth-child(n+3),
.best-card table tbody td:nth-child(n+3) { width:120px; text-align:right; }

/* 상품 이미지 확대 */
img.thumb { width:84px; height:auto; border-radius:10px; }
</style>
""", unsafe_allow_html=True)

# =========================
# Helpers
# =========================
@st.cache_data(show_spinner=False)
def load_google_sheet(sheet_name: str) -> pd.DataFrame:
    import gspread
    from oauth2client.service_account import ServiceAccountCredentials
    import json
    GOOGLE_SHEET_URL = "https://docs.google.com/spreadsheets/d/1oyVzCgGK1Q3Qi_sbYwE-wKG6SArnfUDRe7rQfGOF-Eo"
    scope = ["https://spreadsheets.google.com/feeds","https://www.googleapis.com/auth/drive"]
    creds_json = {k: str(v) for k, v in st.secrets["gcp_service_account"].items()}
    with open("/tmp/service_account.json","w") as f: json.dump(creds_json, f)
    creds = ServiceAccountCredentials.from_json_keyfile_name("/tmp/service_account.json", scope)
    client = gspread.authorize(creds)
    ws = client.open_by_url(GOOGLE_SHEET_URL).worksheet(sheet_name)
    df = pd.DataFrame(ws.get_all_records())
    df.columns = [c.lower().strip() for c in df.columns]
    return df

def parse_temudate(x):
    s = str(x)
    if "(" in s: s = s.split("(")[0].strip()
    try: return parser.parse(s, fuzzy=True)
    except Exception: return pd.NaT

def parse_sheindate(x):
    try: return pd.to_datetime(str(x), errors="coerce", infer_datetime_format=True)
    except Exception: return pd.NaT

def clean_money(s: pd.Series) -> pd.Series:
    return (s.astype(str).str.replace(r"[^0-9.\-]", "", regex=True).replace("", pd.NA).astype(float))

def _safe_minmax(*series):
    s = pd.concat([pd.to_datetime(x, errors="coerce") for x in series], ignore_index=True).dropna()
    if s.empty:
        t = pd.Timestamp.today().normalize().date()
        return t, t
    return s.min().date(), s.max().date()

STYLE_RE = re.compile(r"\b([A-Z]{1,3}\d{3,5}[A-Z0-9]?)\b")
def build_img_map(df_info: pd.DataFrame):
    keys = df_info["product number"].astype(str).str.upper().str.replace(" ", "", regex=False)
    return dict(zip(keys, df_info["image"]))

def style_key_from_label(label: str, img_map: dict) -> str | None:
    s = str(label).strip().upper()
    if not s: return None
    s_key = s.replace(" ", "")
    if s_key in img_map: return s_key
    m = STYLE_RE.search(s)
    if m:
        cand = m.group(1).replace(" ", "")
        if cand in img_map: return cand
    for k in img_map.keys():
        if k in s_key: return k
    return None

def img_tag(url): return f"<img src='{url}' class='thumb'>" if str(url).startswith("http") else ""

# =========================
# 1) Load data FIRST
# =========================
df_temu  = load_google_sheet("TEMU_SALES")
df_shein = load_google_sheet("SHEIN_SALES")
df_info  = load_google_sheet("PRODUCT_INFO")
IMG_MAP = build_img_map(df_info)

# Normalize
df_temu["order date"] = df_temu["purchase date"].apply(parse_temudate)
df_shein["order date"] = df_shein["order processed on"].apply(parse_sheindate)

df_temu["order item status"] = df_temu["order item status"].astype(str)
df_temu["quantity shipped"] = pd.to_numeric(df_temu["quantity shipped"], errors="coerce").fillna(0)
df_temu["quantity purchased"] = pd.to_numeric(df_temu.get("quantity purchased", 0), errors="coerce").fillna(0)
df_temu["base price total"] = clean_money(df_temu["base price total"])

df_shein["order status"] = df_shein["order status"].astype(str)
df_shein["product price"] = clean_money(df_shein["product price"])

# =========================
# 2) Controls
# =========================
min_dt, max_dt = _safe_minmax(df_temu["order date"], df_shein["order date"])
today_ts = pd.Timestamp.today().normalize()
today_d  = today_ts.date()

def _clamp_date(d): return max(min_dt, min(d, max_dt))

default_start = _clamp_date((today_ts - pd.Timedelta(days=6)).date())
default_end   = _clamp_date(today_d)

if "sales_date_range" not in st.session_state:
    st.session_state["sales_date_range"] = (default_start, default_end)

c1, c2 = st.columns([1.2, 8.8])
with c1:
    platform = st.radio("플랫폼 선택", ["TEMU", "SHEIN", "BOTH"], horizontal=True)

def _apply_quick_range():
    label = st.session_state.get("quick_range")
    if not label: return
    if label == "최근 1주":
        s = (today_ts - pd.Timedelta(days=6)).date(); e = today_d
    elif label == "최근 1개월":
        s = (today_ts - pd.Timedelta(days=29)).date(); e = today_d
    elif label == "이번 달":
        s = today_ts.replace(day=1).date(); e = today_d
    elif label == "지난 달":
        first_this = today_ts.replace(day=1); last_end = first_this - pd.Timedelta(days=1)
        s = last_end.replace(day=1).date(); e = last_end.date()
    else:
        return
    s = _clamp_date(s); e = _clamp_date(e)
    if e < s: e = s
    st.session_state["sales_date_range"] = (s, e)
    st.session_state["sales_date_input"] = (s, e)

with c2:
    s_val, e_val = st.session_state["sales_date_range"]
    s_val = _clamp_date(s_val); e_val = _clamp_date(e_val)
    if e_val < s_val: e_val = s_val

    dr = st.date_input(
        "조회 기간",
        value=(s_val, e_val),
        min_value=min_dt,
        max_value=max_dt,
        key="sales_date_input"
    )
    if isinstance(dr, (list, tuple)) and len(dr) == 2:
        s, e = dr
    else:
        s = e = dr
    s = pd.to_datetime(s).date(); e = pd.to_datetime(e).date()
    s = _clamp_date(s); e = _clamp_date(e)
    if e < s: e = s
    st.session_state["sales_date_range"] = (s, e)

    try:
        st.segmented_control("", ["최근 1주", "최근 1개월", "이번 달", "지난 달"],
                             key="quick_range", on_change=_apply_quick_range)
    except Exception:
        st.pills("", ["최근 1주", "최근 1개월", "이번 달", "지난 달"],
                 selection_mode="single", key="quick_range", on_change=_apply_quick_range)

# 최종 범위
start = pd.to_datetime(st.session_state["sales_date_range"][0])
end   = pd.to_datetime(st.session_state["sales_date_range"][1]) + pd.Timedelta(hours=23, minutes=59, seconds=59)
period_days = (end - start).days + 1
prev_start  = start - pd.Timedelta(days=period_days)
prev_end    = start - pd.Timedelta(seconds=1)

# =========================
# 3) Aggregations
# =========================
def temu_agg(df, s, e):
    d = df[(df["order date"] >= s) & (df["order date"] <= e)].copy()
    stt = d["order item status"].str.lower()
    sold = d[stt.isin(["shipped", "delivered"])]
    qty_sum   = sold["quantity shipped"].sum()
    sales_sum = sold["base price total"].sum()
    aov       = (sales_sum / qty_sum) if qty_sum > 0 else 0.0
    cancel_qty = d[stt.eq("canceled")]["quantity purchased"].sum()
    return sales_sum, qty_sum, aov, cancel_qty, sold

def shein_agg(df, s, e):
    d = df[(df["order date"] >= s) & (df["order date"] <= e)].copy()
    stt = d["order status"].str.lower()
    sold = d[~stt.isin(["customer refunded"])]
    qty_sum   = len(sold)
    sales_sum = sold["product price"].sum()
    aov       = (sales_sum / qty_sum) if qty_sum > 0 else 0.0
    cancel_qty = stt.eq("customer refunded").sum()
    return sales_sum, qty_sum, aov, cancel_qty, sold

# =========================
# 4) Current vs Prev
# =========================
if platform == "TEMU":
    sales_sum, qty_sum, aov, cancel_qty, df_sold = temu_agg(df_temu, start, end)
    psales, pqty, paov, pcancel, p_sold = temu_agg(df_temu, prev_start, prev_end)
elif platform == "SHEIN":
    sales_sum, qty_sum, aov, cancel_qty, df_sold = shein_agg(df_shein, start, end)
    psales, pqty, paov, pcancel, p_sold = shein_agg(df_shein, prev_start, prev_end)
else:
    s1, q1, a1, c1, d1 = temu_agg(df_temu, start, end)
    s2, q2, a2, c2, d2 = shein_agg(df_shein, start, end)
    sales_sum, qty_sum, cancel_qty = s1 + s2, q1 + q2, c1 + c2
    aov = sales_sum / qty_sum if qty_sum > 0 else 0.0
    df_sold = pd.concat([d1, d2], ignore_index=True)

    ps1, pq1, pa1, pc1, d1p = temu_agg(df_temu, prev_start, prev_end)
    ps2, pq2, pa2, pc2, d2p = shein_agg(df_shein, prev_start, prev_end)
    psales, pqty, pcancel = ps1 + ps2, pq1 + pq2, pc1 + pc2
    paov = psales / pqty if pqty > 0 else 0.0
    p_sold = pd.concat([d1p, d2p], ignore_index=True)

# =========================
# 5) KPI (네이티브 컨테이너로 박스 보장)
# =========================
def _delta_str(now, prev):
    if prev in (0, None) or pd.isna(prev): return "—"
    pct = (now - prev) / prev * 100
    sign = "+" if pct >= 0 else ""
    return f"{sign}{pct:.1f}%"

st.subheader("")  # 상단 여백용(있어도/없어도 됨)
with st.container(border=True):
    cols = st.columns(4, gap="small")
    with cols[0]:
        st.metric("Total Order Amount", f"${sales_sum:,.2f}", _delta_str(sales_sum, psales))
    with cols[1]:
        st.metric("Total Order Quantity", f"{int(qty_sum):,}", _delta_str(qty_sum, pqty))
    with cols[2]:
        st.metric("AOV", f"${aov:,.2f}", _delta_str(aov, paov))
    with cols[3]:
        st.metric("Canceled Order", f"{int(cancel_qty):,}", _delta_str(cancel_qty, pcancel))

# =========================
# =========================
# 6) Insights (풍성하게)
# =========================
def _pc(cur, prev):
    if prev in (0, None) or pd.isna(prev): return None
    return (cur - prev) / prev * 100.0

# Top10 비교
def get_bestseller_labels(platform, df_sold, s, e):
    if platform == "TEMU":
        best = df_sold.groupby("product number")["quantity shipped"].sum().sort_values(ascending=False).head(10)
        return list(best.index.astype(str))
    elif platform == "SHEIN":
        tmp = df_sold.copy(); tmp["qty"] = 1
        best = tmp.groupby("product description")["qty"].sum().sort_values(ascending=False).head(10)
        return list(best.index.astype(str))
    else:
        t = df_temu[(df_temu["order date"]>=s)&(df_temu["order date"]<=e)]
        t = t[t["order item status"].str.lower().isin(["shipped","delivered"])].copy()
        t["style_key"] = t["product number"].astype(str).apply(lambda x: style_key_from_label(x, IMG_MAP))
        t = t.dropna(subset=["style_key"])
        t_cnt = t.groupby("style_key")["quantity shipped"].sum()

        s2 = df_shein[(df_shein["order date"]>=s)&(df_shein["order date"]<=e)]
        s2 = s2[~s2["order status"].str.lower().isin(["customer refunded"])].copy()
        s2["style_key"] = s2["product description"].astype(str).apply(lambda x: style_key_from_label(x, IMG_MAP))
        s2 = s2.dropna(subset=["style_key"])
        s_cnt = s2.groupby("style_key").size()

        mix = (pd.DataFrame({"t":t_cnt, "s":s_cnt}).fillna(0))
        mix["tot"] = mix["t"] + mix["s"]
        return list(mix["tot"].sort_values(ascending=False).head(10).index.astype(str))

cur_top = get_bestseller_labels(platform, df_sold, start, end)
prev_top = get_bestseller_labels(platform, p_sold, prev_start, prev_end) if 'p_sold' in locals() else []
entered = [x for x in cur_top if x not in prev_top]
dropped = [x for x in prev_top if x not in cur_top]

bullets = []
for label, now, prev in [
    ("매출액", sales_sum, psales),
    ("판매수량", qty_sum, pqty),
    ("AOV", aov, paov),
    ("취소건", cancel_qty, pcancel),
]:
    v = _pc(now, prev)
    if v is not None:
        dir_ = "증가" if v >= 0 else "감소"
        bullets.append(f"• {label} **{dir_} {abs(v):.1f}%**")

if entered:
    bullets.append(f"• Top10 **신규 진입**: {', '.join(entered)} → 재고 확보/광고 확대 권장")
if dropped:
    bullets.append(f"• Top10 **이탈**: {', '.join(dropped)} → 인벤토리/가격/노출 점검")

bullets.append("• 체크리스트: 쿠폰/프로모션, 상위 상품 재고(핵심 사이즈), 경쟁가/리뷰, 이미지/타이틀")

with st.container(border=True):
    st.markdown("**자동 인사이트 & 액션 제안**")
    st.markdown("\n".join([f"- {b}" for b in bullets]))

# =========================
# 7) Daily Chart
# =========================
def build_daily(platform: str, s: pd.Timestamp, e: pd.Timestamp) -> pd.DataFrame:
    if platform == "TEMU":
        t = df_temu[(df_temu["order date"]>=s)&(df_temu["order date"]<=e)]
        t = t[t["order item status"].str.lower().isin(["shipped","delivered"])]
        daily = t.groupby(pd.Grouper(key="order date", freq="D")).agg(
            qty=("quantity shipped","sum"), Total_Sales=("base price total","sum")
        )
    elif platform == "SHEIN":
        s2 = df_shein[(df_shein["order date"]>=s)&(df_shein["order date"]<=e)]
        s2 = s2[~s2["order status"].str.lower().isin(["customer refunded"])]
        s2["qty"] = 1
        daily = s2.groupby(pd.Grouper(key="order date", freq="D")).agg(
            qty=("qty","sum"), Total_Sales=("product price","sum")
        )
    else:
        t = df_temu[(df_temu["order date"]>=s)&(df_temu["order date"]<=e)]
        t = t[t["order item status"].str.lower().isin(["shipped","delivered"])].copy()
        s2 = df_shein[(df_shein["order date"]>=s)&(df_shein["order date"]<=e)]
        s2 = s2[~s2["order status"].str.lower().isin(["customer refunded"])].copy()
        s2["qty"] = 1
        t_daily = t.groupby(pd.Grouper(key="order date", freq="D")).agg(
            t_qty=("quantity shipped","sum"), t_sales=("base price total","sum")
        )
        s_daily = s2.groupby(pd.Grouper(key="order date", freq="D")).agg(
            s_qty=("qty","sum"), s_sales=("product price","sum")
        )
        daily = pd.concat([t_daily, s_daily], axis=1).fillna(0.0)
        daily["qty"] = daily["t_qty"] + daily["s_qty"]
        daily["Total_Sales"] = daily["t_sales"] + daily["s_sales"]
        daily = daily[["qty","Total_Sales"]]
    return daily.reset_index().set_index("order date").fillna(0.0)

st.markdown("<div class='block-title'>일별 판매 추이</div>", unsafe_allow_html=True)
_daily = build_daily(platform, start, end)
box = st.empty()
if _daily.empty:
    box.info("해당 기간에 데이터가 없습니다.")
else:
    _ = box.line_chart(_daily[["Total_Sales","qty"]])

# =========================
# 8) Best Seller 10
# =========================
st.subheader("Best Seller 10")

def best_table(platform, df_sold, s, e):
    if platform == "TEMU":
        g = (df_sold.assign(style_key=lambda d: d["product number"].astype(str)
                             .apply(lambda x: style_key_from_label(x, IMG_MAP)))
             .dropna(subset=["style_key"])
             .groupby("style_key")["quantity shipped"].sum().astype(int).reset_index())
        g = g.rename(columns={"style_key":"Style Number","quantity shipped":"Sold Qty"})
        g["Image"] = g["Style Number"].apply(lambda x: img_tag(IMG_MAP.get(x, "")))
        return g[["Image","Style Number","Sold Qty"]].sort_values("Sold Qty", ascending=False).head(10)

    if platform == "SHEIN":
        tmp = df_sold.copy(); tmp["qty"] = 1
        g = (tmp.assign(style_key=lambda d: d["product description"].astype(str)
                        .apply(lambda x: style_key_from_label(x, IMG_MAP)))
             .dropna(subset=["style_key"])
             .groupby("style_key")["qty"].sum().astype(int).reset_index())
        g = g.rename(columns={"style_key":"Style Number","qty":"Sold Qty"})
        g["Image"] = g["Style Number"].apply(lambda x: img_tag(IMG_MAP.get(x, "")))
        return g[["Image","Style Number","Sold Qty"]].sort_values("Sold Qty", ascending=False).head(10)

    # BOTH
    t = df_temu[(df_temu["order date"]>=s)&(df_temu["order date"]<=e)&
                (df_temu["order item status"].str.lower().isin(["shipped","delivered"]))].copy()
    t["style_key"] = t["product number"].astype(str).apply(lambda x: style_key_from_label(x, IMG_MAP))
    t = t.dropna(subset=["style_key"])
    t_group = t.groupby("style_key")["quantity shipped"].sum().astype(int)

    s2 = df_shein[(df_shein["order date"]>=s)&(df_shein["order date"]<=e)&
                  (~df_shein["order status"].str.lower().isin(["customer refunded"]))].copy()
    s2["style_key"] = s2["product description"].astype(str).apply(lambda x: style_key_from_label(x, IMG_MAP))
    s2 = s2.dropna(subset=["style_key"])
    s_group = s2.groupby("style_key").size().astype(int)

    mix = pd.DataFrame({"TEMU Qty": t_group, "SHEIN Qty": s_group}).fillna(0).astype(int)
    mix["Sold Qty"] = (mix["TEMU Qty"] + mix["SHEIN Qty"]).astype(int)
    mix = mix.sort_values("Sold Qty", ascending=False).head(10).reset_index()
    if "index" in mix.columns: mix = mix.rename(columns={"index":"Style Number"})
    elif "style_key" in mix.columns: mix = mix.rename(columns={"style_key":"Style Number"})
    elif "Style Number" not in mix.columns: mix["Style Number"] = mix.index.astype(str)
    mix["Image"] = mix["Style Number"].apply(lambda x: img_tag(IMG_MAP.get(x, "")))
    return mix[["Image","Style Number","Sold Qty","TEMU Qty","SHEIN Qty"]]

best_df = best_table(platform, df_sold, start, end)

# ✅ 불필요한 HTML 래퍼 제거 → 빈 네모 사라짐
with st.container(border=True):
    st.markdown(best_df.to_html(escape=False, index=False), unsafe_allow_html=True)
