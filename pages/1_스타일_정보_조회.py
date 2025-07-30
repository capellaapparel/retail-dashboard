import streamlit as st
from utils import load_google_sheet, show_price_block, get_latest_temu_price, get_latest_shein_price

PRODUCT_SHEET = "PRODUCT_INFO"
SHEIN_SHEET = "SHEIN_SALES"
TEMU_SHEET = "TEMU_SALES"

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

        # 좌우 배치: 이미지(중앙) + 정보
        st.markdown("---")
        col1, col2 = st.columns([1.2, 2.3], gap="large")

        with col1:
            if image_url:
                st.image(image_url, width=250, use_column_width=False)
            else:
                st.caption("이미지 없음")

        with col2:
            st.markdown(
                f"""
                <div style='line-height: 1.85; font-size:1.08em'>
                    <b>Product Number:</b> {row['product number']}<br>
                    <b>ERP PRICE:</b> {row.get('erp price', 'NA')}<br>
                    <b>TEMU PRICE:</b> {get_latest_temu_price(df_temu, selected)}<br>
                    <b>SHEIN PRICE:</b> {get_latest_shein_price(df_shein, selected)}<br>
                    <b>SLEEVE:</b> {row.get('sleeve', '')}<br>
                    <b>NECKLINE:</b> {row.get('neckline', '')}<br>
                    <b>LENGTH:</b> {row.get('length', '')}<br>
                    <b>FIT:</b> {row.get('fit', '')}<br>
                    <b>DETAIL:</b> {row.get('detail', '')}<br>
                    <b>STYLE MOOD:</b> {row.get('style mood', '')}<br>
                    <b>MODEL:</b> {row.get('model', '')}<br>
                    <b>NOTES:</b> {row.get('notes', '')}
                </div>
                """,
                unsafe_allow_html=True,
            )

        # 넓게 아래에 사이즈 차트
        st.markdown("---")
        st.markdown(
            "<div style='display:flex;align-items:center;gap:7px;'>"
            "<span style='font-size:2em'>✏️</span>"
            "<span style='font-size:1.6em;font-weight:700;'>Size Chart</span></div>",
            unsafe_allow_html=True,
        )

        def has_size_data(*args):
            return any(str(v).strip() not in ["", "0", "0.0"] for v in args)

        # --- 사이즈 차트 표 전체 넓게 ---
top1_vals = (row.get("top1_chest", ""), row.get("top1_length", ""), row.get("top1_sleeve", ""))
top2_vals = (row.get("top2_chest", ""), row.get("top2_length", ""), row.get("top2_sleeve", ""))
bottom_vals = (
    row.get("bottom_waist", ""), row.get("bottom_hip", ""),
    row.get("bottom_length", ""), row.get("bottom_inseam", "")
)

def has_size_data(*args):
    return any(str(v).strip() not in ["", "0", "0.0"] for v in args)

size_table_html = ""
if has_size_data(*top1_vals):
    size_table_html += f"""
    <table style='width:360px; margin:auto; margin-bottom:10px; border-collapse:collapse; text-align:center;' border='1'>
        <tr style="background:#F7F7F7"><th colspan='2'>Top 1</th></tr>
        <tr><td>Chest</td><td>{top1_vals[0]}</td></tr>
        <tr><td>Length</td><td>{top1_vals[1]}</td></tr>
        <tr><td>Sleeve</td><td>{top1_vals[2]}</td></tr>
    </table>
    """
if has_size_data(*top2_vals):
    size_table_html += f"""
    <table style='width:360px; margin:auto; margin-bottom:10px; border-collapse:collapse; text-align:center;' border='1'>
        <tr style="background:#F7F7F7"><th colspan='2'>Top 2</th></tr>
        <tr><td>Chest</td><td>{top2_vals[0]}</td></tr>
        <tr><td>Length</td><td>{top2_vals[1]}</td></tr>
        <tr><td>Sleeve</td><td>{top2_vals[2]}</td></tr>
    </table>
    """
if has_size_data(*bottom_vals):
    size_table_html += f"""
    <table style='width:360px; margin:auto; border-collapse:collapse; text-align:center;' border='1'>
        <tr style="background:#F7F7F7"><th colspan='2'>Bottom</th></tr>
        <tr><td>Waist</td><td>{bottom_vals[0]}</td></tr>
        <tr><td>Hip</td><td>{bottom_vals[1]}</td></tr>
        <tr><td>Length</td><td>{bottom_vals[2]}</td></tr>
        <tr><td>Inseam</td><td>{bottom_vals[3]}</td></tr>
    </table>
    """

if size_table_html:
    st.markdown(
        f"<div style='width:100%;text-align:center'>{size_table_html}</div>",
        unsafe_allow_html=True,
    )
else:
    st.caption("사이즈 정보가 없습니다.")

