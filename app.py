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

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        target_m = st.number_input("Таргет маржа, %", value=20.0)
    with col2:
        acquiring = st.number_input("Интернет-эквайринг, %", value=1.5)
    with col3:
        marketing = st.number_input("Маркетинг + ретро, %", value=8.0)
    with col4:
        extra_costs = st.number_input("Доп. расходы, руб/шт", value=0.0)

    col5, col6 = st.columns(2)
    with col5:
        logistics_extra = st.number_input(
            "Доп. логистика продавца, руб/шт",
            value=0.0,
            help="Ваши логистические затраты сверх тарифов М.Видео"
        )
    with col6:
        qty = st.number_input("Количество в партии (для справки)", value=1, min_value=1)

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
            cost = 0.0
            if df_raw is not None and "артикул" in df_raw.columns:
                try:
                    cost = float(
                        df_raw[
                            df_raw["артикул"].astype(str) == str(sku)
                        ]["себестоимость"].values[0]
                    )
                except Exception:
                    cost = 0.0

            # Полная логистика
            logistics_total = mv_logistics + logistics_extra

            # Суммарные проценты от цены
            k_percent = comm + marketing + acquiring

            # Деноминатор формулы
            denom = 1 - (k_percent / 100) - (target_m / 100)

            if denom > 0 and cost > 0:
                rrc = (cost + logistics_total + extra_costs) / denom
            else:
                rrc = 0

            # Прибыль и факт-маржа
            if rrc > 0:
                percent_costs = rrc * (k_percent / 100)
                profit = rrc - cost - logistics_total - extra_costs - percent_costs
                margin_fact = (profit / rrc) * 100
            else:
                profit = 0
                margin_fact = 0

            results.append({
                "Артикул": sku,
                "Наименование": name,
                "Категория": cat,
                "Комиссия, %": round(comm, 2),
                "Маркетинг, %": round(marketing, 2),
                "Эквайринг, %": round(acquiring, 2),
                "Тип": size_type,
                "Объём, м³": round(volume_m3, 4),
                "Логистика М.Видео, руб": round(mv_logistics, 2),
                "Доп. логистика, руб": round(logistics_extra, 2),
                "Доп. расходы, руб": round(extra_costs, 2),
                "Закупка, руб": round(cost, 2),
                "РРЦ, руб": round(rrc, 0),
                "Прибыль, руб": round(profit, 0),
                "Маржа факт, %": round(margin_fact, 1),
            })

        res_df = pd.DataFrame(results)
        st.subheader("Результаты расчёта")
        st.dataframe(res_df, use_container_width=True)

        st.download_button(
            "📥 Скачать результат (CSV)",
            res_df.to_csv(index=False).encode("utf-8"),
            "rrc_results.csv",
            mime="text/csv"
        )
else:
    st.info("Сначала обновите комиссии из PDF М.Видео в боковом меню.")
