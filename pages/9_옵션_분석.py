# ==========================================
# File: pages/9_옵션_분석.py
# 옵션(색상/사이즈) 단위 분석
# ==========================================
import streamlit as st
import pandas as pd
import re
from dateutil import parser
from collections import defaultdict
import altair as alt

st.set_page_config(page_title="옵션(색상·사이즈) 분석", layout="wide")
st.title("🎯 옵션(색상·사이즈) 분석")

# ---------- Loaders ----------
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
    if "(" in s: s = s.split("(")[0].strip()
    try: return parser.parse(s, fuzzy=True)
    except Exception: return pd.NaT

def parse_sheindate(x):
    try: return pd.to_datetime(str(x), errors="coerce", infer_datetime_format=True)
    except Exception: return pd.NaT

def money_series(s):
    return pd.to_numeric(pd.Series(s).astype(str).str.replace(r"[^0-9.\-]", "", regex=True), errors="coerce")

# ---------- Base data ----------
info  = load_google_sheet("PRODUCT_INFO")
temu  = load_google_sheet("TEMU_SALES")
shein = load_google_sheet("SHEIN_SALES")

IMG_MAP = dict(zip(info.get("product number", pd.Series(dtype=str)).astype(str).str.upper().str.replace(" ", "", regex=False), info.get("image","")))

# normalize dates & numerics
temu["order date"]  = temu["purchase date"].apply(parse_temudate)
shein["order date"] = shein["order processed on"].apply(parse_sheindate)

temu["order item status"] = temu["order item status"].astype(str)
temu["quantity shipped"]  = pd.to_numeric(temu.get("quantity shipped", 0), errors="coerce").fillna(0)
if "base price total" in temu.columns:
    temu["base price total"] = money_series(temu["base price total"]).fillna(0.0)

shein["order status"] = shein["order status"].astype(str)
if "product price" in shein.columns:
    shein["product price"] = money_series(shein["product price"]).fillna(0.0)

# ---------- UI ----------
min_dt = pd.to_datetime(pd.concat([temu["order date"], shein["order date"]]).dropna()).min()
max_dt = pd.to_datetime(pd.concat([temu["order date"], shein["order date"]]).dropna()).max()

c1, c2, c3 = st.columns([1.3, 1, 1])
with c1:
    dr = st.date_input(
        "조회 기간(주문일 기준)",
        value=(max_dt.date() - pd.Timedelta(days=29), max_dt.date()),
        min_value=min_dt.date(), max_value=max_dt.date(),
    )
    start, end = (dr if isinstance(dr, (list, tuple)) else (dr, dr))
    start = pd.to_datetime(start); end = pd.to_datetime(end) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
with c2:
    platform = st.radio("플랫폼", ["TEMU","SHEIN","BOTH"], horizontal=True)
with c3:
    dim = st.selectbox("분석 단위", ["색상", "사이즈", "색상×사이즈"], index=0)

# ---------- Helpers : style key & option extraction ----------
def style_key_from_label(label: str) -> str | None:
    s = str(label).strip().upper().replace(" ", "")
    if not s: return None
    if s in IMG_MAP: return s
    m = STYLE_RE.search(s)
    if m:
        cand = m.group(1)
        if cand in IMG_MAP: return cand
    for k in IMG_MAP.keys():
        if k in s: return k
    return None

def pick_first(df, candidates):
    for c in candidates:
        if c in df.columns: return c
    return None

COLOR_SYNONYM = {
    "blk":"black","bk":"black","black":"black","navy":"navy","nvy":"navy","blu":"blue","blue":"blue",
    "wht":"white","white":"white","ivory":"ivory","ivo":"ivory","gry":"gray","gray":"gray","gr":"gray",
    "beige":"beige","bg":"beige","khaki":"khaki","kha":"khaki","brn":"brown","brown":"brown",
    "pink":"pink","red":"red","wine":"wine","green":"green","grn":"green","orange":"orange","ora":"orange",
}
SIZE_ORDER = ["XS","S","M","L","XL","2XL","3XL","4XL","5XL"]

def norm_color(x:str):
    s = str(x).strip().lower()
    s = re.sub(r"[/,;].*$", "", s)  # "Black/White" -> "Black"
    s = re.sub(r"\s+", "", s)
    return COLOR_SYNONYM.get(s, s or "-")

def norm_size(x:str):
    s = str(x).strip().upper().replace(" ", "")
    # map 1X/2X -> XL/2XL, 3XL etc
    s = s.replace("XXL", "2XL").replace("XXXL","3XL")
    s = s.replace("1X","XL").replace("2X","2XL").replace("3X","3XL")
    # numbers like "L/10" -> "L"
    s = s.split("/")[0]
    # keep common ones, else raw
    return s or "-"

def extract_from_text(text:str, key:str):
    """
    try parse 'Color: Black' / 'Colour= Navy' / 'Size: M' like patterns
    """
    t = str(text)
    if key=="color":
        m = re.search(r"(?i)(?:color|colour)\s*[:=]\s*([A-Za-z\- ]+)", t)
        return norm_color(m.group(1)) if m else "-"
    if key=="size":
        m = re.search(r"(?i)(?:size)\s*[:=]\s*([A-Za-z0-9/ .\-]+)", t)
        return norm_size(m.group(1)) if m else "-"
    return "-"

