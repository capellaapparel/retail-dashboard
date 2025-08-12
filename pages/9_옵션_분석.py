# ==========================================
# File: pages/9_옵션_분석.py
# 옵션(색상/사이즈) 단위 교차 플랫폼 성과 분석
# ==========================================
import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
import re
from dateutil import parser

st.set_page_config(page_title="옵션(색상/사이즈) 분석", layout="wide")
st.title("🧩 옵션(색상·사이즈) 성과 분석")

# -------------------------
# Helpers
# -------------------------
@st.cache_data(show_spinner=False)
def load_google_sheet(sheet_name: str) -> pd.DataFrame:
    import gspread
    from oauth2client.service_account import ServiceAccountCredentials
    import json
    GOOGLE_SHEET_URL = "https://docs.google.com/spreadsheets/d/1oyVzCgGK1Q3Qi_sbYwE-wKG6SArnfUDRe7rQfGOF-Eo"
    scope = ["https://spreadsheets.google.com/feeds","https://www.googleapis.com/auth/drive"]
    creds_json = {k: str(v) for k, v in st.secrets["gcp_service_account"].items()}
    with open("/tmp/service_account.json","w") as f:
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
    if "(" in s: s = s.split("(")[0].strip()
    try: return parser.parse(s, fuzzy=True)
    except Exception: return pd.NaT

def parse_sheindate(x):
    try: return pd.to_datetime(str(x), errors="coerce", infer_datetime_format=True)
    except Exception: return pd.NaT

def build_img_map(df_info: pd.DataFrame):
    keys = df_info.get("product number", pd.Series(dtype=str)).astype(str).str.upper().str.replace(" ", "", regex=False)
    return dict(zip(keys, df_info.get("image","")))

def to_style_key(s: str) -> str | None:
    if not s: return None
    s = str(s).upper().replace(" ", "")
    m = STYLE_RE.search(s)
    return (m.group(1) if m else s) if s else None

# ----- 옵션 정규화 -----
def norm_color(s: str) -> str:
    if pd.isna(s) or str(s).strip()=="":
        return ""
    s = str(s).strip()
    s = s.replace("_", " ")
    # 너무 공격적으로 대문자화하지 않고 Title case
    return " ".join([w.capitalize() for w in s.split()])

_SIZE_MAP = {
    "1XL":"1X", "1-XL":"1X", "1 X":"1X", "1X":"1X",
    "2XL":"2X", "2-XL":"2X", "2 X":"2X", "2X":"2X",
    "3XL":"3X", "3-XL":"3X", "3 X":"3X", "3X":"3X",
    "SMALL":"S", "SM":"S",
    "MEDIUM":"M", "MD":"M", "M":"M",
    "LARGE":"L", "LG":"L", "L":"L"
}
def norm_size(s: str) -> str:
    if pd.isna(s) or str(s).strip()=="":
        return ""
    x = str(s).strip().upper().replace(".", "").replace("  ", " ")
    x = x.replace("-", "-")  # 그대로 두지만 매핑에서 커버
    # 공백 패턴도 매핑에서 커버
    return _SIZE_MAP.get(x, x)

# SHEIN Seller SKU 파서: STYLE-COLOR-SIZE (COLOR가 여러 토큰이면 중간을 모두 color로)
def parse_shein_sku(s: str):
    if not s or str(s).strip()=="":
        return None, "", ""
    parts = str(s).strip().split("-")
    if len(parts) < 3:
        return to_style_key(parts[0]) if parts else None, "", ""
    style = to_style_key(parts[0])
    size  = norm_size(parts[-1])
    color_mid = "-".join(parts[1:-1])  # 가운데는 color(하이픈 포함)
    color = norm_color(color_mid)
    return style, color, size

def money_series(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s.astype(str).str.replace(r"[^0-9.\-]","", regex=True), errors="coerce").fillna(0.0)

# -------------------------
# Load
# -------------------------
info  = load_google_sheet("PRODUCT_INFO")
temu  = load_google_sheet("TEMU_SALES")
shein = load_google_sheet("SHEIN_SALES")

IMG_MAP = build_img_map(info)

# 날짜/수치 정규화
temu["order date"]  = temu["purchase date"].apply(parse_temudate)
shein["order date"] = shein["order processed on"].apply(parse_sheindate)

temu["order item status"] = temu["order item status"].astype(str)
temu["quantity shipped"]  = pd.to_numeric(temu.get("quantity shipped", 0), errors="coerce").fillna(0)
if "base price total" in temu.columns:
    temu["base price total"] = money_series(temu["base price total"])

shein["order status"]   = shein["order status"].astype(str)
if "product price" in shein.columns:
    shein["product price"] = money_series(shein["product price"])

# -------------------------
# Controls
# -------------------------
min_dt = pd.to_datetime(pd.concat([temu["order date"], shein["order date"]]).dropna()).min()
max_dt = pd.to_datetime(pd.concat([temu["order date"], shein["order date"]]).dropna()).max()

