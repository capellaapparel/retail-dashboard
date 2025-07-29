import pandas as pd
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from dateutil import parser

GOOGLE_SHEET_URL = "https://docs.google.com/spreadsheets/d/1oyVzCgGK1Q3Qi_sbYwE-wKG6SArnfUDRe7rQfGOF-Eo"

def load_google_sheet(sheet_name, st_secrets):
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive"
    ]
    json_data = {k: str(v) for k, v in st_secrets["gcp_service_account"].items()}
    with open("/tmp/service_account.json", "w") as f:
        json.dump(json_data, f)
    creds = ServiceAccountCredentials.from_json_keyfile_name("/tmp/service_account.json", scope)
    client = gspread.authorize(creds)
    sheet = client.open_by_url(GOOGLE_SHEET_URL).worksheet(sheet_name)
    data = sheet.get_all_records()
    df = pd.DataFrame(data)
    df.columns = [c.lower().strip() for c in df.columns]
    return df

def parse_temudate(dt):
    try:
        return parser.parse(str(dt).split('(')[0].strip(), fuzzy=True)
    except Exception:
        return pd.NaT

def parse_sheindate(dt):
    try:
        return pd.to_datetime(str(dt), errors="coerce", infer_datetime_format=True)
    except Exception:
        return pd.NaT

def load_sales_data(secrets=None):
    # secrets 파라미터는 streamlit_app.py처럼 넘겨줘야함
    PRODUCT_SHEET = "PRODUCT_INFO"
    SHEIN_SHEET = "SHEIN_SALES"
    TEMU_SHEET = "TEMU_SALES"
    GOOGLE_SHEET_URL = "https://docs.google.com/spreadsheets/d/1oyVzCgGK1Q3Qi_sbYwE-wKG6SArnfUDRe7rQfGOF-Eo"

    from utils import load_google_sheet   # 이미 utils에 있으면 생략

    df_shein = load_google_sheet(SHEIN_SHEET, secrets)
    df_temu = load_google_sheet(TEMU_SHEET, secrets)

    df_shein["order date"] = df_shein["order processed on"].apply(parse_sheindate)
    df_temu["order date"]  = df_temu["purchase date"].apply(parse_temudate)

    shein_sales = df_shein.rename(columns={
        "product description": "product number",
        "qty": "qty",
        "product price": "unit price"
    }).copy()
    shein_sales["platform"] = "SHEIN"
    shein_sales["qty"] = pd.to_numeric(shein_sales["qty"], errors="coerce").fillna(0)
    shein_sales["sales"] = shein_sales["qty"] * pd.to_numeric(shein_sales["unit price"], errors="coerce").fillna(0)

    temu_sales = df_temu.rename(columns={
        "product number": "product number",
        "qty": "qty",
        "base price total": "unit price"
    }).copy()
    temu_sales["platform"] = "TEMU"
    temu_sales["qty"] = pd.to_numeric(temu_sales["qty"], errors="coerce").fillna(0)
    temu_sales["sales"] = temu_sales["qty"] * pd.to_numeric(temu_sales["unit price"], errors="coerce").fillna(0)

    df_all = pd.concat([shein_sales, temu_sales], ignore_index=True)
    df_all = df_all[df_all["order date"].notna()]
    return df_all


def show_price_block(st, label, value):
    if value not in ("", None, float("nan")) and str(value).strip() not in ("", "nan", "NaN"):
        try:
            v = str(value).strip()
            if v.startswith("$"):
                price = v
            else:
                price = f"${v}"
            st.markdown(f"**{label}:** {price}")
        except:
            st.markdown(f"**{label}:** {value}")

def get_latest_shein_price(df_sales, product_number):
    filtered = df_sales[
        df_sales["product description"].astype(str).str.strip().str.upper() == str(product_number).strip().upper()
    ]
    if not filtered.empty:
        filtered = filtered.copy()
        filtered["order date"] = pd.to_datetime(filtered["order processed on"], errors="coerce")
        filtered = filtered.dropna(subset=["order date"])
        if not filtered.empty:
            latest = filtered.sort_values("order date").iloc[-1]
            price = latest["product price"]
            try:
                price = float(str(price).replace("$", "").replace(",", ""))
                return f"${price:.2f}"
            except:
                return "NA"
    return "NA"

def get_latest_temu_price(df_temu, product_number):
    filtered = df_temu[
        df_temu["product number"].astype(str).str.strip().str.upper() == str(product_number).strip().upper()
    ]
    if not filtered.empty:
        filtered = filtered.copy()
        filtered["order date"] = filtered["purchase date"].apply(parse_temudate)
        filtered = filtered.dropna(subset=["order date"])
        if not filtered.empty:
            latest = filtered.sort_values("order date").iloc[-1]
            price = latest["base price total"]
            try:
                price = float(str(price).replace("$", "").replace(",", ""))
                return f"${price:.2f}"
            except:
                return "NA"
    return "NA"
