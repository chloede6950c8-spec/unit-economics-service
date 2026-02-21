import streamlit as st
import pandas as pd
import sqlite3
import pdfplumber
from openai import OpenAI
import os

# --- КОНФИГУРАЦИЯ ---
st.set_page_config(page_title="Unit Economics AI", layout="wide")

# Ввод API ключа (лучше хранить в st.secrets на Streamlit Cloud)
api_key = st.sidebar.text_input("OpenAI API Key", type="password")
client = OpenAI(api_key=api_key) if api_key else None

# --- РАБОТА С БАЗОЙ ДАННЫХ (ПАМЯТЬ) ---
conn = sqlite3.connect('economics_data.db', check_same_thread=False)
cursor = conn.cursor()

# Создаем таблицы, если их нет
cursor.execute('''CREATE TABLE IF NOT EXISTS product_cache 
                  (name TEXT PRIMARY KEY, category TEXT)''')
cursor.execute('''CREATE TABLE IF NOT EXISTS commissions 
                  (category TEXT PRIMARY KEY, rate REAL)''')
conn.commit()

# --- ФУНКЦИИ ---

def parse_mvideo_pdf(uploaded_file):
    """Парсит PDF и вытаскивает категории и комиссии"""
    data = []
    with pdfplumber.open(uploaded_file) as pdf:
        for page in pdf.pages:
            table = page.extract_table()
            if table:
                # Здесь логика очистки: обычно категория в одном столбце, % в другом
                for row in table:
                    if row[0] and "%" in str(row[-1]):
                        category = row[0].strip()
                        try:
                            rate = float(str(row[-1]).replace('%', '').replace(',', '.'))
                            data.append((category, rate))
                        except:
                            continue
    # Сохраняем в базу
    cursor.executemany("INSERT OR REPLACE INTO commissions VALUES (?, ?)", data)
    conn.commit()
    return len(data)

def get_category_via_ai(product_name, available_categories):
    """Использует ИИ, чтобы сопоставить товар с категорией из М.Видео"""
    # 1. Проверяем в кэше
    cursor.execute("SELECT category FROM product_cache WHERE name=?", (product_name,))
    result = cursor.fetchone()
    if result:
        return result[0]

    # 2. Если нет в кэше — спрашиваем OpenAI
    if not client:
        return "Не определено (нужен API ключ)"
    
    prompt = f"У меня есть товар: '{product_name}'. Выбери для него наиболее подходящую категорию из списка: {', '.join(available_categories)}. Ответь только названием категории."
    
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}]
    )
    category = response.choices[0].message.content.strip()
    
    # 3. Сохраняем в кэш
    cursor.execute("INSERT OR REPLACE INTO product_cache VALUES (?, ?)", (product_name, category))
    conn.commit()
    return category

# --- ИНТЕРФЕЙС STREAMLIT ---

st.title("📊 Умная юнит-экономика М.Видео")

with st.sidebar:
    st.header("Настройки базы")
    pdf_file = st.file_uploader("Загрузить PDF с комиссиями", type="pdf")
    if pdf_file and st.button("Обновить справочник комиссий"):
        count = parse_mvideo_pdf(pdf_file)
        st.success(f"Загружено {count} категорий из PDF")

# Проверяем, есть ли данные в базе
cursor.execute("SELECT category FROM commissions")
all_categories = [r[0] for r in cursor.fetchall()]

if not all_categories:
    st.warning("⚠️ Сначала загрузите PDF файл с комиссиями М.Видео в боковом меню.")
else:
    st.header("🚀 Расчёт цен")
    
    # Параметры, которые НЕ зависят от категории
    col1, col2 = st.columns(2)
    with col1:
        retro = st.number_input("Ретро-бонус, %", value=5.0)
        marketing = st.number_input("Маркетинг, %", value=3.0)
    with col2:
        acquiring = st.number_input("Эквайринг, %", value=1.5)
        target_margin = st.number_input("Целевая маржа, %", value=20.0)

    uploaded_data = st.file_uploader("Загрузите Excel/CSV с товарами (колонки: name, purchase_price, logistics_fix)")

    if uploaded_data:
        df = pd.read_excel(uploaded_data) if uploaded_data.name.endswith("xlsx") else pd.read_csv(uploaded_data)
        
        if st.button("Начать умный расчёт"):
            with st.spinner("ИИ классифицирует товары и считает цены..."):
                results = []
                for _, row in df.iterrows():
                    # Определяем категорию через ИИ или кэш
                    category = get_category_via_ai(row['name'], all_categories)
                    
                    # Получаем комиссию из нашей базы
                    cursor.execute("SELECT rate FROM commissions WHERE category=?", (category,))
                    comm_rate = cursor.fetchone()[0]
                    
                    # Считаем РРЦ
                    # k_var = (Комиссия + Ретро + Маркетинг + Эквайринг) / 100
                    k_var = (comm_rate + retro + marketing + acquiring) / 100
                    margin_dec = target_margin / 100
                    
                    denominator = 1 - k_var - margin_dec
                    if denominator > 0:
                        rrc = (row['purchase_price'] + row['logistics_fix']) / denominator
                    else:
                        rrc = 0
                        
                    results.append({
                        "Товар": row['name'],
                        "Категория (ИИ)": category,
                        "Комиссия М.Видео": f"{comm_rate}%",
                        "Закупка": row['purchase_price'],
                        "РРЦ": round(rrc, 2)
                    })
                
                res_df = pd.DataFrame(results)
                st.dataframe(res_df)
                
                st.download_button("Скачать результат", res_df.to_csv(index=False).encode("utf-8"), "results.csv")
