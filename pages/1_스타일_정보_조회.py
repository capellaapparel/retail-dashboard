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

        # 레이아웃: 이미지와 정보 박스 중앙 정렬
        st.markdown("""
        <div style="display: flex; justify-content: center; align-items: flex-start; gap:60px;">
            <div>
                %s
            </div>
            <div style="min-width:350px;">
                <h4 style='margin-bottom:10px;'><b>Product Number:</b> %s</h4>
                <p><b>ERP PRICE:</b> %s</p>
                <p><b>TEMU PRICE:</b> %s</p>
                <p><b>SHEIN PRICE:</b> %s</p>
                <p><b>SLEEVE:</b> %s</p>
                <p><b>NECKLINE:</b> %s</p>
                <p><b>LENGTH:</b> %s</p>
                <p><b>FIT:</b> %s</p>
                <p><b>STYLE MOOD:</b> %s</p>
                <p><b>MODEL:</b> %s</p>
                <p><b>NOTES:</b> %s</p>
            </div>
        </div>
        <hr style="margin:40px 0 16px 0;">
        """ % (
            f"<img src='{image_url}' width='270' style='border-radius:16px;'>" if image_url else "<p>이미지 없음</p>",
            row.get("product number", ""),
            f"${row.get('erp price', '')}" if row.get("erp price", "") else "",
            get_latest_temu_price(df_temu, selected),
            get_latest_shein_price(df_shein, selected),
            row.get("sleeve", ""),
            row.get("neckline", ""),
            row.get("length", ""),
            row.get("fit", ""),
            row.get("style mood", ""),
            row.get("model", ""),
            row.get("notes", ""),
        ), unsafe_allow_html=True)

        # --- 사이즈 차트 영역 ---
        st.markdown(
            "<div style='width:100%; display:flex; flex-direction:column; align-items:center; margin-top:16px;'>"
            "<div style='font-size:1.5em; font-weight:700; margin-bottom:8px;'><span style='font-size:1.2em;'>✏️</span> Size Chart</div>",
            unsafe_allow_html=True
        )

        def has_size_data(*args):
            return any(str(v).strip() not in ["", "0", "0.0"] for v in args)

        top1_vals = (row.get("top1_chest", ""), row.get("top1_length", ""), row.get("top1_sleeve", ""))
        top2_vals = (row.get("top2_chest", ""), row.get("top2_length", ""), row.get("top2_sleeve", ""))
        bottom_vals = (row.get("bottom_waist", ""), row.get("bottom_hip", ""), row.get("bottom_length", ""), row.get("bottom_inseam", ""))

        html_parts = []
        if has_size_data(*top1_vals):
            html_parts.append(f"""
                <table style='width:380px; margin:0 auto 12px auto; border-collapse:collapse;'>
                <tr><th colspan='2' style='text-align:center; background:#f5f5f5;'>Top 1</th></tr>
                <tr><td style='width:100px;'>Chest</td><td>{top1_vals[0]}</td></tr>
                <tr><td>Length</td><td>{top1_vals[1]}</td></tr>
                <tr><td>Sleeve</td><td>{top1_vals[2]}</td></tr>
                </table>
            """)
        if has_size_data(*top2_vals):
            html_parts.append(f"""
                <table style='width:380px; margin:0 auto 12px auto; border-collapse:collapse;'>
                <tr><th colspan='2' style='text-align:center; background:#f5f5f5;'>Top 2</th></tr>
                <tr><td style='width:100px;'>Chest</td><td>{top2_vals[0]}</td></tr>
                <tr><td>Length</td><td>{top2_vals[1]}</td></tr>
                <tr><td>Sleeve</td><td>{top2_vals[2]}</td></tr>
                </table>
            """)
        if has_size_data(*bottom_vals):
            html_parts.append(f"""
                <table style='width:380px; margin:0 auto 16px auto; border-collapse:collapse;'>
                <tr><th colspan='2' style='text-align:center; background:#f5f5f5;'>Bottom</th></tr>
                <tr><td style='width:100px;'>Waist</td><td>{bottom_vals[0]}</td></tr>
                <tr><td>Hip</td><td>{bottom_vals[1]}</td></tr>
                <tr><td>Length</td><td>{bottom_vals[2]}</td></tr>
                <tr><td>Inseam</td><td>{bottom_vals[3]}</td></tr>
                </table>
            """)
        if html_parts:
            st.markdown("".join(html_parts) + "</div>", unsafe_allow_html=True)
        else:
            st.caption("사이즈 정보가 없습니다.")
