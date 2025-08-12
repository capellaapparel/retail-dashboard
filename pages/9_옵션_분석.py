# ==========================================
# File: pages/9_옵션_카테고리_분석.py
# ==========================================
import streamlit as st
import pandas as pd
import re
from dateutil import parser

st.set_page_config(page_title="옵션/카테고리 분석", layout="wide")
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

def money_series(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s.astype(str).str.replace(r"[^0-9.\-]", "", regex=True), errors="coerce").fillna(0.0)

# 스타일 키 통일(공백 제거 + 대문자)
def norm_style(s) -> str:
    return str(s).upper().replace(" ", "")

# Size 표준화(주신 등가 매핑)
SIZE_MAP = {
    "1XL":"1X","2XL":"2X","3XL":"3X",
    "SMALL":"S","MEDIUM":"M","LARGE":"L",
    "S":"S","M":"M","L":"L","XL":"XL","XXL":"2X","XXXL":"3X","1X":"1X","2X":"2X","3X":"3X"
}

def norm_size(x: str) -> str:
    s = str(x).strip().upper()
    return SIZE_MAP.get(s, s)

def norm_color(x: str) -> str:
    # SHEIN 색상은 언더스코어로 공백 대체 → 복원
    s = str(x).strip().replace("_", " ")
    return s.title()

# 카테고리 매핑(기본: PRODUCT_INFO.length)
TOP_TAGS    = {"crop top","waist top","long top","top"}
DRESS_TAGS  = {"mini dress","midi dress","maxi dress","dress"}
SKIRT_TAGS  = {"mini skirt","midi skirt","maxi skirt","skirt"}
BOTTOM_TAGS = {"shorts","knee","capri","full","pants","bottom"}  # pants/shorts류

def base_category_from_length(length_val: str) -> str | None:
    s = str(length_val).strip().lower()
    if not s or s in {"nan","none","-"}:
        return None
    if "set" in s:
        return "SET"
    if any(t in s for t in TOP_TAGS):
        return "TOP"
    if any(t in s for t in DRESS_TAGS):
        return "DRESS"
    if any(t in s for t in SKIRT_TAGS):
        return "SKIRT"
    if any(t in s for t in BOTTOM_TAGS):
        # BOTTOM은 뒤에서 ROMPER/JUMPSUIT 감지로 세분화
        return "BOTTOM"
    return None

# TEMU product name에서 ROMPER/JUMPSUIT 감지
def refine_bottom_with_name(base_cat: str, name_text: str) -> str:
    if base_cat != "BOTTOM":
        return base_cat
    s = str(name_text).lower()
    if "romper" in s:
        return "ROMPER"
    if "jumpsuit" in s:
        return "JUMPSUIT"
    return "PANTS"   # 그 외 바텀류는 PANTS로

# SHEIN Seller SKU 파싱: 'SKU-COLOR-SIZE' (하이픈으로 구분, 컬러는 '_' → ' ')
def parse_shein_sku(sku: str) -> tuple[str,str,str]:
    raw = str(sku)
    parts = raw.split("-")
    if len(parts) >= 3:
        sz  = norm_size(parts[-1])
        col = norm_color("-".join(parts[1:-1]))  # 컬러에 '-'가 포함될 수 있어 중간부 합침
        sty = norm_style(parts[0])
        return sty, col, sz
    # fallback
    return norm_style(raw), "", ""

# -------------------------
# Load sheets
# -------------------------
info  = load_google_sheet("PRODUCT_INFO")
temu  = load_google_sheet("TEMU_SALES")
shein = load_google_sheet("SHEIN_SALES")

# Precompute style→length/category, image
info["style_key"] = info["product number"].astype(str).map(norm_style)
INFO_LEN_MAP  = dict(zip(info["style_key"], info.get("length","")))
IMG_MAP       = dict(zip(info["style_key"], info.get("image","")))

# -------------------------
# Normalize sales rows
# -------------------------
# TEMU
temu["order date"]  = temu["purchase date"].apply(parse_temudate)
temu["order item status"] = temu["order item status"].astype(str)
temu["quantity shipped"]  = pd.to_numeric(temu.get("quantity shipped", 0), errors="coerce").fillna(0)
if "base price total" in temu.columns:
    temu["base price total"] = money_series(temu["base price total"])

temu["style_key"] = temu["product number"].astype(str).map(norm_style)
temu["color_norm"] = temu.get("color","").astype(str).apply(norm_color)
temu["size_norm"]  = temu.get("size","").astype(str).apply(norm_size)

# SHEIN
shein["order date"] = shein["order processed on"].apply(parse_sheindate)
shein["order status"] = shein["order status"].astype(str)
if "product price" in shein.columns:
    shein["product price"] = money_series(shein["product price"])

# Seller SKU → style/color/size
sty, col, sz = zip(*shein.get("seller sku", "").astype(str).apply(parse_shein_sku))
shein["style_key"] = list(sty)
shein["color_norm"] = list(col)
shein["size_norm"]  = list(sz)

# -------------------------
# Controls
# -------------------------
min_dt = pd.to_datetime(pd.concat([temu["order date"], shein["order date"]]).dropna()).min()
max_dt = pd.to_datetime(pd.concat([temu["order date"], shein["order date"]]).dropna()).max()

c1, c2 = st.columns([1.4,1])
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

# 기간 & 상태 필터
t = temu[(temu["order date"]>=start)&(temu["order date"]<=end)&
         (temu["order item status"].str.lower().isin(["shipped","delivered"]))].copy()
t["qty"] = t["quantity shipped"]
t["sales"] = t.get("base price total", 0.0)

s = shein[(shein["order date"]>=start)&(shein["order date"]<=end)&
          (~shein["order status"].str.lower().eq("customer refunded"))].copy()
