# citilink.py
import streamlit as st
import pandas as pd

# ─────────────────────────────────────────────────────────────────────────────
# 1. СПРАВОЧНИКИ КОМИССИЙ (Placeholder)
# ─────────────────────────────────────────────────────────────────────────────
CATEGORY_COMMISSIONS = {
    "Компьютеры и комплектующие (9%)": 9.0,
    "Периферия и аксессуары (11%)": 11.0,
    "Телевизоры и аудио (10%)": 10.0,
    "Смартфоны и планшеты (8%)": 8.0,
    "Бытовая техника (12%)": 12.0,
    "Садовая техника (13%)": 13.0,
}

# ─────────────────────────────────────────────────────────────────────────────
# 2. ТАРИФЫ ЛОГИСТИКИ (Citilink FBS Placeholder)
# ─────────────────────────────────────────────────────────────────────────────
def get_logistics_tariff(weight_kg):
    # Условный тариф: фиксированный 120 руб + 40 руб за крупногабарит (> 20 кг)
    base = 120.0
    extra = 40.0 if weight_kg > 20 else 0.0
    return base + extra

def render(conn, get_ai_category, normalize_value, calc_tax, params: dict):
    st.header("Ситилинк — Юнит-экономика (FBS)")

    # ── Боковая панель: настройки комиссий ──────────────────────────────────
    with st.sidebar:
        st.divider()
        st.subheader("Комиссии Ситилинк")
        uploaded_comm = st.file_uploader(
            "Загрузить Excel с комиссиями", type=["xlsx"], key="cl_comm_upload"
        )
        if uploaded_comm and st.button("Обновить справочник", key="cl_update_comm"):
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
                    st.session_state["cl_commissions"] = new_comm
                    st.success(f"Обновлено {len(new_comm)} категорий")
                else:
                    st.warning("Не удалось распознать категории в файле.")
            except Exception as e:
                st.error(f"Ошибка: {e}")

        if "cl_commissions" in st.session_state:
            st.caption(f"В кэше: {len(st.session_state['cl_commissions'])} категорий (из Excel)")
        else:
            st.caption(f"Используется справочник по умолчанию ({len(CATEGORY_COMMISSIONS)} категорий)")

    commissions: dict = st.session_state.get("cl_commissions", CATEGORY_COMMISSIONS)

    # ── Блок 1: Каталог товаров ─────────────────────────────────────────────
    with st.expander("Блок 1. Каталог товаров", expanded=True):
        col_a, col_b = st.columns(2)
        with col_a:
            dim_unit = st.selectbox("Единица размеров", ["см", "мм"], key="cl_dim")
        with col_b:
            wt_unit = st.selectbox("Единица веса", ["кг", "г"], key="cl_wt")

        uploaded = st.file_uploader(
            "Excel: SKU | Название | Длина | Ширина | Высота | Вес | Себестоимость",
            type=["xlsx", "xls"],
            key="cl_upload"
        )

        if uploaded and st.button("Сохранить в каталог", key="cl_save"):
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
        if st.button("Рассчитать РРЦ для всего каталога", key="cl_calc"):
            target_m = params["target_margin"]
            acq = params["acquiring"]
            ep = params["early_payout"]
            mkt = params["marketing"]
            extra_c = params["extra_costs"]
            extra_l = params["extra_logistics"]
            tax_regime = params["tax_regime"]

            results = []
            for p in all_products:
                sku, name, l, w, h, wt, cost = p
                cost = cost or 0.0

                # Логистика Ситилинк
                logistics_cl = get_logistics_tariff(wt)
                logistics_total = logistics_cl + extra_l

                # AI Классификация
                category = get_ai_category(name, cat_list, conn, "citilink")
                commission = commissions.get(category, 0.0)

                # Формула РРЦ
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
                    "Логистика Ситилинк, руб": logistics_cl,
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
                "citilink_rrc_results.csv",
                mime="text/csv"
            )
