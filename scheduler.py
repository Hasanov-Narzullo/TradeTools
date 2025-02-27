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
    """Обновление календаря событий."""
    logger.info("Начало обновления календаря событий...")

    # Проверяем портфель
    async with aiosqlite.connect(settings.db.DB_PATH) as db:
        cursor = await db.execute("SELECT DISTINCT symbol FROM portfolios")
        symbols = [row[0] for row in await cursor.fetchall()]
        logger.info(f"Найдено {len(symbols)} уникальных символов в портфеле: {symbols}")

    # Получаем события через Finnhub (IPO, экономические события, отчетности)
    finnhub_events = await fetch_economic_calendar()
    logger.info(f"Получено {len(finnhub_events)} событий с Finnhub")
    for event in finnhub_events:
        try:
            await add_event(
                event_date=event["event_date"],
                title=event["title"],
                description=event["description"],
                source=event["source"],
                event_type=event["type"],
                symbol=event["symbol"]
            )
            logger.debug(f"Добавлено событие с Finnhub: {event['title']}")
        except Exception as e:
            logger.error(f"Ошибка при добавлении события с Finnhub: {e}")

    # Получаем дивиденды для активов из портфеля через yfinance
    for symbol in symbols:
        yfinance_events = await fetch_dividends_and_earnings(symbol)
        logger.info(f"Получено {len(yfinance_events)} событий для актива {symbol} через yfinance")
        for event in yfinance_events:
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

    # Проверяем базу данных после обновления
    async with aiosqlite.connect(settings.db.DB_PATH) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM events")
        event_count = (await cursor.fetchone())[0]
        logger.info(f"Календарь событий обновлен. В базе данных {event_count} событий.")

def setup_scheduler(scheduler: AsyncIOScheduler):
    """Настройка планировщика задач."""
    scheduler.add_job(check_alerts, "interval", minutes=5)  # Проверка алертов каждые 5 минут
    scheduler.add_job(update_quotes, "interval", minutes=10)  # Обновление котировок каждые 10 минут
    scheduler.add_job(update_calendar, "interval", hours=24)  # Обновление календаря раз в день
    logger.info("Планировщик настроен.")