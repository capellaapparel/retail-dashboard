# ==========================================
# File: pages/9_옵션_카테고리_분석.py
# ==========================================
import streamlit as st
import pandas as pd
import re
from collections import defaultdict
from dateutil import parser

st.set_page_config(page_title="옵션 · 카테고리 분석", layout="wide")
st.title("🧩 옵션 · 카테고리 분석")

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
    if "(" in s:
        s = s.split("(")[0].strip()
    try: return parser.parse(s, fuzzy=True)
    except Exception: return pd.NaT

def parse_sheindate(x):
    try: return pd.to_datetime(str(x), errors="coerce", infer_datetime_format=True)
    except Exception: return pd.NaT

def norm_size(v: str) -> str:
    if v is None: return ""
    s = str(v).strip().upper().replace(" ", "")
    # XL 변형 먼저
    s = s.replace("1XL", "1X").replace("2XL", "2X").replace("3XL", "3X")
    # 단어형
    s = s.replace("SMALL", "S").replace("MEDIUM", "M").replace("LARGE", "L")
    s = s.replace("XLARGE", "XL").replace("X-LARGE", "XL")
    return s

def norm_color(v: str) -> str:
    if v is None: return ""
    s = str(v).replace("_", " ").strip()
    return s.title()

def style_key_from_any(label: str) -> str | None:
    s = str(label).strip().upper()
    if not s:
        return None
    s_key = s.replace(" ", "")
    m = STYLE_RE.search(s)
    return m.group(1).replace(" ", "") if m else s_key

# -------------------------
# Load data
# -------------------------
info  = load_google_sheet("PRODUCT_INFO")
temu  = load_google_sheet("TEMU_SALES")
shein = load_google_sheet("SHEIN_SALES")

# images
IMG_MAP = dict(zip(
    info.get("product number", pd.Series(dtype=str)).astype(str).str.upper().str.replace(" ", "", regex=False),
    info.get("image","")
))

# normalize dates
temu["order date"]  = temu["purchase date"].apply(parse_temudate)
shein["order date"] = shein["order processed on"].apply(parse_sheindate)

# numeric cleanup
def money_series(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s.astype(str).str.replace(r"[^0-9.\-]", "", regex=True), errors="coerce").fillna(0.0)

temu["quantity shipped"]  = pd.to_numeric(temu.get("quantity shipped", 0), errors="coerce").fillna(0)
temu["order item status"] = temu["order item status"].astype(str)
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

r1, r2 = st.columns([1.4, 1])
with r1:
    dr = st.date_input(
        "조회 기간",
        value=(max_dt.date()-pd.Timedelta(days=29), max_dt.date()),
        min_value=min_dt.date(),
        max_value=max_dt.date(),
    )
    if isinstance(dr,(list,tuple)):
        start, end = dr
    else:
        start, end = dr, dr
    start = pd.to_datetime(start); end = pd.to_datetime(end) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
with r2:
    platform = st.radio("플랫폼", ["BOTH","TEMU","SHEIN"], horizontal=True)

# -------------------------
# Filter sold rows
# -------------------------
T = temu[(temu["order item status"].str.lower().isin(["shipped","delivered"])) &
         (temu["order date"]>=start) & (temu["order date"]<=end)].copy()
T["qty"] = pd.to_numeric(T["quantity shipped"], errors="coerce").fillna(0)

S = shein[(~shein["order status"].str.lower().eq("customer refunded")) &
          (shein["order date"]>=start) & (shein["order date"]<=end)].copy()
S["qty"] = 1.0

# -------------------------
# Option parsing
# -------------------------
# TEMU: product number / color / size
T["style_key"] = T["product number"].astype(str).apply(style_key_from_any)
T["color_opt"] = T.get("color", "").astype(str).apply(norm_color)
T["size_opt"]  = T.get("size", "").astype(str).apply(norm_size)

# SHEIN: seller sku => SKU-COLOR-SIZE
def split_shein_sku(x):
    s = str(x).strip()
    if "-" not in s:
        return "", "", ""
    parts = s.split("-")
    if len(parts) < 3:
        # 최대한 보수적으로: 첫/끝을 스타일/사이즈, 가운데를 컬러
        sku   = parts[0]
        size  = parts[-1]
        color = "-".join(parts[1:-1])
    else:
        sku   = parts[0]
        size  = parts[-1]
        color = "-".join(parts[1:-1])
    return sku, color, size

