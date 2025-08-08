# pages/2_세일즈_대시보드.py
import streamlit as st
import pandas as pd
from dateutil import parser

# ---------- UI ----------
st.set_page_config(page_title="세일즈 대시보드", layout="wide")
st.title("세일즈 대시보드")

# ---------- Helpers ----------
@st.cache_data(show_spinner=False)
def load_google_sheet(sheet_name: str) -> pd.DataFrame:
    import gspread
    from oauth2client.service_account import ServiceAccountCredentials
    import json

    GOOGLE_SHEET_URL = "https://docs.google.com/spreadsheets/d/1oyVzCgGK1Q3Qi_sbYwE-wKG6SArnfUDRe7rQfGOF-Eo"
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive",
    ]
    creds_json = {k: str(v) for k, v in st.secrets["gcp_service_account"].items()}
    with open("/tmp/service_account.json", "w") as f:
        json.dump(creds_json, f)
    creds = ServiceAccountCredentials.from_json_keyfile_name("/tmp/service_account.json", scope)
    client = gspread.authorize(creds)
    ws = client.open_by_url(GOOGLE_SHEET_URL).worksheet(sheet_name)
    data = ws.get_all_records()
    df = pd.DataFrame(data)
    df.columns = [c.lower().strip() for c in df.columns]
    return df

def parse_temudate(x):
    # 예: "Aug 3, 2025, 7:15 pm PDT(UTC-7)" → 괄호 앞까지만 파싱
    s = str(x)
    if "(" in s:
        s = s.split("(")[0].strip()
    try:
        return parser.parse(s, fuzzy=True)
    except Exception:
        return pd.NaT

def parse_sheindate(x):
    try:
        return pd.to_datetime(str(x), errors="coerce", infer_datetime_format=True)
    except Exception:
        return pd.NaT

def clean_money(series: pd.Series) -> pd.Series:
    # "$12.34", "12,345.67" → float
    return (
        series.astype(str)
        .str.replace(r"[^0-9.\-]", "", regex=True)
        .replace("", pd.NA)
        .astype(float)
    )

def kpi_delta(now, prev):
    if prev == 0 or pd.isna(prev):
        return ""
    pct = (now - prev) / prev * 100
    arrow = "▲" if pct >= 0 else "▼"
    color = "#11b500" if pct >= 0 else "red"
    return f"<span style='color:{color}'>{arrow} {abs(pct):.1f}%</span>"

def _safe_minmax(*series):
    s = pd.concat([pd.to_datetime(x, errors="coerce") for x in series], ignore_index=True)
    s = s.dropna()
    if s.empty:
        today_ts = pd.Timestamp.today().normalize()
        return today_ts.date(), today_ts.date()
    return s.min().date(), s.max().date()

# ---------- Load data ----------
df_temu  = load_google_sheet("TEMU_SALES")
df_shein = load_google_sheet("SHEIN_SALES")
df_info  = load_google_sheet("PRODUCT_INFO")

# Normalize dates
df_temu["order date"] = df_temu["purchase date"].apply(parse_temudate)
df_shein["order date"] = df_shein["order processed on"].apply(parse_sheindate)

# Money/qty columns for Temu
df_temu["order item status"] = df_temu["order item status"].astype(str)
df_temu["quantity shipped"] = pd.to_numeric(df_temu["quantity shipped"], errors="coerce").fillna(0)
df_temu["quantity purchased"] = pd.to_numeric(df_temu.get("quantity purchased", 0), errors="coerce").fillna(0)
df_temu["base price total"] = clean_money(df_temu["base price total"])

# Money for Shein
df_shein["order status"] = df_shein["order status"].astype(str)
df_shein["product price"] = clean_money(df_shein["product price"])

# Image map
info_img = dict(zip(df_info["product number"].astype(str), df_info["image"]))

# ---------- Date widget ----------
min_dt, max_dt = _safe_minmax(df_temu["order date"], df_shein["order date"])
today_ts = pd.Timestamp.today().normalize()
today_d  = today_ts.date()
default_start = max(min_dt, (today_ts - pd.Timedelta(days=6)).date())
default_end   = min(max_dt, today_d)

if "sales_date_range" not in st.session_state:
    st.session_state["sales_date_range"] = (default_start, default_end)

col_left, col_right = st.columns([1.2, 8.8])
with col_left:
    platform = st.radio("플랫폼 선택", ["TEMU", "SHEIN", "BOTH"], horizontal=True)

