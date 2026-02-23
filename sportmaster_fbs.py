# sportmaster_fbs.py
import streamlit as st
import pandas as pd

# ─────────────────────────────────────────────────────────────────────────────
# 1. СПРАВОЧНИК КОМИССИЙ (из Базы Знаний, с 01.02.2026)
# ─────────────────────────────────────────────────────────────────────────────
CATEGORY_COMMISSIONS = {
    "SUP и аксессуары": 32,
    "Автотуризм": 25,
    "Аксессуары для велоспорта": 35,
    "Аксессуары для водного туризма": 30,
    "Аксессуары для горных и беговых лыж": 31,
    "Аксессуары для единоборств": 32,
    "Аксессуары для лодок": 29,
    "Аксессуары для лыжероллеров": 29,
    "Аксессуары для настольного тенниса": 35,
    "Аксессуары для носимых устройств": 35,
    "Аксессуары для оптики": 32,
    "Аксессуары для ракеточных видов спорта": 35,
    "Аксессуары для роликовых коньков, скейтбордов и самокатов": 33,
    "Аксессуары для силовых тренировок": 33,
    "Аксессуары для флорбола": 33,
    "Аксессуары для хоккея": 30,
    "Аксессуары и запчасти для вейкбординга, вейкфойлинга, виндсерфинга, серфинга, кайтсерфинга": 35,
    "Аксессуары и инвентарь для плавания": 35,
    "Бассейны и аксессуары": 28,
    "Батуты": 28,
    "Беговелы": 34,
    "Беговые лыжи": 31,
    "Белье и форма для хоккея": 31,
    "Бильярд": 32,
    "Ботинки для беговых лыж": 31,
    "Брусья и турники": 32,
    "Вейдерсы": 38,
    "Вейкбординг, вейкфойлинг, виндсерфинг, серфинг, кайтсерфинг": 35,
    "Велозащита": 35,
    "Велокомпоненты": 35,
    "Велокомпьютеры": 28,
    "Велообувь": 32,
    "Велоодежда": 35,
    "Велосипеды": 22,
    "Велостанки": 25,
    "Гидрокостюмы, одежда и обувь для водного спорта": 33,
    "Гироскутеры, роллерсерфы": 22,
    "Гольф": 32,
    "Горные лыжи, сноуборды, ботинки, крепления": 32,
    "Дартс": 35,
    "Дорожные аксессуары": 30,
    "Защита для роликовых коньков, скейтбордов и самокатов": 33,
    "Защита для хоккея": 31,
    "Защита, шлемы, маски для горнолыжного спорта": 31,
    "Зонты": 33,
    "Игры для активного отдыха": 33,
    "Инвентарь для альпинизма и скалолазания": 25,
    "Инвентарь для единоборств": 33,
    "Инвентарь для конного спорта": 28,
    "Инвентарь для охоты": 35,
    "Инвентарь для рыбалки": 30,
    "Инвентарь и аксессуары для командных видов спорта": 36,
    "Иные категории": 40,
    "Карповые аксессуары": 31,
    "Катушки": 34,
    "Киберспорт": 22,
    "Клубная атрибутика": 10,
    "Клюшки для флорбола": 32,
    "Клюшки для хоккея": 31,
    "Косметика и спортивная медицина": 33,
    "Ледовые коньки": 31,
    "Лодки, байдарки, катамараны, пакрафты": 28,
    "Лодочные моторы": 28,
    "Луки и арбалеты": 31,
    "Лыжероллеры": 31,
    "Массажеры": 31,
    "Мебель": 32,
    "Мотозащита и мотошлемы": 26,
    "Мототехника": 5,
    "Мотоэкипировка": 26,
    "Навигаторы, рации, солнечные панели, зарядные кемпинговые станции": 25,
    "Насосы": 32,
    "Настольные игры": 30,
    "Наушники": 30,
    "Обувь для взрослых и детей": 39,
    "Обувь для единоборств": 33,
    "Обувь для конного спорта": 32,
    "Обувь для охоты и рыбалки": 40,
    "Одежда для взрослых и детей": 34,
    "Одежда для единоборств": 33,
    "Одежда специальная": 32,
    "Одежные аксессуары": 35,
    "Оптика": 35,
    "Отдых на воде": 35,
    "Палатки": 35,
    "Пейнтбол": 28,
    "Перчатки и защита для единоборств": 32,
    "Прикормки и насадки": 30,
    "Прочие аксессуары": 35,
    "Ракетки и наборы": 35,
    "Ракетки и наборы для настольного тенниса": 35,
    "Роботы для настольного тенниса": 25,
    "Роликовые коньки": 32,
    "Роллер-хоккей и коньки-трансформеры": 31,
    "Рыболовные платформы и аксессуары": 29,
    "Рыболовные приманки и оснастка": 35,
    "Рюкзаки для походов и трекинга": 31,
    "Самокаты": 31,
    "Санки, снегокаты, ледянки и тюбинги": 33,
    "Скейтборды": 32,
    "Снаряжение для туризма, активного отдыха, рыбалки и охоты": 32,
    "Снегоступы": 31,
    "Сноускейты": 32,
    "Солнцезащитные очки": 35,
    "Спальные мешки": 32,
    "Спортивное питание и БАДы": 31,
    "Спортивные комплексы": 36,
    "Столы для настольного тенниса": 30,
    "Сумки и рюкзаки": 38,
    "Суппорты": 35,
    "Таймеры": 28,
    "Тейпы": 35,
    "Товары для животных": 32,
    "Тренажеры": 31,
    "Удилища": 35,
    "Уход за одеждой, обувью и аксессуары": 33,
    "Фитнес-аксессуары": 35,
    "Фотоловушки": 32,
    "Электровелосипеды": 29,
    "Электроника": 28,
    "Электросамокаты и электротранспорт": 29,
    "Эхолоты": 31,
}