def add_option_columns(df, is_temu=True):
    # style key
    if is_temu:
        df["style_key"] = df["product number"].astype(str).apply(style_key_from_label)
    else:
        df["style_key"] = df["product description"].astype(str).apply(style_key_from_label)

    # color / size column candidates
    if is_temu:
        ccol = pick_first(df, ["color", "colour", "variation color", "sku color", "product color"])
        scol = pick_first(df, ["size", "sku size", "variation size", "product size"])
        text_col = pick_first(df, ["product description", "seller sku", "product number"])
    else:
        ccol = pick_first(df, ["color", "colour", "variation color", "sku color", "product color"])
        scol = pick_first(df, ["size", "sku size", "variation size", "product size"])
        text_col = pick_first(df, ["product description", "seller sku"])

    # normalize
    if ccol is not None:
        df["color"] = df[ccol].apply(norm_color)
    else:
        df["color"] = df[text_col].apply(lambda x: extract_from_text(x, "color")) if text_col else "-"

    if scol is not None:
        df["size"] = df[scol].apply(norm_size)
    else:
        df["size"] = df[text_col].apply(lambda x: extract_from_text(x, "size")) if text_col else "-"

    return df

# ---------- Filter rows (sold) & add options ----------
T = temu[(temu["order date"]>=start) & (temu["order date"]<=end) &
         (temu["order item status"].str.lower().isin(["shipped","delivered"]))].copy()
T["qty"] = pd.to_numeric(T["quantity shipped"], errors="coerce").fillna(0)
T = add_option_columns(T, is_temu=True)

S = shein[(shein["order date"]>=start) & (shein["order date"]<=end) &
          (~shein["order status"].str.lower().eq("customer refunded"))].copy()
S["qty"] = 1.0
S = add_option_columns(S, is_temu=False)

# ---------- Choose platform ----------
frames = []
if platform in ["TEMU","BOTH"] and not T.empty:
    t = T.dropna(subset=["style_key"]).copy()
    t["sales"] = t.get("base price total", 0.0)
    t["platform"] = "TEMU"
    frames.append(t[["style_key","color","size","qty","sales","platform"]])
if platform in ["SHEIN","BOTH"] and not S.empty:
    s = S.dropna(subset=["style_key"]).copy()
    s["sales"] = s.get("product price", 0.0)
    s["platform"] = "SHEIN"
    frames.append(s[["style_key","color","size","qty","sales","platform"]])

if not frames:
    st.info("표시할 데이터가 없습니다.")
    st.stop()

ALL = pd.concat(frames, ignore_index=True)

# ---------- Aggregate ----------
if dim == "색상":
    grp_cols = ["style_key","color","platform"]
elif dim == "사이즈":
    grp_cols = ["style_key","size","platform"]
else:
    grp_cols = ["style_key","color","size","platform"]

agg = ALL.groupby(grp_cols, dropna=False).agg(qty=("qty","sum"), sales=("sales","sum")).reset_index()
agg["aov"] = agg.apply(lambda r: (r["sales"]/r["qty"]) if r["qty"]>0 else 0.0, axis=1)
agg["image_url"] = agg["style_key"].apply(lambda x: IMG_MAP.get(str(x).upper(), ""))

# ---------- Leaderboard ----------
st.subheader("📋 옵션 리더보드")
display_cols = ["image_url","style_key","platform","qty","sales","aov"]
if "color" in agg.columns: display_cols.insert(2, "color")
if "size" in agg.columns:  display_cols.insert(3, "size")

st.dataframe(
    agg.sort_values(["sales","qty"], ascending=[False, False])[display_cols]
      .rename(columns={
          "image_url":"이미지","style_key":"Style","qty":"Qty",
          "sales":"Sales","aov":"AOV","color":"Color","size":"Size"
      }),
    use_container_width=True, hide_index=True,
    column_config={
        "이미지": st.column_config.ImageColumn("이미지", width="medium"),
        "Sales":  st.column_config.NumberColumn("Sales", format="$%,.2f"),
        "AOV":    st.column_config.NumberColumn("AOV",   format="$%,.2f"),
        "Qty":    st.column_config.NumberColumn("Qty",   format="%,d", step=1),
    }
)

# ---------- Size curve heatmap ----------
if "size" in agg.columns:
    st.subheader("📊 사이즈 커브(Heatmap)")
    # 사이즈 순서 고정
    size_order = SIZE_ORDER + sorted(list(set(agg["size"]) - set(SIZE_ORDER)))
    heat = agg.groupby(["size","platform"]).agg(qty=("qty","sum")).reset_index()
    heat["size"] = pd.Categorical(heat["size"], categories=size_order, ordered=True)
    chart = alt.Chart(heat).mark_rect().encode(
        x=alt.X("size:N", title="Size", sort=size_order),
        y=alt.Y("platform:N", title="Platform"),
        color=alt.Color("qty:Q", title="Qty"),
        tooltip=["platform","size","qty"]
    ).properties(height=160)
    st.altair_chart(chart, use_container_width=True)

# ---------- Color mix ----------
if "color" in agg.columns:
    st.subheader("🎨 컬러 믹스")
    col_mix = agg.groupby(["color","platform"]).agg(qty=("qty","sum")).reset_index()
    bars = alt.Chart(col_mix).mark_bar().encode(
        x=alt.X("qty:Q", title="Qty"), y=alt.Y("color:N", title=None, sort="-x"),
        color=alt.Color("platform:N", title="Platform"),
        tooltip=["platform","color","qty"]
    ).properties(height=380)
    st.altair_chart(bars, use_container_width=True)

# ---------- Download ----------
st.download_button(
    "CSV 다운로드 (옵션 리더보드)",
    data=agg.to_csv(index=False),
    file_name="option_analysis.csv",
    mime="text/csv",
)
