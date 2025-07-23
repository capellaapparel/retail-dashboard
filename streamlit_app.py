# streamlit_app.py
import streamlit as st
import pandas as pd
import requests

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
        top1 = st.text_input("Top 1 Size (Chest, Length, Sleeve Length)")
        top2 = st.text_input("Top 2 Size (Chest, Length, Sleeve Length)")
        bottom = st.text_input("Bottom Size (Waist, Hip, Length, Inseam)")

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

    default_necklines = ["Round", "Scoop", "V neck", "Halter", "Crew", "Off Shoulder", "One Shoulder", "Square", "Hooded", "Asymmetrical", "Spaghetti", "Double Strap", "Cami", "Split", "Mock", "High", "Tube", "Jacket", "Plunge", "Cut Out", "Collar", "Cowl"]
    neckline = st.selectbox("NECKLINE", [""] + default_necklines)
    new_neckline = st.text_input("+ 새로운 NECKLINE 추가")
    if new_neckline and new_neckline not in default_necklines:
        neckline = new_neckline

    default_lengths = ["Crop Top", "Waist Top", "Long Top", "Mini Dress", "Midi Dress", "Maxi Dress", "Mini Skirt", "Midi Skirt", "Maxi Skirt", "Shorts", "Knee", "Capri", "Full"]
    length = st.multiselect("LENGTH", default_lengths)

    fit = st.radio("FIT", ["Slim", "Regular", "Loose"], index=1)

    default_details = ["Ruched", "Cut Out", "Drawstring", "Slit", "Button/Zipper", "Tie", "Backless", "Wrap", "Stripe", "Graphic", "Wide Leg", "Pocket", "Pleated", "Exposed Seam", "Criss Cross", "Ring", "Asymmetrical", "Mesh", "Puff", "Shirred", "Tie Dye", "Fringe", "Racer Back", "Corset", "Lace", "Tier", "Twist", "Lettuce Trim"]
    detail = st.multiselect("DETAIL", default_details)
    new_detail = st.text_input("+ 새로운 DETAIL 추가")
    if new_detail and new_detail not in detail:
        detail.append(new_detail)

    style_mood = st.selectbox("STYLE MOOD", ["Sexy", "Casual", "Lounge", "Formal", "Activewear"])
    model = st.multiselect("MODEL", ["Latina", "Black", "Caucasian", "Plus", "Asian"])
    notes = st.text_area("NOTES")

    top1_new = st.text_input("Top 1 Size Chart", key="top1")
    top2_new = st.text_input("Top 2 Size Chart", key="top2")
    bottom_new = st.text_input("Bottom Size Chart", key="bottom")

    submitted = st.form_submit_button("추가하기")
    if submitted:
        st.success("새 스타일이 등록되었습니다! (저장은 CSV 수동처리 필요)")