if "seller sku" in S.columns:
    sku_col = "seller sku"
elif "seller_sku" in S.columns:
    sku_col = "seller_sku"
else:
    sku_col = None

if sku_col:
    tmp = S[sku_col].apply(split_shein_sku)
    S["style_key"] = tmp.apply(lambda t: style_key_from_any(t[0]))
    S["color_opt"] = tmp.apply(lambda t: norm_color(t[1]))
    S["size_opt"]  = tmp.apply(lambda t: norm_size(t[2]))
else:
    # 폴백: product description에서 스타일만, 옵션은 빈값
    S["style_key"] = S["product description"].astype(str).apply(style_key_from_any)
    S["color_opt"] = ""
    S["size_opt"]  = ""

# -------------------------
# Category mapping
# -------------------------
LEN = dict(zip(
    info.get("product number", pd.Series(dtype=str)).astype(str).str.upper().str.replace(" ", "", regex=False),
    info.get("length", "")
))

def get_length(style_key):
    return str(LEN.get(str(style_key).upper().replace(" ", ""), "")).strip()

def is_set(length_str: str) -> bool:
    return str(length_str).lower().startswith("sets")

TOP_SET   = {"crop top","waist top","long top"}
DRESS_SET = {"mini dress","midi dress","maxi dress"}
SKIRT_SET = {"mini skirt","midi skirt","maxi skirt"}
PANTS_SET = {"shorts","knee","capri","full"}  # 하의 길이 키워드

# 텍스트로 하위 분류 (romper/jumpsuit)
def bottom_sub_by_temutext(style_key: str) -> str:
    rows = T[T["style_key"].eq(style_key)]
    # TEMU 텍스트 컬럼 이름 맞추기
    col_candidates = [
        "product name by customer order",
        "product name",
        "product description",
    ]
    text = " ".join([
        str(rows.get(c,"")).upper()
        for c in col_candidates if c in rows.columns
    ])
    if "ROMPER" in text:
        return "ROMPER"
    if "JUMPSUIT" in text:
        return "JUMPSUIT"
    return "PANTS"

def map_category(style_key: str) -> str:
    length = get_length(style_key)
    low = length.lower()
    if not length:
        return "OTHER"
    if is_set(length):
        return "SET"
    if low in TOP_SET:
        return "TOP"
    if low in SKIRT_SET:
        return "SKIRT"
    if low in DRESS_SET:
        return "DRESS"
    if low in PANTS_SET:
        return bottom_sub_by_temutext(style_key)
    # length 문구가 dress/ skirt 포함
    if "dress" in low:
        return "DRESS"
    if "skirt" in low:
        return "SKIRT"
    if "top" in low:
        return "TOP"
    # 마지막 폴백
    return bottom_sub_by_temutext(style_key)

# 스타일→카테고리 캐시
CAT_CACHE = {}
def cat_of(style_key: str) -> str:
    if style_key not in CAT_CACHE:
        CAT_CACHE[style_key] = map_category(style_key)
    return CAT_CACHE[style_key]

T["cat"] = T["style_key"].apply(cat_of)
S["cat"] = S["style_key"].apply(cat_of)

# -------------------------
# Category summary
# -------------------------
frames = []
if platform in ["BOTH","TEMU"]:
    tg = T.groupby("cat").agg(qty=("qty","sum"), sales=("base price total","sum")).reset_index()
    tg["aov"] = tg.apply(lambda r: (r["sales"]/r["qty"]) if r["qty"]>0 else 0.0, axis=1)
    tg["platform"] = "TEMU"
    frames.append(tg)
if platform in ["BOTH","SHEIN"]:
    sg = S.groupby("cat").agg(qty=("qty","sum"), sales=("product price","sum")).reset_index()
    sg["aov"] = sg.apply(lambda r: (r["sales"]/r["qty"]) if r["qty"]>0 else 0.0, axis=1)
    sg["platform"] = "SHEIN"
    frames.append(sg)

if not frames:
    st.info("데이터가 없습니다.")
    st.stop()

