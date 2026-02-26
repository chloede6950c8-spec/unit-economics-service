"""
PIM Enrichment Module — поиск габаритов и веса товаров.

Логика:
1. Поиск в интернете по названию/артикулу/EAN через AI (web search + GPT)
2. Извлечение характеристик из результатов поиска
3. Fallback на средние значения по категории из category_defaults
4. Логирование источника данных

Используется в pim.py (Streamlit страница PIM).
"""

import json
import sqlite3
from typing import Optional, Dict, Tuple

from openai import OpenAI


# ── Средние габариты по категориям (базовый справочник) ─────────────
# Используется как fallback если web-поиск не дал результата
CATEGORY_DEFAULTS_BUILTIN = {
    "Велосипеды":          {"length_cm": 170, "width_cm": 60,  "height_cm": 100, "weight_kg": 14.0},
    "Самокаты":            {"length_cm": 110, "width_cm": 45,  "height_cm": 110, "weight_kg": 5.0},
    "Скейтборды":          {"length_cm": 80,  "width_cm": 25,  "height_cm": 15,  "weight_kg": 2.0},
    "Ролики":              {"length_cm": 35,  "width_cm": 25,  "height_cm": 20,  "weight_kg": 2.5},
    "Шлемы":               {"length_cm": 30,  "width_cm": 25,  "height_cm": 20,  "weight_kg": 0.4},
    "Защита":              {"length_cm": 40,  "width_cm": 30,  "height_cm": 10,  "weight_kg": 0.5},
    "Зимний спорт":        {"length_cm": 160, "width_cm": 30,  "height_cm": 10,  "weight_kg": 2.0},
    "Лыжи":                {"length_cm": 170, "width_cm": 20,  "height_cm": 10,  "weight_kg": 3.5},
    "Сноуборды":           {"length_cm": 160, "width_cm": 30,  "height_cm": 10,  "weight_kg": 3.0},
    "Ботинки":             {"length_cm": 35,  "width_cm": 25,  "height_cm": 20,  "weight_kg": 1.5},
    "Одежда":              {"length_cm": 40,  "width_cm": 30,  "height_cm": 5,   "weight_kg": 0.5},
    "Аксессуары":          {"length_cm": 30,  "width_cm": 20,  "height_cm": 10,  "weight_kg": 0.3},
    "Электросамокаты":     {"length_cm": 120, "width_cm": 50,  "height_cm": 120, "weight_kg": 15.0},
    "Велозапчасти":        {"length_cm": 30,  "width_cm": 20,  "height_cm": 10,  "weight_kg": 0.5},
    "Инструменты":         {"length_cm": 30,  "width_cm": 20,  "height_cm": 10,  "weight_kg": 0.5},
    "Детские товары":      {"length_cm": 60,  "width_cm": 40,  "height_cm": 30,  "weight_kg": 2.0},
    "Туризм":              {"length_cm": 60,  "width_cm": 30,  "height_cm": 30,  "weight_kg": 1.5},
    "Фитнес":              {"length_cm": 40,  "width_cm": 30,  "height_cm": 20,  "weight_kg": 1.0},
    "Прочее":              {"length_cm": 30,  "width_cm": 20,  "height_cm": 15,  "weight_kg": 0.5},
}

# Маппинг ключевых слов для умного угадывания категорий
CATEGORY_KEYWORDS = {
        "Велосипеды": ["велосипед", "bike", "mtb", "шоссейн", "горный"],
        "Самокаты": ["самокат", "scooter", "кикборд"],
        "Фитнес": ["коврик", "тренажер", "гантел", "эспандер", "фитнес", "йога", "спортивн"],
        "Лыжи": ["лыж", "ski", "беговые"],
        "Сноуборды": ["сноуборд", "snowboard"],
        "Электросамокаты": ["электросамокат", "электро", "e-scooter"],
        "Скейтборды": ["скейт", "skateboard", "доска"],
        "Ролики": ["ролик", "коньки", "inline"],
    }



