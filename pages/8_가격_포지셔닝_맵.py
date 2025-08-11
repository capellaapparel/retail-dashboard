# ==========================================
# File: pages/8_가격_포지셔닝_맵.py
# ==========================================
import streamlit as st
import pandas as pd
import altair as alt
import re
from dateutil import parser

st.set_page_config(page_title="가격 포지셔닝 맵", layout="wide")
st.title("📍 가격 포지셔닝 맵")

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

# load
info  = load_google_sheet("PRODUCT_INFO")
temu  = load_google_sheet("TEMU_SALES")
shein = load_google_sheet("SHEIN_SALES")

IMG_MAP = dict(zip(info.get("product number", pd.Series(dtype=str)).astype(str).str.upper().str.replace(" ", "", regex=False), info.get("image","")))

money = lambda s: pd.to_numeric(str(s).replace("$",""), errors="coerce") if not pd.isna(s) else 0.0

# normalize

temu["order date"]  = temu["purchase date"].apply(parse_temudate)
shein["order date"] = shein["order processed on"].apply(parse_sheindate)

temu["order item status"] = temu["order item status"].astype(str)
temu["quantity shipped"]  = pd.to_numeric(temu.get("quantity shipped", 0), errors="coerce").fillna(0)
if "base price total" in temu.columns:
    temu["base price total"] = pd.to_numeric(temu["base price total"].astype(str).str.replace(r"[^0-9.\-]", "", regex=True), errors="coerce").fillna(0.0)

shein["order status"]   = shein["order status"].astype(str)
if "product price" in shein.columns:
    shein["product price"] = pd.to_numeric(shein["product price"].astype(str).str.replace(r"[^0-9.\-]", "", regex=True), errors="coerce").fillna(0.0)

# controls
min_dt = pd.to_datetime(pd.concat([temu["order date"], shein["order date"]]).dropna()).min()
max_dt = pd.to_datetime(pd.concat([temu["order date"], shein["order date"]]).dropna()).max()

r1, r2 = st.columns([1.2,1])
with r1:
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
    start = pd.to_datetime(start); end = pd.to_datetime(end) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
with r2:
    platform = st.radio("플랫폼", ["TEMU","SHEIN","BOTH"], horizontal=True)

# aggregate per style
frames = []
if platform in ["TEMU","BOTH"]:
    df = temu[(temu["order date"]>=start) & (temu["order date"]<=end) & (temu["order item status"].str.lower().isin(["shipped","delivered"]))].copy()
    g = df.groupby("product number").agg(qty=("quantity shipped","sum"), sales=("base price total","sum"))
    g["aov"] = g.apply(lambda r: (r["sales"]/r["qty"]) if r["qty"]>0 else 0.0, axis=1)
    g = g.reset_index().rename(columns={"product number":"Style Number"})
    g["platform"] = "TEMU"
    frames.append(g)
if platform in ["SHEIN","BOTH"]:
    df = shein[(shein["order date"]>=start) & (shein["order date"]<=end) & (~shein["order status"].str.lower().eq("customer refunded"))].copy()
    df["qty"] = 1
    g = df.groupby("product description").agg(qty=("qty","sum"), sales=("product price","sum"))
    g["aov"] = g.apply(lambda r: (r["sales"]/r["qty"]) if r["qty"]>0 else 0.0, axis=1)
    g = g.reset_index().rename(columns={"product description":"Style Number"})
    g["platform"] = "SHEIN"
    frames.append(g)

if not frames:
    st.info("데이터가 없습니다.")
    st.stop()

all_df = pd.concat(frames, ignore_index=True)
# 이미지 URL
all_df["image_url"] = all_df["Style Number"].astype(str).apply(lambda x: IMG_MAP.get(x.upper().replace(" ", ""), ""))

# median lines
med_aov = all_df["aov"].median()
med_qty = all_df["qty"].median()

st.caption("점 크기 = 매출, 색상 = 플랫폼")

chart = alt.Chart(all_df).mark_circle(opacity=0.8).encode(
    x=alt.X("aov:Q", title="AOV (평균 판매가)"),
    y=alt.Y("qty:Q", title="판매수량"),
    size=alt.Size("sales:Q", title="매출", legend=None),
    color=alt.Color("platform:N", title="플랫폼"),
    tooltip=["Style Number","platform","qty","aov","sales"]
).properties(height=520)

rule_x = alt.Chart(pd.DataFrame({"aov":[med_aov]})).mark_rule(strokeDash=[4,4], color="#999").encode(x="aov:Q")
rule_y = alt.Chart(pd.DataFrame({"qty":[med_qty]})).mark_rule(strokeDash=[4,4], color="#999").encode(y="qty:Q")

st.altair_chart(chart + rule_x + rule_y, use_container_width=True)

# quadrant tables
all_df["quadrant"] = (
    (all_df["aov"]>=med_aov).map({True:"High AOV", False:"Low AOV"}) + " / " +
    (all_df["qty"]>=med_qty).map({True:"High Qty", False:"Low Qty"})
)

q1, q2 = st.columns(2)
with q1:
    st.markdown("**High AOV / Low Qty (가격 높고 저판매 → 이미지/노출/가성비 점검)**")
    st.dataframe(all_df[all_df["quadrant"].eq("High AOV / Low Qty")][["Style Number","platform","qty","aov","sales"]]
                 .sort_values("aov", ascending=False), use_container_width=True, hide_index=True)
with q2:
    st.markdown("**Low AOV / High Qty (가격 낮고 고판매 → 마진 확인/소폭 인상 검토)**")
    st.dataframe(all_df[all_df["quadrant"].eq("Low AOV / High Qty")][["Style Number","platform","qty","aov","sales"]]
                 .sort_values("qty", ascending=False), use_container_width=True, hide_index=True)

# download
st.download_button(
    "CSV 다운로드",
    data=all_df.to_csv(index=False),
    file_name="price_positioning_map.csv",
    mime="text/csv",
)
