import aiosqlite
from config import settings
from loguru import logger
from datetime import datetime

from events_data import get_sample_events


async def init_db():
    """Инициализация базы данных и создание таблиц."""
    try:
        async with aiosqlite.connect(settings.db.DB_PATH) as db:
            # Проверяем текущую структуру таблицы
            cursor = await db.execute("PRAGMA table_info(events)")
            columns = [row[1] for row in await cursor.fetchall()]

            # Создаем таблицу portfolios
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
            logger.info("Таблица portfolios создана или уже существует.")

            # Создаем таблицу alerts
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
            logger.info("Таблица alerts создана или уже существует.")

            # Создаем таблицу events
            await db.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_date TEXT,
                    title TEXT,
                    description TEXT,
                    source TEXT,
                    type TEXT,
                    symbol TEXT,
                    UNIQUE(event_date, title, symbol)
                )
            """)
            logger.info("Таблица events создана или уже существует.")

            # Добавляем столбцы, если они отсутствуют
            if "type" not in columns:
                await db.execute("ALTER TABLE events ADD COLUMN type TEXT")
                logger.info("Добавлен столбец 'type' в таблицу events.")
            if "symbol" not in columns:
                await db.execute("ALTER TABLE events ADD COLUMN symbol TEXT")
                logger.info("Добавлен столбец 'symbol' в таблицу events.")

            await db.commit()
        logger.info("База данных успешно инициализирована.")
    except Exception as e:
        logger.error(f"Ошибка при инициализации базы данных: {e}")
        raise

# Функции для работы с портфелем
async def add_to_portfolio(user_id: int, asset_type: str, symbol: str, amount: float, purchase_price: float):
    """Добавление актива в портфель пользователя."""
    async with aiosqlite.connect(settings.db.DB_PATH) as db:
        try:
            await db.execute("""
                INSERT OR REPLACE INTO portfolios (user_id, asset_type, symbol, amount, purchase_price, purchase_date)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (user_id, asset_type, symbol, amount, purchase_price, datetime.now().isoformat()))
            await db.commit()
            logger.info(f"Актив {symbol} добавлен в портфель пользователя {user_id}.")
        except Exception as e:
            logger.error(f"Ошибка при добавлении актива {symbol} для пользователя {user_id}: {e}")
            raise

async def get_portfolio(user_id: int):
    """Получает портфель пользователя из базы данных."""
    async with aiosqlite.connect(settings.db.DB_PATH) as db:
        try:
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
            logger.info(f"Получено {len(result)} активов из портфеля пользователя {user_id}")
            return result
        except Exception as e:
            logger.error(f"Ошибка при получении портфеля пользователя {user_id}: {e}")
            raise

async def remove_from_portfolio(user_id: int, symbol: str):
    """Удаление актива из портфеля пользователя."""
    async with aiosqlite.connect(settings.db.DB_PATH) as db:
        try:
            await db.execute("DELETE FROM portfolios WHERE user_id = ? AND symbol = ?", (user_id, symbol))
            await db.commit()
            logger.info(f"Актив {symbol} удален из портфеля пользователя {user_id}.")
        except Exception as e:
            logger.error(f"Ошибка при удалении актива {symbol} для пользователя {user_id}: {e}")
            raise

