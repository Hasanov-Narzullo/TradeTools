from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from config import settings
from loguru import logger
from database import init_db

# Инициализация бота и диспетчера
bot = Bot(token=settings.bot.TOKEN)
storage = MemoryStorage()  # Хранилище состояний (можно заменить на Redis для продакшн)
dp = Dispatcher(bot=bot, storage=storage)

# Логирование
logger.add("logs/bot.log", rotation="10 MB", level="INFO")

# Импорт хэндлеров (будет добавлен позже)
from handlers import register_handlers

def setup_bot():
    """Настройка бота и регистрация хэндлеров."""
    logger.info("Инициализация бота...")
    from handlers import router  # Импортируем роутер
    dp.include_router(router)   # Регистрируем роутер
    logger.info("Хэндлеры зарегистрированы.")

async def on_startup():
    """Действия при запуске бота."""
    await init_db()  # Инициализация базы данных
    logger.info("Бот запущен.")

async def on_shutdown():
    """Действия при остановке бота."""
    logger.info("Бот остановлен.")
    await bot.session.close()  # Закрытие сессии бота
    await storage.close()      # Закрытие хранилища