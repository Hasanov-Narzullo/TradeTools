# alert_checker
import asyncio
from datetime import datetime
from loguru import logger
from aiogram import Bot
from database import get_alerts, remove_alert
from api import fetch_asset_price_with_retry

"""Фоновая задача для проверки алертов."""
async def check_alerts(bot: Bot):
    while True:
        try:
            alerts = await get_alerts()
            for alert in alerts:
                alert_id, chat_id, asset_type, symbol, target_price, condition, created_at = alert

                current_price = await fetch_asset_price_with_retry(symbol, asset_type)
                if current_price is None:
                    logger.warning(f"Не удалось получить цену для {symbol} ({asset_type})")
                    continue

                triggered = False
                if condition == "above" and current_price >= target_price:
                    triggered = True
                elif condition == "below" and current_price <= target_price:
                    triggered = True

                if triggered:
                    try:
                        await bot.send_message(
                            chat_id,
                            f"🔔 Алерт сработал!\n"
                            f"Актив: {symbol} ({asset_type})\n"
                            f"Текущая цена: ${current_price:.2f}\n"
                            f"Целевая цена: ${target_price:.2f} ({'выше' if condition == 'above' else 'ниже'})"
                        )
                        await remove_alert(alert_id)
                        logger.info(f"Алерт сработал для чата {chat_id}: {symbol} - {condition} ${target_price:.2f}")
                    except Exception as e:
                        logger.error(f"Ошибка при отправке уведомления в чат {chat_id}: {e}")

        except Exception as e:
            logger.error(f"Ошибка при проверке алертов: {e}")

        await asyncio.sleep(60)