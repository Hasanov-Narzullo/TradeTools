# database
import aiosqlite
from config import settings
from loguru import logger
from datetime import datetime

from events_data import get_sample_events

# Инициализация базы данных и создание таблиц.
async def init_db():
    try:
        async with aiosqlite.connect(settings.db.DB_PATH) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS portfolios (
                    user_id INTEGER,
                    sub_account_name TEXT NOT NULL DEFAULT 'Основной',
                    asset_type TEXT,
                    symbol TEXT,
                    amount REAL,
                    purchase_price REAL,
                    purchase_date TEXT,
                    PRIMARY KEY (user_id, sub_account_name, symbol)
                )
            """)
            logger.info("Таблица portfolios создана или уже существует.")

            # Проверка и добавление колонки sub_account_name, если ее нет
            cursor = await db.execute("PRAGMA table_info(portfolios)")
            columns = [column[1] for column in await cursor.fetchall()]
            if 'sub_account_name' not in columns:
                logger.warning("Колонка 'sub_account_name' отсутствует в таблице 'portfolios'. Добавляем...")
                await db.execute("ALTER TABLE portfolios ADD COLUMN sub_account_name TEXT NOT NULL DEFAULT 'Основной'")
                logger.info("Колонка 'sub_account_name' успешно добавлена.")
            else:
                logger.debug("Колонка 'sub_account_name' уже существует.")


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

            await db.execute("""
                CREATE TABLE IF NOT EXISTS chat_settings (
                    chat_id INTEGER PRIMARY KEY,
                    allow_all_users BOOLEAN DEFAULT TRUE
                )
            """)
            logger.info("Таблица chat_settings создана или уже существует.")

            await db.commit()
        logger.info("База данных успешно инициализирована.")
    except Exception as e:
        logger.error(f"Ошибка при инициализации базы данных: {e}")
        raise

# Функции для работы с портфелем
# Добавление актива в портфель пользователя.
async def add_to_portfolio(user_id: int, sub_account_name: str, asset_type: str, symbol: str, amount: float, purchase_price: float):
    effective_sub_account_name = sub_account_name if sub_account_name else "Основной"
    async with aiosqlite.connect(settings.db.DB_PATH) as db:
        try:
            await db.execute("""
                INSERT OR REPLACE INTO portfolios (user_id, sub_account_name, asset_type, symbol, amount, purchase_price, purchase_date)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (user_id, effective_sub_account_name, asset_type, symbol, amount, purchase_price, datetime.now().isoformat()))
            await db.commit()
            logger.info(f"Актив {symbol} добавлен в портфель пользователя {user_id} (суб-счет: {effective_sub_account_name}).")
        except Exception as e:
            logger.error(f"Ошибка при добавлении актива {symbol} для пользователя {user_id} (суб-счет: {effective_sub_account_name}): {e}")
            raise

# Получает портфель пользователя из базы данных.
async def get_portfolio(user_id: int):
    portfolio_by_sub_account = {}
    async with aiosqlite.connect(settings.db.DB_PATH) as db:
        try:
            cursor = await db.execute(
                "SELECT sub_account_name, symbol, asset_type, amount, purchase_price FROM portfolios WHERE user_id = ? ORDER BY sub_account_name, symbol",
                (user_id,)
            )
            rows = await cursor.fetchall()
            if not rows:
                logger.info(f"Портфель пользователя {user_id} пуст.")
                return {}

            for row in rows:
                try:
                    sub_account = str(row[0])
                    portfolio_item = {
                        'symbol': str(row[1]),
                        'asset_type': row[2],
                        'amount': float(row[3]),
                        'purchase_price': float(row[4])
                    }
                    if sub_account not in portfolio_by_sub_account:
                        portfolio_by_sub_account[sub_account] = []
                    portfolio_by_sub_account[sub_account].append(portfolio_item)
                except (ValueError, TypeError, IndexError) as e:
                    logger.error(f"Ошибка при преобразовании данных актива {row[1]} для суб-счета {row[0]}: {e}")
                    continue
            logger.info(f"Получен портфель для пользователя {user_id} с {len(portfolio_by_sub_account)} суб-счетами.")
            return portfolio_by_sub_account
        except Exception as e:
            logger.error(f"Ошибка при получении портфеля пользователя {user_id}: {e}")
            raise

# Удаление актива из портфеля пользователя.
async def remove_from_portfolio(user_id: int, sub_account_name: str, symbol: str):
    async with aiosqlite.connect(settings.db.DB_PATH) as db:
        try:
            await db.execute("DELETE FROM portfolios WHERE user_id = ? AND sub_account_name = ? AND symbol = ?", (user_id, sub_account_name, symbol))
            await db.commit()
            logger.info(f"Актив {symbol} удален из суб-счета '{sub_account_name}' пользователя {user_id}.")
        except Exception as e:
            logger.error(f"Ошибка при удалении актива {symbol} из суб-счета '{sub_account_name}' для пользователя {user_id}: {e}")
            raise

