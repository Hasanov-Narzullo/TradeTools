import random
import yfinance as yf
import ccxt
from asyncio import sleep
import aiohttp
import asyncio
from loguru import logger
from typing import Optional
from config import settings
import ccxt.async_support as ccxt
from datetime import datetime, timedelta


_stock_price_cache: dict = {}
_crypto_price_cache: dict = {}
STOCK_CACHE_TIMEOUT = 600  # 10 минут
CRYPTO_CACHE_TIMEOUT = 120  # 2 минуты

def clean_cache():
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

async def fetch_asset_price(symbol: str, asset_type: str) -> Optional[float]:
    if asset_type == "stock":
        return await get_stock_price(symbol)
    elif asset_type == "crypto":
        return await get_crypto_price(symbol)
    return None

async def get_stock_price(symbol: str) -> Optional[float]:
    """Получение цены акции с переключением между API."""
    # Проверка кэша
    if symbol in _stock_price_cache:
        price, timestamp = _stock_price_cache[symbol]
        if (datetime.now() - timestamp).total_seconds() < STOCK_CACHE_TIMEOUT:
            logger.info(f"Использована кэшированная цена для акции {symbol}: {price}")
            return price

    # Попытка получения цены из трех API
    apis = [
        (get_stock_price_alpha_vantage, "Alpha Vantage"),
        (get_stock_price_yfinance(), "Yfinance"),
        (get_stock_price_finnhub, "Finnhub")
    ]

    for api_func, api_name in apis:
        price = await api_func(symbol)
        if price is not None:
            logger.info(f"Цена для {symbol} получена через {api_name}: {price}")
            return price
        logger.warning(f"Цена для {symbol} не найдена через {api_name}, переходим к следующему API")

    logger.error(f"Не удалось получить цену для {symbol} через все доступные API")
    return None

async def get_crypto_price(symbol: str) -> Optional[float]:
    """Получение цены криптовалюты через ccxt (без изменений)."""
    # Проверка кэша
    if symbol in _crypto_price_cache:
        price, timestamp = _crypto_price_cache[symbol]
        if (datetime.now() - timestamp).total_seconds() < CRYPTO_CACHE_TIMEOUT :
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