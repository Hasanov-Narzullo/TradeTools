# api
import random
import requests
import yfinance as yf
from yfinance import Ticker
import ccxt
import ccxt.async_support as ccxt
import asyncio
from asyncio import sleep
from typing import Optional
import aiohttp
from aiocache import cached, Cache
from aiocache.serializers import JsonSerializer
from config import settings
from datetime import datetime, timedelta
from loguru import logger
from eodhd import APIClient
import sys
import platform

# Устанавливаем SelectorEventLoop на Windows
if platform.system() == "Windows":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

_stock_price_cache: dict = {}
_crypto_price_cache: dict = {}
STOCK_CACHE_TIMEOUT = 600  # 10 минут
CRYPTO_CACHE_TIMEOUT = 120  # 2 минуты

# Очистка устаревших записей из кэша.
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

# Получение цены акции через Alpha Vantage.
@cached(ttl=600, cache=Cache.MEMORY, serializer=JsonSerializer())
async def get_stock_price_alpha_vantage(symbol: str) -> Optional[float]:
    try:
        url = f"https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol={symbol}&apikey={settings.ALPHA_VANTAGE_API_KEY}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                data = await response.json()
                logger.debug(f"Alpha Vantage for {symbol}: {data}")
                if "Global Quote" in data and "05. price" in data["Global Quote"]:
                    return float(data["Global Quote"]["05. price"])
                logger.error(f"Price not found in Alpha Vantage response for {symbol}: {data}")
                return None
    except Exception as e:
        logger.error(f"Error getting price for {symbol} via Alpha Vantage: {e}")
        return None

# Получение цены акции через Finnhub.
@cached(ttl=600, cache=Cache.MEMORY, serializer=JsonSerializer())
async def get_stock_price_finnhub(symbol: str) -> Optional[float]:
    try:
        url = f"https://finnhub.io/api/v1/quote?symbol={symbol}&token={settings.FINNHUB_API_KEY}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                data = await response.json()
                logger.debug(f"Finnhub for {symbol}: {data}")
                if "c" in data and data["c"] > 0:
                    return float(data["c"])
                logger.error(f"Price not found in Finnhub response for {symbol}: {data}")
                return None
    except Exception as e:
        logger.error(f"Error getting price for {symbol} via Finnhub: {e}")
        return None

# Получение цены акции через yfinance.
@cached(ttl=600, cache=Cache.MEMORY, serializer=JsonSerializer())
async def get_stock_price_yfinance(symbol: str) -> Optional[float]:
    try:
        ticker = yf.Ticker(symbol + ".ME" if symbol in ["SBER", "GAZP", "LKOH"] else symbol)
        data = ticker.history(period="1d")
        if not data.empty:
            price = data['Close'].iloc[-1]
            logger.info(f"yfinance price for {symbol}: {price}")
            return price
        logger.error(f"Price not found via yfinance for {symbol}")
        return None
    except Exception as e:
        logger.error(f"Error getting price for {symbol} via yfinance: {e}")
        return None

# Получение цены акции с переключением между API.
async def get_stock_price(symbol: str) -> Optional[float]:
    apis = [
        (get_stock_price_alpha_vantage, "Alpha Vantage"),
        (get_stock_price_yfinance, "yfinance"),
        (get_stock_price_finnhub, "Finnhub")
    ]
    random.shuffle(apis)
    for api_func, api_name in apis:
        try:
            price = await api_func(symbol)
            if price is not None:
                logger.info(f"Price for {symbol} via {api_name}: {price}")
                return price
            logger.warning(f"Price for {symbol} not found via {api_name}, trying next.")
        except Exception as e:
            logger.error(f"Error calling {api_name} for {symbol}: {e}")
    logger.error(f"Failed to get price for {symbol} from all stock APIs.")
    return None

# Получение цены криптовалюты через ccxt.
@cached(ttl=120, cache=Cache.MEMORY, serializer=JsonSerializer())
async def get_crypto_price(symbol: str) -> Optional[float]:
    exchange = None
    try:
        exchange = ccxt.binance()
        ticker = await exchange.fetch_ticker(symbol)
        price = ticker['last']
        logger.info(f"Crypto price for {symbol}: {price}")
        return price
    except Exception as e:
        logger.error(f"Error getting crypto price for {symbol} via ccxt: {e}")
        return None
    finally:
        if exchange:
            await exchange.close()

# Получение истории стоимости акций
async def get_stock_history(symbol: str, days: int = 30):
    try:
        stock = yf.Ticker(symbol)
        history = stock.history(period=f"{days}d")
        logger.info(f"Получены исторические данные для акции {symbol}")
        return history
    except Exception as e:
        logger.error(f"Ошибка при получении истории акции {symbol}: {e}")
        return None

# Получение истории стоиомости криптовалют
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

