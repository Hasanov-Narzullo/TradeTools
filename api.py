import random

import aiosqlite
import yfinance as yf
import ccxt
import asyncio
from asyncio import sleep
from typing import Optional
from config import settings
import ccxt.async_support as ccxt
import aiohttp
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from yfinance import Ticker
from loguru import logger
from aiocache import cached

from database import add_event

_stock_price_cache: dict = {}
_crypto_price_cache: dict = {}
STOCK_CACHE_TIMEOUT = 600  # 10 минут
CRYPTO_CACHE_TIMEOUT = 120  # 2 минуты

def clean_cache():
    """Очистка устаревших записей из кэша."""
    current_time = datetime.now()
    for symbol in list(_stock_price_cache.keys()):
        price, timestamp = _stock_price_cache[symbol]
        if (current_time - timestamp).total_seconds() > STOCK_CACHE_TIMEOUT:
            del _stock_price_cache[symbol]
    for symbol in list(_crypto_price_cache.keys()):
        price, timestamp = _crypto_price_cache[symbol]
        if (current_time - timestamp).total_seconds() > CRYPTO_CACHE_TIMEOUT:
            del _crypto_price_cache[symbol]

async def get_stock_price_alpha_vantage(symbol: str) -> Optional[float]:
    """Получение цены акции через Alpha Vantage."""
    try:
        url = f"https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol={symbol}&apikey={settings.ALPHA_VANTAGE_API_KEY}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                data = await response.json()
                logger.debug(f"Ответ Alpha Vantage для {symbol}: {data}")
                if "Global Quote" in data and "05. price" in data["Global Quote"]:
                    price = float(data["Global Quote"]["05. price"])
                    _stock_price_cache[symbol] = (price, datetime.now())
                    return price
                else:
                    logger.error(f"Цена для {symbol} не найдена в ответе Alpha Vantage: {data}")
                    return None
    except Exception as e:
        logger.error(f"Ошибка при получении цены для {symbol} через Alpha Vantage: {e}")
        return None

async def get_stock_price_finnhub(symbol: str) -> Optional[float]:
    """Получение цены акции через Finnhub."""
    try:
        url = f"https://finnhub.io/api/v1/quote?symbol={symbol}&token={settings.FINNHUB_API_KEY}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                data = await response.json()
                logger.debug(f"Ответ Finnhub для {symbol}: {data}")
                if "c" in data and data["c"] > 0:
                    price = float(data["c"])
                    _stock_price_cache[symbol] = (price, datetime.now())
                    return price
                else:
                    logger.error(f"Цена для {symbol} не найдена в ответе Finnhub: {data}")
                    return None
    except Exception as e:
        logger.error(f"Ошибка при получении цены для {symbol} через Finnhub: {e}")
        return None

async def get_stock_price_yfinance(symbol: str) -> Optional[float]:
    """Получение цены акции через yfinance."""
    try:
        ticker = yf.Ticker(symbol + ".ME" if symbol in ["SBER", "GAZP", "LKOH"] else symbol)
        data = ticker.history(period="1d")
        if not data.empty:
            price = data['Close'].iloc[-1]
            _stock_price_cache[symbol] = (price, datetime.now())
            logger.info(f"Цена для {symbol} получена через yfinance: {price}")
            return price
        else:
            logger.error(f"Цена для {symbol} не найдена через yfinance")
            return None
    except Exception as e:
        logger.error(f"Ошибка при получении цены для {symbol} через yfinance: {e}")
        return None