c1, c2, c3 = st.columns([1.4, 1, 1])
with c1:
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
with c2:
    platform = st.radio("플랫폼", ["BOTH","TEMU","SHEIN"], horizontal=True)
with c3:
    group_mode = st.selectbox("그룹 기준", ["Color+Size","Color","Size"])

style_filter = st.text_input("스타일 번호(선택, 포함검색)", "")

# -------------------------
# Build normalized option rows (per platform)
# -------------------------
rows = []

# TEMU: product number + color + size
if platform in ["BOTH","TEMU"]:
    t = temu[(temu["order item status"].str.lower().isin(["shipped","delivered"])) &
             (temu["order date"]>=start) & (temu["order date"]<=end)].copy()
    t["style"] = t.get("product number", "").astype(str).map(to_style_key)
    t["color"] = t.get("color", "").astype(str).map(norm_color) if "color" in t.columns else ""
    t["size"]  = t.get("size", "").astype(str).map(norm_size) if "size" in t.columns else ""
    if style_filter.strip():
        t = t[t["style"].astype(str).str.contains(style_filter.strip().upper().replace(" ",""), na=False)]
    for _, r in t.iterrows():
        rows.append({
            "platform":"TEMU",
            "style": r["style"],
            "color": r.get("color",""),
            "size":  r.get("size",""),
            "qty":   float(r.get("quantity shipped",0)),
            "sales": float(r.get("base price total",0.0)),
            "date":  r.get("order date")
        })

# SHEIN: Seller SKU = STYLE-COLOR-SIZE
if platform in ["BOTH","SHEIN"]:
    s = shein[(~shein["order status"].str.lower().eq("customer refunded")) &
              (shein["order date"]>=start) & (shein["order date"]<=end)].copy()
    # parse seller sku 우선
    if "seller sku" in s.columns:
        parsed = s["seller sku"].apply(parse_shein_sku)
        s["style"] = parsed.apply(lambda x: x[0])
        s["color"] = parsed.apply(lambda x: x[1])
        s["size"]  = parsed.apply(lambda x: x[2])
    else:
        # fallback: style은 description에서, color/size는 빈값
        s["style"] = s.get("product description","").astype(str).map(to_style_key)
        s["color"] = ""
        s["size"]  = ""
    if style_filter.strip():
        s = s[s["style"].astype(str).str.contains(style_filter.strip().upper().replace(" ",""), na=False)]
    for _, r in s.iterrows():
        rows.append({
            "platform":"SHEIN",
            "style": r.get("style"),
            "color": r.get("color",""),
            "size":  r.get("size",""),
            "qty":   1.0,
            "sales": float(r.get("product price",0.0)),
            "date":  r.get("order date")
        })

df = pd.DataFrame(rows)
if df.empty:
    st.info("선택 조건에 해당하는 옵션 데이터가 없습니다.")
    st.stop()

# 그룹 키 결정
def group_key(row):
    if group_mode == "Color": 
        return (row["style"], row["color"])
    if group_mode == "Size":
        return (row["style"], row["size"])
    return (row["style"], row["color"], row["size"])

df["gkey"] = df.apply(group_key, axis=1)

# 플랫폼별 집계
g = df.groupby(["platform","gkey"]).agg(qty=("qty","sum"), sales=("sales","sum")).reset_index()
g["aov"] = g.apply(lambda r: (r["sales"]/r["qty"]) if r["qty"]>0 else 0.0, axis=1)

# wide화
def expand_keys(s):
    # gkey 튜플 → style / color / size 열로 분해
    if isinstance(s, tuple):
        if len(s)==2:  # (style, color) or (style, size)
            return pd.Series({"style":s[0], "p2":s[1], "p3":""})
        elif len(s)==3:
            return pd.Series({"style":s[0], "p2":s[1], "p3":s[2]})
    return pd.Series({"style":None,"p2":"","p3":""})

exp = g["gkey"].apply(expand_keys)
gg = pd.concat([g.drop(columns=["gkey"]), exp], axis=1)

# 컬럼 레이블
if group_mode == "Color":
    gg = gg.rename(columns={"p2":"Color", "p3":"Size"})
elif group_mode == "Size":
    gg = gg.rename(columns={"p2":"Size", "p3":"Color"})
else:
    gg = gg.rename(columns={"p2":"Color", "p3":"Size"})

# 플랫폼별로 피벗해 합치기
temu_w  = gg[gg["platform"].eq("TEMU")].drop(columns=["platform"])
shein_w = gg[gg["platform"].eq("SHEIN")].drop(columns=["platform"])

temu_w  = temu_w.rename(columns={"qty":"TEMU_Qty", "sales":"TEMU_Sales", "aov":"TEMU_AOV"})
shein_w = shein_w.rename(columns={"qty":"SHEIN_Qty","sales":"SHEIN_Sales","aov":"SHEIN_AOV"})

