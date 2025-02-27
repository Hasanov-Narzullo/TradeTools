from apscheduler.schedulers.asyncio import AsyncIOScheduler
from loguru import logger

from config import settings
from database import get_alerts, remove_alert, add_event
from api import get_stock_price, get_crypto_price, fetch_economic_calendar, fetch_dividends_and_earnings
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
    logger.info("Обновление календаря событий...")

    # Получаем общеэкономические события
    economic_events = await fetch_economic_calendar()
    for event in economic_events:
        await add_event(
            event_date=event["event_date"],
            title=event["title"],
            description=event["description"],
            source=event["source"],
            event_type=event["type"],
            symbol=None
        )

    # Получаем события для активов из портфеля
    async with aiosqlite.connect(settings.db.DB_PATH) as db:
        cursor = await db.execute("SELECT DISTINCT symbol FROM portfolios")
        symbols = [row[0] for row in await cursor.fetchall()]

    for symbol in symbols:
        asset_events = await fetch_dividends_and_earnings(symbol)
        for event in asset_events:
            await add_event(
                event_date=event["event_date"],
                title=event["title"],
                description=event["description"],
                source=event["source"],
                event_type=event["type"],
                symbol=event["symbol"]
            )

    logger.info("Календарь событий обновлен.")

def setup_scheduler(scheduler: AsyncIOScheduler):
    """Настройка планировщика задач."""
    scheduler.add_job(check_alerts, "interval", minutes=5)  # Проверка алертов каждые 5 минут
    scheduler.add_job(update_quotes, "interval", minutes=10)  # Обновление котировок каждые 10 минут
    scheduler.add_job(update_calendar, "interval", hours=24)  # Обновление календаря раз в день
    logger.info("Планировщик настроен.")