async def get_stock_price(symbol: str) -> Optional[float]:
    """Получение цены акции с переключением между API."""
    if symbol in _stock_price_cache:
        price, timestamp = _stock_price_cache[symbol]
        if (datetime.now() - timestamp).total_seconds() < STOCK_CACHE_TIMEOUT:
            logger.info(f"Использована кэшированная цена для акции {symbol}: {price}")
            return price

    apis = [
        (get_stock_price_alpha_vantage, "Alpha Vantage"),
        (get_stock_price_yfinance, "yfinance"),  # Исправлено: ссылка на функцию
        (get_stock_price_finnhub, "Finnhub")
    ]
    random.shuffle(apis)

    for api_func, api_name in apis:
        try:
            price = await api_func(symbol)  # Передаем symbol при вызове
            if price is not None:
                logger.info(f"Цена для {symbol} получена через {api_name}: {price}")
                return price
            logger.warning(f"Цена для {symbol} не найдена через {api_name}, переходим к следующему API")
        except Exception as e:
            logger.error(f"Ошибка при вызове {api_name} для {symbol}: {e}")
            continue

    logger.error(f"Не удалось получить цену для {symbol} через все доступные API")
    return None

async def get_crypto_price(symbol: str) -> Optional[float]:
    """Получение цены криптовалюты через ccxt."""
    if symbol in _crypto_price_cache:
        price, timestamp = _crypto_price_cache[symbol]
        if (datetime.now() - timestamp).total_seconds() < CRYPTO_CACHE_TIMEOUT:
            logger.info(f"Использована кэшированная цена для криптовалюты {symbol}: {price}")
            return price

    try:
        exchange = ccxt.binance()
        ticker = await exchange.fetch_ticker(symbol)
        price = ticker['last']
        _crypto_price_cache[symbol] = (price, datetime.now())
        logger.info(f"Цена криптовалюты {symbol}: {price}")
        return price
    except Exception as e:
        logger.error(f"Ошибка при получении цены для {symbol} через ccxt: {e}")
        return None
    finally:
        await exchange.close()

async def get_stock_history(symbol: str, days: int = 30):
    try:
        stock = yf.Ticker(symbol)
        history = stock.history(period=f"{days}d")
        logger.info(f"Получены исторические данные для акции {symbol}")
        return history
    except Exception as e:
        logger.error(f"Ошибка при получении истории акции {symbol}: {e}")
        return None

async def get_crypto_history(symbol: str, exchange: str = "binance", days: int = 30):
    try:
        exchange_class = getattr(ccxt, exchange)()
        since = int((datetime.now() - timedelta(days=days)).timestamp() * 1000)
        ohlcv = exchange_class.fetch_ohlcv(symbol, timeframe="1d", since=since)
        logger.info(f"Получены исторические данные для криптовалюты {symbol}")
        return ohlcv
    except Exception as e:
        logger.error(f"Ошибка при получении истории криптовалюты {symbol}: {e}")
        return None

async def get_stock_price_with_retry(symbol: str, retries: int = 3, delay: int = 60) -> Optional[float]:
    for attempt in range(retries):
        price = await get_stock_price(symbol)
        if price is not None:
            return price
        if attempt < retries - 1:
            logger.warning(f"Попытка {attempt + 1}/{retries} не удалась, ждем {delay} секунд")
            await sleep(delay)
    return None

async def fetch_asset_price(symbol: str, asset_type: str) -> Optional[float]:
    if asset_type == "stock":
        price = await get_stock_price(symbol)
        if price is None:
            logger.error(f"Не удалось получить цену для {symbol} через все API")
            # Здесь можно отправить уведомление пользователю, если требуется
        return price
    elif asset_type == "crypto":
        return await get_crypto_price(symbol)
    return None

async def fetch_asset_price_with_retry(symbol: str, asset_type: str, retries: int = 3, delay: int = 5) -> Optional[float]:
    for attempt in range(retries):
        price = await fetch_asset_price(symbol, asset_type)
        if price is not None:
            return price
        logger.warning(f"Попытка {attempt + 1} не удалась для {symbol} ({asset_type}). Повтор через {delay} секунд.")
        await asyncio.sleep(delay)
    return None

