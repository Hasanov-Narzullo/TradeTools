from datetime import datetime

EVENT_TYPES = {
    "macro": "Общеэкономические",
    "dividends": "Дивиденды",
    "earnings": "Отчетности",
    "press": "Пресс-конференции"
}

# Пример событий (200 событий, 60 крипто, 140 инвестиции)
SAMPLE_EVENTS = {
    "crypto": [
        {
            "event_date": "2025-01-15 00:00:00",
            "title": "Обновление Ethereum (Dencun Upgrade)",
            "description": "Обновление сети Ethereum",
            "source": "Sample Data",
            "type": "macro",
            "symbol": "ETH"
        },
        {
            "event_date": "2025-02-01 00:00:00",
            "title": "Bitcoin Halving",
            "description": "Уменьшение награды за блок BTC",
            "source": "Sample Data",
            "type": "macro",
            "symbol": "BTC"
        },
        {
            "event_date": "2025-02-15 00:00:00",
            "title": "Конференция Consensus 2025",
            "description": "Ключевая конференция по блокчейну",
            "source": "Sample Data",
            "type": "press",
            "symbol": "-"
        },
        {
            "event_date": "2025-03-01 00:00:00",
            "title": "Обновление Cardano (Voltaire Era)",
            "description": "Введение управления в Cardano",
            "source": "Sample Data",
            "type": "macro",
            "symbol": "ADA"
        },
        {
            "event_date": "2025-03-15 00:00:00",
            "title": "Binance Blockchain Week",
            "description": "Конференция Binance",
            "source": "Sample Data",
            "type": "press",
            "symbol": "BNB"
        },
        {
            "event_date": "2025-04-01 00:00:00",
            "title": "Регуляторное решение SEC по ETF на ETH",
            "description": "Решение по спотовым ETF на Ethereum",
            "source": "Sample Data",
            "type": "macro",
            "symbol": "ETH"
        },
        {
            "event_date": "2025-04-15 00:00:00",
            "title": "Обновление Solana (v1.18)",
            "description": "Улучшение производительности Solana",
            "source": "Sample Data",
            "type": "macro",
            "symbol": "SOL"
        },
        {
            "event_date": "2025-05-01 00:00:00",
            "title": "Халвинг Litecoin",
            "description": "Уменьшение награды за блок LTC",
            "source": "Sample Data",
            "type": "macro",
            "symbol": "LTC"
        },
        {
            "event_date": "2025-05-15 00:00:00",
            "title": "Конференция EthCC 2025",
            "description": "Конференция по Ethereum",
            "source": "Sample Data",
            "type": "press",
            "symbol": "ETH"
        },
        {
            "event_date": "2025-06-01 00:00:00",
            "title": "Обновление Polkadot (Parachain Auctions)",
            "description": "Аукционы парачейнов",
            "source": "Sample Data",
            "type": "macro",
            "symbol": "DOT"
        },
        # Продолжение списка криптовалютных событий...
    ],
    "investments": [
        {
            "event_date": "2025-01-15 00:00:00",
            "title": "Отчетность Apple (Q4 2024)",
            "description": "Финансовые результаты Apple",
            "source": "Sample Data",
            "type": "earnings",
            "symbol": "AAPL"
        },
        {
            "event_date": "2025-01-22 00:00:00",
            "title": "Заседание ФРС по процентной ставке",
            "description": "Решение по ставке ФРС",
            "source": "Sample Data",
            "type": "macro",
            "symbol": "-"
        },
        {
            "event_date": "2025-01-29 00:00:00",
            "title": "Отчетность Microsoft (Q2 FY2025)",
            "description": "Финансовые результаты Microsoft",
            "source": "Sample Data",
            "type": "earnings",
            "symbol": "MSFT"
        },
        {
            "event_date": "2025-02-05 00:00:00",
            "title": "Отчетность Amazon (Q4 2024)",
            "description": "Финансовые результаты Amazon",
            "source": "Sample Data",
            "type": "earnings",
            "symbol": "AMZN"
        },
        {
            "event_date": "2025-02-12 00:00:00",
            "title": "Индекс потребительских цен США (CPI)",
            "description": "Данные по инфляции",
            "source": "Sample Data",
            "type": "macro",
            "symbol": "-"
        },
        {
            "event_date": "2025-02-19 00:00:00",
            "title": "Отчетность Tesla (Q4 2024)",
            "description": "Финансовые результаты Tesla",
            "source": "Sample Data",
            "type": "earnings",
            "symbol": "TSLA"
        },
        {
            "event_date": "2025-03-05 00:00:00",
            "title": "Заседание ЕЦБ по монетарной политике",
            "description": "Решение по ставке ЕЦБ",
            "source": "Sample Data",
            "type": "macro",
            "symbol": "-"
        },
        {
            "event_date": "2025-03-12 00:00:00",
            "title": "Отчетность NVIDIA (Q4 FY2025)",
            "description": "Финансовые результаты NVIDIA",
            "source": "Sample Data",
            "type": "earnings",
            "symbol": "NVDA"
        },
        {
            "event_date": "2025-04-16 00:00:00",
            "title": "Отчетность Goldman Sachs (Q1 2025)",
            "description": "Финансовые результаты Goldman Sachs",
            "source": "Sample Data",
            "type": "earnings",
            "symbol": "GS"
        },
        {
            "event_date": "2025-04-23 00:00:00",
            "title": "ВВП США (Q1 2025)",
            "description": "Данные по ВВП",
            "source": "Sample Data",
            "type": "macro",
            "symbol": "-"
        },
        {
            "event_date": "2025-06-15 00:00:00",
            "title": "Обновление Chainlink (CCIP v2)",
            "description": "Обновление протокола межсетевого взаимодействия",
            "source": "Sample Data",
            "type": "macro",
            "symbol": "LINK"
        },
        {
            "event_date": "2025-07-01 00:00:00",
            "title": "Конференция по DeFi 2025",
            "description": "Обсуждение децентрализованных финансов",
            "source": "Sample Data",
            "type": "press",
            "symbol": "-"
        },
        {
            "event_date": "2025-07-15 00:00:00",
            "title": "Обновление XRP Ledger (Hooks)",
            "description": "Введение смарт-контрактов в XRP Ledger",
            "source": "Sample Data",
            "type": "macro",
            "symbol": "XRP"
        },
        {
            "event_date": "2025-08-01 00:00:00",
            "title": "Dogecoin Conference 2025",
            "description": "Конференция по Dogecoin",
            "source": "Sample Data",
            "type": "press",
            "symbol": "DOGE"
        },
        {
            "event_date": "2025-08-15 00:00:00",
            "title": "Обновление Ethereum (Verkle Trees)",
            "description": "Оптимизация хранения данных в Ethereum",
            "source": "Sample Data",
            "type": "macro",
            "symbol": "ETH"
        },
        {
            "event_date": "2025-09-01 00:00:00",
            "title": "Регуляторное решение ЕС по криптовалютам",
            "description": "Решение по регулированию криптовалют в ЕС",
            "source": "Sample Data",
            "type": "macro",
            "symbol": "-"
        },
        {
            "event_date": "2025-09-15 00:00:00",
            "title": "Обновление Solana (QUIC Protocol)",
            "description": "Улучшение сетевой производительности Solana",
            "source": "Sample Data",
            "type": "macro",
            "symbol": "SOL"
        },
        {
            "event_date": "2025-10-01 00:00:00",
            "title": "Конференция по блокчейну в Азии",
            "description": "Ключевая конференция в Азии",
            "source": "Sample Data",
            "type": "press",
            "symbol": "-"
        },
        {
            "event_date": "2025-10-15 00:00:00",
            "title": "Обновление Polkadot (XCM v3)",
            "description": "Обновление протокола межсетевого взаимодействия",
            "source": "Sample Data",
            "type": "macro",
            "symbol": "DOT"
        },
        {
            "event_date": "2025-11-01 00:00:00",
            "title": "Регуляторное решение SEC по стейблкоинам",
            "description": "Решение по регулированию стейблкоинов",
            "source": "Sample Data",
            "type": "macro",
            "symbol": "-"
        },
    {
        "event_date": "2025-05-07 00:00:00",
        "title": "Отчетность Visa (Q2 2025)",
        "description": "Финансовые результаты Visa",
        "source": "Sample Data",
        "type": "earnings",
        "symbol": "V"
    },
    {
        "event_date": "2025-05-14 00:00:00",
        "title": "Заседание ФРС по процентной ставке",
        "description": "Решение по ставке ФРС",
        "source": "Sample Data",
        "type": "macro",
        "symbol": "-"
    },
    {
        "event_date": "2025-05-21 00:00:00",
        "title": "Отчетность Mastercard (Q2 2025)",
        "description": "Финансовые результаты Mastercard",
        "source": "Sample Data",
        "type": "earnings",
        "symbol": "MA"
    },
    {
        "event_date": "2025-06-04 00:00:00",
        "title": "Индекс потребительских цен США (CPI)",
        "description": "Данные по инфляции",
        "source": "Sample Data",
        "type": "macro",
        "symbol": "-"
    },
    {
        "event_date": "2025-06-11 00:00:00",
        "title": "Отчетность JPMorgan Chase (Q2 2025)",
        "description": "Финансовые результаты JPMorgan Chase",
        "source": "Sample Data",
        "type": "earnings",
        "symbol": "JPM"
    },
    {
        "event_date": "2025-06-18 00:00:00",
        "title": "Заседание ЕЦБ по монетарной политике",
        "description": "Решение по ставке ЕЦБ",
        "source": "Sample Data",
        "type": "macro",
        "symbol": "-"
    },
    {
        "event_date": "2025-07-02 00:00:00",
        "title": "Отчетность Apple (Q2 2025)",
        "description": "Финансовые результаты Apple",
        "source": "Sample Data",
        "type": "earnings",
        "symbol": "AAPL"
    },
    {
        "event_date": "2025-07-09 00:00:00",
        "title": "ВВП США (Q2 2025)",
        "description": "Данные по ВВП",
        "source": "Sample Data",
        "type": "macro",
        "symbol": "-"
    },
    {
        "event_date": "2025-07-16 00:00:00",
        "title": "Отчетность Microsoft (Q4 FY2025)",
        "description": "Финансовые результаты Microsoft",
        "source": "Sample Data",
        "type": "earnings",
        "symbol": "MSFT"
    },
    {
        "event_date": "2025-07-23 00:00:00",
        "title": "Заседание ФРС по процентной ставке",
        "description": "Решение по ставке ФРС",
        "source": "Sample Data",
        "type": "macro",
        "symbol": "-"
    },
    ]
}

def get_sample_events():
    """Возвращает пример событий, отсортированных по дате."""
    all_events = SAMPLE_EVENTS["crypto"] + SAMPLE_EVENTS["investments"]
    return sorted(all_events, key=lambda x: datetime.strptime(x["event_date"], "%Y-%m-%d %H:%M:%S"))