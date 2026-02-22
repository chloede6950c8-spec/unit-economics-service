# mvideo.py — модуль М.Видео FBS
import streamlit as st
import pandas as pd
import pdfplumber
import requests
from io import BytesIO

COMMISSIONS_PDF_URL = (
    "https://static.mvideo.ru/media/Promotions/Promo_Page/2025/September/"
    "marketplace/applications/applications-1new.pdf"
)

# Тарифы логистики FBS (applications-2-v2.pdf, 2026)
LOGISTICS = {"S": 109, "M": 149, "L": 259, "XL": 259}


def classify_size(length_cm: float, width_cm: float,
                  height_cm: float, weight_kg: float) -> str:
    vol = (length_cm * width_cm * height_cm) / 1000.0  # дм3
    if weight_kg <= 1 and vol <= 27:
        return "S"
    elif weight_kg <= 5 and vol <= 54:
        return "M"
    elif weight_kg <= 25 and vol <= 160:
        return "L"
    else:
        return "XL"


def parse_pdf_commissions(url: str) -> dict:
    try:
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        result = {}
        with pdfplumber.open(BytesIO(r.content)) as pdf:
            for page in pdf.pages:
                table = page.extract_table()
                if not table:
                    continue
                for row in table:
                    if not row or len(row) < 2:
                        continue
                    name = str(row[-2] or "").strip()
                    val  = str(row[-1] or "").strip().replace(",", ".")
                    try:
                        pct = float(val)
                        if name and 0 < pct < 100:
                            result[name] = pct
                    except ValueError:
                        pass
        return result
    except Exception as e:
        st.error(f"Ошибка загрузки PDF комиссий М.Видео: {e}")
        return {}