combined = pd.merge(temu_w, shein_w, on=["style",*(["Color"] if "Color" in gg.columns else []),*(["Size"] if "Size" in gg.columns else [])], how="outer")
for c in ["TEMU_Qty","TEMU_Sales","TEMU_AOV","SHEIN_Qty","SHEIN_Sales","SHEIN_AOV"]:
    if c not in combined.columns:
        combined[c] = 0.0

# 총합 및 AOV
combined["Total_Qty"]   = combined["TEMU_Qty"].fillna(0)+combined["SHEIN_Qty"].fillna(0)
combined["Total_Sales"] = combined["TEMU_Sales"].fillna(0)+combined["SHEIN_Sales"].fillna(0)
combined["Total_AOV"]   = combined.apply(lambda r: (r["Total_Sales"]/r["Total_Qty"]) if r["Total_Qty"]>0 else 0.0, axis=1)

# 이미지/스타일 표시
combined["Style Number"] = combined["style"]
combined["이미지"] = combined["Style Number"].astype(str).apply(lambda x: IMG_MAP.get(str(x).upper().replace(" ",""), ""))

# 정렬: 총매출 desc
combined = combined.sort_values("Total_Sales", ascending=False).reset_index(drop=True)

# -------------------------
# KPIs
# -------------------------
with st.container(border=True):
    c1, c2, c3, c4 = st.columns(4)
    with c1: st.metric("분석 옵션 수", f"{combined.shape[0]:,}")
    with c2: st.metric("총 판매수량", f"{int(combined['Total_Qty'].sum()):,}")
    with c3: st.metric("총 매출", f"${combined['Total_Sales'].sum():,.2f}")
    with c4: st.metric("평균 AOV", f"${(combined['Total_Sales'].sum()/combined['Total_Qty'].sum() if combined['Total_Qty'].sum()>0 else 0):,.2f}")

# -------------------------
# 표 출력
# -------------------------
show_cols = ["이미지","Style Number"]
if "Color" in combined.columns: show_cols.append("Color")
if "Size"  in combined.columns: show_cols.append("Size")
show_cols += ["TEMU_Qty","TEMU_Sales","TEMU_AOV","SHEIN_Qty","SHEIN_Sales","SHEIN_AOV","Total_Qty","Total_Sales","Total_AOV"]

st.dataframe(
    combined[show_cols],
    use_container_width=True,
    hide_index=True,
    column_config={
        "이미지": st.column_config.ImageColumn("이미지", width="large"),
        "TEMU_Qty":   st.column_config.NumberColumn("TEMU_Qty",   format="%,d",   step=1),
        "SHEIN_Qty":  st.column_config.NumberColumn("SHEIN_Qty",  format="%,d",   step=1),
        "TEMU_Sales": st.column_config.NumberColumn("TEMU_Sales", format="$%,.2f",step=0.01),
        "SHEIN_Sales":st.column_config.NumberColumn("SHEIN_Sales",format="$%,.2f",step=0.01),
        "TEMU_AOV":   st.column_config.NumberColumn("TEMU_AOV",   format="$%,.2f",step=0.01),
        "SHEIN_AOV":  st.column_config.NumberColumn("SHEIN_AOV",  format="$%,.2f",step=0.01),
        "Total_Qty":  st.column_config.NumberColumn("Total_Qty",  format="%,d",   step=1),
        "Total_Sales":st.column_config.NumberColumn("Total_Sales",format="$%,.2f",step=0.01),
        "Total_AOV":  st.column_config.NumberColumn("Total_AOV",  format="$%,.2f",step=0.01),
    }
)

# -------------------------
# 선택 스타일 heatmap (Color x Size)
# -------------------------
sel_style = st.selectbox("Heatmap용 스타일 선택(선택)", ["(선택 안함)"] + sorted(combined["Style Number"].dropna().astype(str).unique().tolist()))
if sel_style and sel_style != "(선택 안함)":
    sub = combined[combined["Style Number"].astype(str).eq(sel_style)].copy()
    if {"Color","Size"}.issubset(sub.columns):
        heat = sub.pivot_table(index="Size", columns="Color", values="Total_Qty", aggfunc="sum", fill_value=0.0)
        heat_df = heat.reset_index().melt(id_vars="Size", var_name="Color", value_name="Qty")
        chart = alt.Chart(heat_df).mark_rect().encode(
            x=alt.X("Color:N", sort="ascending"),
            y=alt.Y("Size:N",  sort="ascending"),
            color=alt.Color("Qty:Q", scale=alt.Scale(scheme="blues")),
            tooltip=["Color","Size","Qty"]
        ).properties(height=360)
        st.subheader(f"🧮 {sel_style} · Color × Size 판매수량 Heatmap")
        st.altair_chart(chart, use_container_width=True)
    else:
        st.info("Heatmap은 Color와 Size 두 차원이 모두 있을 때 표시됩니다.")

# -------------------------
# Download
# -------------------------
st.download_button(
    "CSV 다운로드",
    data=combined[show_cols].to_csv(index=False),
    file_name="option_performance.csv",
    mime="text/csv",
)