def init_pim_tables(conn: sqlite3.Connection):
    """Создать таблицы PIM если их нет, расширить products новыми полями."""
    c = conn.cursor()

    # Добавляем новые колонки в products если их нет
    existing = [r[1] for r in c.execute("PRAGMA table_info(products)")]
    new_cols = {
        "ean":            "TEXT",
        "brand":          "TEXT",
        "category":       "TEXT",
        "description":    "TEXT",
        "main_image_url": "TEXT",
        "enrich_source":  "TEXT",
        "enrich_status":  "TEXT",
    }
    for col, col_type in new_cols.items():
        if col not in existing:
            try:
                c.execute(f"ALTER TABLE products ADD COLUMN {col} {col_type}")
            except Exception:
                pass

    # Таблица средних по категориям
    c.execute("""
        CREATE TABLE IF NOT EXISTS category_defaults (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            base_category TEXT UNIQUE NOT NULL,
            length_cm REAL,
            width_cm  REAL,
            height_cm REAL,
            weight_kg REAL,
            source_comment TEXT
        )
    """)

    # Лог обогащения
    c.execute("""
        CREATE TABLE IF NOT EXISTS enrichment_log (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER,
            method     TEXT,
            success    INTEGER DEFAULT 0,
            comment    TEXT,
            updated_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (product_id) REFERENCES products(id)
        )
    """)

    conn.commit()


def _seed_category_defaults(conn: sqlite3.Connection):
    """Заполнить category_defaults базовыми значениями если таблица пустая."""
    c = conn.cursor()
    count = c.execute("SELECT COUNT(*) FROM category_defaults").fetchone()[0]
    if count == 0:
        for cat, vals in CATEGORY_DEFAULTS_BUILTIN.items():
            try:
                c.execute(
                    """INSERT OR IGNORE INTO category_defaults
                       (base_category, length_cm, width_cm, height_cm, weight_kg, source_comment)
                       VALUES (?,?,?,?,?,?)""",
                    (cat, vals["length_cm"], vals["width_cm"],
                     vals["height_cm"], vals["weight_kg"], "builtin_default")
                )
            except Exception:
                pass
        conn.commit()


def get_category_defaults(conn: sqlite3.Connection, category: str) -> Optional[Dict]:
    """Получить средние габариты по категории из БД."""
    _seed_category_defaults(conn)
    c = conn.cursor()
    row = c.execute(
        """SELECT length_cm, width_cm, height_cm, weight_kg, source_comment
           FROM category_defaults WHERE base_category = ?""",
        (category,)
    ).fetchone()
    if row:
        return {
            "length_cm": row[0], "width_cm": row[1],
            "height_cm": row[2], "weight_kg": row[3],
            "source": row[4] or "category_default",
        }

    # Частичное совпадение по подстроке
    rows = c.execute("SELECT base_category, length_cm, width_cm, height_cm, weight_kg FROM category_defaults").fetchall()
    cat_lower = (category or "").lower()
    for r in rows:
        if r[0].lower() in cat_lower or cat_lower in r[0].lower():
            return {
                "length_cm": r[1], "width_cm": r[2],
                "height_cm": r[3], "weight_kg": r[4],
                "source": f"category_default_partial ({r[0]})",
            }
    return None


def search_dimensions_via_ai(query: str, api_key: str, snippets: list) -> Optional[Dict]:
    """
    Извлечь габариты и вес из текстовых сниппетов через GPT.

    Args:
        query:    поисковый запрос (название товара)
        api_key:  OpenAI key
        snippets: список текстовых фрагментов из поиска

    Returns:
        Dict с length_cm, width_cm, height_cm, weight_kg, confidence, source или None
    """
    if not api_key or not snippets:
        return None

    content = f"Товар: {query}\n\n"
    for i, s in enumerate(snippets[:5], 1):
        content += f"[Источник {i}]\n{s}\n\n"

    system_prompt = """Извлеки габариты и вес товара из текста.
Верни ТОЛЬКО валидный JSON без markdown:
{
  "length_cm": число или null,
  "width_cm": число или null,
  "height_cm": число или null,
  "weight_kg": число или null,
  "confidence": "high" | "medium" | "low",
  "source": "краткое описание источника"
}

Правила:
- Все размеры переводи в СМ (мм / 10, м * 100)
- Вес переводи в КГ (г / 1000)
- Если несколько источников расходятся — бери среднее или наиболее достоверное
- confidence = high если из официального магазина/производителя
- confidence = medium если из маркетплейса (Wildberries, Ozon, Яндекс.Маркет)
- confidence = low если данные сомнительные или неточные
- Если нет данных — ставь null"""

    try:
        client = OpenAI(api_key=api_key)
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": content},
            ],
            temperature=0,
            max_tokens=200,
        )
        raw = resp.choices[0].message.content.strip()
        # Убираем markdown если есть
        raw = raw.replace("```json", "").replace("```", "").strip()
        result = json.loads(raw)
        return result
    except Exception:
        return None


