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


def setup_scheduler(scheduler: AsyncIOScheduler):
    """Настройка планировщика задач."""
    scheduler.add_job(check_alerts, "interval", minutes=5)  # Проверка алертов каждые 5 минут
    scheduler.add_job(update_quotes, "interval", minutes=10)  # Обновление котировок каждые 10 минут
    scheduler.add_job(update_calendar, "interval", hours=5)  # Обновление календаря каждые 5 часов
    logger.info("Планировщик настроен.")

def setup_scheduler(scheduler: AsyncIOScheduler):
    """Настройка планировщика задач."""
    scheduler.add_job(check_alerts, "interval", minutes=5)  # Проверка алертов каждые 5 минут
    scheduler.add_job(update_quotes, "interval", minutes=10)  # Обновление котировок каждые 10 минут
    scheduler.add_job(update_calendar, "interval", hours=24)  # Обновление календаря раз в день
    logger.info("Планировщик настроен.")