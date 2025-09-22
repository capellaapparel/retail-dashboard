# pages/2_세일즈_대시보드.py
import streamlit as st
import pandas as pd
import re
from dateutil import parser
import altair as alt

# =========================
# Page
# =========================
st.set_page_config(page_title="세일즈 대시보드", layout="wide")
st.title("세일즈 대시보드")

# =========================
# CSS
# =========================
st.markdown("""
<style>
.cap-card { border:1px solid #e9e9ef; border-radius:12px; padding:16px; background:#fff; }
.cap-card + .cap-card { margin-top:14px; }
.kpi-wrap { display:grid; grid-template-columns: repeat(4, minmax(240px, 1fr)); gap:16px; }
.kpi-cell { border:1px solid #f0f0f5; border-radius:12px; padding:14px 16px; background:#fff; }
.insight-title { font-weight:700; margin-bottom:8px; font-size:1.05rem; }
.insight-list { margin:0; padding-left:18px; }
.insight-list li { margin:4px 0; line-height:1.45; }
.block-title { margin:18px 0 8px 0; font-weight:700; font-size:1.05rem; }
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
img.thumb { width:84px; height:auto; border-radius:12px; }
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

def clean_money(x) -> pd.Series:
    s = x if isinstance(x, pd.Series) else pd.Series(x)
    s = s.astype(str).str.replace(r"[^0-9.\-]", "", regex=True).replace("", pd.NA)
    s = pd.to_numeric(s, errors="coerce")
    return s

def ensure_series(df: pd.DataFrame, col: str, default: float = 0.0) -> pd.Series:
    if col in df.columns:
        return df[col]
    return pd.Series([default] * len(df), index=df.index, dtype=float)

def _safe_minmax(*series):
    s = pd.concat([pd.to_datetime(x, errors="coerce") for x in series], ignore_index=True).dropna()
    if s.empty:
        t = pd.Timestamp.today().normalize().date()
        return t, t
    return s.min().date(), s.max().date()

STYLE_RE = re.compile(r"\b([A-Z]{1,3}\d{3,5}[A-Z0-9]?)\b")

def build_img_map(df_info: pd.DataFrame):
    keys = df_info["product number"].astype(str).str.upper().str.replace(" ", "", regex=False)
    return dict(zip(keys, df_info.get("image", pd.Series(index=df_info.index)).fillna("")))

def style_key_from_label(label: str, img_map: dict) -> str | None:
    s = str(label).strip().upper()
    if not s:
        return None
    s_key = s.replace(" ", "")
    if s_key in img_map:
        return s_key
    m = STYLE_RE.search(s)
    if m:
        cand = m.group(1).replace(" ", "")
        if cand in img_map:
            return cand
    for k in img_map.keys():
        if k in s_key:
            return k
    return None

def img_tag(url):
    return f"<img src='{url}' class='thumb'>" if str(url).startswith("http") else ""

# robust status helpers
def temu_sold_mask(s: pd.Series) -> pd.Series:
    return s.astype(str).str.lower().str.contains("shipped|delivered", regex=True, na=False)

def temu_cancel_mask(s: pd.Series) -> pd.Series:
    return s.astype(str).str.lower().str.contains("cancel", regex=True, na=False)

def shein_refund_mask(s: pd.Series) -> pd.Series:
    return s.astype(str).str.lower().str.contains("customer refunded", na=False)

# SHEIN 프로모션 여부
def shein_promo_mask(df: pd.DataFrame) -> pd.Series:
    c1 = ensure_series(df, "coupon discount", default=0.0)
    c2 = ensure_series(df, "store campaign discount", default=0.0)
    c1v = clean_money(c1).fillna(0)
    c2v = clean_money(c2).fillna(0)
    return (c1v != 0) | (c2v != 0)

def _normalize_style_input(s: str | None) -> str | None:
    if not s: return None
    return str(s).upper().replace(" ", "")

# Style-key helpers (TEMU는 PN에서, SHEIN은 Seller SKU 우선)
def _style_key_series_temu(df: pd.DataFrame) -> pd.Series:
    return df["product number"].astype(str).apply(lambda x: style_key_from_label(x, IMG_MAP))

def _style_key_series_shein_fallback(df: pd.DataFrame) -> pd.Series:
    # fallback: description에서 추정
    return df["product description"].astype(str).apply(lambda x: style_key_from_label(x, IMG_MAP))

def _short_title_mask(series: pd.Series, thresh:int=25) -> pd.Series:
    return series.astype(str).str.len().fillna(0) < thresh

# =========================
# 1) Load data
# =========================
df_temu  = load_google_sheet("TEMU_SALES")
df_shein = load_google_sheet("SHEIN_SALES")
df_info  = load_google_sheet("PRODUCT_INFO")
IMG_MAP = build_img_map(df_info)

# Normalize
df_temu["order date"] = df_temu["purchase date"].apply(parse_temudate)
df_shein["order date"] = df_shein["order processed on"].apply(parse_sheindate)

df_temu["order item status"] = df_temu["order item status"].astype(str)
df_temu["quantity shipped"] = pd.to_numeric(ensure_series(df_temu, "quantity shipped", 0.0), errors="coerce").fillna(0)
df_temu["quantity purchased"] = pd.to_numeric(ensure_series(df_temu, "quantity purchased", 0.0), errors="coerce").fillna(0)
df_temu["base price total"] = clean_money(ensure_series(df_temu, "base price total", 0.0)).fillna(0.0)

df_shein["order status"] = df_shein["order status"].astype(str)
df_shein["product price"] = clean_money(ensure_series(df_shein, "product price", 0.0)).fillna(0.0)

# =========================
# 1.5) SHEIN Seller SKU 파싱: "STYLE-COLOR-SIZE"
# =========================
if "seller sku" in df_shein.columns:
    parts = df_shein["seller sku"].astype(str).str.split("-", n=2, expand=True)
    df_shein["style_key"] = parts[0].str.upper().str.strip()
    df_shein["color"] = parts[1].str.strip() if parts.shape[1] > 1 else ""
    df_shein["size"]  = parts[2].str.strip() if parts.shape[1] > 2 else ""
else:
    # 컬럼이 없으면 fallback
    df_shein["style_key"] = _style_key_series_shein_fallback(df_shein)
    df_shein["color"] = ""
    df_shein["size"]  = ""

# TEMU 쪽도 color/size가 있으면 사용, 없으면 빈 값
if "color" not in df_temu.columns:
    df_temu["color"] = ""
if "size" not in df_temu.columns:
    df_temu["size"] = ""

# =========================
# 2) Date Controls
# =========================
min_dt, max_dt = _safe_minmax(df_temu["order date"], df_shein["order date"])
today_ts = pd.Timestamp.today().normalize()

def _clamp_date(d) -> pd.Timestamp.date:
    d_date = pd.to_datetime(d).date()
    mn = pd.to_datetime(min_dt).date()
    mx = pd.to_datetime(max_dt).date()
    if d_date < mn: d_date = mn
    if d_date > mx: d_date = mx
    return d_date

default_start = _clamp_date(today_ts - pd.Timedelta(days=6))
default_end   = _clamp_date(today_ts)

if "sales_date_input" not in st.session_state:
    st.session_state["sales_date_input"] = (default_start, default_end)

c1, c2 = st.columns([1.2, 8.8])
with c1:
    # ✅ 기본값을 SHEIN으로 (첫번째 옵션이 기본)
    platform = st.radio("플랫폼 선택", ["SHEIN", "TEMU", "BOTH"], horizontal=True)

def _apply_quick_range():
    label = st.session_state.get("quick_range")
    if not label: return
    if label == "최근 1주":
        s = today_ts - pd.Timedelta(days=6); e = today_ts
    elif label == "최근 1개월":
        s = today_ts - pd.Timedelta(days=29); e = today_ts
    elif label == "이번 달":
        s = today_ts.replace(day=1); e = today_ts
    elif label == "지난 달":
        first_this = today_ts.replace(day=1)
        last_end   = first_this - pd.Timedelta(days=1)
        s = last_end.replace(day=1); e = last_end
    else:
        return
    s = _clamp_date(s); e = _clamp_date(e)
    if e < s: e = s
    st.session_state["sales_date_input"] = (s, e)

with c2:
    st.date_input(
        "조회 기간",
        value=st.session_state["sales_date_input"],
        key="sales_date_input",
        min_value=min_dt,
        max_value=max_dt,
    )
    try:
        st.segmented_control("", ["최근 1주", "최근 1개월", "이번 달", "지난 달"],
                             key="quick_range", on_change=_apply_quick_range)
    except Exception:
        st.pills("", ["최근 1주", "최근 1개월", "이번 달", "지난 달"],
                 selection_mode="single", key="quick_range", on_change=_apply_quick_range)

s_date, e_date = st.session_state["sales_date_input"]
s_date = pd.to_datetime(s_date).date()
e_date = pd.to_datetime(e_date).date()
s_date = max(s_date, min_dt); e_date = min(e_date, max_dt)
if e_date < s_date: e_date = s_date
start = pd.to_datetime(s_date)
end   = pd.to_datetime(e_date) + pd.Timedelta(hours=23, minutes=59, seconds=59)

period_days = (end - start).days + 1
prev_start  = start - pd.Timedelta(days=period_days)
prev_end    = start - pd.Timedelta(seconds=1)

# =========================
# 3) Aggregations
# =========================
def temu_agg(df, s, e):
    d = df[(df["order date"] >= s) & (df["order date"] <= e)].copy()
    stt = d["order item status"]
    sold = d[temu_sold_mask(stt)]
    qty_sum   = sold["quantity shipped"].sum()
    sales_sum = sold["base price total"].sum()
    aov       = (sales_sum / qty_sum) if qty_sum > 0 else 0.0
    cancel_qty = d[temu_cancel_mask(stt)]["quantity purchased"].sum()
    return sales_sum, qty_sum, aov, cancel_qty, sold

def shein_agg(df, s, e):
    d = df[(df["order date"] >= s) & (df["order date"] <= e)].copy()
    stt = d["order status"]
    sold = d[~shein_refund_mask(stt)]
    qty_sum   = len(sold)
    sales_sum = sold["product price"].sum()
    aov       = (sales_sum / qty_sum) if qty_sum > 0 else 0.0
    cancel_qty = shein_refund_mask(stt).sum()
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
# ⭐ Style Search (스타일번호 검색) + 색상/사이즈 상세
# =========================
def _donut_chart(labels, values, title: str):
    if len(values) == 0 or pd.Series(values).fillna(0).sum() == 0:
        st.caption("차트 표시할 데이터가 없습니다")
        return
    data = pd.DataFrame({"label": pd.Series(labels, dtype="string"),
                         "value": pd.to_numeric(values, errors="coerce").fillna(0)})
    chart = (
        alt.Chart(data)
        .mark_arc(innerRadius=60)
        .encode(
            theta=alt.Theta("value:Q", stack=True),
            color=alt.Color("label:N", legend=alt.Legend(title="")),
            tooltip=[alt.Tooltip("label:N", title="항목"),
                     alt.Tooltip("value:Q", title="수량", format=",")]
        )
        .properties(width=320, height=260, title=title)
    )
    st.altair_chart(chart, use_container_width=False)

with st.container(border=True):
    st.markdown("### 스타일번호 검색 (기간/플랫폼 적용)")
    cols = st.columns([2.2, 1, 1.2, 1.2])
    with cols[0]:
        _raw_input = st.text_input("Style Number 입력 (예: BT5603)", key="style_search")
        style_search = _raw_input.strip() if _raw_input else ""
    with cols[1]:
        do_search = st.button("검색")

    if style_search and not do_search:
        do_search = True

    if do_search:
        skey = _normalize_style_input(style_search)
        if not skey:
            st.warning("유효한 스타일번호를 입력하세요.")
        else:
            res_tables = []
            total_sales = 0.0
            total_qty   = 0
            temu_df_filtered = pd.DataFrame()
            shein_df_filtered = pd.DataFrame()

            # TEMU
            if platform in ("TEMU", "BOTH"):
                t = df_temu[(df_temu["order date"]>=start)&(df_temu["order date"]<=end)].copy()
                t = t[temu_sold_mask(t["order item status"])].copy()
                t["style_key"] = _style_key_series_temu(t)
                t = t[t["style_key"] == skey]
                temu_df_filtered = t.copy()
                if not t.empty:
                    qty = t["quantity shipped"].sum()
                    sales = t["base price total"].sum()
                    total_qty += int(qty)
                    total_sales += float(sales)
                    t_daily = (
                        t.groupby(pd.Grouper(key="order date", freq="D"))
                         .agg(qty=("quantity shipped","sum"), sales=("base price total","sum"))
                         .reset_index()
                    )
                    t_table = t[["order date","product number","color","size","quantity shipped","base price total"]].rename(
                        columns={"product number":"Product", "quantity shipped":"Qty", "base price total":"Sales"}
                    )
                    res_tables.append(("TEMU", t_daily, t_table))

            # SHEIN (Seller SKU 기반 style_key/color/size 사용)
            if platform in ("SHEIN", "BOTH"):
                s = df_shein[(df_shein["order date"]>=start)&(df_shein["order date"]<=end)].copy()
                s = s[~shein_refund_mask(s["order status"])].copy()
                # 이미 df_shein에 style_key/color/size가 생성되어 있음
                s = s[s["style_key"] == skey]
                shein_df_filtered = s.copy()
                if not s.empty:
                    qty = len(s)  # 건수
                    sales = s["product price"].sum()
                    total_qty += int(qty)
                    total_sales += float(sales)
                    s["qty"] = 1
                    s_daily = (
                        s.groupby(pd.Grouper(key="order date", freq="D"))
                         .agg(qty=("qty","sum"), sales=("product price","sum"))
                         .reset_index()
                    )
                    s_table = s[["order date","product description","color","size","product price"]].rename(
                        columns={"product description":"Product", "product price":"Sales"}
                    )
                    res_tables.append(("SHEIN", s_daily, s_table))

            if total_qty == 0:
                st.info("해당 기간/플랫폼에서 일치하는 스타일 판매가 없습니다.")
            else:
                # 플랫폼별 요약
                plat_rows = []
                for label, _daily_df, table in res_tables:
                    if label == "TEMU":
                        p_qty = int(table["Qty"].sum()) if "Qty" in table.columns else 0
                        p_sales = float(table["Sales"].sum()) if "Sales" in table.columns else 0.0
                    else:
                        p_qty = int(len(table))
                        p_sales = float(table["Sales"].sum()) if "Sales" in table.columns else 0.0
                    plat_rows.append({
                        "Platform": label,
                        "Sales": p_sales,
                        "Qty": p_qty,
                        "AOV": (p_sales / p_qty) if p_qty > 0 else 0.0
                    })
                plat_df = pd.DataFrame(plat_rows).sort_values("Sales", ascending=False)

                # 총계 KPI
                aov = total_sales / total_qty if total_qty > 0 else 0.0
                c1, c2, c3, c4 = st.columns(4)
                with c1:
                    st.metric("Style Total Sales", f"${total_sales:,.2f}")
                with c2:
                    st.metric("Style Order Qty", f"{total_qty:,}")
                with c3:
                    st.metric("Style AOV", f"${aov:,.2f}")
                with c4:
                    thumb = IMG_MAP.get(skey, "")
                    if thumb:
                        st.markdown(
                            f"<div style='text-align:center'>{img_tag(thumb)}"
                            f"<div style='font-size:12px;color:#666'>{skey}</div></div>",
                            unsafe_allow_html=True
                        )
                    else:
                        st.caption(f"이미지 없음 • {skey}")

                st.markdown("**플랫폼별 요약 (Style Breakdown)**")
                st.dataframe(
                    plat_df.assign(
                        Sales=lambda d: d["Sales"].map(lambda x: f"${x:,.2f}"),
                        Qty=lambda d: d["Qty"].map(lambda x: f"{x:,}"),
                        AOV=lambda d: d["AOV"].map(lambda x: f"${x:,.2f}"),
                    ),
                    use_container_width=True
                )

                # ---- 정렬 (에러 fix: ascending=False만 사용)
                for label, daily_df, table in res_tables:
                    st.markdown(f"**{label} - {skey} 일별 추이**")
                    if not daily_df.empty:
                        st.line_chart(daily_df.set_index("order date")[["sales","qty"]])
                    st.dataframe(table.sort_values("order date", ascending=False), use_container_width=True)

                # ---- 색상/사이즈별 세부 판매 (표 + 도넛)
                st.divider()
                st.markdown("### 스타일 세부 판매 (색상 · 사이즈)")

                def _agg_variant_temudf(df: pd.DataFrame):
                    if df.empty: 
                        return pd.DataFrame(), pd.DataFrame()
                    # TEMU: 수량 = quantity shipped 합
                    cdf = df.groupby("color")["quantity shipped"].sum().reset_index().rename(columns={"quantity shipped":"Qty"})
                    sdf = df.groupby("size")["quantity shipped"].sum().reset_index().rename(columns={"quantity shipped":"Qty"})
                    cdf = cdf.sort_values("Qty", ascending=False)
                    sdf = sdf.sort_values("Qty", ascending=False)
                    return cdf, sdf

                def _agg_variant_sheindf(df: pd.DataFrame):
                    if df.empty:
                        return pd.DataFrame(), pd.DataFrame()
                    # SHEIN: 건수 기준
                    cdf = df.groupby("color").size().reset_index(name="Qty").sort_values("Qty", ascending=False)
                    sdf = df.groupby("size").size().reset_index(name="Qty").sort_values("Qty", ascending=False)
                    return cdf, sdf

                if not shein_df_filtered.empty:
                    st.markdown("**SHEIN 변형 판매**")
                    cdf, sdf = _agg_variant_sheindf(shein_df_filtered)
                    cols = st.columns(2)
                    with cols[0]:
                        if not cdf.empty:
                            st.dataframe(cdf, use_container_width=True)
                            _donut_chart(cdf["color"], cdf["Qty"], "SHEIN · Color Mix")
                        else:
                            st.caption("색상 정보 없음")
                    with cols[1]:
                        if not sdf.empty:
                            st.dataframe(sdf, use_container_width=True)
                            _donut_chart(sdf["size"], sdf["Qty"], "SHEIN · Size Mix")
                        else:
                            st.caption("사이즈 정보 없음")

                if not temu_df_filtered.empty:
                    st.markdown("**TEMU 변형 판매**")
                    cdf, sdf = _agg_variant_temudf(temu_df_filtered)
                    cols = st.columns(2)
                    with cols[0]:
                        if not cdf.empty:
                            st.dataframe(cdf, use_container_width=True)
                            _donut_chart(cdf["color"], cdf["Qty"], "TEMU · Color Mix")
                        else:
                            st.caption("색상 정보 없음")
                    with cols[1]:
                        if not sdf.empty:
                            st.dataframe(sdf, use_container_width=True)
                            _donut_chart(sdf["size"], sdf["Qty"], "TEMU · Size Mix")
                        else:
                            st.caption("사이즈 정보 없음")

                if platform == "BOTH" and (not temu_df_filtered.empty or not shein_df_filtered.empty):
                    st.markdown("**통합 변형 판매 (선택된 플랫폼 전체)**")
                    merged = []
                    if not temo_df_filtered.empty if 'temo_df_filtered' in locals() else False:
                        pass  # (타이포 방지용, 아래 실제 merged는 temu_df_filtered 사용)
                    if not temu_df_filtered.empty:
                        tmp = temu_df_filtered.copy()
                        tmp["__platform__"] = "TEMU"
                        merged.append(tmp)
                    if not shein_df_filtered.empty:
                        tmp = shein_df_filtered.copy()
                        tmp["__platform__"] = "SHEIN"
                        merged.append(tmp)
                    M = pd.concat(merged, ignore_index=True)
                    # 통합은 수량 기준 통일: TEMU 규칙(수량 합), SHEIN은 1로 환산
                    M = M.copy()
                    if "quantity shipped" not in M.columns:
                        M["quantity shipped"] = 0
                    M.loc[M["__platform__"] == "SHEIN", "quantity shipped"] = 1
                    cdf_all = M.groupby("color")["quantity shipped"].sum().reset_index().rename(columns={"quantity shipped":"Qty"}).sort_values("Qty", ascending=False)
                    sdf_all = M.groupby("size")["quantity shipped"].sum().reset_index().rename(columns={"quantity shipped":"Qty"}).sort_values("Qty", ascending=False)
                    cols = st.columns(2)
                    with cols[0]:
                        if not cdf_all.empty:
                            st.dataframe(cdf_all, use_container_width=True)
                            _donut_chart(cdf_all["color"], cdf_all["Qty"], "ALL · Color Mix")
                        else:
                            st.caption("색상 정보 없음")
                    with cols[1]:
                        if not sdf_all.empty:
                            st.dataframe(sdf_all, use_container_width=True)
                            _donut_chart(sdf_all["size"], sdf_all["Qty"], "ALL · Size Mix")
                        else:
                            st.caption("사이즈 정보 없음")

# =========================
# 5) KPI
# =========================
def _delta_str(now, prev):
    if prev in (0, None) or pd.isna(prev):
        return "—"
    pct = (now - prev) / prev * 100
    sign = "+" if pct >= 0 else ""
    return f"{sign}{pct:.1f}%"

st.subheader("")
with st.container(border=True):
    cols = st.columns(4, gap="small")
    with cols[0]:
        st.metric("Total Order Amount", f"${sales_sum:,.2f}", _delta_str(sales_sum, locals().get("psales")))
    with cols[1]:
        st.metric("Total Order Quantity", f"{int(qty_sum):,}", _delta_str(qty_sum, locals().get("pqty")))
    with cols[2]:
        st.metric("AOV", f"${aov:,.2f}", _delta_str(aov, locals().get("paov")))
    with cols[3]:
        st.metric("Canceled Order", f"{int(cancel_qty):,}", _delta_str(cancel_qty, locals().get("pcancel")))

# =========================
# 6) Insights
# =========================
def _pc(cur, prev):
    if prev in (0, None) or pd.isna(prev):
        return None
    return (cur - prev) / prev * 100.0

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
        t = t[temu_sold_mask(t["order item status"])].copy()
        t["style_key"] = t["product number"].astype(str).apply(lambda x: style_key_from_label(x, IMG_MAP))
        t = t.dropna(subset=["style_key"])
        t_cnt = t.groupby("style_key")["quantity shipped"].sum()
        s2 = df_shein[(df_shein["order date"]>=s)&(df_shein["order date"]<=e)]
        s2 = s2[~shein_refund_mask(s2["order status"])].copy()
        s2["style_key"] = s2["product description"].astype(str).apply(lambda x: style_key_from_label(x, IMG_MAP))
        s2 = s2.dropna(subset=["style_key"])
        s_cnt = s2.groupby("style_key").size()
        mix = (pd.DataFrame({"t":t_cnt, "s":s_cnt}).fillna(0))
        mix["tot"] = mix["t"] + mix["s"]
        return list(mix["tot"].sort_values(ascending=False).head(10).index.astype(str))

cur_top = get_bestseller_labels(platform, df_sold, start, end)
prev_top = get_bestseller_labels(platform, locals().get("p_sold", pd.DataFrame()), prev_start, prev_end) if 'p_sold' in locals() else []
entered = [x for x in cur_top if x not in prev_top]
dropped = [x for x in prev_top if x not in cur_top]

bullets = []
for label, now, prev in [
    ("매출액", sales_sum, locals().get("psales")),
    ("판매수량", qty_sum, locals().get("pqty")),
    ("AOV", aov, locals().get("paov")),
    ("취소건", cancel_qty, locals().get("pcancel")),
]:
    v = _pc(now, prev)
    if v is not None:
        dir_ = "증가" if v >= 0 else "감소"
        bullets.append(f"• {label} **{dir_} {abs(v):.1f}%**")

if entered:
    bullets.append(f"• Top10 **신규 진입**: {', '.join(entered[:5])} → 재고/광고 예산 소폭 증액")
if dropped:
    bullets.append(f"• Top10 **이탈**: {', '.join(dropped[:5])} → 썸네일/타이틀/가격 비교 및 재노출")

# SHEIN 프로모션 인사이트
try:
    if platform in ("SHEIN", "BOTH"):
        shein_cur = df_shein[(df_shein["order date"] >= start) & (df_shein["order date"] <= end)]
        shein_cur = shein_cur[~shein_refund_mask(shein_cur["order status"])].copy()
        if not shein_cur.empty:
            p_mask = shein_promo_mask(shein_cur)
            total_orders = len(shein_cur)
            promo_orders = int(p_mask.sum())
            promo_sales  = shein_cur.loc[p_mask, "product price"].sum()
            promo_ratio  = (promo_orders / total_orders * 100) if total_orders > 0 else 0.0
            prefix = "SHEIN " if platform == "BOTH" else ""
            bullets.append(f"• {prefix}프로모션 주문 비중: **{promo_ratio:.1f}%** ({promo_orders:,}/{total_orders:,})")
            bullets.append(f"• {prefix}프로모션 매출: **${promo_sales:,.2f}**")
except Exception:
    pass

with st.container(border=True):
    st.markdown("**자동 인사이트 & 액션 제안**")
    st.markdown("\n".join([f"- {b}" for b in bullets]) if bullets else "- 인사이트가 없습니다. 기간/플랫폼을 변경해 보세요.")

# =========================
# 7) 실행 액션 (아이템 구체 리스트 포함)
# =========================
with st.container(border=True):
    st.markdown("### 이번 기간 실행 권장 액션 (아이템 지정)")

    actions = []

    # 현재/전기간 스타일별 수량 집계
    t_cur = df_temu[(df_temu["order date"]>=start)&(df_temu["order date"]<=end)].copy()
    t_cur["style_key"] = _style_key_series_temu(t_cur)
    t_cur_sold = t_cur[temu_sold_mask(t_cur["order item status"])].dropna(subset=["style_key"])
    t_cur_qty = t_cur_sold.groupby("style_key")["quantity shipped"].sum().astype(int)

    # SHEIN은 Seller SKU 파싱된 style_key 사용
    s_cur = df_shein[(df_shein["order date"]>=start)&(df_shein["order date"]<=end)].copy()
    s_cur_sold = s_cur[~shein_refund_mask(s_cur["order status"])].dropna(subset=["style_key"])
    s_cur_qty = s_cur_sold.groupby("style_key").size().astype(int)

    # ---- 전기간
    t_prev = df_temu[(df_temu["order date"]>=prev_start)&(df_temu["order date"]<=prev_end)].copy()
    t_prev["style_key"] = _style_key_series_temu(t_prev)
    t_prev_sold = t_prev[temu_sold_mask(t_prev["order item status"])].dropna(subset=["style_key"])
    t_prev_qty = t_prev_sold.groupby("style_key")["quantity shipped"].sum().astype(int)

    s_prev = df_shein[(df_shein["order date"]>=prev_start)&(df_shein["order date"]<=prev_end)].copy()
    s_prev_sold = s_prev[~shein_refund_mask(s_prev["order status"])].dropna(subset=["style_key"])
    s_prev_qty = s_prev_sold.groupby("style_key").size().astype(int)

    # 1) SHEIN 환불비율 높은 스타일
    if not s_cur.empty:
        s_all_cur = s_cur.dropna(subset=["style_key"]).copy()
        s_all_cur["is_refund"] = shein_refund_mask(s_all_cur["order status"])
        refund_stats = s_all_cur.groupby("style_key")["is_refund"].mean().sort_values(ascending=False)
        high_refund = refund_stats[refund_stats >= 0.15].head(5)
        for sk, r in high_refund.items():
            actions.append(f"SHEIN 환불률 높음({r*100:.0f}%): {sk} → PDP 설명/사이즈 안내 보강 & 리뷰 상단 고정")

    # 2) TEMU 취소비율 높은 스타일
    if not t_cur.empty:
        t_all_cur = t_cur.dropna(subset=["style_key"]).copy()
        t_all_cur["is_cancel"] = temu_cancel_mask(t_all_cur["order item status"])
        qty_purchased = t_all_cur.groupby("style_key")["quantity purchased"].sum().replace(0, pd.NA)
        cancel_cnt = t_all_cur.groupby("style_key")["is_cancel"].sum()
        cancel_rate = (cancel_cnt / qty_purchased).fillna(cancel_cnt / cancel_cnt.where(cancel_cnt==0, other=1)).sort_values(ascending=False)
        high_cancel = cancel_rate[cancel_rate >= 0.10].head(5)
        for sk, r in high_cancel.items():
            actions.append(f"TEMU 취소율 높음({r*100:.0f}%): {sk} → 상세/배송안내 보강 및 옵션/가격 점검")

    # 3) 판매 급감 스타일(전기간 대비 -40% 이상)
    common_s = set(s_prev_qty.index).intersection(set(s_cur_qty.index))
    s_drop = [(sk, s_prev_qty.get(sk, 0), s_cur_qty.get(sk, 0))
              for sk in common_s if s_prev_qty.get(sk, 0) > 0 and (s_cur_qty.get(sk, 0)-s_prev_qty.get(sk, 0))/s_prev_qty.get(sk, 0) <= -0.4]
    s_drop = sorted(s_drop, key=lambda x: (x[1]-x[2]), reverse=True)[:5]
    for sk, p, c in s_drop:
        actions.append(f"SHEIN 판매 급감: {sk} ({p}→{c}) → 썸네일/타이틀/가격 비교 및 재노출")

    common_t = set(t_prev_qty.index).intersection(set(t_cur_qty.index))
    t_drop = [(sk, t_prev_qty.get(sk, 0), t_cur_qty.get(sk, 0))
              for sk in common_t if t_prev_qty.get(sk, 0) > 0 and (t_cur_qty.get(sk, 0)-t_prev_qty.get(sk, 0))/t_prev_qty.get(sk, 0) <= -0.4]
    t_drop = sorted(t_drop, key=lambda x: (x[1]-x[2]), reverse=True)[:5]
    for sk, p, c in t_drop:
        actions.append(f"TEMU 판매 급감: {sk} ({p}→{c}) → 노출 리프레시/가격 점검/번들 제안")

    # 4) Top10 이탈
    for sk in dropped[:5]:
        actions.append(f"Top10 이탈: {sk} → 광고·노출 재강화 및 경쟁가 점검")

    # 5) 이미지 누락
    top_s = s_cur_sold.groupby("style_key").size().sort_values(ascending=False).head(20)
    for sk in [sk for sk in top_s.index if not IMG_MAP.get(sk)][:5]:
        actions.append(f"SHEIN 이미지 없음: {sk} → 썸네일 업로드/교체")
    top_t = t_cur_sold.groupby("style_key")["quantity shipped"].sum().sort_values(ascending=False).head(20)
    for sk in [sk for sk in top_t.index if not IMG_MAP.get(sk)][:5]:
        actions.append(f"TEMU 이미지 없음: {sk} → 썸네일 업로드/교체")

    # 6) 타이틀 짧은 상품
    if not s_cur_sold.empty and "product description" in s_cur_sold.columns:
        s_cur_sold = s_cur_sold.assign(
            short_title=_short_title_mask(s_cur_sold["product description"], 25),
            style_key=s_cur_sold["style_key"]
        ).dropna(subset=["style_key"])
        short_candidates = (
            s_cur_sold[s_cur_sold["short_title"]]
            .groupby("style_key").size()
            .sort_values(ascending=False).index.tolist()
        )
        for sk in short_candidates[:5]:
            actions.append(f"SHEIN 타이틀 짧음: {sk} → 핵심 키워드/시즌키워드 추가")

    # dedup & cap
    seen, final = set(), []
    for a in actions:
        if a not in seen:
            final.append(a); seen.add(a)
    final = final[:12]

    if final:
        st.markdown("\n".join([f"- {a}" for a in final]))
        md = "## 실행 액션(아이템 지정)\n" + "\n".join([f"- {a}" for a in final])
        st.download_button("액션 체크리스트 .txt 다운로드", data=md, file_name="actions_itemized.txt")
    else:
        st.info("추천할 아이템 단위 액션이 없습니다. 기간/플랫폼을 변경해 보세요.")

# =========================
# 8) Daily Chart
# =========================
def build_daily(platform: str, s: pd.Timestamp, e: pd.Timestamp) -> pd.DataFrame:
    if platform == "TEMU":
        t = df_temu[(df_temu["order date"]>=s)&(df_temu["order date"]<=e)]
        t = t[temu_sold_mask(df_temu["order item status"])]
        daily = t.groupby(pd.Grouper(key="order date", freq="D")).agg(
            qty=("quantity shipped","sum"), Total_Sales=("base price total","sum")
        )
    elif platform == "SHEIN":
        s2 = df_shein[(df_shein["order date"]>=s)&(df_shein["order date"]<=e)]
        s2 = s2[~shein_refund_mask(df_shein["order status"])]
        s2["qty"] = 1
        daily = s2.groupby(pd.Grouper(key="order date", freq="D")).agg(
            qty=("qty","sum"), Total_Sales=("product price","sum")
        )
    else:
        t = df_temu[(df_temu["order date"]>=s)&(df_temu["order date"]<=e)]
        t = t[temu_sold_mask(df_temu["order item status"])].copy()
        s2 = df_shein[(df_shein["order date"]>=s)&(df_shein["order date"]<=e)]
        s2 = s2[~shein_refund_mask(s2["order status"])].copy()
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
# 9) Best Seller 10
# =========================
st.subheader("Best Seller 10")

def best_table(platform, df_sold, s, e):
    if platform == "TEMU":
        g = (
            df_sold.assign(style_key=lambda d: d["product number"].astype(str)
                           .apply(lambda x: style_key_from_label(x, IMG_MAP)))
               .dropna(subset=["style_key"])
               .groupby("style_key")["quantity shipped"].sum().astype(int).reset_index()
        )
        g = g.rename(columns={"style_key":"Style Number","quantity shipped":"Sold Qty"})
        g["Image"] = g["Style Number"].apply(lambda x: img_tag(IMG_MAP.get(x, "")))
        return g[["Image","Style Number","Sold Qty"]].sort_values("Sold Qty", ascending=False).head(10)

    if platform == "SHEIN":
        tmp = df_sold.copy(); tmp["qty"] = 1
        g = (
            tmp.assign(style_key=lambda d: d["product description"].astype(str)
                       .apply(lambda x: style_key_from_label(x, IMG_MAP)))
               .dropna(subset=["style_key"])
               .groupby("style_key")["qty"].sum().astype(int).reset_index()
        )
        g = g.rename(columns={"style_key":"Style Number","qty":"Sold Qty"})
        g["Image"] = g["Style Number"].apply(lambda x: img_tag(IMG_MAP.get(x, "")))
        return g[["Image","Style Number","Sold Qty"]].sort_values("Sold Qty", ascending=False).head(10)

    # BOTH
    t = df_temu[(df_temu["order date"]>=s)&(df_temu["order date"]<=e)&
                (temu_sold_mask(df_temu["order item status"]))].copy()
    t["style_key"] = t["product number"].astype(str).apply(lambda x: style_key_from_label(x, IMG_MAP))
    t = t.dropna(subset=["style_key"])
    t_group = t.groupby("style_key")["quantity shipped"].sum().astype(int)

    s2 = df_shein[(df_shein["order date"]>=s)&(df_shein["order date"]<=e)&
                  (~shein_refund_mask(df_shein["order status"]))].copy()
    s2["style_key"] = s2["product description"].astype(str).apply(lambda x: style_key_from_label(x, IMG_MAP))
    s2 = s2.dropna(subset=["style_key"])
    s_group = s2.groupby("style_key").size().astype(int)

    mix = pd.DataFrame({"TEMU Qty": t_group, "SHEIN Qty": s_group}).fillna(0).astype(int)
    mix["Sold Qty"] = (mix["TEMU Qty"] + mix["SHEIN Qty"]).astype(int)
    mix = mix.sort_values("Sold Qty", ascending=False).head(10).reset_index()
    if "index" in mix.columns:
        mix = mix.rename(columns={"index":"Style Number"})
    elif "style_key" in mix.columns:
        mix = mix.rename(columns={"style_key":"Style Number"})
    elif "Style Number" not in mix.columns:
        mix["Style Number"] = mix.index.astype(str)
    mix["Image"] = mix["Style Number"].apply(lambda x: img_tag(IMG_MAP.get(x, "")))

    def badge_row(row):
        t_val = int(row["TEMU Qty"]); s_val = int(row["SHEIN Qty"])
        return (
            f"<span style='display:inline-block;padding:4px 8px;border-radius:10px;background:#eef6ff;color:#1456b8;font-size:12px;'>"
            f"TEMU {t_val:,}</span> "
            f"<span style='display:inline-block;padding:4px 8px;border-radius:10px;background:#fff1f0;color:#b81414;font-size:12px;'>"
            f"SHEIN {s_val:,}</span>"
        )
    mix["Platform Mix"] = mix.apply(badge_row, axis=1)
    return mix[["Image","Style Number","Sold Qty","Platform Mix","TEMU Qty","SHEIN Qty"]]

best_df = best_table(platform, df_sold, start, end)
with st.container(border=True):
    st.markdown(best_df.to_html(escape=False, index=False), unsafe_allow_html=True)