def enrich_product(
    product: Dict,
    conn: sqlite3.Connection,
    api_key: str,
    search_results: Optional[list] = None,
    force: bool = False,
) -> Tuple[Dict, str]:
    """
    Обогатить один товар габаритами и весом.

    Args:
        product:        dict с полями name, sku, ean, brand, category,
                        length_cm, width_cm, height_cm, weight_kg
        conn:           соединение с БД
        api_key:        OpenAI API ключ
        search_results: готовые сниппеты из web-поиска (если уже искали)
        force:          перезаписать даже если данные уже есть

    Returns:
        (обновлённый_product, метод_обогащения)
    """
    # Проверяем нужно ли обогащать
    # Проверяем нужно ли обогащать (значения должны быть > 0, а не просто заполнены)
    has_dims = all([
                    product.get("length_cm") is not None and product.get("length_cm") > 0,
                    product.get("width_cm") is not None and product.get("width_cm") > 0,
                    product.get("height_cm") is not None and product.get("height_cm") > 0,
                    product.get("weight_kg") is not None and product.get("weight_kg") > 0,
                ])
    if has_dims and not force:
        return product, "already_filled"

    method = "failed"

    # 1. Пробуем через web-поиск + AI
    if search_results and api_key:
        query = f"{product.get('brand', '')} {product.get('name', '')} {product.get('sku', '')}".strip()
        ai_result = search_dimensions_via_ai(query, api_key, search_results)

        if ai_result and ai_result.get("confidence") in ("high", "medium"):
            for field in ("length_cm", "width_cm", "height_cm", "weight_kg"):
                val = ai_result.get(field)
                if val and val > 0:
                                        if product.get(field) is None or product.get(field) <= 0 or force:
                        product[field] = round(float(val), 2)
            method = f"web_ai ({ai_result.get('confidence', '')}, {ai_result.get('source', '')})"

            # Проверяем что хотя бы что-то нашлось
            if any([product.get("length_cm"), product.get("width_cm"),
                    product.get("height_cm"), product.get("weight_kg")]):
                product["enrich_source"] = method
                product["enrich_status"] = "enriched"
                return product, method

    # 2. Fallback на средние по категории
    category = product.get("category", "")
    defaults = get_category_defaults(conn, category) if category else None

    if not defaults:
# Умное угадывание категории через keywords
            name_lower = (product.get("name", "") + " " + product.get("sku", "")).lower()
                for cat, keywords in CATEGORY_KEYWORDS.items():
                                if any(kw in name_lower for kw in keywords):
                                                    defaults = {
                                                                            **CATEGORY_DEFAULTS_BUILTIN[cat],
                                                                            "source": f"keyword_match ({cat})"
                                                                        }
                                                    break

    if defaults:
        for field in ("length_cm", "width_cm", "height_cm", "weight_kg"):
                        if product.get(field) is None or product.get(field) <= 0 or force:
                product[field] = defaults.get(field)
        method = f"category_default ({defaults.get('source', category)})"
        product["enrich_source"] = method
    return product, method

        # Fallback на "Прочее" если ничего не нашли
        if not defaults:
                    defaults = CATEGORY_DEFAULTS_BUILTIN.get("Прочее")
                    if defaults:
                                    for field in ("length_cm", "width_cm", "height_cm", "weight_kg"):
                                                                                if product.get(field) is None or product.get(field) <= 0 or force:
                                                                                product[field] = defaults[field]
                                                                        method = "category_default (fallback_generic)"
                                                    product["enrich_source"] = method
                                    product["enrich_status"] = "default"
                                    return product, method
                        
    product["enrich_status"] = "failed"
    return product, "failed"


def log_enrichment(conn: sqlite3.Connection, product_id: int, method: str, success: bool, comment: str = ""):
    """Записать результат обогащения в лог."""
    try:
        c = conn.cursor()
        c.execute(
            """INSERT INTO enrichment_log (product_id, method, success, comment)
               VALUES (?, ?, ?, ?)""",
            (product_id, method, int(success), comment)
        )
        conn.commit()
    except Exception:
        pass
