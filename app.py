import streamlit as st
import pandas as pd
import sqlite3
import pdfplumber
import requests
from io import BytesIO
from openai import OpenAI

# --- КОНФИГУРАЦИЯ ---
st.set_page_config(
    page_title="B2B Unit Economics System",
    layout="wide",
    page_icon="📦"
)

# --- КОНСТАНТЫ ---
COMMISSIONS_PDF_URL = "https://static.mvideo.ru/media/Promotions/Promo_Page/2025/September/marketplace/applications/applications-1new.pdf"
LOGISTICS_PDF_URL = "https://static.mvideo.ru/media/Promotions/Promo_Page/2025/September/marketplace/applications/2026/applications-2-v2.pdf"

# Тарифы логистики М.Видео 2026 (пример — подставь актуальные цифры из applications-2-v2.pdf)
LOGISTICS_TARIFFS = {
    "S": 110.0,    # руб/ед
    "M": 190.0,
    "L": 1290.0,   # XL считаем как L
}


# --- ИНИЦИАЛИЗАЦИЯ БД ---
def init_db():
    conn = sqlite3.connect("products_storage.db", check_same_thread=False)
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS products (
            sku TEXT PRIMARY KEY,
            name TEXT,
            length REAL,
            height REAL,
            width REAL,
            weight REAL
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS category_cache (
            name TEXT PRIMARY KEY,
            category TEXT
        )
        """
    )

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
    """Исправление единиц измерения: мм -> см, г -> кг."""
    try:
        val = float(str(val).replace(",", "."))
        if unit_type == "dim" and val > 250:
            return val / 10  # мм -> см
        if unit_type == "weight" and val > 150:
            return val / 1000  # г -> кг
        return val
    except Exception:
        return 0.0


def get_ai_category(product_name, categories):
    """ИИ-классификация с кэшем в SQLite."""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT category FROM category_cache WHERE name = ?",
        (product_name,)
    )
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
        cursor.execute(
            "INSERT OR REPLACE INTO category_cache VALUES (?, ?)",
            (product_name, category)
        )
        conn.commit()
        return category
    except Exception:
        return "Прочее"


def parse_pdf_commissions(url):
    """Парсинг комиссий (проценты) из PDF договора М.Видео."""
    data = {}
    try:
        resp = requests.get(url)
        resp.raise_for_status()
        with pdfplumber.open(BytesIO(resp.content)) as pdf:
            for page in pdf.pages:
                tables = page.extract_tables()
                for table in tables:
                    for row in table:
                        clean = [
                            str(c).replace("\n", " ").strip()
                            for c in row if c
                        ]
                        for cell in clean:
                            if "%" in cell:
                                try:
                                    cat = clean[0]
                                    rate = float(
                                        cell.replace("%", "")
                                        .replace(",", ".")
                                        .strip()
                                    )
                                    data[cat] = rate
                                except Exception:
                                    continue
        return data
    except Exception:
        return None


def classify_size(length_cm, height_cm, width_cm):
    """
    Определение типа S/M/L/XL по габаритам и объёму.
    Логику порогов при необходимости скорректируй по applications-2-v2.pdf.
    """
    if not all([length_cm, height_cm, width_cm]):
        return "S", 0.0, 0.0

    sides = sorted([length_cm, height_cm, width_cm], reverse=True)
    a, b, c = sides  # a >= b >= c

    volume_m3 = (length_cm * height_cm * width_cm) / 1_000_000

    # Примерная логика: малый / средний / крупный / негабарит
    if a > 180 or (a > 120 and b > 120):
        size_type = "XL"
    elif volume_m3 > 0.2:
        size_type = "L"
    elif volume_m3 >= 0.01:
        size_type = "M"
    else:
        size_type = "S"

    # Для тарифа XL считаем как L
    tariff_key = "L" if size_type == "XL" else size_type
    mv_logistics = LOGISTICS_TARIFFS.get(tariff_key, 0.0)

    return size_type, volume_m3, mv_logistics


def calc_tax(price, profit_before_tax, tax_regime):
    """
    Налог в зависимости от системы.
    Ставки можно поправить под реальные условия.
    """
    if tax_regime == "ОСНО":
        # Налог на прибыль, условно 25% от прибыли
        return max(profit_before_tax, 0) * 0.25
    elif tax_regime == "УСН (Доходы)":
        # 6% с выручки
        return price * 0.06
    elif tax_regime == "УСН (Доходы-Расходы)":
        # 15% с прибыли (если есть)
        return max(profit_before_tax, 0) * 0.15
    elif tax_regime == "АУСН":
        # условно 8% с выручки
        return price * 0.08
    elif tax_regime == "УСН с НДС 5%":
        # упрощённо: 6% налог + 5% НДС с выручки
        return price * 0.11
    elif tax_regime == "УСН с НДС 7%":
        # упрощённо: 6% налог + 7% НДС
        return price * 0.13
    else:
        return 0.0


# --- UI ---

st.title("🚀 Универсальный сервис юнит-экономики")

# Боковое меню
with st.sidebar:
    st.header("🛒 Настройка ритейлера")
    retailer = st.selectbox(
        "Выберите покупателя",
        ["М.Видео", "DNS (в разработке)", "Ситилинк (в разработке)"]
    )

    if st.button("🔄 Обновить комиссии из PDF М.Видео"):
        res = parse_pdf_commissions(COMMISSIONS_PDF_URL)
        if res:
            st.session_state["commissions"] = res
            st.success(f"Загружено {len(res)} категорий комиссий")
        else:
            st.error("Не удалось загрузить комиссии из PDF")

st.header("1. Загрузка базы данных товаров")
up_file = st.file_uploader(
    "Загрузите Excel (артикул, наименование, себестоимость, длина, высота, ширина, вес)",
    type=["xlsx"]
)

df_raw = None
if up_file:
    df_raw = pd.read_excel(up_file)
    df_raw.columns = [c.lower().strip() for c in df_raw.columns]

    if st.button("📥 Сохранить/обновить товары в базе"):
        cursor = conn.cursor()
        for _, r in df_raw.iterrows():
            l = normalize_value(r.get("длина", 0), "dim")
            h = normalize_value(r.get("высота", 0), "dim")
            w = normalize_value(r.get("ширина", 0), "dim")
            wg = normalize_value(r.get("вес", 0), "weight")
            cursor.execute(
                """
                INSERT OR REPLACE INTO products
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    str(r.get("артикул")),
                    str(r.get("наименование")),
                    l, h, w, wg
                )
            )
        conn.commit()
        st.success("База данных обновлена!")