# Повторный запрос стоимости акций в случае ошибка
async def get_stock_price_with_retry(symbol: str, retries: int = 3, delay: int = 60) -> Optional[float]:
    for attempt in range(retries):
        price = await get_stock_price(symbol)
        if price is not None:
            return price
        if attempt < retries - 1:
            logger.warning(f"Попытка {attempt + 1}/{retries} не удалась, ждем {delay} секунд")
            await sleep(delay)
    return None

# Ошибка получения данных через апи
async def fetch_asset_price(symbol: str, asset_type: str) -> Optional[float]:
    if asset_type == "stock":
        return await get_stock_price(symbol)
    elif asset_type == "crypto":
        return await get_crypto_price(symbol)
    logger.error(f"Unknown asset type '{asset_type}' for symbol {symbol}")
    return None

# Повторная попытка получения стоимости - ???
async def fetch_asset_price_with_retry(symbol: str, asset_type: str, retries: int = 3, delay: int = 5) -> Optional[float]:
    for attempt in range(retries):
        price = await fetch_asset_price(symbol, asset_type)
        if price is not None:
            return price
        logger.warning(f"Попытка {attempt + 1} не удалась для {symbol} ({asset_type}). Повтор через {delay} секунд.")
        await asyncio.sleep(delay)
    logger.error(f"Не удалось получить цену для {symbol} ({asset_type}) после {retries} попыток.")
    return None

# Получение курса обмена валют через exchangerate-api.
@cached(ttl=3600)
async def get_exchange_rate(from_currency: str = "USD", to_currency: str = "RUB") -> float:
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

# Получение данных о рынке (индексы, золото, нефть, газ, биткоин).
@cached(ttl=300)  # Кэшируем данные на 5 минут
async def get_market_data() -> dict:
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

# Получение календаря отчетностей через Alpha Vantage API.
@cached(ttl=18000, cache=Cache.MEMORY, serializer=JsonSerializer())
async def fetch_alpha_vantage_earnings() -> list:
    events = []
    url = f"https://www.alphavantage.co/query?function=EARNINGS_CALENDAR&horizon=3month&apikey={ALPHA_VANTAGE_API_KEY}"
    try:
        logger.info("Fetching Alpha Vantage earnings calendar")
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    content = await response.text()
                    data = content.splitlines()
                    if len(data) <= 1:
                        logger.warning("Alpha Vantage earnings calendar is empty")
                        return events
                    for line in data[1:]:
                        try:
                            symbol, name, report_date, fiscal_date, estimate, currency = line.split(',')
                            event_date = datetime.strptime(report_date, "%Y-%m-%d").strftime("%Y-%m-%d %H:%M:%S")
                            events.append({
                                "event_date": event_date, "title": f"Отчетность для {symbol}",
                                "description": f"Компания: {name}, Ожидаемый EPS: {estimate} {currency}, Фискальная дата: {fiscal_date}",
                                "source": "Alpha Vantage", "type": "earnings", "symbol": symbol
                            })
                        except Exception as e:
                            logger.error(f"Error processing Alpha Vantage earning event line '{line}': {e}")
                else:
                    logger.error(f"Error fetching Alpha Vantage earnings: {response.status}")
    except Exception as e:
        logger.error(f"Error fetching Alpha Vantage earnings data: {e}")
    logger.info(f"Fetched {len(events)} Alpha Vantage earnings events")
    return events

# Получение макроэкономических событий через Alpha Vantage API (например, ВВП, CPI).
@cached(ttl=18000, cache=Cache.MEMORY, serializer=JsonSerializer())
async def fetch_alpha_vantage_macro() -> list:
    events = []
    indicators = [
        {"function": "REAL_GDP", "interval": "annual", "name": "ВВП (реальный)"},
        {"function": "CPI", "interval": "monthly", "name": "Индекс потребительских цен (CPI)"}
    ]
    for indicator in indicators:
        url = f"https://www.alphavantage.co/query?function={indicator['function']}&interval={indicator['interval']}&apikey={ALPHA_VANTAGE_API_KEY}"
        try:
            logger.info(f"Fetching Alpha Vantage macro indicator {indicator['name']}")
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        if "data" in data:
                            for item in data["data"]:
                                try:
                                    event_date = datetime.strptime(item["date"], "%Y-%m-%d").strftime("%Y-%m-%d %H:%M:%S")
                                    events.append({
                                        "event_date": event_date, "title": indicator['name'],
                                        "description": f"Значение: {item['value']}",
                                        "source": "Alpha Vantage", "type": "macro", "symbol": None
                                    })
                                except Exception as e:
                                    logger.error(f"Error processing Alpha Vantage macro event item {item}: {e}")
                        else:
                            logger.warning(f"Alpha Vantage macro indicator {indicator['name']} is empty or missing 'data' key")
                    else:
                        logger.error(f"Error fetching Alpha Vantage macro {indicator['name']}: {response.status}")
        except Exception as e:
            logger.error(f"Error fetching Alpha Vantage macro data for {indicator['name']}: {e}")
    logger.info(f"Fetched {len(events)} Alpha Vantage macro events")
    return events