def render(conn, get_ai_category, normalize_value, calc_tax, params: dict):
    st.header("М.Видео — Юнит-экономика (FBS)")

    # Обновление комиссий — в боковой панели
    with st.sidebar:
        st.divider()
        st.subheader("Комиссии М.Видео")
        if st.button("Обновить комиссии из PDF", key="mv_update_comm"):
            with st.spinner("Загружаю PDF..."):
                comms = parse_pdf_commissions(COMMISSIONS_PDF_URL)
            if comms:
                st.session_state["mvideo_commissions"] = comms
                st.success(f"Загружено {len(comms)} категорий")
            else:
                st.warning("Не удалось загрузить. Проверьте PDF.")
        if "mvideo_commissions" in st.session_state:
            cnt = len(st.session_state["mvideo_commissions"])
            st.caption(f"В кэше: {cnt} категорий")
        else:
            st.caption("Комиссии не загружены")

    commissions: dict = st.session_state.get("mvideo_commissions", {})

    # Блок 1: Каталог товаров
    with st.expander("Блок 1. Каталог товаров", expanded=True):
        col_a, col_b = st.columns(2)
        with col_a:
            dim_unit = st.selectbox("Единица размеров", ["см", "мм"], key="mv_dim")
        with col_b:
            wt_unit = st.selectbox("Единица веса", ["кг", "г"], key="mv_wt")

        uploaded = st.file_uploader(
            "Excel: SKU | Название | Длина | Ширина | Высота | Вес | Себестоимость",
            type=["xlsx", "xls"], key="mv_upload"
        )
        if uploaded and st.button("Сохранить в каталог", key="mv_save"):
            df = pd.read_excel(uploaded)
            df.columns = [str(c).strip() for c in df.columns]
            saved = skipped = 0
            cur = conn.cursor()
            for _, row in df.iterrows():
                try:
                    sku  = str(row.get("SKU", row.get("Артикул", ""))).strip()
                    name = str(row.get("Название", row.get("Наименование", ""))).strip()
                    if not sku or not name:
                        skipped += 1
                        continue
                    l  = normalize_value(row.get("Длина",  0), dim_unit)
                    w  = normalize_value(row.get("Ширина", 0), dim_unit)
                    h  = normalize_value(row.get("Высота", 0), dim_unit)
                    wt = normalize_value(row.get("Вес",    0), wt_unit)
                    cost = float(str(row.get("Себестоимость", row.get("Закупка", 0))).replace(",", ".") or 0)
                    cur.execute("""
                        INSERT INTO products
                            (sku, name, length_cm, width_cm, height_cm, weight_kg, cost)
                        VALUES (?,?,?,?,?,?,?)
                        ON CONFLICT(sku) DO UPDATE SET
                            name=excluded.name,
                            length_cm=excluded.length_cm,
                            width_cm=excluded.width_cm,
                            height_cm=excluded.height_cm,
                            weight_kg=excluded.weight_kg,
                            cost=excluded.cost
                    """, (sku, name, l, w, h, wt, cost))
                    saved += 1
                except Exception:
                    skipped += 1
            conn.commit()
            st.success(f"Сохранено: {saved}, пропущено: {skipped}")

        all_products = conn.execute(
            "SELECT sku, name, length_cm, width_cm, height_cm, weight_kg, cost FROM products"
        ).fetchall()
        if all_products:
            df_show = pd.DataFrame(all_products,
                columns=["SKU", "Название", "Длина, см", "Ширина, см", "Высота, см", "Вес, кг", "Себестоимость, руб"])
            st.dataframe(df_show, use_container_width=True)
        else:
            st.info("Каталог пуст. Загрузите Excel.")

    all_products = conn.execute(
        "SELECT sku, name, length_cm, width_cm, height_cm, weight_kg, cost FROM products"
    ).fetchall()

    if not all_products:
        st.warning("Загрузите каталог товаров для расчёта.")
        return

    if not commissions:
        st.warning("Нажмите 'Обновить комиссии из PDF' в боковом меню.")
        return

    # Блок 2: Расчёт
    with st.expander("Блок 2. Расчёт юнит-экономики", expanded=True):
        cat_list = list(commissions.keys())

        if st.button("Рассчитать РРЦ для всего каталога", key="mv_calc"):
            target_m    = params["target_margin"]
            acq         = params["acquiring"]
            ep          = params["early_payout"]
            mkt         = params["marketing"]
            extra_c     = params["extra_costs"]
            extra_l     = params["extra_logistics"]
            tax_regime  = params["tax_regime"]

            results = []
            for p in all_products:
                sku, name, l, w, h, wt, cost = p
                cost = cost or 0.0

                size_type   = classify_size(l, w, h, wt)
                logistics_mv = LOGISTICS.get(size_type, 259)
                logistics_total = logistics_mv + extra_l

                category = get_ai_category(name, cat_list, conn, "mvideo")
                commission = commissions.get(category, 0.0)

                k_percent = commission + acq + ep + mkt
                denom = 1 - (k_percent / 100) - (target_m / 100)

                if denom > 0 and cost > 0:
                    rrc = (cost + logistics_total + extra_c) / denom
                else:
                    rrc = 0.0

                if rrc > 0:
                    percent_costs = rrc * (k_percent / 100)
                    profit_before = rrc - cost - logistics_total - extra_c - percent_costs
                    margin_before = (profit_before / rrc * 100) if rrc > 0 else 0
                    tax, profit_after, margin_after = calc_tax(rrc, cost + logistics_total + extra_c + percent_costs, tax_regime)
                else:
                    profit_before = margin_before = tax = profit_after = margin_after = 0.0

                results.append({
                    "SKU": sku,
                    "Название": name,
                    "Тип": size_type,
                    "Логистика МВ, руб": logistics_mv,
                    "Категория": category,
                    "Комиссия, %": commission,
                    "Себестоимость, руб": round(cost, 0),
                    "РРЦ, руб": round(rrc, 0),
                    "Прибыль до налога, руб": round(profit_before, 0),
                    "Маржа до налога, %": round(margin_before, 1),
                    "Налог, руб": round(tax, 0),
                    "Прибыль после налога, руб": round(profit_after, 0),
                    "Маржа после налога, %": round(margin_after, 1),
                })

            res_df = pd.DataFrame(results)
            st.subheader("Результаты расчёта")
            st.dataframe(res_df, use_container_width=True)
            st.download_button(
                "Скачать результат (CSV)",
                res_df.to_csv(index=False).encode("utf-8"),
                "mvideo_rrc_results.csv",
                mime="text/csv"
            )
