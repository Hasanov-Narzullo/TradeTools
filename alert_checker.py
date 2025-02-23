import asyncio
from datetime import datetime
from loguru import logger
from aiogram import Bot
from database import get_alerts, remove_alert
from api import fetch_asset_price_with_retry

async def check_alerts(bot: Bot):
    """Фоновая задача для проверки алертов."""
    while True:
        try:
            # Получаем все алерты из базы данных
            alerts = await get_alerts()  # Предполагается, что get_alerts() без user_id возвращает все алерты
            for alert in alerts:
                alert_id, user_id, asset_type, symbol, target_price, condition, created_at = alert

                # Получаем текущую цену актива
                current_price = await fetch_asset_price_with_retry(symbol, asset_type)
                if current_price is None:
                    logger.warning(f"Не удалось получить цену для {symbol} ({asset_type})")
                    continue

                # Проверяем условие алерта
                triggered = False
                if condition == "above" and current_price >= target_price:
                    triggered = True
                elif condition == "below" and current_price <= target_price:
                    triggered = True

                # Если условие выполнено, отправляем уведомление и удаляем алерт
                if triggered:
                    try:
                        await bot.send_message(
                            user_id,
                            f"🔔 Алерт сработал!\n"
                            f"Актив: {symbol} ({asset_type})\n"
                            f"Текущая цена: ${current_price:.2f}\n"
                            f"Целевая цена: ${target_price:.2f} ({'выше' if condition == 'above' else 'ниже'})"
                        )
                        await remove_alert(alert_id, user_id)
                        logger.info(f"Алерт сработал для пользователя {user_id}: {symbol} - {condition} ${target_price:.2f}")
                    except Exception as e:
                        logger.error(f"Ошибка при отправке уведомления пользователю {user_id}: {e}")

        except Exception as e:
            logger.error(f"Ошибка при проверке алертов: {e}")

        # Пауза перед следующей проверкой (например, 60 секунд)
        await asyncio.sleep(60)