# ==========================================
# File: pages/6_반품_취소율.py
# ==========================================
import streamlit as st
import pandas as pd
import re
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

STYLE_RE = re.compile(r"\b([A-Z]{1,3}\d{3,5}[A-Z0-9]?)\b")

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

def build_img_map(df_info: pd.DataFrame):
    keys = df_info.get("product number", pd.Series(dtype=str)).astype(str).str.upper().str.replace(" ", "", regex=False)
    return dict(zip(keys, df_info.get("image", "")))

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

_money = lambda s: pd.to_numeric(
    s.astype(str).str.replace(r"[^0-9.\-]", "", regex=True), errors="coerce"
).fillna(0.0)

# ---------- Load ----------
df_info  = load_google_sheet("PRODUCT_INFO")
df_temu  = load_google_sheet("TEMU_SALES")
df_shein = load_google_sheet("SHEIN_SALES")
IMG_MAP  = build_img_map(df_info)

df_temu["order date"]  = df_temu["purchase date"].apply(parse_temudate)
df_shein["order date"] = df_shein["order processed on"].apply(parse_sheindate)

df_temu["order item status"]  = df_temu["order item status"].astype(str)
df_temu["quantity shipped"]   = pd.to_numeric(df_temu.get("quantity shipped", 0), errors="coerce").fillna(0)
df_temu["quantity purchased"] = pd.to_numeric(df_temu.get("quantity purchased", 0), errors="coerce").fillna(0)
df_shein["order status"]      = df_shein["order status"].astype(str)

# ---------- Date controls ----------
min_dt = pd.to_datetime(pd.concat([df_temu["order date"], df_shein["order date"]]).dropna()).min()
max_dt = pd.to_datetime(pd.concat([df_temu["order date"], df_shein["order date"]]).dropna()).max()
if pd.isna(min_dt) or pd.isna(max_dt):
    st.info("날짜 데이터가 없습니다. 시트를 확인하세요.")
    st.stop()

dr = st.date_input(
    "조회 기간",
    value=(max_dt.date() - pd.Timedelta(days=29), max_dt.date()),
    min_value=min_dt.date(),
    max_value=max_dt.date(),
)
if isinstance(dr, (list, tuple)):
    start, end = dr
else:
    start, end = dr, dr
start = pd.to_datetime(start)
end   = pd.to_datetime(end) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)

# ---------- Controls ----------
c1, c2, c3, c4 = st.columns([2.2, 2.2, 2, 2])
with c1:
    min_orders = st.number_input("최소 주문 기준(노이즈 제거)", min_value=0, value=5, step=1)
with c2:
    st.caption("취소율 = (취소/환불) ÷ (출고+취소)")
with c3:
    temu_warn = st.slider("TEMU 취소율 경고 임계값", 0.0, 1.0, 0.25, 0.01)
with c4:
    shein_warn = st.slider("SHEIN 환불률 경고 임계값", 0.0, 1.0, 0.20, 0.01)

# ---------- TEMU aggregate ----------
T = df_temu[(df_temu["order date"]>=start) & (df_temu["order date"]<=end)].copy()
T["status"]    = T["order item status"].str.lower()
T["style_key"] = T["product number"].astype(str).apply(lambda x: style_key_from_label(x, IMG_MAP))
T = T.dropna(subset=["style_key"])

T_shipped  = T[T["status"].isin(["shipped", "delivered"])].copy()
T_canceled = T[T["status"].eq("canceled")].copy()

T_g1 = T_shipped.groupby("style_key").agg(
    shipped_qty=("quantity shipped","sum"),
    shipped_orders=("product number","count"),
)
T_g2 = T_canceled.groupby("style_key").agg(
    canceled_qty=("quantity purchased","sum"),
    canceled_orders=("product number","count"),
)
T_tbl = pd.concat([T_g1, T_g2], axis=1).fillna(0)
T_tbl["orders_total"] = (T_tbl["shipped_orders"] + T_tbl["canceled_orders"]).astype(int)
T_tbl["cancel_rate"]  = (
    T_tbl["canceled_qty"] /
    (T_tbl["shipped_qty"] + T_tbl["canceled_qty"]).replace(0, pd.NA)
).fillna(0.0)
T_tbl = T_tbl.reset_index().rename(columns={"style_key":"Style Number"})

temu_total_rate = (
    T_tbl["canceled_qty"].sum() /
    max(T_tbl["shipped_qty"].sum() + T_tbl["canceled_qty"].sum(), 1)
)

# ---------- SHEIN aggregate ----------
S = df_shein[(df_shein["order date"]>=start) & (df_shein["order date"]<=end)].copy()
S["status"]    = S["order status"].str.lower()
S["style_key"] = S["product description"].astype(str).apply(lambda x: style_key_from_label(x, IMG_MAP))
S = S.dropna(subset=["style_key"])