# ─────────────────────────────────────────────────────────────────────────────
# 2. ЛОГИСТИКА FBS (с 01.02.2026)
# ─────────────────────────────────────────────────────────────────────────────
def get_fbs_logistics(weight_kg):
    # Округляем в большую сторону до целого
    import math
    w = math.ceil(weight_kg)
    if w <= 2:
        return 220.0
    else:
        return 220.0 + (w - 2) * 90.0

def render(conn, get_ai_category, normalize_value, calc_tax, params: dict):
    st.header("Спортмастер — Юнит-экономика (FBS)")
    
    with st.sidebar:
        st.divider()
        st.subheader("Настройки Спортмастер")
        is_promo = st.checkbox("Льготный период (5% комиссия)", value=False)
        st.caption("Действует первые 2 месяца со дня подписания договора")

    commissions = CATEGORY_COMMISSIONS

    # Блок 1: Каталог товаров
    with st.expander("Блок 1. Каталог товаров", expanded=True):
        col_a, col_b = st.columns(2)
        with col_a:
            dim_unit = st.selectbox("Единица размеров", ["см", "мм"], key="sm_dim")
        with col_b:
            wt_unit = st.selectbox("Единица веса", ["кг", "г"], key="sm_wt")
        
        uploaded = st.file_uploader(
            "Excel: SKU | Название | Длина | Ширина | Высота | Вес | Себестоимость",
            type=["xlsx", "xls"], key="sm_upload"
        )
        
        if uploaded and st.button("Сохранить в каталог", key="sm_save"):
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
                    cost = float(str(row.get("Себестоимость", row.get("Закупка", 0))).replace(",", ".") or 0)
                    
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
            df_show = pd.DataFrame(all_products, columns=["SKU", "Название", "Длина, см", "Ширина, см", "Высота, см", "Вес, кг", "Себестоимость, руб"])
            st.dataframe(df_show, use_container_width=True)
        else:
            st.info("Каталог пуст. Загрузите Excel.")

    all_products = conn.execute(
        "SELECT sku, name, length_cm, width_cm, height_cm, weight_kg, cost FROM products"
    ).fetchall()
    
    if not all_products:
        st.warning("Загрузите каталог товаров для расчёта.")
        return

    # Блок 2: Расчёт
    with st.expander("Блок 2. Расчёт юнит-экономики", expanded=True):
        cat_list = list(commissions.keys())
        if st.button("Рассчитать РРЦ для всего каталога", key="sm_calc"):
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
                
                # Логистика Спортмастер FBS
                logistics_sm = get_fbs_logistics(wt)
                logistics_total = logistics_sm + extra_l
                
                # Комиссия
                if is_promo:
                    commission = 5.0
                    category = "Льготный период (Все категории)"
                else:
                    category = get_ai_category(name, cat_list, conn, "sportmaster")
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
                    "Вес, кг": round(wt, 2),
                    "Логистика СМ, руб": logistics_sm,
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
                "sportmaster_fbs_results.csv",
                mime="text/csv"
            )
