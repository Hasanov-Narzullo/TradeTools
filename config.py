# config
import os
from pathlib import Path

class BotConfig:
    TOKEN = "7578698416:AAGnMWW743OkRduMYz5x2CytMO2j4NJrM1g"

class DatabaseConfig:
    DB_PATH = Path("database/bot_database.db")

class APIConfig:
    CRYPTO_API_KEY = os.getenv("CRYPTO_API_KEY", "")
    STOCK_API_KEY = os.getenv("STOCK_API_KEY", "")
    ALPHA_VANTAGE_KEY = "ZDFVKRCE8UTMR2SP"
    FINNHUB_API_KEY = "cutg85hr01qrsirmlv1gcutg85hr01qrsirmlv20"
    CRYPTO_API_URL = "https://api.example.com/crypto"
    STOCK_API_URL = "https://api.example.com/stocks"
    EODHD_API_KEY = '67c06446457f30.71105398'

class SchedulerConfig:
    TIMEZONE = "UTC"  # Часовой пояс для задач

class Settings:
    bot = BotConfig()
    db = DatabaseConfig()
    api = APIConfig()
    scheduler = SchedulerConfig()

class DatabaseConfig:
    BASE_DIR = Path(__file__).resolve().parent.parent  # Корневая директория проекта
    DB_PATH = BASE_DIR / "database" / "bot_database.db"

    @classmethod
    def ensure_db_directory(cls):
        """Создание директории для базы данных, если она не существует."""
        os.makedirs(cls.DB_PATH.parent, exist_ok=True)

settings = Settings()
DatabaseConfig.ensure_db_directory()