import streamlit as st
import pandas as pd
import sqlite3
import pdfplumber
import requests
from io import BytesIO
from openai import OpenAI

# --- КОНФИГУРАЦИЯ ---
st.set_page_config(page_title="B2B Unit Economics System", layout="wide", page_icon="📦")

# Константы
DEFAULT_PDF_URL = "https://static.mvideo.ru/media/Promotions/Promo_Page/2025/September/marketplace/applications/applications-1new.pdf"

# --- ИНИЦИАЛИЗАЦИЯ БД (ПАМЯТЬ ТОВАРОВ) ---
def init_db():
    conn = sqlite3.connect('products_storage.db', check_same_thread=False)
    cursor = conn.cursor()
    # Таблица товаров: храним паспортные данные
    cursor.execute('''CREATE TABLE IF NOT EXISTS products 
                      (sku TEXT PRIMARY KEY, name TEXT, length REAL, height REAL, width REAL, weight REAL)''')
    # Таблица кэша категорий ИИ
    cursor.execute('''CREATE TABLE IF NOT EXISTS category_cache 
                      (name TEXT PRIMARY KEY, category TEXT)''')
    conn.commit()
    return conn

conn = init_db()

# --- ИНИЦИАЛИЗАЦИЯ ИИ ---
if "OPENAI_API_KEY" in st.secrets:
    api_key = st.secrets["OPENAI_API_KEY"]
else:
    api_key = st.sidebar.text_input("🔑 OpenAI API Key", type="password")

client = OpenAI(api_key=api_key) if api_key else None

# --- ФУНКЦИИ ОБРАБОТКИ ---

def normalize_value(val, unit_type):
    """Исправление единиц измерения: мм -> см, г -> кг"""
    try:
        val = float(str(val).replace(',', '.'))
        if unit_type == 'dim' and val > 250: return val / 10  # Похоже на мм
        if unit_type == 'weight' and val > 150: return val / 1000  # Похоже на граммы
        return val
    except: return 0.0

def get_ai_category(product_name, categories):
    """ИИ классификация с проверкой кэша"""
    cursor = conn.cursor()
    cursor.execute("SELECT category FROM category_cache WHERE name=?", (product_name,))
    cached = cursor.fetchone()
    if cached: return cached[0]

    if not client: return "Прочее"
    
    try:
        prompt = f"Товар: '{product_name}'. Выбери ОДНУ категорию из списка: {', '.join(categories)}. Ответь только названием."
        resp = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}], temperature=0)
        category = resp.choices[0].message.content.strip()
        cursor.execute("INSERT OR REPLACE INTO category_cache VALUES (?, ?)", (product_name, category))
        conn.commit()
        return category
    except: return "Прочее"

def parse_pdf(url):
    """Парсинг комиссий из PDF"""
    data = {}
    try:
        resp = requests.get(url)
        with pdfplumber.open(BytesIO(resp.content)) as pdf:
            for page in pdf.pages:
                tables = page.extract_tables()
                for table in tables:
                    for row in table:
                        clean = [str(c).replace('\n', ' ').strip() for c in row if c]
                        for cell in clean:
                            if "%" in cell:
                                try:
                                    cat = clean[0]
                                    rate = float(cell.replace('%', '').replace(',', '.').strip())
                                    data[cat] = rate
                                except: continue
        return data
    except: return None

# --- ИНТЕРФЕЙС ---
st.title("🚀 Универсальный сервис юнит-экономики")

with st.sidebar:
    st.header("🛒 Настройка Ритейлера")
    retailer = st.selectbox("Выберите покупателя", ["М.Видео", "DNS (в разработке)", "Ситилинк (в разработке)"])
    if st.button("🔄 Обновить комиссии из PDF"):
        res = parse_pdf(DEFAULT_PDF_URL)
        if res:
            st.session_state['commissions'] = res
            st.success(f"Загружено {len(res)} категорий")

st.header("1. Загрузка базы данных товаров")
up_file = st.file_uploader("Загрузите Excel (артикул, наименование, себестоимость, длина, высота, ширина, вес)", type=["xlsx"])

if up_file:
    df_raw = pd.read_excel(up_file)
    # Приведение колонок к нижнему регистру для поиска
    df_raw.columns = [c.lower().strip() for c in df_raw.columns]
    
    if st.button("📥 Сохранить/Обновить товары в базе"):
        cursor = conn.cursor()
        for _, r in df_raw.iterrows():
            l = normalize_value(r.get('длина', 0), 'dim')
            h = normalize_value(r.get('высота', 0), 'dim')
            w = normalize_value(r.get('ширина', 0), 'dim')
            wg = normalize_value(r.get('вес', 0), 'weight')
            cursor.execute("INSERT OR REPLACE INTO products VALUES (?, ?, ?, ?, ?, ?)",
                           (str(r.get('артикул')), str(r.get('наименование')), l, h, w, wg))
        conn.commit()
        st.success("База данных обновлена!")

st.divider()

if 'commissions' in st.session_state:
    st.header("2. Расчет партии")
    col1, col2, col3 = st.columns(3)
    with col1: target_m = st.number_input("Целевая маржа, %", value=20.0)
    with col2: logistics_base = st.number_input("Фикс. логистика, руб", value=200.0)
    with col3: marketing = st.number_input("Маркетинг + Ретро, %", value=8.0)

    if st.button("💸 Рассчитать РРЦ для всех товаров"):
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM products")
        all_products = cursor.fetchall()
        
        results = []
        cat_list = list(st.session_state['commissions'].keys())
        
        for p in all_products:
            sku, name, l, h, w, weight = p
            cat = get_ai_category(name, cat_list)
            comm = st.session_state['commissions'].get(cat, 15.0)
            
            # Поиск себестоимости в загруженном файле (если он есть)
            try:
                # Ищем закупку по артикулу в df_raw
                cost = float(df_raw[df_raw['артикул'].astype(str) == str(sku)]['себестоимость'].values[0])
            except: cost = 0.0

            # Формула
            k_var = (comm + marketing + 1.5) / 100 # +1.5 эквайринг
            denom = 1 - k_var - (target_m / 100)
            
            if denom > 0 and cost > 0:
                rrc = (cost + logistics_base) / denom
            else: rrc = 0
            
            results.append({
                "Артикул": sku, "Наименование": name, "Категория": cat,
                "Комиссия": f"{comm}%", "Закупка": cost, "РРЦ": round(rrc, 0),
                "Объем м3": round((l*h*w)/1000000, 4)
            })
        
        res_df = pd.DataFrame(results)
        st.dataframe(res_df)
        st.download_button("📥 Скачать результат", res_df.to_csv(index=False).encode('utf-8'), "rrc_results.csv")
else:
    st.info("Сначала обновите комиссии в боковом меню.")