st.divider()

if "commissions" in st.session_state:
    st.header("2. Расчёт партии")

    # Параметры в процентах
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        target_m = st.number_input("Таргет маржа, % (до налогов)", value=20.0)
    with col2:
        acquiring = st.number_input("Интернет-эквайринг, %", value=1.5)
    with col3:
        marketing = st.number_input("Маркетинг + ретро, %", value=0.0)
    with col4:
        early_payout = st.number_input("Досрочный вывод денег, %", value=0.0)

    # Параметры в рублях
    col5, col6 = st.columns(2)
    with col5:
        extra_costs = st.number_input("Доп. расходы, руб/шт", value=0.0)
    with col6:
        logistics_extra = st.number_input(
            "Доп. логистика продавца, руб/шт",
            value=0.0,
            help="Ваши логистические затраты сверх тарифов М.Видео"
        )

    # Система налогообложения
    tax_regime = st.selectbox(
        "Система налогообложения",
        [
            "ОСНО",
            "УСН (Доходы)",
            "УСН (Доходы-Расходы)",
            "АУСН",
            "УСН с НДС 5%",
            "УСН с НДС 7%",
        ]
    )

    if st.button("💸 Рассчитать РРЦ для всех товаров"):
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM products")
        all_products = cursor.fetchall()

        results = []
        cat_list = list(st.session_state["commissions"].keys())

        for p in all_products:
            sku, name, l, h, w, weight = p

            # Тип, объём и логистика М.Видео
            size_type, volume_m3, mv_logistics = classify_size(l, h, w)

            # Категория и комиссия
            cat = get_ai_category(name, cat_list)
            comm = st.session_state["commissions"].get(cat, 15.0)

            # Себестоимость
            cost =