@cached(ttl=3600)
async def get_exchange_rate(from_currency: str = "USD", to_currency: str = "RUB") -> float:
    """Получение курса обмена валют через exchangerate-api."""
    try:
        url = f"https://api.exchangerate-api.com/v4/latest/{from_currency}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                data = await response.json()
                logger.debug(f"Ответ exchangerate-api для {from_currency}/{to_currency}: {data}")
                if "rates" in data and to_currency in data["rates"]:
                    rate = float(data["rates"][to_currency])
                    logger.info(f"Курс {from_currency}/{to_currency}: {rate}")
                    return rate
                else:
                    logger.error(f"Курс для {from_currency}/{to_currency} не найден в ответе exchangerate-api: {data}")
                    return 90.0  # Фиксированный курс в случае ошибки
    except Exception as e:
        logger.error(f"Ошибка при получении курса для {from_currency}/{to_currency}: {e}")
        return 90.0  # Фиксированный курс в случае ошибки

MARKET_ASSETS = {
    "indices": {
        "S&P 500": "^GSPC",
        "Dow Jones": "^DJI",
        "NASDAQ": "^IXIC",
        "FTSE 100": "^FTSE",
        "DAX": "^GDA",
        "CAC 40": "^FCHI",
        "Nikkei 225": "^N225",
        "Hang Seng": "^HSI",
        "Shanghai Composite": "000001.SS",
        "RTS": "^RTS"
    },
    "commodities": {
        "Gold": "GC=F",
        "Oil (Brent)": "BZ=F",
        "Natural Gas": "NG=F"
    },
    "crypto": {
        "Bitcoin": "BTC/USDT"
    }
}

@cached(ttl=300)  # Кэшируем данные на 5 минут
async def get_market_data() -> dict:
    """Получение данных о рынке (индексы, золото, нефть, газ, биткоин)."""
    market_data = {
        "indices": {},
        "commodities": {},
        "crypto": {}
    }

    # Получение данных для индексов и сырьевых товаров через yfinance
    for category, assets in [("indices", MARKET_ASSETS["indices"]), ("commodities", MARKET_ASSETS["commodities"])]:
        for name, symbol in assets.items():
            try:
                ticker = yf.Ticker(symbol)
                history = ticker.history(period="2d")
                if len(history) >= 2:
                    current_price = history['Close'].iloc[-1]
                    previous_price = history['Close'].iloc[-2]
                    change_percent = ((current_price - previous_price) / previous_price) * 100
                    market_data[category][name] = {
                        "price": current_price,
                        "change_percent": change_percent
                    }
                else:
                    logger.warning(f"Недостаточно данных для {name} ({symbol})")
                    market_data[category][name] = {"price": None, "change_percent": None}
            except Exception as e:
                logger.error(f"Ошибка при получении данных для {name} ({symbol}): {e}")
                market_data[category][name] = {"price": None, "change_percent": None}

    # Получение данных для криптовалют через ccxt
    for name, symbol in MARKET_ASSETS["crypto"].items():
        try:
            exchange = ccxt.binance()
            ticker = await exchange.fetch_ticker(symbol)
            current_price = ticker['last']
            previous_price = ticker['open']  # Примерно за 24 часа
            change_percent = ((current_price - previous_price) / previous_price) * 100
            market_data["crypto"][name] = {
                "price": current_price,
                "change_percent": change_percent
            }
        except Exception as e:
            logger.error(f"Ошибка при получении данных для {name} ({symbol}): {e}")
            market_data["crypto"][name] = {"price": None, "change_percent": None}
        finally:
            await exchange.close()

    return market_data

EVENT_TYPES = {
    "macro": "Общеэкономические",
    "dividends": "Дивиденды",
    "earnings": "Отчетности",
    "press": "Пресс-конференции"
}