with col_right:
    v_start, v_end = st.session_state["sales_date_range"]
    v_start = max(min_dt, min(v_start, max_dt))
    v_end   = max(v_start, min(v_end, max_dt))

    dr = st.date_input(
        "조회 기간",
        value=(v_start, v_end),
        min_value=min_dt,
        max_value=max_dt,
        key="sales_date_input"
    )
    if isinstance(dr, (list, tuple)) and len(dr) == 2:
        start_date, end_date = dr
    else:
        start_date = end_date = dr

    start_date = max(min_dt, min(start_date, max_dt))
    end_date   = max(start_date, min(end_date, max_dt))
    st.session_state["sales_date_range"] = (start_date, end_date)

# time range (종료일 23:59:59 포함)
start = pd.to_datetime(st.session_state["sales_date_range"][0])
end   = pd.to_datetime(st.session_state["sales_date_range"][1]) + pd.Timedelta(hours=23, minutes=59, seconds=59)
period_days = (end - start).days + 1
prev_start  = start - pd.Timedelta(days=period_days)
prev_end    = start - pd.Timedelta(seconds=1)

# ---------- Aggregations ----------
def temu_agg(df, s, e):
    mask = (df["order date"] >= s) & (df["order date"] <= e)
    d = df[mask].copy()
    status = d["order item status"].astype(str).str.lower()
    sold = d[status.isin(["shipped", "delivered"])]

    qty_sum   = sold["quantity shipped"].sum()
    sales_sum = sold["base price total"].sum()
    aov       = (sales_sum / qty_sum) if qty_sum > 0 else 0.0

    cancel_qty = d[status.eq("canceled")]["quantity purchased"].sum()
    return sales_sum, qty_sum, aov, cancel_qty, sold

def shein_agg(df, s, e):
    mask = (df["order date"] >= s) & (df["order date"] <= e)
    d = df[mask].copy()
    status = d["order status"].astype(str).str.lower()

    sold = d[~status.isin(["customer refunded"])]

    qty_sum   = len(sold)  # 한 행 = 1
    sales_sum = sold["product price"].sum()
    aov       = (sales_sum / qty_sum) if qty_sum > 0 else 0.0
    cancel_qty = status.eq("customer refunded").sum()
    return sales_sum, qty_sum, aov, cancel_qty, sold

def get_bestseller_list(platform, df_sold, start, end):
    if platform == "TEMU":
        best = (
            df_sold.groupby("product number")["quantity shipped"].sum()
            .sort_values(ascending=False).head(10)
        )
        labels = best.index.astype(str)
    elif platform == "SHEIN":
        tmp = df_sold.copy()
        tmp["qty"] = 1
        best = (
            tmp.groupby("product description")["qty"].sum()
            .sort_values(ascending=False).head(10)
        )
        labels = best.index.astype(str)
    else:
        # BOTH
        t = df_temu[(df_temu["order date"] >= start) & (df_temu["order date"] <= end)]
        t = t[t["order item status"].astype(str).str.lower().isin(["shipped", "delivered"])]
        t_cnt = t.groupby("product number")["quantity shipped"].sum()

        s = df_shein[(df_shein["order date"] >= start) & (df_shein["order date"] <= end)]
        s = s[~s["order status"].astype(str).str.lower().isin(["customer refunded"])]
        s_cnt = s.groupby("product description").size()

        mix = pd.DataFrame({"TEMU Qty": t_cnt, "SHEIN Qty": s_cnt}).fillna(0)
        mix["Sold Qty"] = mix["TEMU Qty"] + mix["SHEIN Qty"]
        best = mix["Sold Qty"].sort_values(ascending=False).head(10)
        labels = best.index.astype(str)
    return list(labels), best

# ---------- Current & Previous ----------
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

# ---------- KPI ----------
k1, k2, k3, k4 = st.columns(4)
k1.metric("Total Order Amount", f"${sales_sum:,.2f}", delta=None)
k1.markdown(kpi_delta(sales_sum, psales), unsafe_allow_html=True)

k2.metric("Total Order Quantity", f"{int(qty_sum):,}", delta=None)
k2.markdown(kpi_delta(qty_sum, pqty), unsafe_allow_html=True)

k3.metric("AOV", f"${aov:,.2f}", delta=None)
k3.markdown(kpi_delta(aov, paov), unsafe_allow_html=True)

k4.metric("Canceled Order", f"{int(cancel_qty):,}", delta=None)
k4.markdown(kpi_delta(cancel_qty, pcancel), unsafe_allow_html=True)

