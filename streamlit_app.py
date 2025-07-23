# streamlit_app.py
import streamlit as st
import pandas as pd
import os

# --- 유저 정의 옵션 저장 경로 ---
NECKLINE_FILE = "neckline_options.csv"
DETAIL_FILE = "detail_options.csv"

# --- 기본값 정의 ---
def load_or_create_options(file_path, default_list):
    if os.path.exists(file_path):
        return pd.read_csv(file_path)["option"].tolist()
    else:
        pd.DataFrame({"option": default_list}).to_csv(file_path, index=False)
        return default_list

def save_new_option(file_path, new_option):
    if new_option:
        df = pd.read_csv(file_path)
        if new_option not in df["option"].values:
            df.loc[len(df)] = new_option
            df.to_csv(file_path, index=False)

# --- 데이터 로딩 ---
@st.cache_data
def load_data():
    try:
        df = pd.read_csv("shein_sales_summary.csv")
        return df
    except FileNotFoundError:
        return pd.DataFrame()

df = load_data()

# --- 제목 ---
st.title("Product Info Dashboard")

# --- 스타일넘버 검색 기능 ---
style_input = st.text_input("🔍 스타일 번호를 입력하세요:", "")

if style_input:
    matched = df[df['SPU'].str.contains(style_input, case=False, na=False)]
    if not matched.empty:
        selected = st.selectbox("스타일 선택", matched['SPU'] + " - " + matched['Goods name'])
        selected_spu = selected.split(" - ")[0]
        product = df[df['SPU'] == selected_spu].iloc[0]

        # --- 이미지 ---
        st.image(product['Product image link'], width=300)

        # --- 사이즈차트 자리 ---
        st.subheader("📏 Size Chart")
        st.markdown("**TOP 1**")
        col1, col2, col3 = st.columns(3)
        with col1:
            top1_chest = st.number_input("Chest", key="top1_chest")
        with col2:
            top1_length = st.number_input("Length", key="top1_length")
        with col3:
            top1_sleeve = st.number_input("Sleeve Length", key="top1_sleeve")

        st.markdown("**TOP 2**")
        col4, col5, col6 = st.columns(3)
        with col4:
            top2_chest = st.number_input("Chest", key="top2_chest")
        with col5:
            top2_length = st.number_input("Length", key="top2_length")
        with col6:
            top2_sleeve = st.number_input("Sleeve Length", key="top2_sleeve")

        st.markdown("**BOTTOM**")
        col7, col8, col9, col10 = st.columns(4)
        with col7:
            bottom_waist = st.number_input("Waist", key="bottom_waist")
        with col8:
            bottom_hip = st.number_input("Hip", key="bottom_hip")
        with col9:
            bottom_length = st.number_input("Length", key="bottom_length")
        with col10:
            bottom_inseam = st.number_input("Inseam", key="bottom_inseam")

        # --- 상세 정보 ---
        st.subheader("💡 Product Info")
        st.write(f"**ERP PRICE**: {product['Gross Merchandise Volume']}")
        st.write(f"**SHEIN PRICE**: 자동입력 예정")
        st.write(f"**TEMU PRICE**: 자동입력 예정")
        st.write("---")

    else:
        st.warning("해당 스타일을 찾을 수 없습니다.")

# --- 스타일 추가 기능 ---
st.subheader("➕ 새로운 스타일 추가")
with st.form("add_style"):
    new_spu = st.text_input("STYLE NUMBER (필수)", key="new_spu")
    erp_price = st.number_input("ERP PRICE", step=0.01, key="erp")
    shein_price = st.number_input("SHEIN PRICE", step=0.01, key="shein")
    temu_price = st.number_input("TEMU PRICE", step=0.01, key="temu")

    # --- NECKLINE 항목 불러오기 및 업데이트 ---
    default_necklines = ["Round", "Scoop", "V neck", "Halter", "Crew", "Off Shoulder", "One Shoulder", "Square", "Hooded", "Asymmetrical", "Spaghetti", "Double Strap", "Cami", "Split", "Mock", "High", "Tube", "Jacket", "Plunge", "Cut Out", "Collar", "Cowl"]
    neckline_options = load_or_create_options(NECKLINE_FILE, default_necklines)
    neckline = st.selectbox("NECKLINE", [""] + neckline_options)
    new_neckline = st.text_input("+ 새로운 NECKLINE 추가")
    save_new_option(NECKLINE_FILE, new_neckline)
    if new_neckline:
        neckline = new_neckline

    # --- LENGTH ---
    default_lengths = ["Crop Top", "Waist Top", "Long Top", "Mini Dress", "Midi Dress", "Maxi Dress", "Mini Skirt", "Midi Skirt", "Maxi Skirt", "Shorts", "Knee", "Capri", "Full"]
    length = st.multiselect("LENGTH", default_lengths)

    fit = st.radio("FIT", ["Slim", "Regular", "Loose"], index=1)

    # --- DETAIL 항목 불러오기 및 업데이트 ---
    default_details = ["Ruched", "Cut Out", "Drawstring", "Slit", "Button/Zipper", "Tie", "Backless", "Wrap", "Stripe", "Graphic", "Wide Leg", "Pocket", "Pleated", "Exposed Seam", "Criss Cross", "Ring", "Asymmetrical", "Mesh", "Puff", "Shirred", "Tie Dye", "Fringe", "Racer Back", "Corset", "Lace", "Tier", "Twist", "Lettuce Trim"]
    detail_options = load_or_create_options(DETAIL_FILE, default_details)
    detail = st.multiselect("DETAIL", detail_options)
    new_detail = st.text_input("+ 새로운 DETAIL 추가")
    save_new_option(DETAIL_FILE, new_detail)
    if new_detail and new_detail not in detail:
        detail.append(new_detail)

    style_mood = st.selectbox("STYLE MOOD", ["Sexy", "Casual", "Lounge", "Formal", "Activewear"])
    model = st.multiselect("MODEL", ["Latina", "Black", "Caucasian", "Plus", "Asian"])
    notes = st.text_area("NOTES")

    submitted = st.form_submit_button("추가하기")
    if submitted:
        st.success("새 스타일이 등록되었습니다! (저장은 CSV 수동처리 필요)")
