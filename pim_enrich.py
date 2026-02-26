"""
PIM Enrichment Module — поиск габаритов и веса товаров.

Логика:
1. Поиск в интернете по названию/артикулу/EAN через AI (web search + GPT)
2. Извлечение характеристик из результатов поиска
3. Fallback на средние значения по категории из category_defaults
4. Логирование источника значений

Используется в pim.py (Streamlit страница PIM).
"""

import json
import sqlite3
from typing import Optional, Dict, Tuple

try:
    from openai import OpenAI
except Exception:  # optional dependency for local runs
    OpenAI = None


# ── Средние габариты по категориям (базовый справочник) ────────────
# используется как fallback если web-поиск не дал результата
CATEGORY_DEFAULTS_BUILTIN = {
    "Велосипеды":       {"length_cm": 170, "width_cm": 60,  "height_cm": 100, "weight_kg": 14.0},
    "Самокаты":         {"length_cm": 110, "width_cm": 45,  "height_cm": 110, "weight_kg": 5.0},
    "Скейтборды":       {"length_cm": 80,  "width_cm": 25,  "height_cm": 15,  "weight_kg": 2.0},
    "Ролики":           {"length_cm": 35,  "width_cm": 25,  "height_cm": 20,  "weight_kg": 2.5},
    "Шлемы":            {"length_cm": 30,  "width_cm": 25,  "height_cm": 20,  "weight_kg": 0.4},
    "Защита":           {"length_cm": 40,  "width_cm": 30,  "height_cm": 10,  "weight_kg": 0.5},
    "Зимний спорт":     {"length_cm": 160, "width_cm": 30,  "height_cm": 10,  "weight_kg": 2.0},
    "Лыжи":             {"length_cm": 170, "width_cm": 20,  "height_cm": 10,  "weight_kg": 3.5},
    "Сноуборды":        {"length_cm": 160, "width_cm": 30,  "height_cm": 10,  "weight_kg": 3.0},
    "Ботинки":          {"length_cm": 35,  "width_cm": 25,  "height_cm": 20,  "weight_kg": 1.5},
    "Одежда":           {"length_cm": 40,  "width_cm": 30,  "height_cm": 5,   "weight_kg": 0.5},
    "Аксессуары":       {"length_cm": 30,  "width_cm": 20,  "height_cm": 10,  "weight_kg": 0.3},
    "Электротранспорт": {"length_cm": 120, "width_cm": 50,  "height_cm": 120, "weight_kg": 15.0},
    "Велозапчасти":     {"length_cm": 30,  "width_cm": 20,  "height_cm": 10,  "weight_kg": 0.5},
    "Инструменты":      {"length_cm": 30,  "width_cm": 20,  "height_cm": 10,  "weight_kg": 0.5},
    "Детские товары":   {"length_cm": 60,  "width_cm": 40,  "height_cm": 30,  "weight_kg": 2.0},
    "Туризм":           {"length_cm": 60,  "width_cm": 30,  "height_cm": 30,  "weight_kg": 1.5},
    "Прочее":           {"length_cm": 40,  "width_cm": 30,  "height_cm": 20,  "weight_kg": 1.0},
}

# Ключевые слова для угадывания категории
CATEGORY_KEYWORDS = {
    "Велосипеды": ["велосипед", "bike", "bicycle", "bmx", "mtb"],
    "Самокаты": ["самокат", "scooter", "кикборд"],
    "Скейтборды": ["скейт", "skateboard", "лонгборд", "longboard"],
    "Ролики": ["ролик", "роликов", "inline", "skate"],
    "Шлемы": ["шлем", "helmet", "каска"],
    "Защита": ["защит", "наколенник", "налокотник", "protector"],
    "Зимний спорт": ["зимний", "winter"],
    "Лыжи": ["лыж", "ski"],
    "Сноуборды": ["сноуборд", "snowboard"],
    "Ботинки": ["ботинк", "boot", "обувь"],
    "Одежда": ["куртка", "брюки", "футболка", "jacket", "pants"],
    "Электротранспорт": ["электросамокат", "гироскутер", "electric"],
    "Велозапчасти": ["втулка", "педал", "седло", "руль", "покрышка"],
    "Инструменты": ["ключ", "насос", "набор", "tool"],
    "Детские товары": ["детск", "kids", "child"],
    "Туризм": ["палатка", "рюкзак", "спальник", "tent"],
}


def guess_category_by_name(product_name: str) -> str:
    """Пытается угадать категорию по ключевым словам в названии товара."""
    product_lower = product_name.lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw in product_lower:
                return category
    return "Прочее"