@cached(ttl=3600)
async def fetch_economic_calendar() -> list:
    """Парсинг экономического календаря с Trading Economics."""
    url = "https://tradingeconomics.com/calendar"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    events = []

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                if response.status != 200:
                    logger.error(f"Ошибка при запросе к Trading Economics: {response.status}")
                    return events

                soup = BeautifulSoup(await response.text(), "html.parser")
                table = soup.find("table", {"id": "calendar"})
                if not table:
                    logger.error("Таблица событий не найдена на Trading Economics")
                    return events

                rows = table.find("tbody").find_all("tr")
                if not rows:
                    logger.warning("События не найдены на Trading Economics")
                    return events

                for row in rows:
                    try:
                        cells = row.find_all("td")
                        if len(cells) < 4:
                            logger.debug("Недостаточно данных в строке, пропускаем")
                            continue

                        # Парсинг времени и даты
                        event_time = cells[0].text.strip()
                        event_date = datetime.now().strftime("%Y-%m-%d")  # Улучшить парсинг даты
                        try:
                            # Попытка парсинга даты из заголовка таблицы (если доступно)
                            date_header = row.find_previous("tr", class_="calendar-date")
                            if date_header:
                                date_text = date_header.text.strip()
                                event_date = datetime.strptime(date_text, "%Y-%m-%d").strftime("%Y-%m-%d")
                        except Exception as e:
                            logger.debug(f"Ошибка при парсинге даты: {e}, используется текущая дата")

                        event_title = cells[2].text.strip()
                        event_impact = cells[3].text.strip() or "Low Impact"

                        events.append({
                            "event_date": f"{event_date} {event_time}",
                            "title": event_title,
                            "description": f"Влияние: {event_impact}",
                            "source": "Trading Economics",
                            "type": "macro",
                            "symbol": None
                        })
                        logger.debug(f"Добавлено событие: {event_title}")
                    except Exception as e:
                        logger.error(f"Ошибка при парсинге события: {e}")
                        continue
    except Exception as e:
        logger.error(f"Ошибка при парсинге Trading Economics: {e}")

    logger.info(f"Получено {len(events)} общеэкономических событий с Trading Economics")
    return events


@cached(ttl=3600)  # Кэшируем на 1 час
async def fetch_dividends_and_earnings(symbol: str) -> list:
    """Получение дивидендов и отчетностей для актива через yfinance."""
    events = []
    try:
        ticker = Ticker(symbol)
        dividends = ticker.dividends
        earnings_dates = ticker.earnings_dates

        # Дивиденды
        if dividends is not None and not dividends.empty:
            for date, amount in dividends.items():
                event_date = date.strftime("%Y-%m-%d %H:%M:%S")
                events.append({
                    "event_date": event_date,
                    "title": f"Дивиденды для {symbol}",
                    "description": f"Сумма: ${amount:.2f}",
                    "source": "Yahoo Finance",
                    "type": "dividends",
                    "symbol": symbol
                })
                logger.debug(f"Добавлено событие дивидендов для {symbol}")

        # Отчетности
        if earnings_dates is not None and not earnings_dates.empty:
            for date, _ in earnings_dates.iterrows():
                event_date = date.strftime("%Y-%m-%d %H:%M:%S")
                events.append({
                    "event_date": event_date,
                    "title": f"Отчетность для {symbol}",
                    "description": "Отчетность компании",
                    "source": "Yahoo Finance",
                    "type": "earnings",
                    "symbol": symbol
                })
                logger.debug(f"Добавлено событие отчетности для {symbol}")
    except Exception as e:
        logger.error(f"Ошибка при получении событий для {symbol}: {e}")

    logger.info(f"Получено {len(events)} событий для актива {symbol}")
    return events


async def fetch_test_events() -> list:
    """Добавление тестовых событий для проверки системы."""
    events = []
    current_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Тестовые общеэкономические события
    events.append({
        "event_date": current_date,
        "title": "Тестовое общеэкономическое событие",
        "description": "Влияние: Высокое",
        "source": "Test Source",
        "type": "macro",
        "symbol": None
    })

    # Тестовые события для активов
    events.append({
        "event_date": current_date,
        "title": "Тестовые дивиденды для AAPL",
        "description": "Сумма: $0.22",
        "source": "Test Source",
        "type": "dividends",
        "symbol": "AAPL"
    })
    events.append({
        "event_date": current_date,
        "title": "Тестовая отчетность для AAPL",
        "description": "Отчетность компании",
        "source": "Test Source",
        "type": "earnings",
        "symbol": "AAPL"
    })

    logger.info(f"Добавлено {len(events)} тестовых событий")
    return events
