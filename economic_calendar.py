# economic_calendar
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
import datetime
import arrow
from loguru import logger

SIGNAL_GOOD = "+"
SIGNAL_BAD = "-"
SIGNAL_UNKNOWN = "?"

class Investing:
    def __init__(self, uri='https://ru.investing.com/economic-calendar/'):
        self.uri = uri
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/51.0.2704.103 Safari/537.36'
        }
        self.result = []

    # Асинхронный парсинг экономического календаря с Investing.com с использованием Playwright.
    async def news(self):
        events = []
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                await page.goto(self.uri, wait_until="networkidle")
                try:
                    await page.wait_for_selector('table#economicCalendarData', timeout=30000)
                except Exception as e:
                    logger.error(f"Timeout waiting for table#economicCalendarData: {e}")
                    await browser.close()
                    return events

                html = await page.content()
                await browser.close()

                soup = BeautifulSoup(html, "html.parser")
                table = soup.find('table', {"id": "economicCalendarData"})
                if not table:
                    logger.error("economicCalendarData table not found on Investing.com")
                    return events

                tbody = table.find('tbody')
                rows = tbody.findAll('tr', {"class": "js-event-item"})
                if not rows:
                    logger.warning("No events found in table on Investing.com")
                    return events

                for row in rows:
                    news_data = {
                        'timestamp': None,'country': None,'impact': None,'url': None,
                        'name': None,'bold': '','fore': '','prev': '',
                        'signal': SIGNAL_UNKNOWN,'type': 'unknown'
                    }
                    try:
                        _datetime = row.attrs.get('data-event-datetime')
                        if _datetime:
                            dt_obj = arrow.get(_datetime, "YYYY/MM/DD HH:mm:ss")
                            news_data['timestamp'] = dt_obj.timestamp
                            event_date = dt_obj.strftime("%Y-%m-%d %H:%M:%S")
                        else: continue

                        cols = row.find('td', {"class": "flagCur"})
                        if cols: news_data['country'] = cols.find('span').get('title', 'Unknown') if cols.find('span') else "Unknown"

                        impact = row.find('td', {"class": "sentiment"})
                        if impact: news_data['impact'] = len(impact.findAll('i', {"class": "grayFullBullishIcon"}))

                        event = row.find('td', {"class": "event"})
                        if event:
                            a = event.find('a')
                            if a:
                                news_data['url'] = f"https://ru.investing.com{a['href']}" if a['href'].startswith('/') else a['href']
                                news_data['name'] = a.text.strip()
                            if event.find('span', {"class": "smallGrayReport"}): news_data['type'] = "report"
                            elif event.find('span', {"class": "audioIconNew"}): news_data['type'] = "speech"
                            elif event.find('span', {"class": "smallGrayP"}): news_data['type'] = "release"
                            elif event.find('span', {"class": "sandClock"}): news_data['type'] = "retrieving data"

                        bold_td = row.find('td', {"class": "bold"})
                        if bold_td: news_data['bold'] = bold_td.text.strip()
                        fore_td = row.find('td', {"class": "fore"})
                        if fore_td: news_data['fore'] = fore_td.text.strip()
                        prev_td = row.find('td', {"class": "prev"})
                        if prev_td: news_data['prev'] = prev_td.text.strip()

                        if bold_td:
                            classes = bold_td.get('class', [])
                            if "blackFont" in classes: news_data['signal'] = SIGNAL_UNKNOWN
                            elif "redFont" in classes: news_data['signal'] = SIGNAL_BAD
                            elif "greenFont" in classes: news_data['signal'] = SIGNAL_GOOD

                        events.append({
                            "event_date": event_date,
                            "title": news_data['name'] or "Неизвестное событие",
                            "description": f"Влияние: {news_data.get('impact','N/A')}*, Страна: {news_data.get('country','N/A')}, Тип: {news_data.get('type','N/A')}, Прогноз: {news_data.get('fore','N/A')}, Пред: {news_data.get('prev','N/A')}",
                            "source": "Investing.com",
                            "type": "macro",
                            "symbol": None
                        })
                    except Exception as e:
                        logger.error(f"Error parsing investing.com event row: {e}")
        except Exception as e:
            logger.error(f"Error during investing.com request/parsing: {e}")

        logger.info(f"Parsed {len(events)} events from Investing.com")
        return events