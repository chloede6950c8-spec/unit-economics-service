import streamlit as st
import sqlite3
import pandas as pd
from openai import OpenAI

import mvideo
import lemanpro_fbs

# --- КОНФИГУРАЦИЯ ---
st.set_page_config(
    page_title="B2B Unit Economics System",
    layout="wide",
    page_icon="📦"
)

# --- ИНИЦИАЛИЗАЦИЯ БД ---
def init_db():
    conn = sqlite3.connect("products_storage.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS products (
            sku TEXT PRIMARY KEY,
            name TEXT,
            length REAL,
            height REAL,
            width REAL,
            weight REAL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS category_cache (
            name TEXT PRIMARY KEY,
            category TEXT
        )
    """)
    conn.commit()
    return conn

conn = init_db()

# --- ИНИЦИАЛИЗАЦИЯ ИИ ---
if "OPENAI_API_KEY" in st.secrets:
    api_key = st.secrets["OPENAI_API_KEY"]
else:
    api_key = st.sidebar.text_input("🔑 OpenAI API Key", type="password")

client = OpenAI(api_key=api_key) if api_key else None

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
def normalize_value(val, unit_type):
    try:
        val = float(str(val).replace(",", "."))
        if unit_type == "dim" and val > 250:
            return val / 10
        if unit_type == "weight" and val > 150:
            return val / 1000
        return val
    except Exception:
        return 0.0

def get_ai_category(product_name, categories):
    cursor = conn.cursor()
    cursor.execute("SELECT category FROM category_cache WHERE name = ?", (product_name,))
    cached = cursor.fetchone()
    if cached:
        return cached[0]
    if not client:
        return "Прочее"
    try:
        prompt = (
            f"Товар: '{product_name}'. "
            f"Выбери ОДНУ категорию из списка: {', '.join(categories)}. "
            f"Ответь только названием категории."
        )
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )
        category = resp.choices[0].message.content.strip()
        cursor.execute("INSERT OR REPLACE INTO category_cache VALUES (?, ?)", (product_name, category))
        conn.commit()
        return category
    except Exception:
        return "Прочее"

def calc_tax(price, profit_before_tax, tax_regime):
    if tax_regime == "ОСНО":
        return max(profit_before_tax, 0) * 0.25
    elif tax_regime == "УСН (Доходы)":
        return price * 0.06
    elif tax_regime == "УСН (Доходы-Расходы)":
        return max(profit_before_tax, 0) * 0.15
    elif tax_regime == "АУСН":
        return price * 0.08
    elif tax_regime == "УСН с НДС 5%":
        return price * 0.11
    elif tax_regime == "УСН с НДС 7%":
        return price * 0.13
    else:
        return 0.0

# --- UI ---
st.title("🚀 Универсальный сервис юнит-экономики")

with st.sidebar:
    st.header("🛒 Настройка ритейлера")
    retailer = st.selectbox(
        "Выберите покупателя",
        ["М.Видео", "Лемана Про (FBS)", "DNS (в разработке)", "Ситилинк (в разработке)"]
    )

# --- РОУТИНГ ПО КЛИЕНТУ ---
if retailer == "М.Видео":
    with st.sidebar:
        mvideo.render(conn, get_ai_category, normalize_value, calc_tax)

elif retailer == "Лемана Про (FBS)":
    lemanpro_fbs.render(conn, get_ai_category, normalize_value, calc_tax)

elif retailer in ["DNS (в разработке)", "Ситилинк (в разработке)"]:
    st.info(f"⏳ Модуль **{retailer}** находится в разработке. Следите за обновлениями!")
