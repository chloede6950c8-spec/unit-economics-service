import streamlit as st
import pandas as pd
import pdfplumber
import requests
from io import BytesIO
from openai import OpenAI

# --- КОНФИГУРАЦИЯ СТРАНИЦЫ ---
st.set_page_config(page_title="M.Video Unit Economics AI", layout="wide", page_icon="📊")

# Ссылка на актуальные комиссии (твоя ссылка)
DEFAULT_PDF_URL = "https://static.mvideo.ru/media/Promotions/Promo_Page/2025/September/marketplace/applications/applications-1new.pdf"

# --- ИНИЦИАЛИЗАЦИЯ ИИ (БЕЗОПАСНО) ---
# Проверяем наличие ключа в Secrets Streamlit или вводим вручную
if "OPENAI_API_KEY" in st.secrets:
    api_key = st.secrets["OPENAI_API_KEY"]
else:
    api_key = st.sidebar.text_input("🔑 Введите OpenAI API Key", type="password", help="Получите ключ на platform.openai.com")

client = OpenAI(api_key=api_key) if api_key else None

# --- ФУНКЦИИ ЛОГИКИ ---

def extract_commissions_from_pdf(file_source):
    """Извлекает категории и проценты комиссий из PDF файла"""
    commissions = {}
    try:
        with pdfplumber.open(file_source) as pdf:
            for page in pdf.pages:
                tables = page.extract_tables()
                for table in tables:
                    for row in table:
                        # Очищаем строку от пустых ячеек и переносов строк
                        clean_row = [str(c).replace('\n', ' ').strip() for c in row if c]
                        
                        # Ищем ячейку, где есть знак %
                        for i, cell in enumerate(clean_row):
                            if "%" in cell:
                                try:
                                    # Название категории обычно в первой колонке (индекс 0)
                                    cat_name = clean_row[0]
                                    # Вытаскиваем число из ячейки с %
                                    rate_str = cell.replace('%', '').replace(',', '.').strip()
                                    rate = float(rate_str)
                                    commissions[cat_name] = rate
                                except:
                                    continue
        return commissions
    except Exception as e:
        st.error(f"Ошибка при чтении PDF: {e}")
        return None

def get_best_category_ai(product_name, available_categories):
    """Использует ИИ для сопоставления товара с категорией из справочника"""
    if not client:
        return None
    
    prompt = f"""
    Твоя задача: сопоставить товар с наиболее подходящей категорией из списка ритейлера М.Видео.
    Товар: "{product_name}"
    
    Доступные категории:
    {", ".join(available_categories)}
    
    Ответь ТОЛЬКО названием категории из списка. Если ничего не подходит, выбери 'Прочее' или наиболее близкую.
    """
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return None

# --- ИНТЕРФЕЙС ---

st.title("📊 Сервис Юнит-Экономики (М.Видео + AI)")
st.markdown("Сервис автоматически подтягивает комиссии с сайта М.Видео и рассчитывает РРЦ с помощью ИИ.")

# Блок синхронизации данных
with st.sidebar:
    st.header("⚙️ Настройки данных")
    sync_url = st.text_input("Ссылка на PDF с комиссиями", value=DEFAULT_PDF_URL)
    
    if st.button("🔄 Обновить комиссии с сайта"):
        with st.spinner("Загрузка PDF..."):
            try:
                resp = requests.get(sync_url)
                if resp.status_code == 200:
                    pdf_data = extract_commissions_from_pdf(BytesIO(resp.content))
                    if pdf_data:
                        st.session_state['comm_dict'] = pdf_data
                        st.success(f"Загружено {len(pdf_data)} категорий!")
                else:
                    st.error("Не удалось скачать файл по ссылке.")
            except Exception as e:
                st.error(f"Ошибка: {e}")

# Основная рабочая область
if 'comm_dict' not in st.session_state:
    st.info("👈 Нажмите кнопку 'Обновить комиссии с сайта' в боковом меню, чтобы начать.")
else:
    # Настройки параметров
    st.header("1. Параметры сделки")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        retro = st.number_input("Ретро-бонус, %", value=5.0)
    with col2:
        marketing = st.number_input("Маркетинг, %", value=3.0)
    with col3:
        acquiring = st.number_input("Эквайринг + Бонусы, %", value=3.5)
    with col4:
        target_margin = st.number_input("Целевая маржа, %", value=20.0)

    st.divider()

    # Загрузка Excel
    st.header("2. Загрузка товаров")
    uploaded_file = st.file_uploader("Загрузите Excel/CSV (name, purchase_price, logistics_fix)", type=["xlsx", "csv"])

    if uploaded_file:
        df_input = pd.read_excel(uploaded_file) if uploaded_file.name.endswith("xlsx") else pd.read_csv(uploaded_file)
        
        if st.button("🚀 Рассчитать РРЦ"):
            if not api_key:
                st.error("Введите API Key в боковом меню!")
            else:
                progress_bar = st.progress(0)
                results = []
                cat_list = list(st.session_state['comm_dict'].keys())
                
                with st.spinner("ИИ классифицирует товары..."):
                    for index, row in df_input.iterrows():
                        # Классификация
                        p_name = str(row['name'])
                        ai_cat = get_best_category_ai(p_name, cat_list)
                        comm_rate = st.session_state['comm_dict'].get(ai_cat, 15.0) # 15% по умолчанию
                        
                        # Расчет
                        # Цена = (Закупка + Логистика) / (1 - %Затрат - %Маржи)
                        k_var = (comm_rate + retro + marketing + acquiring) / 100
                        margin_dec = target_margin / 100
                        
                        denominator = 1 - k_var - margin_dec
                        
                        if denominator > 0:
                            rrc = (row['purchase_price'] + row['logistics_fix']) / denominator
                            profit = rrc * (1 - k_var) - row['purchase_price'] - row['logistics_fix']
                        else:
                            rrc = 0
                            profit = 0
                            
                        results.append({
                            "Товар": p_name,
                            "Категория (ИИ)": ai_cat,
                            "Комиссия": f"{comm_rate}%",
                            "Закупка": row['purchase_price'],
                            "Логистика": row['logistics_fix'],
                            "РРЦ": round(rrc, 0),
                            "Прибыль": round(profit, 0)
                        })
                        progress_bar.progress((index + 1) / len(df_input))

                res_df = pd.DataFrame(results)
                st.success("Расчет готов!")
                st.dataframe(res_df, use_container_width=True)
                
                # Скачивание
                csv = res_df.to_csv(index=False).encode('utf-8')
                st.download_button("📥 Скачать результат (CSV)", csv, "mvideo_calculation.csv", "text/csv")

# Дополнительная информация
with st.expander("Как работает формула?"):
    st.write("""
    **Формула:** `РРЦ = (Закупка + Логистика) / (1 - %Переменных_затрат - %Целевой_маржи)`
    
    Где переменные затраты включают:
    - Комиссию категории (автоматически из PDF)
    - Ретро-бонус
    - Маркетинг
    - Эквайринг и бонусы
    """)
