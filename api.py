import random
import requests
import yfinance as yf
import ccxt
import asyncio
from asyncio import sleep
from typing import Optional
from aiocache.serializers import JsonSerializer
from config import settings
import ccxt.async_support as ccxt
import aiohttp
from datetime import datetime, timedelta
from yfinance import Ticker
from loguru import logger
from aiocache import cached, Cache
from eodhd import APIClient
import asyncio
import sys
import platform

# Устанавливаем SelectorEventLoop на Windows
if platform.system() == "Windows":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

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


ALPHA_VANTAGE_API_KEY = "ZDFVKRCE8UTMR2SP"

# Типы событий
EVENT_TYPES = {
    "macro": "Общеэкономические",
    "dividends": "Дивиденды",
    "earnings": "Отчетности",
    "press": "Пресс-конференции"
}

cache = Cache(Cache.MEMORY, serializer=JsonSerializer(), ttl=5 * 3600)  # 5 часов в секундах


@cached(ttl=5 * 3600, cache=Cache.MEMORY, serializer=JsonSerializer())
async def fetch_alpha_vantage_earnings() -> list:
    """Получение календаря отчетностей через Alpha Vantage API."""
    events = []
    url = f"https://www.alphavantage.co/query?function=EARNINGS_CALENDAR&horizon=3month&apikey={ALPHA_VANTAGE_API_KEY}"
    try:
        logger.info("Запрос календаря отчетностей через Alpha Vantage")
        response = requests.get(url)
        if response.status_code == 200:
            data = response.text.splitlines()
            if len(data) <= 1:
                logger.warning("Календарь отчетностей Alpha Vantage пуст")
                return events

            for line in data[1:]:  # Пропускаем заголовок
                try:
                    symbol, name, report_date, fiscal_date, estimate, currency = line.split(',')
                    event_date = datetime.strptime(report_date, "%Y-%m-%d").strftime("%Y-%m-%d %H:%M:%S")
                    events.append({
                        "event_date": event_date,
                        "title": f"Отчетность для {symbol}",
                        "description": f"Компания: {name}, Ожидаемый EPS: {estimate} {currency}, Фискальная дата: {fiscal_date}",
                        "source": "Alpha Vantage",
                        "type": "earnings",
                        "symbol": symbol
                    })
                    logger.debug(f"Добавлено событие отчетности для {symbol}")
                except Exception as e:
                    logger.error(f"Ошибка при обработке события отчетности: {e}")
                    continue
        else:
            logger.error(f"Ошибка при запросе к Alpha Vantage: {response.status_code}")
    except Exception as e:
        logger.error(f"Ошибка при получении данных Alpha Vantage: {e}")
    logger.info(f"Получено {len(events)} событий отчетностей с Alpha Vantage")
    return events


@cached(ttl=5 * 3600, cache=Cache.MEMORY, serializer=JsonSerializer())
async def fetch_alpha_vantage_macro() -> list:
    """Получение макроэкономических событий через Alpha Vantage API (например, ВВП, CPI)."""
    events = []
    # Пример макроэкономического индикатора (ВВП)
    indicators = [
        {"function": "REAL_GDP", "interval": "annual", "name": "ВВП (реальный)"},
        {"function": "CPI", "interval": "monthly", "name": "Индекс потребительских цен (CPI)"}
    ]

    for indicator in indicators:
        url = f"https://www.alphavantage.co/query?function={indicator['function']}&interval={indicator['interval']}&apikey={ALPHA_VANTAGE_API_KEY}"
        try:
            logger.info(f"Запрос макроэкономического индикатора {indicator['name']} через Alpha Vantage")
            response = requests.get(url)
            if response.status_code == 200:
                data = response.json()
                if "data" in data:
                    for item in data["data"]:
                        try:
                            event_date = datetime.strptime(item["date"], "%Y-%m-%d").strftime("%Y-%m-%d %H:%M:%S")
                            events.append({
                                "event_date": event_date,
                                "title": f"{indicator['name']}",
                                "description": f"Значение: {item['value']}",
                                "source": "Alpha Vantage",
                                "type": "macro",
                                "symbol": None
                            })
                            logger.debug(f"Добавлено макроэкономическое событие: {indicator['name']}")
                        except Exception as e:
                            logger.error(f"Ошибка при обработке макроэкономического события: {e}")
                            continue
                else:
                    logger.warning(f"Макроэкономический индикатор {indicator['name']} пуст")
            else:
                logger.error(f"Ошибка при запросе к Alpha Vantage: {response.status_code}")
        except Exception as e:
            logger.error(f"Ошибка при получении данных Alpha Vantage: {e}")
    logger.info(f"Получено {len(events)} макроэкономических событий с Alpha Vantage")
    return events


