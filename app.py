import streamlit as st
import sqlite3
from openai import OpenAI

st.set_page_config(
    page_title="B2B Unit Economics Service",
    layout="wide",
    page_icon="📦"
)

DB_PATH = "products_storage.db"

def init_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sku TEXT UNIQUE,
            name TEXT,
            length_cm REAL,
            width_cm REAL,
            height_cm REAL,
            weight_kg REAL,
            cost REAL DEFAULT 0
        )
    """)
    cols = [r[1] for r in c.execute("PRAGMA table_info(products)")]
    if "cost" not in cols:
        c.execute("ALTER TABLE products ADD COLUMN cost REAL DEFAULT 0")
    
    c.execute("""
        CREATE TABLE IF NOT EXISTS ai_cache (
            name TEXT,
            client TEXT,
            category TEXT,
            PRIMARY KEY (name, client)
        )
    """)
    conn.commit()
    return conn

def normalize_value(raw, unit):
    try:
        v = float(str(raw).replace(",", ".").strip())
    except (ValueError, TypeError):
        return 0.0
    u = str(unit).strip().lower() if unit else ""
    if u in ("мм", "mm"):
        return v / 10.0
    if u in ("г", "g", "гр", "gr"):
        return v / 1000.0
    return v

def get_ai_category(name: str, categories: list, conn, client_key: str) -> str:
    c = conn.cursor()
    row = c.execute(
        "SELECT category FROM ai_cache WHERE name=? AND client=?",
        (name, client_key)
    ).fetchone()
    if row:
        return row[0]
    
    api_key = st.session_state.get("openai_key", "")
    if not api_key or not categories:
        return categories[0] if categories else "Неизвестно"
    
    try:
        client = OpenAI(api_key=api_key)
        cats_str = "
".join(f"- {cat}" for cat in categories)
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": (
                    f"Ты классификатор товаров для маркетплейса {client_key}. "
                    "Выбери ОДНУ категорию из списка. Ответь ТОЛЬКО её названием."
                )},
                {"role": "user", "content": f"Товар: {name}
Категории:
{cats_str}"}
            ],
            max_tokens=60,
            temperature=0
        )
        category = resp.choices[0].message.content.strip()
        if category not in categories:
            category = categories[0]
    except Exception:
        category = categories[0] if categories else "Неизвестно"
    
    c.execute(
        "INSERT OR REPLACE INTO ai_cache (name, client, category) VALUES (?,?,?)",
        (name, client_key, category)
    )
    conn.commit()
    return category

def calc_tax(revenue: float, cost_total: float, regime: str):
    profit_before = revenue - cost_total
    rates = {
        "ОСНО (25% от прибыли)": ("profit", 0.25),
        "УСН Доходы (6%)": ("revenue", 0.06),
        "УСН Доходы-Расходы (15%)": ("profit", 0.15),
        "АУСН (8% от дохода)": ("revenue", 0.08),
        "УСН с НДС 5%": ("revenue", 0.05),
        "УСН с НДС 7%": ("revenue", 0.07),
    }
    mode, rate = rates.get(regime, ("profit", 0.0))
    if mode == "revenue":
        tax = revenue * rate
    else:
        tax = max(profit_before * rate, 0)
    profit_after = profit_before - tax
    margin_after = (profit_after / revenue * 100) if revenue > 0 else 0
    return round(tax, 2), round(profit_after, 2), round(margin_after, 1)

# ── Инициализация БД ──────────────────────────────────────────────
conn = init_db()

# ── Обработка API ключа (Secrets / Session State) ─────────────────
if "openai_key" not in st.session_state:
    secret_key = st.secrets.get("OPENAI_API_KEY")
    if secret_key:
        st.session_state["openai_key"] = secret_key
    else:
        st.session_state["openai_key"] = ""

# ── Боковая панель ────────────────────────────────────────────────
with st.sidebar:
    st.title("📦 Unit Economics")
    client_choice = st.selectbox(
        "Клиент (маркетплейс)",
        ["М.Видео (FBS)", "Лемана Про (FBS)", "DNS (в разработке)", "Ситилинк (в разработке)"],
        key="client_choice"
    )
    st.divider()
    
    st.subheader("⚙️ Параметры расчёта")
    tax_regime = st.selectbox(
        "Система налогообложения",
        [
            "ОСНО (25% от прибыли)",
            "УСН Доходы (6%)",
            "УСН Доходы-Расходы (15%)",
            "АУСН (8% от дохода)",
            "УСН с НДС 5%",
            "УСН с НДС 7%",
        ],
        key="tax_regime"
    )
    target_margin = st.number_input(
        "Таргет маржа, %", value=20.0, step=0.5,
        min_value=0.0, max_value=99.0, key="target_margin"
    )
    acquiring = st.number_input(
        "Интернет-эквайринг, %", value=1.5, step=0.1,
        min_value=0.0, key="acquiring"
    )
    
    # Скрываем поле "Досрочный вывод" по запросу (1)
    if client_choice != "Лемана Про (FBS)":
        early_payout = st.number_input(
            "Досрочный вывод, %", value=0.0, step=0.1,
            min_value=0.0, key="early_payout"
        )
    else:
        st.session_state["early_payout"] = 0.0
        early_payout = 0.0

    marketing = st.number_input(
        "Маркетинг / ретро, %", value=0.0, step=0.5,
        min_value=0.0, key="marketing"
    )
    extra_costs = st.number_input(
        "Доп. расходы, руб/шт", value=0.0, step=10.0,
        min_value=0.0, key="extra_costs"
    )
    extra_logistics = st.number_input(
        "Доп. логистика, руб/шт", value=0.0, step=10.0,
        min_value=0.0, key="extra_logistics"
    )
    
    if not st.session_state.get("openai_key"):
        st.divider()
        st.subheader("🤖 AI-классификация")
        openai_key_input = st.text_input(
            "OpenAI API ключ", type="password", key="openai_key_input"
        )
        if openai_key_input:
            st.session_state["openai_key"] = openai_key_input
            st.rerun()
    else:
        st.divider()
        st.caption("🤖 AI-классификация: Активна (ключ из secrets/сессии)")
    
    st.divider()
    st.caption("B2B Unit Economics Service v2.3")

params = {
    "tax_regime": st.session_state.get("tax_regime", "УСН Доходы (6%)"),
    "target_margin": st.session_state.get("target_margin", 20.0),
    "acquiring": st.session_state.get("acquiring", 1.5),
    "early_payout": st.session_state.get("early_payout", 0.0),
    "marketing": st.session_state.get("marketing", 0.0),
    "extra_costs": st.session_state.get("extra_costs", 0.0),
    "extra_logistics": st.session_state.get("extra_logistics", 0.0),
}

if client_choice == "М.Видео (FBS)":
    import mvideo
    mvideo.render(conn, get_ai_category, normalize_value, calc_tax, params)
elif client_choice == "Лемана Про (FBS)":
    import lemanpro_fbs
    lemanpro_fbs.render(conn, get_ai_category, normalize_value, calc_tax, params)
else:
    st.info(f"🔧 Модуль '{client_choice}' находится в разработке.")