# Добавление тестовых событий для проверки системы.
@cached(ttl=5 * 3600, cache=Cache.MEMORY, serializer=JsonSerializer())
async def fetch_test_events() -> list:
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

#     Получение экономического календаря через EODHD API используя HTTP-запросы.
@cached(ttl=EODHD_EVENTS_CACHE_TIMEOUT, cache=Cache.MEMORY, serializer=JsonSerializer())
async def fetch_eodhd_economic_calendar(from_date: str = None, to_date: str = None) -> list:
    events = []
    from_date = from_date or datetime.now().strftime("%Y-%m-%d")
    to_date = to_date or (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
    url = f"https://eodhistoricaldata.com/api/economic-events?api_token={settings.api.EODHD_API_KEY}&from={from_date}&to={to_date}"
    logger.info(f"Fetching EODHD economic calendar from {from_date} to {to_date}")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    if not data:
                        logger.warning("EODHD economic calendar is empty")
                        return events
                    for event in data:
                        try:
                            event_type = "macro"
                            event_title = event.get("event", "Economic Event").lower()
                            if "earnings" in event_title: event_type = "earnings"
                            elif "dividend" in event_title: event_type = "dividends"
                            elif "meeting" in event_title or "conference" in event_title: event_type = "press"

                            if not event.get("date"):
                                logger.warning(f"Skipping EODHD event with no date: {event}")
                                continue
                            event_date = datetime.fromisoformat(event["date"].replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M:%S")

                            desc = []
                            if event.get("actual"): desc.append(f"Факт: {event['actual']}")
                            if event.get("forecast"): desc.append(f"Прогноз: {event['forecast']}")
                            if event.get("previous"): desc.append(f"Пред: {event['previous']}")
                            desc_text = ", ".join(desc) if desc else "Нет данных"

                            events.append({
                                "event_date": event_date, "title": event.get("event", "Economic Event"),
                                "description": desc_text, "source": "EODHD", "type": event_type,
                                "symbol": event.get("code")
                            })
                        except Exception as e:
                            logger.error(f"Error processing EODHD economic event {event}: {e}")
                elif response.status in [401, 429]:
                     logger.error(f"EODHD API error: {'Rate limit' if response.status == 429 else 'Invalid key'} ({response.status})")
                     return events
                else:
                    logger.error(f"Error fetching EODHD economic calendar: {response.status}")
                    return events
        logger.info(f"Fetched {len(events)} EODHD economic events")
    except Exception as e:
        logger.error(f"Error fetching EODHD economic data: {e}")
    return events

# Получение календаря отчетностей через EODHD API используя HTTP-запросы.
@cached(ttl=EODHD_EVENTS_CACHE_TIMEOUT, cache=Cache.MEMORY, serializer=JsonSerializer())
async def fetch_eodhd_earnings_calendar(symbol: str = None, from_date: str = None, to_date: str = None) -> list:
    events = []
    from_date = from_date or datetime.now().strftime("%Y-%m-%d")
    to_date = to_date or (datetime.now() + timedelta(days=90)).strftime("%Y-%m-%d")
    url = f"https://eodhistoricaldata.com/api/earnings?api_token={settings.api.EODHD_API_KEY}&from={from_date}&to={to_date}"
    if symbol: url += f"&symbols={symbol}"
    logger.info(f"Fetching EODHD earnings calendar for {symbol or 'all assets'}")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    earnings_data = data.get("earnings", [])
                    if not earnings_data:
                        logger.warning("EODHD earnings calendar is empty")
                        return events
                    for earning in earnings_data:
                        try:
                            if not earning.get("report_date"):
                                logger.warning(f"Skipping EODHD earning event with no report_date: {earning}")
                                continue
                            event_date = datetime.strptime(earning["report_date"], "%Y-%m-%d").strftime("%Y-%m-%d %H:%M:%S")
                            desc = []
                            if earning.get("epsActual"): desc.append(f"EPS факт: {earning['epsActual']}")
                            if earning.get("epsEstimate"): desc.append(f"EPS прогноз: {earning['epsEstimate']}")
                            desc_text = ", ".join(desc) if desc else "Нет данных"
                            event_symbol = earning.get("code", symbol)
                            events.append({
                                "event_date": event_date, "title": f"Отчетность для {event_symbol}",
                                "description": desc_text, "source": "EODHD", "type": "earnings",
                                "symbol": event_symbol
                            })
                        except Exception as e:
                            logger.error(f"Error processing EODHD earning event {earning}: {e}")
                elif response.status in [401, 429]:
                     logger.error(f"EODHD API error: {'Rate limit' if response.status == 429 else 'Invalid key'} ({response.status}) for earnings")
                     return events
                else:
                    logger.error(f"Error fetching EODHD earnings calendar: {response.status}")
                    return events
        logger.info(f"Fetched {len(events)} EODHD earnings events")
    except Exception as e:
        logger.error(f"Error fetching EODHD earnings data: {e}")
    return events

# Обновленная функция получения экономического календаря, включающая EODHD.
@cached(ttl=EODHD_EVENTS_CACHE_TIMEOUT, cache=Cache.MEMORY, serializer=JsonSerializer())
async def fetch_economic_calendar() -> list:
    events = []
    try:
        tasks = [
            fetch_alpha_vantage_earnings(),
            fetch_alpha_vantage_macro(),
            fetch_eodhd_economic_calendar()
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, list):
                events.extend(result)
            elif isinstance(result, Exception):
                logger.error(f"Error fetching events subset: {result}")

        logger.info(f"Total economic events fetched: {len(events)}")
        return events
    except Exception as e:
        logger.error(f"Error fetching combined economic calendar: {e}")
        return events

# Обновленная функция получения дивидендов и отчетностей, включающая EODHD.
@cached(ttl=EODHD_EVENTS_CACHE_TIMEOUT, cache=Cache.MEMORY, serializer=JsonSerializer())
async def fetch_dividends_and_earnings(symbol: str) -> list:
    events = []
    try:
        eodhd_earnings_task = fetch_eodhd_earnings_calendar(symbol=symbol)
        eodhd_dividends_task = fetch_eodhd_dividends(symbol)
        yfinance_dividends_task = fetch_yfinance_dividends(symbol)

        results = await asyncio.gather(
            eodhd_earnings_task,
            eodhd_dividends_task,
            yfinance_dividends_task,
            return_exceptions=True
        )

        for result in results:
            if isinstance(result, list):
                events.extend(result)
            elif isinstance(result, Exception):
                logger.error(f"Error fetching dividends/earnings subset for {symbol}: {result}")

        logger.info(f"Fetched {len(events)} dividends & earnings events for {symbol}")
        return events
    except Exception as e:
        logger.error(f"Error fetching combined dividends & earnings for {symbol}: {e}")
        return events

async def fetch_eodhd_dividends(symbol: str) -> list:
    events = []
    from_date = datetime.now().strftime("%Y-%m-%d")
    to_date = (datetime.now() + timedelta(days=90)).strftime("%Y-%m-%d")
    url = f"https://eodhistoricaldata.com/api/dividends/{symbol}.US?api_token={settings.api.EODHD_API_KEY}&from={from_date}&to={to_date}&fmt=json"
    logger.info(f"Fetching EODHD dividends for {symbol}")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    dividends_data = await response.json()
                    if isinstance(dividends_data, list):
                         for dividend in dividends_data:
                             try:
                                 if not dividend.get("paymentDate") or not dividend.get("value"):
                                     logger.warning(f"Skipping EODHD dividend with missing data: {dividend}")
                                     continue
                                 event_date = datetime.strptime(dividend["paymentDate"], "%Y-%m-%d").strftime("%Y-%m-%d %H:%M:%S")
                                 amount = dividend.get("value", "N/A")
                                 events.append({
                                     "event_date": event_date, "title": f"Дивиденды для {symbol}",
                                     "description": f"Сумма: ${amount}", "source": "EODHD",
                                     "type": "dividends", "symbol": symbol
                                 })
                             except Exception as e:
                                 logger.error(f"Error processing EODHD dividend {dividend}: {e}")
                elif response.status in [401, 429]:
                     logger.error(f"EODHD API error: {'Rate limit' if response.status == 429 else 'Invalid key'} ({response.status}) for dividends")
                else:
                    logger.error(f"Error fetching EODHD dividends for {symbol}: {response.status}")
    except Exception as e:
        logger.error(f"Error fetching EODHD dividend data for {symbol}: {e}")
    return events

async def fetch_yfinance_dividends(symbol: str) -> list:
    events = []
    logger.info(f"Fetching yfinance dividends for {symbol}")
    try:
        ticker = Ticker(symbol)
        dividends = ticker.dividends
        if dividends is not None and not dividends.empty:
            future_dividends = dividends[dividends.index > datetime.now()]
            for date, amount in future_dividends.items():
                 events.append({
                    "event_date": date.strftime("%Y-%m-%d %H:%M:%S"),
                    "title": f"Дивиденды для {symbol}",
                    "description": f"Сумма: ${amount:.2f}",
                    "source": "Yahoo Finance", "type": "dividends", "symbol": symbol
                 })
    except Exception as e:
        logger.error(f"Error fetching yfinance dividends for {symbol}: {e}")
    return events