# Функции для работы с алертами
async def add_alert(user_id: int, asset_type: str, symbol: str, target_price: float, condition: str):
    """Добавление алерта для пользователя."""
    async with aiosqlite.connect(settings.db.DB_PATH) as db:
        try:
            await db.execute("""
                INSERT INTO alerts (user_id, asset_type, symbol, target_price, condition, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (user_id, asset_type, symbol, target_price, condition, datetime.now().isoformat()))
            await db.commit()
            logger.info(f"Алерт для {symbol} добавлен для пользователя {user_id}.")
        except Exception as e:
            logger.error(f"Ошибка при добавлении алерта для {symbol} пользователя {user_id}: {e}")
            raise

async def get_alerts(user_id: int = None):
    """Получение алертов пользователя или всех алертов."""
    async with aiosqlite.connect(settings.db.DB_PATH) as db:
        try:
            if user_id:
                cursor = await db.execute("SELECT * FROM alerts WHERE user_id = ?", (user_id,))
            else:
                cursor = await db.execute("SELECT * FROM alerts")
            alerts = await cursor.fetchall()
            logger.info(f"Получено {len(alerts)} алертов для пользователя {user_id if user_id else 'всех'}")
            return alerts
        except Exception as e:
            logger.error(f"Ошибка при получении алертов: {e}")
            raise

async def remove_alert(alert_id: int):
    """Удаление алерта по ID."""
    async with aiosqlite.connect(settings.db.DB_PATH) as db:
        try:
            await db.execute("DELETE FROM alerts WHERE id = ?", (alert_id,))
            await db.commit()
            logger.info(f"Алерт {alert_id} удален.")
        except Exception as e:
            logger.error(f"Ошибка при удалении алерта {alert_id}: {e}")
            raise

# Функции для работы с событиями
async def add_event(event_date: str, title: str, description: str, source: str, event_type: str, symbol: str = None):
    """Добавление события в базу данных."""
    async with aiosqlite.connect(settings.db.DB_PATH) as db:
        try:
            # Проверяем, существует ли событие
            cursor = await db.execute(
                "SELECT COUNT(*) FROM events WHERE event_date = ? AND title = ? AND (symbol = ? OR (symbol IS NULL AND ? IS NULL))",
                (event_date, title, symbol, symbol)
            )
            exists = (await cursor.fetchone())[0]
            if exists:
                logger.debug(f"Событие '{title}' уже существует, пропускаем")
                return

            # Вставляем событие
            await db.execute("""
                INSERT INTO events (event_date, title, description, source, type, symbol)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (event_date, title, description, source, event_type, symbol))
            await db.commit()
            logger.info(f"Добавлено событие: {title} (тип: {event_type}, символ: {symbol})")
        except Exception as e:
            logger.error(f"Ошибка при добавлении события '{title}': {e}")
            raise

async def get_events(user_id: int = None, event_type: str = None, portfolio_only: bool = False) -> list:
    """Получение событий с фильтрацией по типу и активам из портфеля."""
    query = "SELECT * FROM events WHERE 1=1"
    params = []

    try:
        if portfolio_only and user_id:
            # Получаем символы из портфеля пользователя
            async with aiosqlite.connect(settings.db.DB_PATH) as db:
                cursor = await db.execute("SELECT DISTINCT symbol FROM portfolios WHERE user_id = ?", (user_id,))
                portfolio_symbols = [row[0] for row in await cursor.fetchall()]
            if portfolio_symbols:
                query += " AND symbol IN (" + ",".join("?" * len(portfolio_symbols)) + ")"
                params.extend(portfolio_symbols)
            else:
                logger.info(f"Портфель пользователя {user_id} пуст, возвращаем пустой список событий")
                return []

        if event_type:
            query += " AND type = ?"
            params.append(event_type)

        query += " ORDER BY event_date ASC"

        async with aiosqlite.connect(settings.db.DB_PATH) as db:
            cursor = await db.execute(query, params)
            events = await cursor.fetchall()
            result = [
                (event[0], event[1], event[2], event[3], event[4], event[5], event[6])
                for event in events
            ]
            logger.info(f"Получено {len(result)} событий для пользователя {user_id if user_id else 'всех'}, тип: {event_type if event_type else 'все'}, только портфель: {portfolio_only}")
            return result
    except Exception as e:
        logger.error(f"Ошибка при получении событий: {e}")
        raise

async def load_sample_events():
    """Загружает пример событий в базу данных."""
    events = get_sample_events()
    for event in events:
        try:
            await add_event(
                event_date=event["event_date"],
                title=event["title"],
                description=event["description"],
                source=event["source"],
                event_type=event["type"],
                symbol=event["symbol"]
            )
            logger.info(f"Добавлено примерное событие: {event['title']}")
        except Exception as e:
            logger.error(f"Ошибка при добавлении примера события: {e}")