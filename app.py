import streamlit as st
import pandas as pd
from openai import OpenAI

st.set_page_config(page_title="Smart Unit Economics", layout="wide")

# --- СПРАВОЧНИК КОМИССИЙ (Пример, можно дополнять) ---
# В идеале это то, что мы потом будем тянуть из PDF
COMMISSIONS_DATA = {
    "Смартфоны": 5.0,
    "Ноутбуки и планшеты": 6.5,
    "Крупная бытовая техника": 10.0,
    "Малая бытовая техника": 12.0,
    "Аксессуары": 20.0,
    "Телевизоры": 8.0
}

# --- ИНИЦИАЛИЗАЦИЯ ИИ ---
api_key = st.sidebar.text_input("Вставьте ваш OpenAI API Key", type="password")
client = OpenAI(api_key=api_key) if api_key else None

st.title("📊 Умный расчет РРЦ для М.Видео")

# --- БЛОК НАСТРОЕК ---
with st.expander("⚙️ Настройки общих затрат (ретро, маркетинг и т.д.)"):
    col1, col2 = st.columns(2)
    with col1:
        retro = st.number_input("Ретро-бонус, %", value=5.0)
        marketing = st.number_input("Маркетинг, %", value=3.0)
    with col2:
        acquiring = st.number_input("Эквайринг, %", value=1.5)
        target_margin = st.number_input("Целевая маржа, %", value=20.0)

# --- ЗАГРУЗКА ДАННЫХ ---
uploaded_file = st.file_uploader("Загрузите Excel с товарами (колонки: name, purchase_price, logistics_fix)")

if uploaded_file:
    df = pd.read_excel(uploaded_file) if uploaded_file.name.endswith("xlsx") else pd.read_csv(uploaded_file)
    
    if st.button("🚀 Рассчитать с помощью ИИ"):
        if not client:
            st.error("❌ Сначала введите API ключ в боковом меню!")
        else:
            with st.spinner("ИИ сопоставляет товары с категориями М.Видео..."):
                results = []
                categories_list = list(COMMISSIONS_DATA.keys())
                
                for _, row in df.iterrows():
                    # Промпт для ИИ
                    prompt = f"Товар: '{row['name']}'. Выбери ОДНУ категорию из списка: {', '.join(categories_list)}. Ответь только названием категории."
                    
                    try:
                        response = client.chat.completions.create(
                            model="gpt-3.5-turbo",
                            messages=[{"role": "user", "content": prompt}]
                        )
                        category = response.choices[0].message.content.strip()
                        # Если ИИ ошибся в названии, берем 'Аксессуары' по умолчанию
                        comm_rate = COMMISSIONS_DATA.get(category, 15.0) 
                    except:
                        category = "Ошибка определения"
                        comm_rate = 15.0

                    # Математика
                    k_var = (comm_rate + retro + marketing + acquiring) / 100
                    denominator = 1 - k_var - (target_margin / 100)
                    
                    if denominator > 0:
                        rrc = (row['purchase_price'] + row['logistics_fix']) / denominator
                    else:
                        rrc = "Ошибка (слишком высокая маржа)"

                    results.append({
                        "Товар": row['name'],
                        "Категория (ИИ)": category,
                        "Комиссия": f"{comm_rate}%",
                        "Закупка": row['purchase_price'],
                        "РРЦ": round(rrc, 2) if isinstance(rrc, float) else rrc
                    })

                res_df = pd.DataFrame(results)
                st.success("Готово!")
                st.dataframe(res_df)
                
                # Скачивание
                st.download_button("📥 Скачать результат", res_df.to_csv(index=False).encode("utf-8"), "result.csv")
