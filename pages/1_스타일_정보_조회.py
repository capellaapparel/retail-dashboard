import streamlit as st
from utils import load_google_sheet, show_price_block, get_latest_temu_price, get_latest_shein_price

PRODUCT_SHEET = "PRODUCT_INFO"
SHEIN_SHEET = "SHEIN_SALES"
TEMU_SHEET = "TEMU_SALES"

st.set_page_config(page_title="Capella 스타일 정보 조회", layout="wide")

df_info = load_google_sheet(PRODUCT_SHEET, st.secrets)
df_shein = load_google_sheet(SHEIN_SHEET, st.secrets)
df_temu = load_google_sheet(TEMU_SHEET, st.secrets)

st.title("📖 스타일 정보 조회")
style_input = st.text_input("🔍 스타일 번호를 입력하세요:", "")
if style_input:
    matched = df_info[df_info["product number"].astype(str).str.contains(style_input, case=False, na=False)]
    if matched.empty:
        st.warning("❌ 해당 스타일을 찾을 수 없습니다.")
    else:
        selected = st.selectbox("스타일 선택", matched["product number"].astype(str))
        row = df_info[df_info["product number"] == selected].iloc[0]
        image_url = str(row.get("image", "")).strip()

        # ---- 레이아웃: 2컬럼(이미지/정보) + 밑에 사이즈차트 ----
        st.markdown("""
        <style>
        .info-card {padding: 10px 20px 10px 0; font-size: 1.1em;}
        .style-table th, .style-table td {padding: 6px 18px;}
        @media (max-width:900px) {.info-card {font-size:0.95em;}}
        </style>
        """, unsafe_allow_html=True)
        col1, col2 = st.columns([1, 2])
        with col1:
            if image_url:
                st.image(image_url, use_column_width="always")
            else:
                st.caption("이미지 없음")
        with col2:
            st.markdown(
                f"<div class='info-card'>"
                f"<h4 style='margin-top:0'>{row.get('default product name(en)','')}</h4>"
                f"<b>Product Number:</b> {row['product number']}<br>"
                + show_price_block(st, "ERP PRICE", row.get("erp price", "")) +
                f"<b>TEMU PRICE:</b> {get_latest_temu_price(df_temu, selected)}<br>"
                f"<b>SHEIN PRICE:</b> {get_latest_shein_price(df_shein, selected)}<br>"
                + "".join(
                    f"<b>{label}:</b> {row.get(col,'')}<br>"
                    for col, label in [
                        ("sleeve", "SLEEVE"), ("neckline", "NECKLINE"), ("length", "LENGTH"),
                        ("fit", "FIT"), ("detail", "DETAIL"), ("style mood", "STYLE MOOD"),
                        ("model", "MODEL"), ("notes", "NOTES")
                    ] if row.get(col,"") and str(row.get(col,"")).strip() not in ("", "nan", "NaN")
                ) +
                "</div>", unsafe_allow_html=True)

        # ---- 아래 넓은 사이즈 차트 ----
        st.markdown("---")
        st.markdown("<div style='margin: 0 auto; max-width:600px;'>", unsafe_allow_html=True)
        st.subheader("📏 Size Chart")

        def has_size_data(*args):
            return any(str(v).strip() not in ["", "0", "0.0"] for v in args)
        top1_vals = (row.get("top1_chest", ""), row.get("top1_length", ""), row.get("top1_sleeve", ""))
        top2_vals = (row.get("top2_chest", ""), row.get("top2_length", ""), row.get("top2_sleeve", ""))
        bottom_vals = (row.get("bottom_waist", ""), row.get("bottom_hip", ""), row.get("bottom_length", ""), row.get("bottom_inseam", ""))
        html_parts = []
        if has_size_data(*top1_vals):
            html_parts.append(f"""
            <table class='style-table' border='1' style='width:100%;text-align:center;margin-bottom:10px'>
                <tr><th colspan='2'>Top 1</th></tr>
                <tr><td>Chest</td><td>{top1_vals[0]}</td></tr>
                <tr><td>Length</td><td>{top1_vals[1]}</td></tr>
                <tr><td>Sleeve</td><td>{top1_vals[2]}</td></tr>
            </table>
            """)
        if has_size_data(*top2_vals):
            html_parts.append(f"""
            <table class='style-table' border='1' style='width:100%;text-align:center;margin-bottom:10px'>
                <tr><th colspan='2'>Top 2</th></tr>
                <tr><td>Chest</td><td>{top2_vals[0]}</td></tr>
                <tr><td>Length</td><td>{top2_vals[1]}</td></tr>
                <tr><td>Sleeve</td><td>{top2_vals[2]}</td></tr>
            </table>
            """)
        if has_size_data(*bottom_vals):
            html_parts.append(f"""
            <table class='style-table' border='1' style='width:100%;text-align:center'>
                <tr><th colspan='2'>Bottom</th></tr>
                <tr><td>Waist</td><td>{bottom_vals[0]}</td></tr>
                <tr><td>Hip</td><td>{bottom_vals[1]}</td></tr>
                <tr><td>Length</td><td>{bottom_vals[2]}</td></tr>
                <tr><td>Inseam</td><td>{bottom_vals[3]}</td></tr>
            </table>
            """)
        if html_parts:
            st.markdown("".join(html_parts), unsafe_allow_html=True)
        else:
            st.caption("사이즈 정보가 없습니다.")
        st.markdown("</div>", unsafe_allow_html=True)
