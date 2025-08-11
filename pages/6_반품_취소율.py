# ==========================================
# File: pages/6_반품_취소율.py
# ==========================================
import streamlit as st
import pandas as pd
from dateutil import parser

st.set_page_config(page_title="반품·취소율 분석", layout="wide")
st.title("↩️ 반품·취소율 분석")

@st.cache_data(show_spinner=False)
def load_google_sheet(sheet_name: str) -> pd.DataFrame:
    import gspread
    from oauth2client.service_account import ServiceAccountCredentials
    import json
    GOOGLE_SHEET_URL = "https://docs.google.com/spreadsheets/d/1oyVzCgGK1Q3Qi_sbYwE-wKG6SArnfUDRe7rQfGOF-Eo"
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_json = {k: str(v) for k, v in st.secrets["gcp_service_account"].items()}
    with open("/tmp/service_account.json", "w") as f:
        import json as _json
        _json.dump(creds_json, f)
    creds = ServiceAccountCredentials.from_json_keyfile_name("/tmp/service_account.json", scope)
    client = gspread.authorize(creds)
    ws = client.open_by_url(GOOGLE_SHEET_URL).worksheet(sheet_name)
    df = pd.DataFrame(ws.get_all_records())
    df.columns = [c.lower().strip() for c in df.columns]
    return df

def parse_temudate(x):
    try:
        s = str(x).split("(")[0].strip()
        return parser.parse(s, fuzzy=True)
    except Exception:
        return pd.NaT

def parse_sheindate(x):
    try:
        return pd.to_datetime(str(x), errors='coerce', infer_datetime_format=True)
    except Exception:
        return pd.NaT

# Load
info = load_google_sheet("PRODUCT_INFO")
temu = load_google_sheet("TEMU_SALES")
shein = load_google_sheet("SHEIN_SALES")

# Dates & normalization

temu["order date"] = temu["purchase date"].apply(parse_temudate)
temu["order item status"] = temu["order item status"].astype(str)
temu["quantity shipped"] = pd.to_numeric(temu.get("quantity shipped", 0), errors="coerce").fillna(0)
temu["quantity purchased"] = pd.to_numeric(temu.get("quantity purchased", 0), errors="coerce").fillna(0)

shein["order date"] = shein["order processed on"].apply(parse_sheindate)
shein["order status"] = shein["order status"].astype(str)

min_dt = pd.to_datetime(pd.concat([temu["order date"], shein["order date"]]).dropna()).min()
max_dt = pd.to_datetime(pd.concat([temu["order date"], shein["order date"]]).dropna()).max()

if pd.isna(min_dt) or pd.isna(max_dt):
    st.info("날짜 데이터가 없습니다.")
    st.stop()

c1, c2, c3 = st.columns([5, 3, 2])
with c1:
    dr = st.date_input(
        "조회 기간",
        value=(max_dt.date() - pd.Timedelta(days=29), max_dt.date()),
        min_value=min_dt.date(), max_value=max_dt.date()
    )
    if isinstance(dr, (list, tuple)):
        start, end = dr
    else:
        start = end = dr
    start = pd.to_datetime(start)
    end = pd.to_datetime(end) + pd.Timedelta(hours=23, minutes=59, seconds=59)
with c2:
    min_order = st.number_input("최소 주문 기준(노이즈 제거)", min_value=1, max_value=100, value=5, step=1)
with c3:
    st.markdown("\n")
    st.caption("*취소율 = (취소/환불) ÷ (출고+취소)*")

# Platform aggregates
# TEMU
T = temu[(temu["order date"] >= start) & (temu["order date"] <= end)].copy()
T_status = T["order item status"].str.lower()
T_ship = T[T_status.isin(["shipped", "delivered"])].copy()
T_cancel = T[T_status.eq("canceled")].copy()

T_ship_qty = T_ship.groupby("product number")["quantity shipped"].sum()
T_cancel_qty = T_cancel.groupby("product number")["quantity purchased"].sum()