s["qty"] = 1.0
s["sales"] = s.get("product price", 0.0)

# 선택 플랫폼 적용
frames = []
if platform in ["BOTH","TEMU"]:  frames.append(t.assign(platform="TEMU"))
if platform in ["BOTH","SHEIN"]: frames.append(s.assign(platform="SHEIN"))
if not frames:
    st.info("데이터가 없습니다.")
    st.stop()
sales_df = pd.concat(frames, ignore_index=True)

# -------------------------
# Category classification per row
# -------------------------
# 1) 기본: PRODUCT_INFO.length → base category
sales_df["base_cat"] = sales_df["style_key"].map(lambda k: base_category_from_length(INFO_LEN_MAP.get(k, "")))

# 2) TEMU: product name에서 ROMPER/JUMPSUIT 감지해 BOTTOM 세분화
name_col = "product name by customer order" if "product name by customer order" in sales_df.columns else ""
if name_col:
    sales_df["cat"] = [
        refine_bottom_with_name(bc, nm) if plat=="TEMU" else (bc if bc!="BOTTOM" else "PANTS")
        for bc, nm, plat in zip(sales_df["base_cat"], sales_df[name_col], sales_df["platform"])
    ]
else:
    # TEMU name이 없으면 BOTTOM → PANTS 로
    sales_df["cat"] = sales_df["base_cat"].apply(lambda x: "PANTS" if x=="BOTTOM" else x)

# 없거나 미분류 → OTHER
sales_df["cat"] = sales_df["cat"].fillna("OTHER")

# 이미지 URL
sales_df["image"] = sales_df["style_key"].map(IMG_MAP)

# -------------------------
# Category Summary
# -------------------------
cat_sum = (sales_df.groupby(["platform","cat"])
           .agg(qty=("qty","sum"), sales=("sales","sum"))
           .reset_index())
cat_sum["aov"] = cat_sum.apply(lambda r: (r["sales"]/r["qty"]) if r["qty"]>0 else 0.0, axis=1)

st.subheader("📊 카테고리별 성과 요약")
st.dataframe(
    cat_sum.sort_values(["platform","sales"], ascending=[True,False]),
    use_container_width=True,
    hide_index=True
)

# -------------------------
# Top Styles by Category
# -------------------------
st.subheader("🏆 카테고리별 Top Styles (매출순)")
sel_cats = st.multiselect(
    "카테고리 선택",
    options=sorted(cat_sum["cat"].unique().tolist()),
    default=sorted(cat_sum["cat"].unique().tolist())
)

if sel_cats:
    topn = st.slider("Top N", 3, 20, 10, 1)
    filt = sales_df[sales_df["cat"].isin(sel_cats)]

    # 스타일 레벨 집계
    g = (filt.groupby(["platform","cat","style_key","image"])
         .agg(qty=("qty","sum"), sales=("sales","sum"))
         .reset_index())
    g["aov"] = g.apply(lambda r: (r["sales"]/r["qty"]) if r["qty"]>0 else 0.0, axis=1)

    # 카테고리·플랫폼마다 Top N
    blocks = []
    for (plat, cat), sub in g.groupby(["platform","cat"]):
        sub2 = sub.sort_values("sales", ascending=False).head(topn).copy()
        sub2.insert(0, "platform", plat)
        sub2.insert(1, "cat", cat)
        blocks.append(sub2)
    if blocks:
        tops = pd.concat(blocks, ignore_index=True)
        # 썸네일 크게 표시
        st.markdown("""
        <style>
        [data-testid="stDataFrame"] img { height: 96px !important; width: 96px !important; object-fit: cover; border-radius: 8px; }
        </style>
        """, unsafe_allow_html=True)
        st.dataframe(
            tops.rename(columns={"style_key":"Style Number","image":"이미지"}),
            use_container_width=True, hide_index=True,
            column_config={
                "이미지": st.column_config.ImageColumn("이미지", width="medium"),
                "qty":    st.column_config.NumberColumn("Qty",    format="%,.0f"),
                "sales":  st.column_config.NumberColumn("Sales",  format="$%,.2f"),
                "aov":    st.column_config.NumberColumn("AOV",    format="$%,.2f"),
            }
        )
    else:
        st.info("선택한 카테고리에 데이터가 없습니다.")

# -------------------------
# 옵션(색상/사이즈) 브레이크다운 (선택)
# -------------------------
st.subheader("🎨 색상 · 🧵 사이즈 분포 (선택 카테고리)")
with st.expander("열기/닫기", expanded=False):
    opt_cats = st.multiselect(
        "카테고리 선택 (옵션 분포)",
        options=sorted(cat_sum["cat"].unique().tolist()),
        default=sorted(cat_sum["cat"].unique().tolist())
    )
    if opt_cats:
        opt = sales_df[sales_df["cat"].isin(opt_cats)].copy()
        color_g = (opt.groupby(["platform","color_norm"])
                   .agg(qty=("qty","sum"), sales=("sales","sum"))
                   .reset_index()
                   .sort_values("qty", ascending=False))
        size_g  = (opt.groupby(["platform","size_norm"])
                   .agg(qty=("qty","sum"), sales=("sales","sum"))
                   .reset_index()
                   .sort_values("qty", ascending=False))
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**색상 분포**")
            st.dataframe(color_g, use_container_width=True, hide_index=True)
        with c2:
            st.markdown("**사이즈 분포**")
            st.dataframe(size_g, use_container_width=True, hide_index=True)

# -------------------------
# Download
# -------------------------
st.download_button(
    "카테고리 요약 CSV 다운로드",
    data=cat_sum.to_csv(index=False),
    file_name="category_summary.csv",
    mime="text/csv",
)