async def get_sub_accounts(user_id: int) -> list[str]:
    main_account_name = "Основной"
    sub_accounts = set()
    async with aiosqlite.connect(settings.db.DB_PATH) as db:
        try:
            cursor = await db.execute(
                "SELECT DISTINCT sub_account_name FROM portfolios WHERE user_id = ?",
                (user_id,)
            )
            rows = await cursor.fetchall()
            for row in rows:
                sub_accounts.add(row[0])

            sub_accounts.add(main_account_name)

            sorted_sub_accounts = sorted(list(sub_accounts))

            if main_account_name in sorted_sub_accounts:
                sorted_sub_accounts.remove(main_account_name)
                sorted_sub_accounts.insert(0, main_account_name)

            logger.info(f"Получены суб-счета для пользователя {user_id}: {sorted_sub_accounts}")
            return sorted_sub_accounts
        except Exception as e:
            logger.error(f"Ошибка при получении суб-счетов пользователя {user_id}: {e}")
            return [main_account_name]

async def delete_sub_account(user_id: int, sub_account_name: str):
    main_account_name = "Основной"
    if sub_account_name == main_account_name:
        logger.warning(f"Попытка удаления основного суб-счета '{main_account_name}' пользователем {user_id}.")
        raise ValueError(f"Нельзя удалить основной суб-счет '{main_account_name}'.")

    async with aiosqlite.connect(settings.db.DB_PATH) as db:
        try:
            cursor = await db.execute(
                "SELECT 1 FROM portfolios WHERE user_id = ? AND sub_account_name = ? LIMIT 1",
                (user_id, sub_account_name)
            )
            exists = await cursor.fetchone()
            if not exists:
                logger.warning(f"Попытка удаления несуществующего суб-счета '{sub_account_name}' пользователем {user_id}.")
                raise ValueError(f"Суб-счет '{sub_account_name}' не найден.")

            await db.execute("DELETE FROM portfolios WHERE user_id = ? AND sub_account_name = ?", (user_id, sub_account_name))
            await db.commit()
            logger.info(f"Суб-счет '{sub_account_name}' и все его активы удалены для пользователя {user_id}.")
        except ValueError as ve:
            raise ve
        except Exception as e:
            logger.error(f"Ошибка при удалении суб-счета '{sub_account_name}' для пользователя {user_id}: {e}")
            raise

# Функции для работы с алертами
# Добавление алерта для пользователя.
async def add_alert(chat_id: int, asset_type: str, symbol: str, target_price: float, condition: str):
    async with aiosqlite.connect(settings.db.DB_PATH) as db:
        try:
            await db.execute("""
                INSERT INTO alerts (user_id, asset_type, symbol, target_price, condition, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (chat_id, asset_type, symbol, target_price, condition, datetime.now().isoformat()))
            await db.commit()
            logger.info(f"Алерт для {symbol} добавлен для чата {chat_id}.")
        except Exception as e:
            logger.error(f"Ошибка при добавлении алерта для {symbol} чата {chat_id}: {e}")
            raise

# Получение алертов пользователя или всех алертов.
async def get_alerts(chat_id: int = None):
    async with aiosqlite.connect(settings.db.DB_PATH) as db:
        try:
            if chat_id:
                cursor = await db.execute("SELECT * FROM alerts WHERE user_id = ?", (chat_id,))
            else:
                cursor = await db.execute("SELECT * FROM alerts")
            alerts = await cursor.fetchall()
            logger.info(f"Получено {len(alerts)} алертов для чата {chat_id if chat_id else 'всех'}")
            return alerts
        except Exception as e:
            logger.error(f"Ошибка при получении алертов: {e}")
            raise

# Удаление алерта по ID.
async def remove_alert(alert_id: int):
    async with aiosqlite.connect(settings.db.DB_PATH) as db:
        try:
            await db.execute("DELETE FROM alerts WHERE id = ?", (alert_id,))
            await db.commit()
            logger.info(f"Алерт {alert_id} удален.")
        except Exception as e:
            logger.error(f"Ошибка при удалении алерта {alert_id}: {e}")
            raise

# Функции для работы с событиями
# Добавление события в базу данных.
async def add_event(event_date: str, title: str, description: str, source: str, event_type: str, symbol: str = None):
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

# Получение событий с фильтрацией по типу и активам из портфеля.
async def get_events(user_id: int = None, event_type: str = None, portfolio_only: bool = False) -> list:
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

# Загружает пример событий в базу данных.
async def load_sample_events():
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

async def get_or_create_chat_settings(chat_id: int) -> tuple:
    async with aiosqlite.connect(settings.db.DB_PATH) as db:
        try:
            cursor = await db.execute("SELECT allow_all_users FROM chat_settings WHERE chat_id = ?", (chat_id,))
            row = await cursor.fetchone()
            if row:
                logger.debug(f"Настройки для чата {chat_id}: allow_all_users={row[0]}")
                return row[0], # Return existing setting
            else:
                # Create default settings if not exist
                await db.execute("INSERT INTO chat_settings (chat_id, allow_all_users) VALUES (?, ?)", (chat_id, True))
                await db.commit()
                logger.info(f"Созданы стандартные настройки для чата {chat_id}.")
                return True, # Return default setting
        except Exception as e:
            logger.error(f"Ошибка при получении/создании настроек для чата {chat_id}: {e}")
            return True, # Return default on error

async def update_chat_settings(chat_id: int, allow_all_users: bool):
    async with aiosqlite.connect(settings.db.DB_PATH) as db:
        try:
            await db.execute("""
                INSERT OR REPLACE INTO chat_settings (chat_id, allow_all_users)
                VALUES (?, ?)
            """, (chat_id, allow_all_users))
            await db.commit()
            logger.info(f"Обновлены настройки для чата {chat_id}: allow_all_users={allow_all_users}")
        except Exception as e:
            logger.error(f"Ошибка при обновлении настроек для чата {chat_id}: {e}")
            raise