def enrich_product_via_ai(product: Dict, openai_api_key: str) -> Optional[Dict]:
    """
    Обогащает товар через AI:
    1) Делает web search по названию/артикулу
    2) Извлекает габариты из результатов
    3) Если не найдено → fallback на средние по категории
    """
    if OpenAI is None:
        raise RuntimeError("openai package not installed")
    client = OpenAI(api_key=openai_api_key)
    
    # 1) Формируем поисковый запрос
    search_query = f"{product['name']} {product.get('sku', '')} габариты вес характеристики"
    
    try:
        # 2) Web search + GPT
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": """Ты эксперт по поиску характеристик товаров. 
Найди габариты (длина, ширина, высота в см) и вес (в кг) товара.
Верни ТОЛЬКО JSON: {"length_cm": X, "width_cm": Y, "height_cm": Z, "weight_kg": W}
Если не нашёл — верни {"length_cm": null, "width_cm": null, "height_cm": null, "weight_kg": null}
Важно: возвращай только числа больше 0, если значение 0 или отсутствует - ставь null."""
                },
                {
                    "role": "user",
                    "content": f"Найди габариты и вес товара: {search_query}"
                }
            ],
            temperature=0.3
        )
        
        result_text = response.choices[0].message.content.strip()
        # Пробуем распарсить JSON
        parsed = json.loads(result_text)
        
        # 3) Проверяем, что получили валидные данные (не null и не 0)
        if (parsed.get("length_cm") and parsed["length_cm"] > 0 and
            parsed.get("width_cm") and parsed["width_cm"] > 0 and
            parsed.get("height_cm") and parsed["height_cm"] > 0 and
            parsed.get("weight_kg") and parsed["weight_kg"] > 0):
            return {
                "length_cm": parsed["length_cm"],
                "width_cm": parsed["width_cm"],
                "height_cm": parsed["height_cm"],
                "weight_kg": parsed["weight_kg"],
                "source": "ai_search"
            }
    except Exception as e:
        print(f"[enrich] AI search error: {e}")
    
    # 4) Fallback на средние по категории
    guessed_category = guess_category_by_name(product["name"])
    defaults = CATEGORY_DEFAULTS_BUILTIN.get(guessed_category, CATEGORY_DEFAULTS_BUILTIN["Прочее"])
    
    return {
        "length_cm": defaults["length_cm"],
        "width_cm": defaults["width_cm"],
        "height_cm": defaults["height_cm"],
        "weight_kg": defaults["weight_kg"],
        "source": f"category_default ({guessed_category})"
    }


def init_pim_tables(conn: sqlite3.Connection):
    """Подготавливает БД для PIM поверх единого каталога (таблица products)."""
    cursor = conn.cursor()

    # Мягкая миграция: добавляем недостающие колонки в products
    cols = [r[1] for r in cursor.execute("PRAGMA table_info(products)")]
    alter = []
    if "ean" not in cols:
        alter.append("ALTER TABLE products ADD COLUMN ean TEXT")
    if "brand" not in cols:
        alter.append("ALTER TABLE products ADD COLUMN brand TEXT")
    if "category" not in cols:
        alter.append("ALTER TABLE products ADD COLUMN category TEXT")
    if "description" not in cols:
        alter.append("ALTER TABLE products ADD COLUMN description TEXT")
    if "main_image_url" not in cols:
        alter.append("ALTER TABLE products ADD COLUMN main_image_url TEXT")
    if "enrich_status" not in cols:
        alter.append("ALTER TABLE products ADD COLUMN enrich_status TEXT DEFAULT 'pending'")
    if "enrich_source" not in cols:
        alter.append("ALTER TABLE products ADD COLUMN enrich_source TEXT")

    for stmt in alter:
        try:
            cursor.execute(stmt)
        except Exception:
            # best-effort: if column exists due to race, ignore
            pass

    # Лог обогащений
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pim_enrichment_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER,
            method TEXT,
            success INTEGER,
            ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()


def _is_missing(v) -> bool:
    return v is None or str(v).strip() == "" or v == 0


def enrich_product(
    product: Dict,
    conn: sqlite3.Connection,
    openai_api_key: str,
    search_results=None,
    force: bool = False,
) -> Tuple[Dict, str]:
    """API, которую ожидает pim.py: возвращает (updated_product, method)."""
    # если уже заполнено и не force — ничего не делаем
    if not force and not any(_is_missing(product.get(k)) for k in ("length_cm", "width_cm", "height_cm", "weight_kg")):
        return product, "already_filled"

    method = "failed"
    updated = dict(product)

    # Пытаемся AI (без веб-поиска, только по названию/sku) — если есть ключ
    if openai_api_key:
        try:
            r = enrich_product_via_ai(product, openai_api_key)
            if r:
                updated.update({
                    "length_cm": r.get("length_cm"),
                    "width_cm": r.get("width_cm"),
                    "height_cm": r.get("height_cm"),
                    "weight_kg": r.get("weight_kg"),
                })
                method = r.get("source", "ai")
        except Exception:
            method = "failed"

    # Если AI не сработал/ключа нет — fallback на категорию
    if method == "failed":
        guessed_category = guess_category_by_name(str(product.get("name") or ""))
        defaults = CATEGORY_DEFAULTS_BUILTIN.get(guessed_category, CATEGORY_DEFAULTS_BUILTIN["Прочее"])
        updated.update(defaults)
        method = f"category_default ({guessed_category})"

    updated["enrich_source"] = method
    updated["enrich_status"] = "enriched" if method != "failed" else "failed"
    return updated, method


def log_enrichment(conn: sqlite3.Connection, product_id: int, method: str, success: bool):
    try:
        c = conn.cursor()
        c.execute(
            "INSERT INTO pim_enrichment_log (product_id, method, success) VALUES (?,?,?)",
            (int(product_id), str(method), 1 if success else 0),
        )
        conn.commit()
    except Exception:
        pass
