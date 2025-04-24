# main
import asyncio
import sys
from aiogram import Bot, Dispatcher
from bot import bot, dp, setup_bot, on_startup, on_shutdown
from loguru import logger
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from config import settings
from scheduler import setup_scheduler
from alert_checker import check_alerts
import platform


# Установка SelectorEventLoop на Windows
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Основная функция для запуска бота.
async def main():
    setup_bot()

    scheduler = AsyncIOScheduler(timezone=settings.scheduler.TIMEZONE)
    setup_scheduler(scheduler)
    scheduler.start()

    try:
        await on_startup()
        
        asyncio.create_task(check_alerts(bot))
        logger.info("Фоновая задача проверки алертов запущена.")

        logger.info("Запуск polling...")
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Ошибка во время работы бота: {e}")
    finally:
        logger.info("Остановка бота...")
        await on_shutdown()
        scheduler.shutdown()
        logger.info("Планировщик остановлен.")

if __name__ == "__main__":
    logger.info("Запуск бота...")
    asyncio.run(main())