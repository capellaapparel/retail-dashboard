import streamlit as st
import pandas as pd
from utils import load_google_sheet, show_price_block, get_latest_temu_price, get_latest_shein_price

# ===== CSS (등록안됨 배지) =====
st.markdown("""
<style>
.pill {display:inline-block; padding:2px 8px; border-radius:10px; font-size:12px;}
.pill-gray {background:#eee; color:#444;}
</style>
""", unsafe_allow_html=True)

PRODUCT_SHEET = "PRODUCT_INFO"
SHEIN_SHEET = "SHEIN_SALES"
TEMU_SHEET = "TEMU_SALES"

df_info = load_google_sheet(PRODUCT_SHEET, st.secrets)
df_shein = load_google_sheet(SHEIN_SHEET, st.secrets)
df_temu = load_google_sheet(TEMU_SHEET, st.secrets)

def _get(row, *keys, default=""):
    """row에서 대소문자 상관없이 첫 매칭 값을 반환"""
    for k in keys:
        if k in row: 
            return row.get(k, default)
    # 혹시 모를 케이스 대비 소문자 키 재검색
    low = {str(k).lower(): v for k, v in row.items()}
    for k in keys:
        v = low.get(str(k).lower(), None)
        if v is not None:
            return v
    return default

def _fmt_price(x):
    if x is None:
        return "-"
    s = str(x).strip()
    return "-" if s == "" or s.lower() in ["nan", "none"] else s

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

        # LIVE DATE 파싱 (대문자/소문자 모두 대응)
        temu_live  = pd.to_datetime(_get(row, "temu_live_date", "TEMU_LIVE_DATE"),  errors="coerce")
        shein_live = pd.to_datetime(_get(row, "shein_live_date", "SHEIN_LIVE_DATE"), errors="coerce")
        temu_registered  = pd.notna(temu_live)
        shein_registered = pd.notna(shein_live)

        # 등록된 경우에만 최신가 조회
        latest_temu  = get_latest_temu_price(df_temu, selected)   if temu_registered  else None
        latest_shein = get_latest_shein_price(df_shein, selected) if shein_registered else None

        st.markdown("---")
        col1, col2 = st.columns([1, 2])

        with col1:
            if image_url:
                st.image(image_url, width=300)
            else:
                st.caption("이미지 없음")

        with col2:
            st.subheader(row.get("default product name(en)", ""))
            st.markdown(f"**Product Number:** {row['product number']}")
            show_price_block(st, "ERP PRICE", row.get("erp price", ""))

            # ▶ TEMU
            if not temu_registered:
                st.markdown("**TEMU:** <span class='pill pill-gray'>등록안됨</span>", unsafe_allow_html=True)
            else:
                st.markdown(f"**TEMU PRICE:** {_fmt_price(latest_temu)}")

            # ▶ SHEIN
            if not shein_registered:
                st.markdown("**SHEIN:** <span class='pill pill-gray'>등록안됨</span>", unsafe_allow_html=True)
            else:
                st.markdown(f"**SHEIN PRICE:** {_fmt_price(latest_shein)}")

            # 속성 표시
            for col, label in [
                ("sleeve", "SLEEVE"), ("neckline", "NECKLINE"), ("length", "LENGTH"),
                ("fit", "FIT"), ("detail", "DETAIL"), ("style mood", "STYLE MOOD"),
                ("model", "MODEL"), ("notes", "NOTES")
            ]:
                val = row.get(col, "")
                if val and str(val).strip().lower() not in ("", "nan", "none"):
                    st.markdown(f"**{label}:** {val}")

            # ===== 사이즈 표 =====
            st.markdown("---")
            st.subheader("📏 Size Chart")

            def has_size_data(*args):
                return any(str(v).strip() not in ["", "0", "0.0"] for v in args)

            top1_vals = (row.get("top1_chest", ""), row.get("top1_length", ""), row.get("top1_sleeve", ""))
            top2_vals = (row.get("top2_chest", ""), row.get("top2_length", ""), row.get("top2_sleeve", ""))
            bottom_vals = (
                row.get("bottom_waist", ""), row.get("bottom_hip", ""), 
                row.get("bottom_length", ""), row.get("bottom_inseam", "")
            )

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
                st.caption("사이즈 정보가 없습니다.")