T_all = pd.concat([T_ship_qty, T_cancel_qty], axis=1).fillna(0)
T_all.columns = ["shipped_qty", "canceled_qty"]
T_all["orders_total"] = T_all["shipped_qty"] + T_all["canceled_qty"]
T_all["cancel_rate"] = T_all.apply(lambda r: (r["canceled_qty"] / r["orders_total"]) if r["orders_total"] > 0 else 0.0, axis=1)
T_all.index.name = "Style Number"

# SHEIN
S = shein[(shein["order date"] >= start) & (shein["order date"] <= end)].copy()
S_status = S["order status"].str.lower()
S_sold = S[~S_status.isin(["customer refunded"])].copy()
S_ref = S[S_status.isin(["customer refunded"])].copy()

S_sold_cnt = S_sold.groupby("product description").size()
S_ref_cnt = S_ref.groupby("product description").size()

S_all = pd.concat([S_sold_cnt, S_ref_cnt], axis=1).fillna(0)
S_all.columns = ["sold_cnt", "refunded_cnt"]
S_all["orders_total"] = S_all["sold_cnt"] + S_all["refunded_cnt"]
S_all["cancel_rate"] = S_all.apply(lambda r: (r["refunded_cnt"] / r["orders_total"]) if r["orders_total"] > 0 else 0.0, axis=1)
S_all.index.name = "Style Number"

# KPI
with st.container(border=True):
    cols = st.columns(4)
    with cols[0]:
        st.metric("TEMU 전체 취소율", f"{(T_all['canceled_qty'].sum() / max(T_all['orders_total'].sum(),1))*100:,.1f}%")
    with cols[1]:
        st.metric("SHEIN 전체 환불율", f"{(S_all['refunded_cnt'].sum() / max(S_all['orders_total'].sum(),1))*100:,.1f}%")
    with cols[2]:
        st.metric("TEMU 분석 스타일 수", f"{(T_all['orders_total']>=min_order).sum():,}")
    with cols[3]:
        st.metric("SHEIN 분석 스타일 수", f"{(S_all['orders_total']>=min_order).sum():,}")

# High rate tables
thr_temu = st.slider("TEMU 취소율 경고 임계값", 0.0, 1.0, 0.25, 0.05)
thr_shein = st.slider("SHEIN 환불율 경고 임계값", 0.0, 1.0, 0.20, 0.05)

T_tbl = T_all[(T_all["orders_total"] >= min_order) & (T_all["cancel_rate"] >= thr_temu)].copy()
S_tbl = S_all[(S_all["orders_total"] >= min_order) & (S_all["cancel_rate"] >= thr_shein)].copy()

# Formatting
T_tbl = T_tbl.reset_index()
S_tbl = S_tbl.reset_index()

T_tbl["취소율"] = (T_tbl["cancel_rate"] * 100).round(1).astype(str) + "%"
S_tbl["환불율"] = (S_tbl["cancel_rate"] * 100).round(1).astype(str) + "%"

# Output
left, right = st.columns(2)
with left:
    st.subheader("TEMU – 취소율 높은 스타일")
    if T_tbl.empty:
        st.info("임계값을 충족하는 스타일이 없습니다.")
    else:
        st.dataframe(T_tbl[["Style Number", "shipped_qty", "canceled_qty", "orders_total", "취소율"]].sort_values("cancel_rate", ascending=False), use_container_width=True)

with right:
    st.subheader("SHEIN – 환불율 높은 스타일")
    if S_tbl.empty:
        st.info("임계값을 충족하는 스타일이 없습니다.")
    else:
        st.dataframe(S_tbl[["Style Number", "sold_cnt", "refunded_cnt", "orders_total", "환불율"]].sort_values("cancel_rate", ascending=False), use_container_width=True)

st.caption("참고: TEMU는 'canceled'를 취소로, SHEIN은 'customer refunded'를 환불로 집계했습니다. 다른 사유코드가 있을 경우 시트 컬럼 기준으로 추가 확장 가능합니다.")
