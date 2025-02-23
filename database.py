import aiosqlite
from config import settings
from loguru import logger
from datetime import datetime

async def init_db():
    """Инициализация базы данных."""
    try:
        async with aiosqlite.connect(settings.db.DB_PATH) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS portfolio (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    asset_type TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    amount REAL NOT NULL,
                    purchase_price REAL NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await db.commit()
            logger.info("База данных инициализирована успешно")
    except Exception as e:
        logger.error(f"Ошибка при инициализации базы данных: {e}")
        raise

# Функции для работы с портфелем
async def add_to_portfolio(user_id: int, asset_type: str, symbol: str, amount: float, purchase_price: float):
    try:
        async with aiosqlite.connect(settings.db.DB_PATH) as db:
            await db.execute(
                """
                INSERT INTO portfolio (user_id, asset_type, symbol, amount, purchase_price)
                VALUES (?, ?, ?, ?, ?)
                """,
                (user_id, asset_type, symbol, amount, purchase_price)
            )
            await db.commit()
            logger.info(f"Добавлен актив в портфель: user_id={user_id}, symbol={symbol}")
    except Exception as e:
        logger.error(f"Ошибка при добавлении актива в портфель: {e}")
        raise

async def get_portfolio(user_id: int) -> list:
    try:
        async with aiosqlite.connect(settings.db.DB_PATH) as db:
            async with db.execute(
                """
                SELECT asset_type, symbol, amount, purchase_price 
                FROM portfolio 
                WHERE user_id = ?
                """,
                (user_id,)
            ) as cursor:
                rows = await cursor.fetchall()
                logger.info(f"Получены данные портфеля для пользователя {user_id}: {rows}")
                return [
                    {
                        'asset_type': row[0],
                        'symbol': row[1],
                        'amount': row[2],
                        'purchase_price': row[3]
                    }
                    for row in rows
                ]
    except Exception as e:
        logger.error(f"Ошибка при получении портфеля для пользователя {user_id}: {e}")
        return []

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