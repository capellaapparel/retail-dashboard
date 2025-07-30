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

        # 1. 이미지+정보 한줄에! (가운데로)
        st.markdown("""
        <div style="display:flex; justify-content:center; align-items:flex-start; gap:60px; margin-bottom:28px;">
            <div style="flex-shrink:0;">
                %s
            </div>
            <div style="min-width:330px; max-width:420px;">
                <div style="font-size:1.15em; margin-bottom:8px;"><b>Product Number:</b> %s</div>
                <div><b>ERP PRICE:</b> %s</div>
                <div><b>TEMU PRICE:</b> %s</div>
                <div><b>SHEIN PRICE:</b> %s</div>
                <div><b>SLEEVE:</b> %s</div>
                <div><b>NECKLINE:</b> %s</div>
                <div><b>LENGTH:</b> %s</div>
                <div><b>FIT:</b> %s</div>
                <div><b>STYLE MOOD:</b> %s</div>
                <div><b>MODEL:</b> %s</div>
                <div><b>NOTES:</b> %s</div>
            </div>
        </div>
        <hr style="margin:24px 0 20px 0;">
        """ % (
            f"<img src='{image_url}' width='260' style='border-radius:14px; box-shadow:0 1px 6px #bbb;'>" if image_url else "<p>이미지 없음</p>",
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

        # 2. 아래쪽 전체 폭(=넓게) 사이즈 차트 카드 스타일!
        st.markdown("<hr>", unsafe_allow_html=True)
        st.markdown("""
        <div style='display:flex; flex-direction:column; align-items:center; margin-top:32px; margin-bottom:12px;'>
    <span style='font-size:2em; font-weight:700;'>📝 Size Chart</span>
    <table style='width:420px; margin-top:18px; border-collapse:collapse;'>
        <tr><th colspan='2'>Top 1</th></tr>
        <tr><td>Chest</td><td>{}</td></tr>
        <tr><td>Length</td><td>{}</td></tr>
        <tr><td>Sleeve</td><td>{}</td></tr>
    </table>
    <table style='width:420px; margin-top:18px; border-collapse:collapse;'>
        <tr><th colspan='2'>Bottom</th></tr>
        <tr><td>Waist</td><td>{}</td></tr>
        <tr><td>Hip</td><td>{}</td></tr>
        <tr><td>Length</td><td>{}</td></tr>
        <tr><td>Inseam</td><td>{}</td></tr>
    </table>
</div>
        """.format(*top1_vals, *bottom_vals), unsafe_allow_html=True)

        def has_size_data(*args):
            return any(str(v).strip() not in ["", "0", "0.0"] for v in args)

        top1_vals = (row.get("top1_chest", ""), row.get("top1_length", ""), row.get("top1_sleeve", ""))
        top2_vals = (row.get("top2_chest", ""), row.get("top2_length", ""), row.get("top2_sleeve", ""))
        bottom_vals = (row.get("bottom_waist", ""), row.get("bottom_hip", ""), row.get("bottom_length", ""), row.get("bottom_inseam", ""))

        size_html = ""
        if has_size_data(*top1_vals):
            size_html += f"""
                <table style='width:420px; margin:0 auto 12px auto; border-collapse:collapse; background:white; border-radius:10px; box-shadow:0 2px 8px #eee;'>
                <tr><th colspan='2' style='text-align:center; background:#f8f8f8; font-size:1.08em; border-radius:8px 8px 0 0;'>Top 1</th></tr>
                <tr><td style='width:110px;'>Chest</td><td>{top1_vals[0]}</td></tr>
                <tr><td>Length</td><td>{top1_vals[1]}</td></tr>
                <tr><td>Sleeve</td><td>{top1_vals[2]}</td></tr>
                </table>
            """
        if has_size_data(*top2_vals):
            size_html += f"""
                <table style='width:420px; margin:0 auto 12px auto; border-collapse:collapse; background:white; border-radius:10px; box-shadow:0 2px 8px #eee;'>
                <tr><th colspan='2' style='text-align:center; background:#f8f8f8; font-size:1.08em;'>Top 2</th></tr>
                <tr><td style='width:110px;'>Chest</td><td>{top2_vals[0]}</td></tr>
                <tr><td>Length</td><td>{top2_vals[1]}</td></tr>
                <tr><td>Sleeve</td><td>{top2_vals[2]}</td></tr>
                </table>
            """
        if has_size_data(*bottom_vals):
            size_html += f"""
                <table style='width:420px; margin:0 auto 16px auto; border-collapse:collapse; background:white; border-radius:10px; box-shadow:0 2px 8px #eee;'>
                <tr><th colspan='2' style='text-align:center; background:#f8f8f8; font-size:1.08em;'>Bottom</th></tr>
                <tr><td style='width:110px;'>Waist</td><td>{bottom_vals[0]}</td></tr>
                <tr><td>Hip</td><td>{bottom_vals[1]}</td></tr>
                <tr><td>Length</td><td>{bottom_vals[2]}</td></tr>
                <tr><td>Inseam</td><td>{bottom_vals[3]}</td></tr>
                </table>
            """
        st.markdown(size_html + "</div>", unsafe_allow_html=True)

        if not size_html:
            st.caption("사이즈 정보가 없습니다.")

