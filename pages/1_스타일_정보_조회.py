import streamlit as st
from utils import load_google_sheet, show_price_block, get_latest_temu_price, get_latest_shein_price

PRODUCT_SHEET = "PRODUCT_INFO"
SHEIN_SHEET = "SHEIN_SALES"
TEMU_SHEET = "TEMU_SALES"

# 데이터 로딩
df_info = load_google_sheet(PRODUCT_SHEET, st.secrets)
df_shein = load_google_sheet(SHEIN_SHEET, st.secrets)
df_temu = load_google_sheet(TEMU_SHEET, st.secrets)

st.markdown("""
<style>
.info-row {display:flex; align-items:flex-start; gap:40px; margin-top:30px;}
.info-img {width:250px; min-width:180px; border-radius:14px; box-shadow:0 4px 16px #eee;}
.info-block {padding-top:4px; min-width:300px;}
.info-block b {color:#28384a;}
.size-title {display:flex; align-items:center; font-size:1.4em; font-weight:700; color:#233; margin:25px 0 8px 0;}
.size-title .emoji {font-size:1.1em; margin-right:10px;}
.schart-box {margin-bottom:18px;}
.size-note {color:#9a9a9a; font-size:1.03em; margin-top:2px;}
@media (max-width:850px) {.info-row {flex-direction:column; gap:10px;} .info-img{margin-bottom:14px;}}
</style>
""", unsafe_allow_html=True)

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

        st.markdown("<hr>", unsafe_allow_html=True)
        st.markdown("<div class='info-row'>", unsafe_allow_html=True)

        # --- 왼쪽: 이미지
        if image_url and image_url.startswith("http"):
            st.markdown(f"<img class='info-img' src='{image_url}' />", unsafe_allow_html=True)
        else:
            st.markdown("<div class='info-img' style='background:#f4f4f4;width:220px;height:290px;display:flex;align-items:center;justify-content:center;color:#aaa;'>이미지 없음</div>", unsafe_allow_html=True)

        # --- 오른쪽: 정보
        st.markdown("<div class='info-block'>", unsafe_allow_html=True)
        st.markdown(f"<b>Product Number:</b> {row.get('product number', '')}<br>", unsafe_allow_html=True)
        st.markdown(f"<b>ERP PRICE:</b> ${row.get('erp price', '')}<br>", unsafe_allow_html=True)
        st.markdown(f"<b>TEMU PRICE:</b> {get_latest_temu_price(df_temu, selected)}<br>", unsafe_allow_html=True)
        st.markdown(f"<b>SHEIN PRICE:</b> {get_latest_shein_price(df_shein, selected)}<br>", unsafe_allow_html=True)
        # 나머지 속성 반복 출력
        labels = [
            ("sleeve", "SLEEVE"), ("neckline", "NECKLINE"), ("length", "LENGTH"),
            ("fit", "FIT"), ("detail", "DETAIL"), ("style mood", "STYLE MOOD"),
            ("model", "MODEL"), ("notes", "NOTES")
        ]
        for col, label in labels:
            val = row.get(col, "")
            if val and str(val).strip() not in ("", "nan", "NaN"):
                st.markdown(f"<b>{label}:</b> {val}<br>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)  # .info-row

        st.markdown("<hr>", unsafe_allow_html=True)

        # ----- SIZE CHART -----
        st.markdown("""
        <div class='schart-box'>
          <div class='size-title'><span class='emoji'>✏️</span>Size Chart</div>
        </div>
        """, unsafe_allow_html=True)

        # ---- 사이즈 데이터 표 or 없음 처리 ----
        def has_size_data(*args):
            return any(str(v).strip() not in ["", "0", "0.0"] for v in args)
        top1_vals = (row.get("top1_chest", ""), row.get("top1_length", ""), row.get("top1_sleeve", ""))
        top2_vals = (row.get("top2_chest", ""), row.get("top2_length", ""), row.get("top2_sleeve", ""))
        bottom_vals = (row.get("bottom_waist", ""), row.get("bottom_hip", ""), row.get("bottom_length", ""), row.get("bottom_inseam", ""))
        html_parts = []
        if has_size_data(*top1_vals):
            html_parts.append(f"""
            <table style='width:80%; text-align:center; border-collapse:collapse; margin-bottom:10px' border='1'>
                <tr><th colspan='2'>Top 1</th></tr>
                <tr><td>Chest</td><td>{top1_vals[0]}</td></tr>
                <tr><td>Length</td><td>{top1_vals[1]}</td></tr>
                <tr><td>Sleeve</td><td>{top1_vals[2]}</td></tr>
            </table>
            """)
        if has_size_data(*top2_vals):
            html_parts.append(f"""
            <table style='width:80%; text-align:center; border-collapse:collapse; margin-bottom:10px' border='1'>
                <tr><th colspan='2'>Top 2</th></tr>
                <tr><td>Chest</td><td>{top2_vals[0]}</td></tr>
                <tr><td>Length</td><td>{top2_vals[1]}</td></tr>
                <tr><td>Sleeve</td><td>{top2_vals[2]}</td></tr>
            </table>
            """)
        if has_size_data(*bottom_vals):
            html_parts.append(f"""
            <table style='width:80%; text-align:center; border-collapse:collapse' border='1'>
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
            st.markdown("<div class='size-note'>사이즈 정보가 없습니다.</div>", unsafe_allow_html=True)
