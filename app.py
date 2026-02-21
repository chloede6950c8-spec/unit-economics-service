import streamlit as st
import pandas as pd

st.set_page_config(page_title="Сервис юнит-экономики", layout="wide")

st.title("📊 Сервис расчёта юнит-экономики — М.Видео")

st.markdown("""
Этот сервис рассчитывает **рекомендованную розничную цену (РРЦ)**  
при заданной целевой маржинальности.

Формула расчёта:

Цена = (Закупка + Логистика) / (1 - %переменных затрат - Целевая маржа)
""")

st.divider()

# --------------------------
# ПАРАМЕТРЫ РИТЕЙЛЕРА
# --------------------------

st.header("🏪 Условия ритейлера")

col1, col2, col3 = st.columns(3)

with col1:
    commission = st.number_input("Комиссия, %", value=15.0)
    retro = st.number_input("Ретро-бонус, %", value=5.0)

with col2:
    marketing = st.number_input("Маркетинг, %", value=3.0)
    bonus = st.number_input("Бонус, %", value=2.0)

with col3:
    acquiring = st.number_input("Эквайринг, %", value=1.5)
    target_margin = st.number_input("Целевая маржа, %", value=20.0)

k_var = (commission + retro + marketing + bonus + acquiring) / 100
target_margin = target_margin / 100

st.divider()

# --------------------------
# ШАБЛОН
# --------------------------

st.header("📥 Шаблон для загрузки")

template_df = pd.DataFrame({
    "name": ["Товар 1", "Товар 2"],
    "purchase_price": [1000, 2000],
    "logistics_fix": [100, 150]
})

st.download_button(
    "Скачать шаблон Excel",
    template_df.to_csv(index=False).encode("utf-8"),
    "template.csv",
    "text/csv"
)

st.info("""
📌 В Excel-файле должны быть колонки:

- name — название товара  
- purchase_price — закупочная цена  
- logistics_fix — фиксированная логистика на единицу
""")

st.divider()

# --------------------------
# ЗАГРУЗКА ФАЙЛА
# --------------------------

st.header("📤 Загрузка файла для расчёта")

uploaded_file = st.file_uploader("Загрузите файл Excel или CSV")

if uploaded_file:

    df = pd.read_excel(uploaded_file) if uploaded_file.name.endswith("xlsx") else pd.read_csv(uploaded_file)

    denominator = 1 - k_var - target_margin

    if denominator <= 0:
        st.error("❌ Целевая маржа слишком высокая для заданных условий.")
    else:
        df["РРЦ"] = (df["purchase_price"] + df["logistics_fix"]) / denominator
        df["Прибыль"] = df["РРЦ"] * (1 - k_var) - df["purchase_price"] - df["logistics_fix"]
        df["Фактическая маржа, %"] = (df["Прибыль"] / df["РРЦ"]) * 100

        st.success("✅ Расчёт выполнен")

        st.dataframe(df)

        st.download_button(
            "📥 Скачать результат",
            df.to_csv(index=False).encode("utf-8"),
            "result.csv",
            "text/csv"
        )
