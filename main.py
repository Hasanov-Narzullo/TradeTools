import asyncio
import sys
from aiogram import Bot, Dispatcher
from bot import bot, dp, setup_bot, on_startup, on_shutdown
from loguru import logger
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from config import settings
from scheduler import setup_scheduler
from alert_checker import check_alerts



# Установка SelectorEventLoop на Windows
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

async def main():
    """Основная функция для запуска бота."""
    # Настройка бота
    setup_bot()

    # Инициализация планировщика
    scheduler = AsyncIOScheduler(timezone=settings.scheduler.TIMEZONE)
    setup_scheduler(scheduler)
    scheduler.start()

    # Запуск бота
    try:
        await on_startup()
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Ошибка при запуске бота: {e}")
    finally:
        await on_shutdown()

    asyncio.create_task(check_alerts(bot))
    logger.info("Фоновая задача проверки алертов запущена.")

    try:
        # Запускаем основной цикл обработки обновлений
        logger.info("Бот запущен.")
        await dp.start_polling(bot)
    finally:
        # Закрываем сессию бота при завершении
        await bot.session.close()
        logger.info("Бот остановлен.")

if __name__ == "__main__":
    logger.info("Запуск бота...")
    asyncio.run(main())