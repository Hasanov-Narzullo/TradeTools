from api import get_stock_price, get_crypto_price, fetch_economic_calendar, fetch_dividends_and_earnings, \
    fetch_test_events
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from loguru import logger
from config import settings
from database import get_alerts, remove_alert, add_event
from bot import bot
import aiosqlite
from datetime import datetime, timedelta
from utils import format_price


async def check_alerts():
    """Проверка алертов и отправка уведомлений."""
    logger.info("Проверка алертов...")
    async with aiosqlite.connect(settings.db.DB_PATH) as db:
        cursor = await db.execute("SELECT * FROM alerts")
        alerts = await cursor.fetchall()

    for alert in alerts:
        alert_id, user_id, asset_type, symbol, target_price, condition, _ = alert
        price = None

        if asset_type == "stock":
            price = await get_stock_price(symbol)
        elif asset_type == "crypto":
            price = await get_crypto_price(symbol)

        if price is None:
            continue

        if (condition == "above" and price >= target_price) or (condition == "below" and price <= target_price):
            await bot.send_message(user_id, f"⚠️ Алерт! {symbol} достиг цены {format_price(price)} (цель: {format_price(target_price)})")
            await remove_alert(alert_id)
            logger.info(f"Алерт {alert_id} сработал и удален.")


async def update_quotes():
    """Обновление котировок (можно расширить для сохранения в базу)."""
    logger.info("Обновление котировок...")


async def update_calendar():
    """Обновление календаря событий с использованием EODHD и других источников."""
    logger.info("Начало обновления календаря событий...")

    try:
        # Проверяем портфель
        async with aiosqlite.connect(settings.db.DB_PATH) as db:
            cursor = await db.execute("SELECT DISTINCT symbol FROM portfolios")
            symbols = [row[0] for row in await cursor.fetchall()]
            logger.info(f"Найдено {len(symbols)} уникальных символов в портфеле: {symbols}")

        # Получаем события через fetch_economic_calendar (включает EODHD и Alpha Vantage)
        calendar_events = await fetch_economic_calendar()
        logger.info(f"Получено {len(calendar_events)} событий экономического календаря")
        for event in calendar_events:
            try:
                await add_event(
                    event_date=event["event_date"],
                    title=event["title"],
                    description=event["description"],
                    source=event["source"],
                    event_type=event["type"],
                    symbol=event["symbol"]
                )
                logger.debug(f"Добавлено событие календаря: {event['title']}")
            except Exception as e:
                logger.error(f"Ошибка при добавлении события календаря: {e}")
                continue

        # Получаем дивиденды и отчетности для активов из портфеля (включает EODHD)
        for symbol in symbols:
            asset_events = await fetch_dividends_and_earnings(symbol)
            logger.info(f"Получено {len(asset_events)} событий для актива {symbol}")
            for event in asset_events:
                try:
                    await add_event(
                        event_date=event["event_date"],
                        title=event["title"],
                        description=event["description"],
                        source=event["source"],
                        event_type=event["type"],
                        symbol=event["symbol"]
                    )
                    logger.debug(f"Добавлено событие для актива {symbol}: {event['title']}")
                except Exception as e:
                    logger.error(f"Ошибка при добавлении события для актива {symbol}: {e}")
                    continue

        # Добавляем тестовые события для проверки
        test_events = await fetch_test_events()
        logger.info(f"Получено {len(test_events)} тестовых событий")
        for event in test_events:
            try:
                await add_event(
                    event_date=event["event_date"],
                    title=event["title"],
                    description=event["description"],
                    source=event["source"],
                    event_type=event["type"],
                    symbol=event["symbol"]
                )
                logger.debug(f"Добавлено тестовое событие: {event['title']}")
            except Exception as e:
                logger.error(f"Ошибка при добавлении тестового события: {e}")
                continue

        # Проверяем базу данных после обновления
        async with aiosqlite.connect(settings.db.DB_PATH) as db:
            cursor = await db.execute("SELECT COUNT(*) FROM events")
            event_count = (await cursor.fetchone())[0]
            logger.info(f"Календарь событий обновлен. В базе данных {event_count} событий.")

    except Exception as e:
        logger.error(f"Ошибка при обновлении календаря событий: {e}")

def setup_scheduler(scheduler: AsyncIOScheduler):
    """Настройка планировщика задач."""
    scheduler.add_job(check_alerts, "interval", minutes=5)  # Проверка алертов каждые 5 минут
    scheduler.add_job(update_quotes, "interval", minutes=10)  # Обновление котировок каждые 10 минут
    scheduler.add_job(update_calendar, "interval", hours=2.5)  # Обновление календаря каждые 5 часов
    logger.info("Планировщик настроен.")