S_ref = S[S["status"].eq("customer refunded")]
S_non = S[~S["status"].eq("customer refunded")]

S_g1 = S_non.groupby("style_key").agg(shipped_qty=("product description","count"))
S_g2 = S_ref .groupby("style_key").agg(refunded_qty=("product description","count"))
S_tbl = pd.concat([S_g1, S_g2], axis=1).fillna(0).astype({"shipped_qty":int, "refunded_qty":int})
S_tbl["orders_total"] = (S_tbl["shipped_qty"] + S_tbl["refunded_qty"]).astype(int)
S_tbl["refund_rate"]  = (
    S_tbl["refunded_qty"] / (S_tbl["orders_total"]).replace(0, pd.NA)
).fillna(0.0)
S_tbl = S_tbl.reset_index().rename(columns={"style_key":"Style Number"})

shein_total_rate = S_tbl["refunded_qty"].sum() / max(S_tbl["orders_total"].sum(), 1)

# ---------- KPI ----------
with st.container(border=True):
    k1, k2, k3, k4 = st.columns(4)
    with k1: st.metric("TEMU 전체 취소율", f"{temu_total_rate:.1%}")
    with k2: st.metric("SHEIN 전체 환불률", f"{shein_total_rate:.1%}")
    with k3: st.metric("TEMU 분석 스타일 수", f"{(T_tbl['orders_total']>=min_orders).sum():,}")
    with k4: st.metric("SHEIN 분석 스타일 수", f"{(S_tbl['orders_total']>=min_orders).sum():,}")

# ---------- Table CSS (bigger thumbs) ----------
THUMB = 96
st.markdown(f"""
<style>
[data-testid="stDataFrame"] td img, [data-testid="stDataEditor"] td img {{
    width:{THUMB}px !important;
    height:{THUMB}px !important;
    object-fit:cover !important;
    border-radius:8px;
}}
[data-testid="stDataFrame"] [role="row"], [data-testid="stDataEditor"] [role="row"] {{
    min-height:{THUMB + 14}px !important;
}}
</style>
""", unsafe_allow_html=True)

# ---------- TEMU – 취소율 높은 스타일 ----------
T_tbl["image_url"] = T_tbl["Style Number"].apply(lambda x: IMG_MAP.get(str(x).upper(), ""))
T_show = (
    T_tbl[T_tbl["orders_total"] >= min_orders]
    .query("cancel_rate >= @temu_warn")
    .sort_values("cancel_rate", ascending=False)
    [["image_url","Style Number","shipped_qty","canceled_qty","orders_total","cancel_rate"]]
    .rename(columns={
        "image_url":"이미지",
        "shipped_qty":"Shipped Qty",
        "canceled_qty":"Canceled Qty",
        "orders_total":"Orders",
        "cancel_rate":"취소율",
    })
)
st.subheader("TEMU – 취소율 높은 스타일")
st.dataframe(
    T_show,
    use_container_width=True,
    hide_index=True,
    column_config={
        "이미지":      st.column_config.ImageColumn("이미지", width=THUMB),
        "취소율":      st.column_config.NumberColumn("취소율", format="0.0%", step=0.001),
        "Shipped Qty": st.column_config.NumberColumn("Shipped Qty", format="%,d", step=1),
        "Canceled Qty":st.column_config.NumberColumn("Canceled Qty", format="%,d", step=1),
        "Orders":      st.column_config.NumberColumn("Orders", format="%,d", step=1),
    }
)

# ---------- SHEIN – 환불률 높은 스타일 ----------
S_tbl["image_url"] = S_tbl["Style Number"].apply(lambda x: IMG_MAP.get(str(x).upper(), ""))
S_show = (
    S_tbl[S_tbl["orders_total"] >= min_orders]
    .query("refund_rate >= @shein_warn")
    .sort_values("refund_rate", ascending=False)  # ← ascending=False가 정답
    [["image_url","Style Number","shipped_qty","refunded_qty","orders_total","refund_rate"]]
    .rename(columns={
        "image_url":"이미지",
        "shipped_qty":"Shipped Qty",
        "refunded_qty":"Refunded Qty",
        "orders_total":"Orders",
        "refund_rate":"환불률",
    })
)
st.subheader("SHEIN – 환불률 높은 스타일")
st.dataframe(
    S_show,
    use_container_width=True,
    hide_index=True,
    column_config={
        "이미지":       st.column_config.ImageColumn("이미지", width=THUMB),
        "환불률":       st.column_config.NumberColumn("환불률", format="0.0%", step=0.001),
        "Shipped Qty":  st.column_config.NumberColumn("Shipped Qty", format="%,d", step=1),
        "Refunded Qty": st.column_config.NumberColumn("Refunded Qty", format="%,d", step=1),
        "Orders":       st.column_config.NumberColumn("Orders", format="%,d", step=1),
    }
)