# ---------- Auto Insights (원인 + 액션) ----------
def pct_change(cur, prev):
    if prev in (0, None) or pd.isna(prev):
        return None
    return (cur - prev) / prev * 100.0

def gen_insights():
    insights = []

    # 변화율 계산
    sales_chg = pct_change(sales_sum, psales)
    qty_chg   = pct_change(qty_sum, pqty)
    aov_chg   = pct_change(aov, paov)
    canc_chg  = pct_change(cancel_qty, pcancel)

    # 1) 성과 변화 요약
    if sales_chg is not None and abs(sales_chg) >= 20:
        direction = "감소" if sales_chg < 0 else "증가"
        insights.append(("⚠️", f"매출이 지난 기간 대비 **{direction} {abs(sales_chg):.1f}%**입니다."))
    if qty_chg is not None and abs(qty_chg) >= 20:
        direction = "감소" if qty_chg < 0 else "증가"
        insights.append(("ℹ️", f"판매수량이 **{direction} {abs(qty_chg):.1f}%** 변화했습니다."))
    if aov_chg is not None and abs(aov_chg) >= 5:
        direction = "하락" if aov_chg < 0 else "상승"
        insights.append(("ℹ️", f"AOV가 {direction} **{abs(aov_chg):.1f}%** 변했습니다."))

    # 2) 가격/프로모션 시그널
    if qty_chg is not None and qty_chg <= -25 and (aov_chg is None or abs(aov_chg) <= 6):
        insights.append(("💡", "판매수량 급감 & AOV 변동이 작아 **노출/프로모션 종료/가격 경쟁력 약화** 가능성이 높습니다."))
        insights.append(("👉", "현재 **쿠폰/프로모션이 동작 중인지 확인**하고, 상위 상품에 **타겟 쿠폰(예: 5~10%)** 테스트를 권장합니다."))

    # 3) 베스트셀러 변화 추적
    cur_top_labels, cur_best = get_bestseller_list(platform, df_sold, start, end)
    prev_top_labels, prev_best = get_bestseller_list(platform, p_sold, prev_start, prev_end)

    entered = [x for x in cur_top_labels if x not in prev_top_labels]
    dropped = [x for x in prev_top_labels if x not in cur_top_labels]

    if entered:
        insights.append(("✅", f"Top10 **신규 진입**: {', '.join(entered)} → **재고 확보/광고 확대** 권장."))
    if dropped:
        insights.append(("⚠️", f"Top10 **이탈**: {', '.join(dropped)} → **인벤토리/가격/노출** 점검 필요."))

    # 4) 취소 증가
    if canc_chg is not None and canc_chg >= 50 and cancel_qty >= 3:
        insights.append(("🚨", "취소가 크게 증가했습니다. 품질/배송/옵션 오류 여부를 확인하세요."))

    # 5) 판매 공백(일별 0 매출) 탐지
    # 하루라도 전량 0인 날이 있으면 운영/노출 이슈 신호
    def zero_day_ratio(df_day):
        if df_day.empty:
            return 0.0
        return (df_day["Total_Sales"] <= 0).mean()

    # 일별 집계 (현재 기간)
    cur_daily = get_daily(platform, start, end)
    if zero_day_ratio(cur_daily) >= 0.2:
        insights.append(("🛠", "최근 기간에 **0 매출 일자 빈도↑**. 노출/캠페인 상태 점검을 권장합니다."))

    # 6) 기본 액션 템플릿
    insights.append(("🧭", "빠른 체크리스트: **쿠폰/프로모션 상태**, **상위 상품 재고(핵심 사이즈)**, **경쟁가/리뷰**, **상품 이미지/타이틀 개선**."))

    return insights, (entered, dropped)