summary = pd.concat(frames, ignore_index=True)
summary = summary[["platform","cat","qty","sales","aov"]].sort_values(["platform","sales"], ascending=[True, False])

st.subheader("📊 카테고리별 성과 요약")
st.dataframe(summary, use_container_width=True, hide_index=True)

# -------------------------
# Category Top Styles (by sales)
# -------------------------
st.subheader("🏆 카테고리별 Top Styles (매출순)")

cats = sorted(summary["cat"].unique().tolist())
sel = st.multiselect("카테고리 선택", cats, default=cats)

topN = st.slider("Top N", 5, 30, 10, 1)

def agg_style(df: pd.DataFrame, plat: str):
    if plat == "TEMU":
        g = df.groupby("style_key").agg(
            qty=("qty","sum"),
            sales=("base price total","sum")
        ).reset_index()
    else:
        g = df.groupby("style_key").agg(
            qty=("qty","sum"),
            sales=("product price","sum")
        ).reset_index()
    g["aov"] = g.apply(lambda r: (r["sales"]/r["qty"]) if r["qty"]>0 else 0.0, axis=1)
    g["platform"] = plat
    return g

sub_frames = []
if platform in ["BOTH","TEMU"]:
    sub_frames.append( agg_style(T[T["cat"].isin(sel)], "TEMU") )
if platform in ["BOTH","SHEIN"]:
    sub_frames.append( agg_style(S[S["cat"].isin(sel)], "SHEIN") )

if sub_frames:
    top_all = pd.concat(sub_frames, ignore_index=True)
    # 이미지 붙이기
    top_all["image_url"] = top_all["style_key"].apply(lambda x: IMG_MAP.get(str(x).upper().replace(" ",""), ""))
    top_all = top_all.sort_values("sales", ascending=False).head(topN)

    show = top_all.rename(columns={
        "style_key":"Style Number",
        "qty":"Qty", "sales":"Sales", "aov":"AOV"
    })[["image_url","platform","Style Number","Qty","Sales","AOV"]]

    st.dataframe(
        show,
        use_container_width=True,
        hide_index=True,
        column_config={
            "image_url": st.column_config.ImageColumn("이미지", width="large"),
            "Qty":   st.column_config.NumberColumn("Qty",   format="%,d", step=1),
            "Sales": st.column_config.NumberColumn("Sales", format="$%,.2f", step=0.01),
            "AOV":   st.column_config.NumberColumn("AOV",   format="$%,.2f", step=0.01),
        }
    )
else:
    st.info("선택된 카테고리에 데이터가 없습니다.")

# -------------------------
# Option drilldown (Color/Size)
# -------------------------
st.subheader("🔎 옵션 상세 (Color · Size)")

opt_tabs = st.tabs(["TEMU", "SHEIN"])

with opt_tabs[0]:
    if platform in ["BOTH","TEMU"]:
        tt = T.copy()
        g = tt.groupby(["style_key","color_opt","size_opt"]).agg(
            qty=("qty","sum"),
            sales=("base price total","sum")
        ).reset_index().sort_values("sales", ascending=False)
        g = g.rename(columns={
            "style_key":"Style Number",
            "color_opt":"Color",
            "size_opt":"Size",
            "qty":"Qty","sales":"Sales"
        })
        st.dataframe(
            g,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Qty":   st.column_config.NumberColumn("Qty",   format="%,d", step=1),
                "Sales": st.column_config.NumberColumn("Sales", format="$%,.2f", step=0.01),
            }
        )
    else:
        st.caption("TEMU 데이터 비활성화")

with opt_tabs[1]:
    if platform in ["BOTH","SHEIN"]:
        ss = S.copy()
        g = ss.groupby(["style_key","color_opt","size_opt"]).agg(
            qty=("qty","sum"),
            sales=("product price","sum")
        ).reset_index().sort_values("sales", ascending=False)
        g = g.rename(columns={
            "style_key":"Style Number",
            "color_opt":"Color",
            "size_opt":"Size",
            "qty":"Qty","sales":"Sales"
        })
        st.dataframe(
            g,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Qty":   st.column_config.NumberColumn("Qty",   format="%,d", step=1),
                "Sales": st.column_config.NumberColumn("Sales", format="$%,.2f", step=0.01),
            }
        )
    else:
        st.caption("SHEIN 데이터 비활성화")
