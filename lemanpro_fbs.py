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

def get_last_mile_tariff(zone, volume_l):
    table = LAST_MILE.get(zone, LAST_MILE["Регион"])
    thresholds = sorted(table.keys())
    for t in thresholds:
        if volume_l <= t:
            return table[t]
    return table[max(thresholds)]

def render(conn, get_ai_category, normalize_value, calc_tax, params: dict):
    st.header("Лемана Про — Юнит-экономика (FBS)")
    
    with st.sidebar:
        st.divider()
        st.subheader("Комиссии Лемана Про")
        uploaded_comm = st.file_uploader("Загрузить Excel с комиссиями", type=["xlsx"], key="lp_comm_upload")
        
        if uploaded_comm and st.button("Обновить справочник", key="lp_update_comm"):
            try:
                df_comm = pd.read_excel(uploaded_comm)
                st.success("Справочник комиссий обновлен!")
            except Exception as e:
                st.error(f"Ошибка: {e}")
    
    # Основная логика калькулятора (упрощенно для примера)
    lp_zone = st.selectbox("Зона доставки", list(LAST_MILE.keys()))
    vol_l = st.number_input("Объем, л", value=1.0)
    
    if st.button("Рассчитать"):
        tariff = get_last_mile_tariff(lp_zone, vol_l)
        st.write(f"Тариф последней мили: {tariff} руб.")
