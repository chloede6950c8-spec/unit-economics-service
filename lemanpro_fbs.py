# lemanpro_fbs.py
import streamlit as st
import pandas as pd

# ─────────────────────────────────────────────────────────────────────────────
# 1. СПРАВОЧНИКИ КОМИССИЙ (Sheet 1: Комиссия_FBS и FBO)
# ─────────────────────────────────────────────────────────────────────────────
CATEGORY_COMMISSIONS = {
    "Блоки, кирпич, бетон (6%)": 6,
    "Арматура / крепёжные элементы (6%)": 6,
    "Сухие смеси / цемент (6%)": 6,
    "Кровельные покрытия (9%)": 9,
    "Теплоизоляция (10%)": 10,
    "Гидроизоляция / пароизоляция (10%)": 10,
    "Сэндвич-панели (10%)": 10,
}

# ─────────────────────────────────────────────────────────────────────────────
# 2. ТАРИФЫ «ПОСЛЕДНЯЯ МИЛЯ» (Sheet 3: Тарифы Последняя миля)
# ─────────────────────────────────────────────────────────────────────────────
# Формат: {зона: {вес_порог: тариф}}
LAST_MILE = {
    "Внутри зоны": {
        1: 143, 3: 150, 5: 157, 10: 201, 15: 218, 20: 253, 30: 311, 50: 524, 80: 593, 100: 615, 120: 682
    },
    "СПБ и ЛО": {
        1: 139, 3: 154, 5: 172, 10: 216, 15: 253, 20: 288, 30: 343, 50: 442, 80: 558, 100: 660, 120: 762
    },
    "Регион": {
        1: 142, 3: 177, 5: 206, 10: 239, 15: 276, 20: 306, 30: 368, 50: 552, 80: 888, 100: 1101, 120: 1257
    }
}


def get_last_mile_tariff(zone, weight_kg):
    table = LAST_MILE.get(zone, LAST_MILE["Регион"])
    thresholds = sorted(table.keys())
    for t in thresholds:
        if weight_kg <= t:
            return table[t]
    return table[max(thresholds)]


def render(conn, get_ai_category, normalize_value, calc_tax, params: dict):
    st.header("Лемана Про — Юнит-экономика (FBS)")

    # ── Боковая панель: настройки комиссий ──────────────────────────────────
    with st.sidebar:
        st.divider()
        st.subheader("Комиссии Лемана Про")
        uploaded_comm = st.file_uploader(
            "Загрузить Excel с комиссиями", type=["xlsx"], key="lp_comm_upload"
        )
        if uploaded_comm and st.button("Обновить справочник", key="lp_update_comm"):
            try:
                df_comm = pd.read_excel(uploaded_comm)
                new_comm = {}
                for _, row in df_comm.iterrows():
                    cols = list(df_comm.columns)
                    name = str(row[cols[0]]).strip()
                    try:
                        val = float(str(row[cols[1]]).replace(",", "."))
                        if name and 0 < val < 100:
                            new_comm[name] = val
                    except (ValueError, TypeError):
                        pass
                if new_comm:
                    st.session_state["lp_commissions"] = new_comm
                    st.success(f"Обновлено {len(new_comm)} категорий")
                else:
                    st.warning("Не удалось распознать категории в файле.")
            except Exception as e:
                st.error(f"Ошибка: {e}")

        if "lp_commissions" in st.session_state:
            st.caption(f"В кэше: {len(st.session_state['lp_commissions'])} категорий (из Excel)")
        else:
            st.caption(f"Используется справочник по умолчанию ({len(CATEGORY_COMMISSIONS)} категорий)")

        st.divider()
        st.subheader("Зона доставки")
        lp_zone = st.selectbox(
            "Зона последней мили",
            list(LAST_MILE.keys()),
            key="lp_zone"
        )

    commissions: dict = st.session_state.get("lp_commissions", CATEGORY_COMMISSIONS)

    # ── Блок 1: Каталог товаров ─────────────────────────────────────────────
    with st.expander("Блок 1. Каталог товаров", expanded=True):
        col_a, col_b = st.columns(2)
        with col_a:
            dim_unit = st.selectbox("Единица размеров", ["см", "мм"], key="lp_dim")
        with col_b:
            wt_unit = st.selectbox("Единица веса", ["кг", "г"], key="lp_wt")

        uploaded = st.file_uploader(
            "Excel: SKU | Название | Длина | Ширина | Высота | Вес | Себестоимость",
            type=["xlsx", "xls"],
            key="lp_upload"
        )
        if uploaded and st.button("Сохранить в каталог", key="lp_save"):
            df = pd.read_excel(uploaded)
            df.columns = [str(c).strip() for c in df.columns]
            saved = skipped = 0
            cur = conn.cursor()
            for _, row in df.iterrows():
                try:
                    sku = str(row.get("SKU", row.get("Артикул", ""))).strip()
                    name = str(row.get("Название", row.get("Наименование", ""))).strip()
                    if not sku or not name:
                        skipped += 1
                        continue
                    l = normalize_value(row.get("Длина", 0), dim_unit)
                    w = normalize_value(row.get("Ширина", 0), dim_unit)
                    h = normalize_value(row.get("Высота", 0), dim_unit)
                    wt = normalize_value(row.get("Вес", 0), wt_unit)
                    cost = float(
                        str(row.get("Себестоимость", row.get("Закупка", 0))).replace(",", ".") or 0
                    )
                    cur.execute("""
                        INSERT INTO products (sku, name, length_cm, width_cm, height_cm, weight_kg, cost)
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
            df_show = pd.DataFrame(
                all_products,
                columns=["SKU", "Название", "Длина, см", "Ширина, см", "Высота, см", "Вес, кг", "Себестоимость, руб"]
            )
            st.dataframe(df_show, use_container_width=True)
        else:
            st.info("Каталог пуст. Загрузите Excel.")

    all_products = conn.execute(
        "SELECT sku, name, length_cm, width_cm, height_cm, weight_kg, cost FROM products"
    ).fetchall()
    if not all_products:
        st.warning("Загрузите каталог товаров для расчёта.")
        return

    # ── Блок 2: Расчёт юнит-экономики ──────────────────────────────────────
    with st.expander("Блок 2. Расчёт юнит-экономики", expanded=True):
        cat_list = list(commissions.keys())

        if st.button("Рассчитать РРЦ для всего каталога", key="lp_calc"):
            target_m = params["target_margin"]
            acq = params["acquiring"]
            ep = params["early_payout"]
            mkt = params["marketing"]
            extra_c = params["extra_costs"]
            extra_l = params["extra_logistics"]
            tax_regime = params["tax_regime"]
            zone = st.session_state.get("lp_zone", "Регион")

            results = []
            for p in all_products:
                sku, name, l, w, h, wt, cost = p
                cost = cost or 0.0

                logistics_lp = get_last_mile_tariff(zone, wt)
                logistics_total = logistics_lp + extra_l

                category = get_ai_category(name, cat_list, conn, "lemanpro")
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
                    tax, profit_after, margin_after = calc_tax(
                        rrc,
                        cost + logistics_total + extra_c + percent_costs,
                        tax_regime
                    )
                else:
                    profit_before = margin_before = tax = profit_after = margin_after = 0.0

                results.append({
                    "SKU": sku,
                    "Название": name,
                    "Вес, кг": round(wt, 3),
                    "Зона": zone,
                    "Последняя миля, руб": logistics_lp,
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
                "lemanpro_rrc_results.csv",
                mime="text/csv"
            )
