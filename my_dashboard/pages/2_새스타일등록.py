import streamlit as st
import pandas as pd
import os

NECKLINE_FILE = "neckline_options.csv"
DETAIL_FILE = "detail_options.csv"

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

st.title("➕ 새 스타일 등록")

with st.form("add_style"):
    new_spu = st.text_input("STYLE NUMBER (필수)", key="new_spu")
    erp_price = st.number_input("ERP PRICE", step=0.01, key="erp")
    shein_price = st.number_input("SHEIN PRICE", step=0.01, key="shein")
    temu_price = st.number_input("TEMU PRICE", step=0.01, key="temu")

    default_necklines = ["Round", "Scoop", "V neck", "Halter", "Crew", "Off Shoulder", "One Shoulder", "Square", "Hooded", "Asymmetrical", "Spaghetti", "Double Strap", "Cami", "Split", "Mock", "High", "Tube", "Jacket", "Plunge", "Cut Out", "Collar", "Cowl"]
    neckline_options = load_or_create_options(NECKLINE_FILE, default_necklines)
    neckline = st.selectbox("NECKLINE", [""] + neckline_options)
    new_neckline = st.text_input("+ 새로운 NECKLINE 추가")
    save_new_option(NECKLINE_FILE, new_neckline)
    if new_neckline:
        neckline = new_neckline

    default_lengths = ["Crop Top", "Waist Top", "Long Top", "Mini Dress", "Midi Dress", "Maxi Dress", "Mini Skirt", "Midi Skirt", "Maxi Skirt", "Shorts", "Knee", "Capri", "Full"]
    length = st.multiselect("LENGTH", default_lengths)

    fit = st.radio("FIT", ["Slim", "Regular", "Loose"], index=1)

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

    st.markdown("### 📏 사이즈 차트 입력")
    st.markdown("**TOP 1**")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.number_input("Top1 Chest", key="f_top1_chest")
    with col2:
        st.number_input("Top1 Length", key="f_top1_length")
    with col3:
        st.number_input("Top1 Sleeve Length", key="f_top1_sleeve")

    st.markdown("**TOP 2**")
    col4, col5, col6 = st.columns(3)
    with col4:
        st.number_input("Top2 Chest", key="f_top2_chest")
    with col5:
        st.number_input("Top2 Length", key="f_top2_length")
    with col6:
        st.number_input("Top2 Sleeve Length", key="f_top2_sleeve")

    st.markdown("**BOTTOM**")
    col7, col8, col9, col10 = st.columns(4)
    with col7:
        st.number_input("Bottom Waist", key="f_bottom_waist")
    with col8:
        st.number_input("Bottom Hip", key="f_bottom_hip")
    with col9:
        st.number_input("Bottom Length", key="f_bottom_length")
    with col10:
        st.number_input("Bottom Inseam", key="f_bottom_inseam")

    submitted = st.form_submit_button("추가하기")
    if submitted:
        st.success("새 스타일이 등록되었습니다! (저장은 CSV 수동처리 필요)")