def get_daily(platform, s, e):
    if platform == "TEMU":
        t = df_temu[(df_temu["order date"] >= s) & (df_temu["order date"] <= e)]
        t = t[t["order item status"].astype(str).str.lower().isin(["shipped", "delivered"])]
        daily = (
            t.groupby(pd.Grouper(key="order date", freq="D"))
            .agg(qty=("quantity shipped", "sum"), Total_Sales=("base price total", "sum"))
            .reset_index().set_index("order date")
        )
    elif platform == "SHEIN":
        s2 = df_shein[(df_shein["order date"] >= s) & (df_shein["order date"] <= e)].copy()
        s2 = s2[~s2["order status"].astype(str).str.lower().isin(["customer refunded"])]
        s2["qty"] = 1
        daily = (
            s2.groupby(pd.Grouper(key="order date", freq="D"))
            .agg(qty=("qty", "sum"), Total_Sales=("product price", "sum"))
            .reset_index().set_index("order date")
        )
    else:
        t = df_temu[(df_temu["order date"] >= s) & (df_temu["order date"] <= e)]
        t = t[t["order item status"].astype(str).str.lower().isin(["shipped", "delivered"])].copy()
        s2 = df_shein[(df_shein["order date"] >= s) & (df_shein["order date"] <= e)]
        s2 = s2[~s2["order status"].astype(str).str.lower().isin(["customer refunded"])].copy()
        s2["qty"] = 1

        t_daily = t.groupby(pd.Grouper(key="order date", freq="D")).agg(
            t_qty=("quantity shipped", "sum"),
            t_sales=("base price total", "sum"),
        )
        s_daily = s2.groupby(pd.Grouper(key="order date", freq="D")).agg(
            s_qty=("qty", "sum"),
            s_sales=("product price", "sum"),
        )
        daily = pd.concat([t_daily, s_daily], axis=1).fillna(0.0)
        daily["qty"] = daily["t_qty"] + daily["s_qty"]
        daily["Total_Sales"] = daily["t_sales"] + daily["s_sales"]
        daily = daily[["qty", "Total_Sales"]]
    return daily.fillna(0.0)

insights, (entered, dropped) = gen_insights()

# ---------- Insights Panel ----------
with st.container():
    st.subheader("🔎 자동 인사이트 & 액션 제안")
    if insights:
        for icon, msg in insights:
            st.markdown(f"{icon} {msg}")
    else:
        st.markdown("✅ 특이 사항 없음. 정상 범위입니다.")

# ---------- Daily chart ----------
st.subheader("일별 판매 추이")
daily = get_daily(platform, start, end)
if daily.empty:
    st.info("해당 기간에 데이터가 없습니다.")
else:
    st.line_chart(daily[["Total_Sales", "qty"]])

# ---------- Best sellers ----------
st.subheader("Best Seller 10")

def img_tag(url):
    u = str(url)
    return f"<img src='{u}' style='width:60px;height:auto;border-radius:10px'>" if u.startswith("http") else ""

if platform == "TEMU":
    best = (
        df_sold.groupby("product number")["quantity shipped"].sum().reset_index()
        .sort_values("quantity shipped", ascending=False).head(10)
    )
    best["Image"] = best["product number"].astype(str).map(info_img).apply(img_tag)
    show = best[["Image", "product number", "quantity shipped"]]
    show.columns = ["Image", "Style Number", "Sold Qty"]
    st.markdown(show.to_html(escape=False, index=False), unsafe_allow_html=True)

elif platform == "SHEIN":
    tmp = df_sold.copy()
    best = tmp.groupby("product description").size().reset_index(name="qty").sort_values("qty", ascending=False).head(10)
    best["Image"] = best["product description"].astype(str).map(info_img).apply(img_tag)
    show = best[["Image", "product description", "qty"]]
    show.columns = ["Image", "Style Number", "Sold Qty"]
    st.markdown(show.to_html(escape=False, index=False), unsafe_allow_html=True)

else:
    t = df_temu[(df_temu["order date"] >= start) & (df_temu["order date"] <= end)]
    t = t[t["order item status"].astype(str).str.lower().isin(["shipped", "delivered"])]
    t_cnt = t.groupby("product number")["quantity shipped"].sum()
    s = df_shein[(df_shein["order date"] >= start) & (df_shein["order date"] <= end)]
    s = s[~s["order status"].astype(str).str.lower().isin(["customer refunded"])]
    s_cnt = s.groupby("product description").size()

    summary = pd.DataFrame({"TEMU Qty": t_cnt, "SHEIN Qty": s_cnt}).fillna(0.0)
    summary["Sold Qty"] = summary["TEMU Qty"] + summary["SHEIN Qty"]
    summary = summary.sort_values("Sold Qty", ascending=False).head(10)
    summary["Image"] = summary.index.astype(str).map(info_img).apply(img_tag)
    summary = summary.reset_index().rename(columns={"index": "Style Number"})
    show = summary[["Image", "Style Number", "Sold Qty", "TEMU Qty", "SHEIN Qty"]]
    st.markdown(show.to_html(escape=False, index=False), unsafe_allow_html=True)
