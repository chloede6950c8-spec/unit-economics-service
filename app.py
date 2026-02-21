import streamlit as st
import pandas as pd
import pdfplumber
import requests
from io import BytesIO
from openai import OpenAI

# Настройки страницы
st.set_page_config(page_title="M.Video Unit Economics AI", layout="wide")

# Константы
DEFAULT_PDF_URL = "https://static.mvideo.ru/media/Promotions/Promo_Page/2025/September/marketplace/applications/applications-1new.pdf"

# --- ИНИЦИАЛИЗАЦИЯ ИИ ---
with st.sidebar:
    st.header("🔑 Настройки ИИ")
    api_key = st.text_input("OpenAI API Key", type="password")
    client = OpenAI(api_key=api_key) if api_key else None
    
    st.divider()
    st.header("📦 Источник комиссий")
    pdf_url = st.text_input("Ссылка на PDF М.Видео", value=DEFAULT_PDF_URL)
    manual_pdf = st.file_uploader("Или загрузите PDF вручную", type="pdf")

# --- ФУНКЦИИ ---

def extract_commissions(file_source):
    """Извлекает категории и комиссии из PDF (байты или путь)"""
    data = {}
    try:
        with pdfplumber.open(file_source) as pdf:
            for page in pdf.pages:
                tables = page.extract_tables()
                for table in tables:
                    for row in table:
                        # Логика: ищем строку, где есть название категории и число с %
                        # Обычно в М.Видео это колонки типа "Категория" и "Комиссия %"
                        clean_row = [str(cell).replace('\n', ' ') for cell in row if cell]
                        for i, cell in enumerate(clean_row):
                            if "%" in cell:
                                try:
                                    # Берем текст слева от процента как название категории
                                    category_name = clean_row[0] 
                                    rate = float(cell.replace('%', '').replace(',', '.').strip())
                                    data[category_name] = rate
                                except:
                                    continue
        return data
    except Exception as e:
        st.error(f"Ошибка парсинга PDF: {e}")
        return None

def get_ai_category(product_name, categories):
    """Сопоставление товара с категорией через ИИ"""
    if not client:
        return None
    
    prompt = f"""
    У меня есть товар: "{product_name}".
    Выбери для него наиболее подходящую категорию из списка ниже. 
    Если точного совпадения нет, выбери самую близкую по смыслу.
    ОТВЕТЬ ТОЛЬКО НАЗВАНИЕМ КАТЕГОРИИ.
    
    Список категорий:
    {", ".join(categories)}
    """
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini", # Дешевле и быстрее
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )
        return response.choices[0].message.content.strip()
    except:
        return None

# --- ГЛАВНЫЙ ИНТЕРФЕЙС ---

st.title("📊 Unit Economics Service — M.Video Edition")

# 1. Загрузка справочника комиссий
if 'commissions' not in st.session_state:
    st.session_state.commissions = None

col_sync, col_status = st.columns([1, 2])
with col_sync:
    if st.button("🔄 Синхронизировать комиссии"):
        with st.spinner("Загрузка и анализ PDF..."):
            if manual_pdf:
                source = manual_pdf
            else:
                response = requests.get(pdf_url)
                source = BytesIO(response.content)
            
            res = extract_commissions(source)
            if res:
                st.session_state.commissions = res
                st.success(f"Загружено категорий: {len(res)}")

if st.session_state.commissions:
    with st.expander("Посмотреть текущие комиссии"):
        st.write(st.session_state.commissions)

    st.divider()

    # 2. Ввод общих параметров
    st.header("🏪 Условия ритейлера")
    c1, c2, c3, c4 = st.columns(4)
    with c1: retro = st.number_input("Ретро-бонус, %", value=5.0)
    with c2: marketing = st.number_input("Маркетинг, %", value=3.0)
    with c3: bonus = st.number_input("Бонусы/Прочее, %", value=2.0)
    with c4: target_margin = st.number_input("Целевая маржа, %", value=20.0)

    # 3. Загрузка товаров
    st.header("📤 Загрузка товаров для расчета")
    uploaded_file = st.file_uploader("Загрузите Excel/CSV (колонки: name, purchase_price, logistics_fix)")

    if uploaded_file:
        df = pd.read_excel(uploaded_file) if uploaded_file.name.endswith("xlsx") else pd.read_csv(uploaded_file)
        
        if st.button("🚀 Начать умный расчет"):
            if not client:
                st.warning("Введите API Key в боковом меню для работы ИИ!")
            else:
                with st.spinner("ИИ анализирует товары..."):
                    results = []
                    cats_list = list(st.session_state.commissions.keys())
                    
                    for _, row in df.iterrows():
                        # ИИ определяет категорию
                        best_cat = get_ai_category(row['name'], cats_list)
                        comm_rate = st.session_state.commissions.get(best_cat, 15.0) # 15% если не нашли
                        
                        # Расчет по формуле
                        # Переменные затраты = Комиссия + Ретро + Маркетинг + Бонус + Эквайринг (пусть 1.5%)
                        k_var = (comm_rate + retro + marketing + bonus + 1.5) / 100
                        target_m_dec = target_margin / 100
                        
                        denom = 1 - k_var - target_m_dec
                        
                        if denom > 0:
                            rrc = (row['purchase_price'] + row['logistics_fix']) / denom
                            profit = rrc * (1 - k_var) - row['purchase_price'] - row['logistics_fix']
                        else:
                            rrc = 0
                            profit = 0

                        results.append({
                            "Товар": row['name'],
                            "Категория (ИИ)": best_cat,
                            "Комиссия": f"{comm_rate}%",
                            "Закупка": row['purchase_price'],
                            "Логистика": row['logistics_fix'],
                            "Рекомендованная цена (РРЦ)": round(rrc, 0),
                            "Прибыль": round(profit, 0)
                        })
                    
                    res_df = pd.DataFrame(results)
                    st.success("Расчет завершен!")
                    st.dataframe(res_df)
                    
                    st.download_button("📥 Скачать Excel", res_df.to_excel(index=False) if False else res_df.to_csv(index=False).encode('utf-8'), "result.csv")

else:
    st.info("Нажмите кнопку 'Синхронизировать комиссии', чтобы подтянуть данные с сайта М.Видео.")
