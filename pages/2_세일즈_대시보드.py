if page == "📊 세일즈 대시보드":
    try:
        df_shein = load_google_sheet(SHEIN_SHEET)
        df_temu = load_google_sheet(TEMU_SHEET)
    except Exception as e:
        st.error("❌ 데이터 로드 실패: " + str(e))
        st.stop()

    df_shein["order date"] = df_shein["order processed on"].apply(parse_sheindate)
    df_temu["order date"] = df_temu["purchase date"].apply(parse_temudate)

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

    st.sidebar.subheader("플랫폼")
    platform_filter = st.sidebar.radio("플랫폼", ["BOTH", "SHEIN", "TEMU"], horizontal=True)
    st.sidebar.subheader("조회 기간")
    min_date = df_all["order date"].min()
    max_date = df_all["order date"].max()
    date_range = st.sidebar.date_input("기간", (min_date, max_date))

    df_view = df_all.copy()
    if platform_filter != "BOTH":
        df_view = df_view[df_view["platform"] == platform_filter]
    df_view = df_view[(df_view["order date"] >= pd.to_datetime(date_range[0])) & (df_view["order date"] <= pd.to_datetime(date_range[1]))]

    total_qty = int(df_view["qty"].sum())
    total_sales = df_view["sales"].sum()
    order_count = df_view.shape[0]

    colA, colB, colC = st.columns(3)
    colA.metric("총 판매수량", f"{total_qty:,}")
    colB.metric("총 매출", f"${total_sales:,.2f}")
    colC.metric("주문건수", f"{order_count:,}")

    st.subheader("일별 판매 추이")
    daily = df_view.groupby("order date").agg({"qty": "sum", "sales": "sum"}).reset_index()
    st.line_chart(daily.set_index("order date")[["qty", "sales"]])

    st.subheader("베스트셀러 TOP10")
    best = df_view.groupby("product number").agg({"qty": "sum", "sales": "sum"}).reset_index()
    best = best.sort_values("qty", ascending=False).head(10)
    st.dataframe(best)

    st.subheader("플랫폼별 매출 비율")
    platform_stats = df_view.groupby("platform")["sales"].sum()
    st.bar_chart(platform_stats)
