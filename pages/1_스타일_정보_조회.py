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

        st.markdown("---")
        col1, col2 = st.columns([0.8, 2])
        with col1:
            if image_url:
                st.image(image_url, width=260)
            else:
                st.caption("이미지 없음")
        with col2:
            st.markdown(
                f"""
                <div style='font-size:1.05em; line-height:1.65;'>
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
                """, unsafe_allow_html=True
            )

        # === Size Chart (wide, 아래 한줄 중앙) ===
        st.markdown("---")
        st.markdown(
            "<div style='display:flex;align-items:center;gap:10px;margin-bottom:8px;'>"
            "<span style='font-size:1.28em;'>📝 <b>Size Chart</b></span></div>", 
            unsafe_allow_html=True
        )

        # --- 표 생성 함수 ---
        def has_any_value(values):
            return any(str(v).strip() not in ["", "0", "0.0", "None", "nan"] and v is not None for v in values)

        def make_table(title, labels, values):
            # 값이 하나라도 있으면 표 출력
            if not has_any_value(values):
                return ""
            rows = "".join([f"<tr><td>{l}</td><td>{v}</td></tr>" for l, v in zip(labels, values)])
            return f"""
                <table style='width:340px; margin:auto; margin-bottom:10px; border-collapse:collapse; text-align:center; font-size:1.05em;'>
                    <tr style="background:#F7F7F7"><th colspan='2'>{title}</th></tr>
                    {rows}
                </table>
            """

        # 표 문자열만 만듦
        top1_html = make_table("Top 1", ["Chest", "Length", "Sleeve"], [
            row.get("top1_chest",""), row.get("top1_length",""), row.get("top1_sleeve","")
        ])
        top2_html = make_table("Top 2", ["Chest", "Length", "Sleeve"], [
            row.get("top2_chest",""), row.get("top2_length",""), row.get("top2_sleeve","")
        ])
        bottom_html = make_table("Bottom", ["Waist", "Hip", "Length", "Inseam"], [
            row.get("bottom_waist",""), row.get("bottom_hip",""), row.get("bottom_length",""), row.get("bottom_inseam","")
        ])
        size_table_html = "".join([top1_html, top2_html, bottom_html])

        # 표가 있으면 중앙에 한 번에 그리기!
        if size_table_html:
            st.markdown(
                f"<div style='display:flex; justify-content:center; width:100%; margin-top:12px;'>{size_table_html}</div>",
                unsafe_allow_html=True
            )
        else:
            st.caption("사이즈 정보가 없습니다.")
