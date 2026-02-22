import streamlit as st
import pandas as pd
import pdfplumber
import requests
from io import BytesIO

COMMISSIONS_PDF_URL = "https://static.mvideo.ru/media/Promotions/Promo_Page/2025/September/marketplace/applications/applications-1new.pdf"
LOGISTICS_PDF_URL = "https://static.mvideo.ru/media/Promotions/Promo_Page/2025/September/marketplace/applications/2026/applications-2-v2.pdf"

LOGISTICS_TARIFFS = {
    "S": 110.0,
    "M": 190.0,
    "L": 1290.0,
}

def parse_pdf_commissions(url):
    data = {}
    try:
        resp = requests.get(url)
        resp.raise_for_status()
        with pdfplumber.open(BytesIO(resp.content)) as pdf:
            for page in pdf.pages:
                tables = page.extract_tables()
                for table in tables:
                    for row in table:
                        clean = [str(c).replace("
", " ").strip() for c in row if c]
                        for cell in clean:
                            if "%" in cell:
                                try:
                                    cat = clean[0]
                                    rate = float(cell.replace("%", "").replace(",", ".").strip())
                                    data[cat] = rate
                                except Exception:
                                    continue
        return data
    except Exception:
        return None

def classify_size(length_cm, height_cm, width_cm):
    if not all([length_cm, height_cm, width_cm]):
        return "S", 0.0, 0.0
    sides = sorted([length_cm, height_cm, width_cm], reverse=True)
    a, b, c = sides
    volume_m3 = (length_cm * height_cm * width_cm) / 1_000_000
    if a > 180 or (a > 120 and b > 120):
        size_type = "XL"
    elif volume_m3 > 0.2:
        size_type = "L"
    elif volume_m3 >= 0.01:
        size_type = "M"
    else:
        size_type = "S"
    tariff_key = "L" if size_type == "XL" else size_type
    mv_logistics = LOGISTICS_TARIFFS.get(tariff_key, 0.0)
    return size_type, volume_m3, mv_logistics

def render(conn, get_ai_category, normalize_value, calc_tax):
    if st.button("🔄 Обновить комиссии из PDF М.Видео"):
        res = parse_pdf_commissions(COMMISSIONS_PDF_URL)
        if res:
            st.session_state["mv_commissions"] = res
            st.success(f"Загружено {len(res)} категорий комиссий")
        else:
            st.error("Не удалось загрузить комиссии из PDF")

    st.header("1. Загрузка базы данных товаров")
    up_file = st.file_uploader(
        "Загрузите Excel (артикул, наименование, себестоимость, длина, высота, ширина, вес)",
        type=["xlsx"], key="mv_upload"
    )
    df_raw = None
    if up_file:
        df_raw = pd.read_excel(up_file)
        df_raw.columns = [c.lower().strip() for c in df_raw.columns]
        if st.button("📥 Сохранить/обновить товары в базе", key="mv_save"):
            cursor = conn.cursor()
            for _, r in df_raw.iterrows():
                l = normalize_value(r.get("длина", 0), "dim")
                h = normalize_value(r.get("высота", 0), "dim")
                w = normalize_value(r.get("ширина", 0), "dim")
                wg = normalize_value(r.get("вес", 0), "weight")
                cursor.execute(
                    "INSERT OR REPLACE INTO products VALUES (?, ?, ?, ?, ?, ?)",
                    (str(r.get("артикул")), str(r.get("наименование")), l, h, w, wg)
                )
            conn.commit()
            st.success("База данных обновлена!")

    st.divider()

    if "mv_commissions" not in st.session_state:
        st.info("Сначала обновите комиссии из PDF М.Видео в боковом меню.")
        return

    st.header("2. Расчёт партии")
    col1, col2, col3, col4 = st.columns(4)
    with col1: target_m = st.number_input("Таргет маржа, %", value=20.0, key="mv_margin")
    with col2: acquiring = st.number_input("Интернет-эквайринг, %", value=1.5, key="mv_acq")
    with col3: marketing = st.number_input("Маркетинг + ретро, %", value=0.0, key="mv_mkt")
    with col4: early_payout = st.number_input("Досрочный вывод, %", value=0.0, key="mv_ep")

    col5, col6 = st.columns(2)
    with col5: extra_costs = st.number_input("Доп. расходы, руб/шт", value=0.0, key="mv_extra")
    with col6: logistics_extra = st.number_input("Доп. логистика продавца, руб/шт", value=0.0, key="mv_logextra")

    tax_regime = st.selectbox("Система налогообложения", [
        "ОСНО", "УСН (Доходы)", "УСН (Доходы-Расходы)", "АУСН", "УСН с НДС 5%", "УСН с НДС 7%"
    ], key="mv_tax")

    if st.button("💸 Рассчитать РРЦ для всех товаров", key="mv_calc"):
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM products")
        all_products = cursor.fetchall()
        results = []
        cat_list = list(st.session_state["mv_commissions"].keys())

        for p in all_products:
            sku, name, l, h, w, weight = p
            size_type, volume_m3, mv_logistics = classify_size(l, h, w)
            cat = get_ai_category(name, cat_list)
            comm = st.session_state["mv_commissions"].get(cat, 15.0)
            cost = 0.0
            if df_raw is not None and "артикул" in df_raw.columns:
                try:
                    cost = float(df_raw[df_raw["артикул"].astype(str) == str(sku)]["себестоимость"].values[0])
                except Exception:
                    cost = 0.0

            logistics_total = mv_logistics + logistics_extra
            k_percent = comm + marketing + acquiring + early_payout
            denom = 1 - (k_percent / 100) - (target_m / 100)
            if denom > 0 and cost > 0:
                rrc = (cost + logistics_total + extra_costs) / denom
            else:
                rrc = 0

            if rrc > 0:
                percent_costs = rrc * (k_percent / 100)
                profit_before_tax = rrc - cost - logistics_total - extra_costs - percent_costs
                tax_amount = calc_tax(rrc, profit_before_tax, tax_regime)
                profit_after_tax = profit_before_tax - tax_amount
                margin_before_tax = (profit_before_tax / rrc) * 100
                margin_after_tax = (profit_after_tax / rrc) * 100
            else:
                percent_costs = profit_before_tax = tax_amount = profit_after_tax = margin_before_tax = margin_after_tax = 0

            results.append({
                "Артикул": sku, "Наименование": name, "Категория": cat,
                "Комиссия, %": round(comm, 2), "Маркетинг, %": round(marketing, 2),
                "Эквайринг, %": round(acquiring, 2), "Досрочный вывод, %": round(early_payout, 2),
                "Тип": size_type, "Объём, м³": round(volume_m3, 4),
                "Логистика М.Видео, руб": round(mv_logistics, 2),
                "Доп. логистика, руб": round(logistics_extra, 2),
                "Доп. расходы, руб": round(extra_costs, 2),
                "Закупка, руб": round(cost, 2), "РРЦ, руб": round(rrc, 0),
                "Прибыль до налога, руб": round(profit_before_tax, 0),
                "Налог, руб": round(tax_amount, 0),
                "Прибыль после налога, руб": round(profit_after_tax, 0),
                "Маржа до налога, %": round(margin_before_tax, 1),
                "Маржа после налога, %": round(margin_after_tax, 1),
            })

        res_df = pd.DataFrame(results)
        st.subheader("Результаты расчёта")
        st.dataframe(res_df, use_container_width=True)
        st.download_button(
            "📥 Скачать результат (CSV)",
            res_df.to_csv(index=False).encode("utf-8"),
            "mvideo_rrc_results.csv", mime="text/csv"
        )
