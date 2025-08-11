# ==========================================
# File: pages/7_타이틀_키워드_도우미.py
# ==========================================
import streamlit as st
import pandas as pd
import re
from collections import Counter
from dateutil import parser

st.set_page_config(page_title="타이틀/키워드 최적화", layout="wide")
st.title("📝 타이틀 · 키워드 최적화 도우미")

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

# text utils
STOP = set("for with and the a an to of on in by 1pc 2pc set women womens woman ladies lady men mens male basic casual chic cute sexy summer spring fall winter new hot best 2024 2025 plus slim regular relaxed oversize outfit dress top pants shorts set jumpsuit romper color solid printed print pattern style fashion clothing apparel".split())
TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z\-]+")

ATTR_COLS = ["neckline","length","fit","detail","style mood"]

# -------------------------
# Load data
# -------------------------
df_info  = load_google_sheet("PRODUCT_INFO")
df_temu  = load_google_sheet("TEMU_SALES")
df_shein = load_google_sheet("SHEIN_SALES")

IMG_MAP = dict(zip(df_info.get("product number", pd.Series(dtype=str)).astype(str).str.upper().str.replace(" ", "", regex=False), df_info.get("image","")))

df_temu["order date"]  = df_temu["purchase date"].apply(parse_temudate)
df_shein["order date"] = df_shein["order processed on"].apply(parse_sheindate)

# -------------------------
# Controls
# -------------------------
min_dt = pd.to_datetime(pd.concat([df_temu["order date"], df_shein["order date"]]).dropna()).min()
max_dt = pd.to_datetime(pd.concat([df_temu["order date"], df_shein["order date"]]).dropna()).max()

left, right = st.columns([1.3, 1])
with left:
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
with right:
    platform = st.radio("플랫폼", ["TEMU","SHEIN","BOTH"], horizontal=True)

c1, c2, c3 = st.columns(3)
with c1:
    title_len = st.slider("제목 글자 수 한도", 30, 80, 60, 1)
with c2:
    topK = st.slider("추천 키워드 개수", 5, 20, 10, 1)
with c3:
    include_attrs = st.multiselect("포함할 속성", ATTR_COLS, default=["fit","length","detail"]) 

style_input = st.text_input("스타일 번호(선택)", "")

# -------------------------
# Build sales-weighted tokens
# -------------------------

def tokenize(text: str):
    toks = [t.lower() for t in TOKEN_RE.findall(str(text)) if t.lower() not in STOP]
    return [t for t in toks if not STYLE_RE.search(t)]

# sold rows per platform
T = df_temu[(df_temu["order item status"].astype(str).str.lower().isin(["shipped","delivered"])) &
            (df_temu["order date"]>=start) & (df_temu["order date"]<=end)].copy()
T["qty"] = pd.to_numeric(T.get("quantity shipped", 0), errors="coerce").fillna(0)
S = df_shein[(~df_shein["order status"].astype(str).str.lower().eq("customer refunded")) &
             (df_shein["order date"]>=start) & (df_shein["order date"]<=end)].copy()
S["qty"] = 1.0

# Pick text source (SHEIN에선 product description 사용)
T_text = T.get("product description") if "product description" in T.columns else pd.Series([], dtype=str)
S_text = S.get("product description") if "product description" in S.columns else pd.Series([], dtype=str)

pool = []
if platform in ["TEMU","BOTH"]:
    if not T_text.empty:
        for text, w in zip(T_text, T["qty"]):
            for tok in tokenize(text):
                pool.append((tok, w))
if platform in ["SHEIN","BOTH"]:
    if not S_text.empty:
        for text, w in zip(S_text, S["qty"]):
            for tok in tokenize(text):
                pool.append((tok, w))

cnt = Counter()
for tok, w in pool:
    cnt[tok] += float(w)
platform_top = [w for w,_ in cnt.most_common(topK*3)]  # 넉넉히 뽑아두고 추후 필터

# -------------------------
# Per-style suggestion
# -------------------------

def get_style_row(style: str):
    if not style:
        return None
    key = str(style).upper().replace(" ", "")
    m = df_info[df_info["product number"].astype(str).str.upper().str.replace(" ", "", regex=False).eq(key)]
    return m.iloc[0] if not m.empty else None

row = get_style_row(style_input)

def clean_words(s):
    return [w for w in tokenize(str(s)) if w not in STOP]

# candidate tokens
cand_tokens = []
if row is not None:
    for c in include_attrs:
        cand_tokens += clean_words(row.get(c, ""))
    # default product name(en)에서 기본 카테고리 추출
    base_name = str(row.get("default product name(en)", "")).strip()
    base_tokens = clean_words(base_name)[:2]
else:
    base_name = ""
    base_tokens = []

# 플랫폼 인기 토큰에서 중복/금지 제거
for t in platform_top:
    if t not in cand_tokens and t not in base_tokens and t not in STOP:
        cand_tokens.append(t)
    if len(cand_tokens) >= topK:
        break

# 제목 생성기

def join_with_limit(parts, limit):
    out = []
    cur = 0
    for p in parts:
        if not p: 
            continue
        add = (len(p) + (1 if out else 0))
        if cur + add <= limit:
            out.append(p)
            cur += add
        else:
            break
    return " ".join(out)

variationA = join_with_limit(base_tokens + cand_tokens, title_len)
variationB = join_with_limit(cand_tokens + base_tokens, title_len)

left, right = st.columns([1.2,1])
with left:
    st.subheader("🔎 추천 제목")
    st.write(f"**A)** {variationA}  ")
    st.caption(f"{len(variationA)} chars / limit {title_len}")
    st.write(f"**B)** {variationB}  ")
    st.caption(f"{len(variationB)} chars / limit {title_len}")
with right:
    st.subheader("🏷️ 추천 키워드")
    st.write(", ".join(cand_tokens[:topK]))

# 이미지/속성 정보 보조
if row is not None:
    st.divider()
    c1, c2 = st.columns([1,2])
    with c1:
        u = str(IMG_MAP.get(str(row.get("product number",""))).strip())
        if u.startswith("http"): st.image(u, width=220)
    with c2:
        st.markdown("**속성**")
        bullets = [f"- {c}: **{row.get(c,'-')}**" for c in ATTR_COLS]
        st.markdown("\n".join(bullets))