@cached(ttl=5 * 3600, cache=Cache.MEMORY, serializer=JsonSerializer())
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


EODHD_EVENTS_CACHE_TIMEOUT = 5 * 1800
EODHD_API_KEY  = '67c06446457f30.71105398'
eodhd_client = APIClient(settings.api.EODHD_API_KEY)


@cached(ttl=EODHD_EVENTS_CACHE_TIMEOUT, cache=Cache.MEMORY, serializer=JsonSerializer())
async def fetch_eodhd_economic_calendar(from_date: str = None, to_date: str = None) -> list:
    """
    Получение экономического календаря через EODHD API используя HTTP-запросы.
    """
    events = []
    try:
        if not from_date:
            from_date = datetime.now().strftime("%Y-%m-%d")
        if not to_date:
            to_date = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")

        url = f"https://eodhistoricaldata.com/api/economic-events?api_token={settings.api.EODHD_API_KEY}&from={from_date}&to={to_date}"
        logger.info(f"Запрос экономического календаря через EODHD с {from_date} по {to_date}")

        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    if not data:
                        logger.warning("Экономический календарь EODHD пуст")
                        return events

                    for event in data:
                        try:
                            # Определяем тип события
                            event_type = "macro"  # По умолчанию макро
                            event_title = event.get("event", "Economic Event").lower()
                            if "earnings" in event_title:
                                event_type = "earnings"
                            elif "dividend" in event_title:
                                event_type = "dividends"
                            elif "meeting" in event_title or "conference" in event_title:
                                event_type = "press"

                            # Проверяем наличие даты и преобразуем
                            if not event.get("date"):
                                logger.warning(f"Пропущено событие без даты: {event}")
                                continue
                            event_date = datetime.strptime(event["date"], "%Y-%m-%dT%H:%M:%S").strftime(
                                "%Y-%m-%d %H:%M:%S")

                            description = []
                            if event.get("actual"):
                                description.append(f"Факт: {event['actual']}")
                            if event.get("forecast"):
                                description.append(f"Прогноз: {event['forecast']}")
                            if event.get("previous"):
                                description.append(f"Пред: {event['previous']}")
                            description_text = ", ".join(description) if description else "Нет данных"

                            events.append({
                                "event_date": event_date,
                                "title": event.get("event", "Economic Event"),
                                "description": description_text,
                                "source": "EODHD",
                                "type": event_type,
                                "symbol": event.get("code")  # Используем code как символ
                            })
                            logger.debug(f"Добавлено событие EODHD: {event.get('event')}")
                        except Exception as e:
                            logger.error(f"Ошибка при обработке события EODHD: {e}")
                            continue
                elif response.status == 429:
                    logger.error("Превышен лимит запросов EODHD API")
                    return events
                elif response.status == 401:
                    logger.error("Неверный API ключ EODHD")
                    return events
                else:
                    logger.error(f"Ошибка при запросе к EODHD: {response.status}")
                    return events

        logger.info(f"Получено {len(events)} событий с EODHD")
    except Exception as e:
        logger.error(f"Ошибка при получении данных EODHD: {e}")
    return events


@cached(ttl=EODHD_EVENTS_CACHE_TIMEOUT, cache=Cache.MEMORY, serializer=JsonSerializer())
async def fetch_eodhd_earnings_calendar(symbol: str = None, from_date: str = None, to_date: str = None) -> list:
    """
    Получение календаря отчетностей через EODHD API используя HTTP-запросы.
    """
    events = []
    try:
        if not from_date:
            from_date = datetime.now().strftime("%Y-%m-%d")
        if not to_date:
            to_date = (datetime.now() + timedelta(days=90)).strftime("%Y-%m-%d")

        url = f"https://eodhistoricaldata.com/api/earnings?api_token={settings.api.EODHD_API_KEY}&from={from_date}&to={to_date}"
        if symbol:
            url += f"&symbol={symbol}"

        logger.info(f"Запрос календаря отчетностей через EODHD для {symbol if symbol else 'всех активов'}")

        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    earnings_data = data.get("earnings", [])
                    if not earnings_data:
                        logger.warning("Календарь отчетностей EODHD пуст")
                        return events

                    for earning in earnings_data:
                        try:
                            if not earning.get("date"):
                                logger.warning(f"Пропущено событие отчетности без даты: {earning}")
                                continue
                            event_date = datetime.strptime(earning["date"], "%Y-%m-%d").strftime("%Y-%m-%d %H:%M:%S")
                            description = []
                            if earning.get("eps_actual"):
                                description.append(f"EPS факт: {earning['eps_actual']}")
                            if earning.get("eps_estimate"):
                                description.append(f"EPS прогноз: {earning['eps_estimate']}")
                            description_text = ", ".join(description) if description else "Нет данных"

                            events.append({
                                "event_date": event_date,
                                "title": f"Отчетность для {earning.get('code', symbol)}",
                                "description": description_text,
                                "source": "EODHD",
                                "type": "earnings",
                                "symbol": earning.get("code", symbol)
                            })
                            logger.debug(f"Добавлено событие отчетности EODHD для {earning.get('code', symbol)}")
                        except Exception as e:
                            logger.error(f"Ошибка при обработке события отчетности EODHD: {e}")
                            continue
                elif response.status == 429:
                    logger.error("Превышен лимит запросов EODHD API")
                    return events
                elif response.status == 401:
                    logger.error("Неверный API ключ EODHD")
                    return events
                else:
                    logger.error(f"Ошибка при запросе к EODHD: {response.status}")
                    return events

        logger.info(f"Получено {len(events)} событий отчетностей с EODHD")
    except Exception as e:
        logger.error(f"Ошибка при получении данных отчетностей EODHD: {e}")
    return events


