import aiosqlite
from config import settings
from loguru import logger
from datetime import datetime

async def init_db():
    async with aiosqlite.connect(settings.db.DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS portfolios (
                user_id INTEGER,
                asset_type TEXT,  -- stock или crypto
                symbol TEXT,
                amount REAL,
                purchase_price REAL,
                purchase_date TEXT,
                PRIMARY KEY (user_id, symbol)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                asset_type TEXT,  -- stock или crypto
                symbol TEXT,
                target_price REAL,
                condition TEXT,   -- above или below
                created_at TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_date TEXT,
                title TEXT,
                description TEXT,
                source TEXT
            )
        """)
        await db.commit()
    logger.info("База данных инициализирована.")

# Функции для работы с портфелем
async def add_to_portfolio(user_id: int, asset_type: str, symbol: str, amount: float, purchase_price: float):
    async with aiosqlite.connect(settings.db.DB_PATH) as db:
        await db.execute("""
            INSERT OR REPLACE INTO portfolios (user_id, asset_type, symbol, amount, purchase_price, purchase_date)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (user_id, asset_type, symbol, amount, purchase_price, datetime.now().isoformat()))
        await db.commit()
    logger.info(f"Актив {symbol} добавлен в портфель пользователя {user_id}.")

async def get_portfolio(user_id: int):
    async with aiosqlite.connect(settings.db.DB_PATH) as db:
        cursor = await db.execute("SELECT * FROM portfolios WHERE user_id = ?", (user_id,))
        return await cursor.fetchall()

async def remove_from_portfolio(user_id: int, symbol: str):
    async with aiosqlite.connect(settings.db.DB_PATH) as db:
        await db.execute("DELETE FROM portfolios WHERE user_id = ? AND symbol = ?", (user_id, symbol))
        await db.commit()
    logger.info(f"Актив {symbol} удален из портфеля пользователя {user_id}.")

async def add_alert(user_id: int, asset_type: str, symbol: str, target_price: float, condition: str):
    async with aiosqlite.connect(settings.db.DB_PATH) as db:
        await db.execute("""
            INSERT INTO alerts (user_id, asset_type, symbol, target_price, condition, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (user_id, asset_type, symbol, target_price, condition, datetime.now().isoformat()))
        await db.commit()
    logger.info(f"Алерт для {symbol} добавлен для пользователя {user_id}.")

async def get_alerts(user_id: int):
    async with aiosqlite.connect(settings.db.DB_PATH) as db:
        cursor = await db.execute("SELECT * FROM alerts WHERE user_id = ?", (user_id,))
        return await cursor.fetchall()

async def remove_alert(alert_id: int):
    async with aiosqlite.connect(settings.db.DB_PATH) as db:
        await db.execute("DELETE FROM alerts WHERE id = ?", (alert_id,))
        await db.commit()
    logger.info(f"Алерт {alert_id} удален.")

# Функции для работы с событиями
async def add_event(event_date: str, title: str, description: str, source: str):
    async with aiosqlite.connect(settings.db.DB_PATH) as db:
        await db.execute("""
            INSERT INTO events (event_date, title, description, source)
            VALUES (?, ?, ?, ?)
        """, (event_date, title, description, source))
        await db.commit()
    logger.info(f"Событие '{title}' добавлено.")

async def get_events():
    async with aiosqlite.connect(settings.db.DB_PATH) as db:
        cursor = await db.execute("SELECT * FROM events")
        return await cursor.fetchall()

# database.py
async def get_portfolio(user_id: int):
    """Получает портфель пользователя из базы данных."""
    async with aiosqlite.connect(settings.db.DB_PATH) as db:
        cursor = await db.execute(
            "SELECT symbol, asset_type, amount, purchase_price FROM portfolios WHERE user_id = ?",
            (user_id,)
        )
        rows = await cursor.fetchall()
        result = []
        for row in rows:
            try:
                portfolio_item = {
                    'symbol': str(row[0]),        # symbol (строка)
                    'asset_type': row[1],         # asset_type (строка)
                    'amount': float(row[2]),      # amount (float)
                    'purchase_price': float(row[3])  # purchase_price (float)
                }
                result.append(portfolio_item)
            except (ValueError, TypeError, IndexError) as e:
                logger.error(f"Ошибка при преобразовании данных актива {row[0]}: {e}")
                continue
        return result


async def init_db():
    """Инициализация базы данных и создание таблиц."""
    try:
        async with aiosqlite.connect(settings.db.DB_PATH) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS portfolios (
                    user_id INTEGER,
                    asset_type TEXT,
                    symbol TEXT,
                    amount REAL,
                    purchase_price REAL,
                    purchase_date TEXT,
                    PRIMARY KEY (user_id, symbol)
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    asset_type TEXT,
                    symbol TEXT,
                    target_price REAL,
                    condition TEXT,
                    created_at TEXT
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_date TEXT,
                    title TEXT,
                    description TEXT,
                    source TEXT
                )
            """)
            await db.commit()
        logger.info("База данных инициализирована.")
    except Exception as e:
        logger.error(f"Ошибка при инициализации базы данных: {e}")
        raise