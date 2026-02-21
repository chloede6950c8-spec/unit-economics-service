import streamlit as st
import pandas as pd

st.title("Сервис юнит-экономики — М.Видео")

st.header("Параметры ритейлера")

commission = st.number_input("Комиссия (%)", value=15.0)
retro = st.number_input("Ретро (%)", value=5.0)
marketing = st.number_input("Маркетинг (%)", value=3.0)
bonus = st.number_input("Бонус (%)", value=2.0)
acquiring = st.number_input("Эквайринг (%)", value=1.5)

k_var = (commission + retro + marketing + bonus + acquiring) / 100

st.divider()

st.header("Массовый расчёт (загрузка Excel)")

uploaded_file = st.file_uploader("Загрузите Excel с колонками: name, purchase_price, logistics_fix")

target_margin = st.number_input("Целевая маржа (%)", value=20.0) / 100

if uploaded_file:

    df = pd.read_excel(uploaded_file)

    def calculate_price(row):
        denominator = 1 - k_var - target_margin
        if denominator <= 0:
            return None
        return (row["purchase_price"] + row["logistics_fix"]) / denominator

    df["calculated_price"] = df.apply(calculate_price, axis=1)

    st.success("Расчёт выполнен")
    st.dataframe(df)

    st.download_button(
        "Скачать результат",
        df.to_csv(index=False).encode("utf-8"),
        "result.csv",
        "text/csv"
    )