@cached(ttl=EODHD_EVENTS_CACHE_TIMEOUT, cache=Cache.MEMORY, serializer=JsonSerializer())
async def fetch_economic_calendar() -> list:
    """
    Обновленная функция получения экономического календаря, включающая EODHD.
    """
    events = []
    try:
        # Получаем события из Alpha Vantage (существующий код)
        earnings_events = await fetch_alpha_vantage_earnings()
        events.extend(earnings_events)
        macro_events = await fetch_alpha_vantage_macro()
        events.extend(macro_events)

        # Получаем события из EODHD
        eodhd_events = await fetch_eodhd_economic_calendar()
        events.extend(eodhd_events)

        logger.info(f"Всего получено {len(events)} событий")
        return events
    except Exception as e:
        logger.error(f"Ошибка при получении экономического календаря: {e}")
        return events


@cached(ttl=EODHD_EVENTS_CACHE_TIMEOUT, cache=Cache.MEMORY, serializer=JsonSerializer())
async def fetch_dividends_and_earnings(symbol: str) -> list:
    """
    Обновленная функция получения дивидендов и отчетностей, включающая EODHD.
    """
    events = []
    try:
        # Получаем дивиденды через yfinance
        try:
            ticker = Ticker(symbol)
            dividends = ticker.dividends
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
                    logger.debug(f"Добавлено событие дивидендов для {symbol} через yfinance")
        except Exception as e:
            logger.error(f"Ошибка при получении дивидендов через yfinance для {symbol}: {e}")

        # Получаем дивиденды через EODHD
        try:
            from_date = datetime.now().strftime("%Y-%m-%d")
            to_date = (datetime.now() + timedelta(days=90)).strftime("%Y-%m-%d")

            url = f"https://eodhistoricaldata.com/api/dividends/{symbol}?api_token={settings.api.EODHD_API_KEY}&from={from_date}&to={to_date}"
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        dividends_data = data.get("dividends", [])
                        if dividends_data:
                            for dividend in dividends_data:
                                try:
                                    if not dividend.get("date"):
                                        logger.warning(f"Пропущено событие дивидендов без даты: {dividend}")
                                        continue
                                    event_date = datetime.strptime(dividend["date"], "%Y-%m-%d").strftime(
                                        "%Y-%m-%d %H:%M:%S")
                                    amount = dividend.get("value", "N/A")
                                    events.append({
                                        "event_date": event_date,
                                        "title": f"Дивиденды для {symbol}",
                                        "description": f"Сумма: ${amount}",
                                        "source": "EODHD",
                                        "type": "dividends",
                                        "symbol": symbol
                                    })
                                    logger.debug(f"Добавлено событие дивидендов для {symbol} через EODHD")
                                except Exception as e:
                                    logger.error(f"Ошибка при обработке события дивидендов EODHD: {e}")
                                    continue
                    elif response.status == 429:
                        logger.error("Превышен лимит запросов EODHD API для дивидендов")
                    elif response.status == 401:
                        logger.error("Неверный API ключ EODHD для дивидендов")
                    else:
                        logger.error(f"Ошибка при запросе дивидендов к EODHD: {response.status}")
        except Exception as e:
            logger.error(f"Ошибка при получении дивидендов через EODHD для {symbol}: {e}")

        # Получаем отчетности через EODHD
        try:
            eodhd_earnings = await fetch_eodhd_earnings_calendar(symbol=symbol)
            events.extend(eodhd_earnings)
        except Exception as e:
            logger.error(f"Ошибка при получении отчетностей через EODHD для {symbol}: {e}")

        logger.info(f"Получено {len(events)} событий (дивиденды и отчетности) для актива {symbol}")
        return events
    except Exception as e:
        logger.error(f"Общая ошибка при получении данных для {symbol}: {e}")
        return events

test_events = asyncio.run(fetch_eodhd_economic_calendar())
print(test_events)