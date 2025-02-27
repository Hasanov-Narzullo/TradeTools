from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
import datetime
import arrow
from loguru import logger

class Good:
    def __init__(self):
        self.value = "+"
        self.name = "good"

    def __repr__(self):
        return "<Good(value='%s')>" % (self.value)

class Bad:
    def __init__(self):
        self.value = "-"
        self.name = "bad"

    def __repr__(self):
        return "<Bad(value='%s')>" % (self.value)

class Unknow:
    def __init__(self):
        self.value = "?"
        self.name = "unknow"

    def __repr__(self):
        return "<Unknow(value='%s')>" % (self.value)

class Investing:
    def __init__(self, uri='https://ru.investing.com/economic-calendar/'):
        self.uri = uri
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/51.0.2704.103 Safari/537.36'
        }
        self.result = []

    async def news(self):
        """Асинхронный парсинг экономического календаря с Investing.com с использованием Playwright."""
        events = []
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                await page.goto(self.uri, wait_until="networkidle")

                # Ждем загрузки таблицы
                try:
                    await page.wait_for_selector('table#economicCalendarData', timeout=30000)
                except Exception as e:
                    logger.error(f"Ошибка при ожидании таблицы: {e}")
                    await browser.close()
                    return events

                html = await page.content()
                await browser.close()

                soup = BeautifulSoup(html, "html.parser")
                table = soup.find('table', {"id": "economicCalendarData"})
                if not table:
                    logger.error("Таблица событий не найдена на Investing.com")
                    return events

                tbody = table.find('tbody')
                rows = tbody.findAll('tr', {"class": "js-event-item"})
                if not rows:
                    logger.warning("События не найдены на Investing.com")
                    return events

                for row in rows:
                    news = {
                        'timestamp': None,
                        'country': None,
                        'impact': None,
                        'url': None,
                        'name': None,
                        'bold': None,
                        'fore': None,
                        'prev': None,
                        'signal': None,
                        'type': None
                    }

                    try:
                        # Парсинг времени и даты
                        _datetime = row.attrs.get('data-event-datetime')
                        if _datetime:
                            news['timestamp'] = arrow.get(_datetime, "YYYY/MM/DD HH:mm:ss").timestamp
                            event_date = arrow.get(_datetime, "YYYY/MM/DD HH:mm:ss").strftime("%Y-%m-%d %H:%M:%S")
                        else:
                            logger.debug("Дата события не найдена, пропускаем")
                            continue

                        # Парсинг страны
                        cols = row.find('td', {"class": "flagCur"})
                        if cols:
                            flag = cols.find('span')
                            news['country'] = flag.get('title') if flag else "Unknown"

                        # Парсинг влияния
                        impact = row.find('td', {"class": "sentiment"})
                        if impact:
                            bull = impact.findAll('i', {"class": "grayFullBullishIcon"})
                            news['impact'] = len(bull)

                        # Парсинг события
                        event = row.find('td', {"class": "event"})
                        if event:
                            a = event.find('a')
                            if a:
                                news['url'] = f"{self.uri}{a['href']}"
                                news['name'] = a.text.strip()

                            # Определение типа события
                            legend = event.find('span', {"class": "smallGrayReport"})
                            if legend:
                                news['type'] = "report"
                            legend = event.find('span', {"class": "audioIconNew"})
                            if legend:
                                news['type'] = "speech"
                            legend = event.find('span', {"class": "smallGrayP"})
                            if legend:
                                news['type'] = "release"
                            legend = event.find('span', {"class": "sandClock"})
                            if legend:
                                news['type'] = "retrieving data"

                        # Парсинг значений
                        bold = row.find('td', {"class": "bold"})
                        if bold and bold.text.strip():
                            news['bold'] = bold.text.strip()
                        else:
                            news['bold'] = ''

                        fore = row.find('td', {"class": "fore"})
                        if fore:
                            news['fore'] = fore.text.strip()
                        else:
                            news['fore'] = ''

                        prev = row.find('td', {"class": "prev"})
                        if prev:
                            news['prev'] = prev.text.strip()
                        else:
                            news['prev'] = ''

                        # Определение сигнала
                        if bold and "blackFont" in bold.get('class', []):
                            news['signal'] = Unknow()
                        elif bold and "redFont" in bold.get('class', []):
                            news['signal'] = Bad()
                        elif bold and "greenFont" in bold.get('class', []):
                            news['signal'] = Good()
                        else:
                            news['signal'] = Unknow()

                        # Формируем событие для базы данных
                        events.append({
                            "event_date": event_date,
                            "title": news['name'] or "Неизвестное событие",
                            "description": f"Влияние: {news['impact']} звезд, Страна: {news['country']}, Тип: {news['type'] or 'unknown'}, Прогноз: {news['fore']}, Предыдущее: {news['prev']}",
                            "source": "Investing.com",
                            "type": "macro",
                            "symbol": None
                        })
                        logger.debug(f"Добавлено событие: {news['name']}")
                    except Exception as e:
                        logger.error(f"Ошибка при парсинге события: {e}")
                        continue
        except Exception as e:
            logger.error(f"Ошибка при запросе к Investing.com: {e}")

        logger.info(f"Получено {len(events)} общеэкономических событий с Investing.com")
        return events