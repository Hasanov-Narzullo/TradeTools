from datetime import datetime
from html import escape
from loguru import logger

def format_portfolio(portfolio, page: int = 1, items_per_page: int = 4) -> tuple[str, int]:
    """
    Форматирует портфель для отображения на указанной странице.
    Возвращает отформатированный текст и общее количество страниц.
    """
    if not portfolio:
        return "Портфель пуст.", 0

    # Вычисляем общее количество страниц
    total_pages = (len(portfolio) + items_per_page - 1) // items_per_page
    if page < 1:
        page = 1
    if page > total_pages:
        page = total_pages

    # Определяем диапазон элементов для текущей страницы
    start_idx = (page - 1) * items_per_page
    end_idx = start_idx + items_per_page
    page_items = portfolio[start_idx:end_idx]

    result = f"📊 Ваш портфель (страница {page}/{total_pages}):\n\n"
    for asset in page_items:
        try:
            symbol = asset['symbol']
            asset_type = "Акция" if asset['asset_type'] == "stock" else "Криптовалюта"
            amount = float(asset['amount'])
            purchase_price = float(asset['purchase_price'])
            current_price = asset.get('current_price')

            result += f"{symbol} ({asset_type})\n"
            result += f"Количество: {amount:.2f}\n"
            result += f"Цена покупки: ${purchase_price:.2f}\n"

            if current_price is not None:
                try:
                    current_price_float = float(current_price)
                    result += f"Текущая цена: ${current_price_float:.2f}\n"
                except (ValueError, TypeError):
                    logger.error(f"Некорректное значение текущей цены для {symbol}: {current_price}")
                    result += "Текущая цена: Не удалось получить\n"
            else:
                result += "Текущая цена: Не удалось получить\n"

            if current_price is not None and purchase_price != 0:
                try:
                    percentage_change = ((current_price_float - purchase_price) / purchase_price) * 100
                    change_emoji = "📈" if percentage_change >= 0 else "📉"
                    result += f"Изменение: {change_emoji} {percentage_change:+.2f}%\n"
                except (ValueError, TypeError) as e:
                    logger.error(f"Ошибка при расчете процента изменения для {symbol}: {e}")
                    result += "Изменение: Н/Д\n"
            else:
                result += "Изменение: Н/Д\n"

            result += "-" * 20 + "\n"
        except KeyError as e:
            logger.error(f"Некорректная структура данных актива: {asset}. Отсутствует ключ: {e}")
            result += f"Ошибка при обработке актива {asset.get('symbol', 'Неизвестный')}\n"
            result += "-" * 20 + "\n"

    return result, total_pages

def format_alerts(alerts: list, page: int = 1, items_per_page: int = 4) -> tuple[str, int]:
    """
    Форматирует список алертов для вывода на указанной странице.
    Возвращает отформатированный текст и общее количество страниц.
    """
    if not alerts:
        return "Алерты не установлены.", 0

    # Вычисляем общее количество страниц
    total_pages = (len(alerts) + items_per_page - 1) // items_per_page
    if page < 1:
        page = 1
    if page > total_pages:
        page = total_pages

    # Определяем диапазон элементов для текущей страницы
    start_idx = (page - 1) * items_per_page
    end_idx = start_idx + items_per_page
    page_items = alerts[start_idx:end_idx]

    result = f"🔔 Ваши алерты (страница {page}/{total_pages}):\n\n"
    for alert in page_items:
        alert_id, user_id, asset_type, symbol, target_price, condition, created_at = alert
        asset_type_display = "Акция" if asset_type == "stock" else "Криптовалюта"
        condition_display = "выше" if condition == "above" else "ниже"
        result += (
            f"ID: {str(alert_id)}\n"
            f"Актив: {symbol} ({asset_type_display})\n"
            f"Целевая цена: {str(target_price)}\n"
            f"Условие: {condition_display}\n"
            f"Дата создания: {str(created_at)}\n"
            f"{'-' * 30}\n"
        )

    return result, total_pages

def format_events(events: list) -> str:
    """Форматирование списка событий для вывода."""
    if not events:
        return "Календарь событий пуст."

    result = "📅 Календарь событий:\n\n"
    for event in events:
        event_id, event_date, title, description, source = event
        result += (
            f"Дата: {event_date}\n"
            f"Название: {title}\n"
            f"Описание: {description}\n"
            f"Источник: {source}\n"
            f"{'-' * 30}\n"
        )
    return result

def validate_symbol(symbol: str, asset_type: str) -> bool:
    """Проверка корректности символа актива."""
    if not symbol:
        return False
    if asset_type == "stock":
        return symbol.isalnum()  # Простая проверка для акций
    elif asset_type == "crypto":
        return "/" in symbol  # Проверка формата для криптовалют (например, BTC/USDT)
    return False

def log_error(user_id: int, error: str):
    """Логирование ошибок."""
    logger.error(f"Ошибка для пользователя {user_id}: {error}")

def format_price(price: float) -> str:
    """Форматирование цены для вывода."""
    return f"{price:.2f}"

def format_market_prices(portfolio):
    """
    Форматирует текущие рыночные цены активов в формате 'Тикер | Стоимость' для команды /market.
    Использует обычный текст для форматирования.
    """
    if not portfolio:
        return "Портфель пуст."

    result = "📈 Текущие рыночные цены:\n\n"
    for asset in portfolio:
        try:
            symbol = asset['symbol']
            current_price = asset.get('current_price')

            if current_price is not None:
                try:
                    current_price_float = float(current_price)
                    result += f"{symbol} | ${current_price_float:.2f}\n"
                except (ValueError, TypeError):
                    logger.error(f"Некорректное значение текущей цены для {symbol}: {current_price}")
                    result += f"{symbol} | Не удалось получить\n"
            else:
                result += f"{symbol} | Не удалось получить\n"

            result += "-" * 20 + "\n"
        except KeyError as e:
            logger.error(f"Некорректная структура данных актива: {asset}. Отсутствует ключ: {e}")
            result += f"Ошибка при обработке актива {asset.get('symbol', 'Неизвестный')}\n"
            result += "-" * 20 + "\n"

    return result

def escape_markdown_v2(text: str) -> str:
    """
    Экранирует зарезервированные символы для MarkdownV2.
    """
    reserved_chars = r'_[]()~`>#+-=|{}.!'
    for char in reserved_chars:
        text = text.replace(char, f'\\{char}')
    return text

def format_market_overview(market_data: dict) -> str:
    """Форматирование обзора рынка."""
    result = "🌍 Обзор рынка:\n\n"

    # Индексы
    result += "📊 *Индексы:*\n"
    for name, data in market_data["indices"].items():
        price = data["price"]
        change_percent = data["change_percent"]
        if price is not None and change_percent is not None:
            change_emoji = "📈" if change_percent >= 0 else "📉"
            result += f"{name}: ${price:.2f} {change_emoji} {change_percent:+.2f}%\n"
        else:
            result += f"{name}: Данные недоступны\n"
    result += "-" * 20 + "\n"

    # Сырьевые товары
    result += "🛢 *Сырьевые товары:*\n"
    for name, data in market_data["commodities"].items():
        price = data["price"]
        change_percent = data["change_percent"]
        if price is not None and change_percent is not None:
            change_emoji = "📈" if change_percent >= 0 else "📉"
            result += f"{name}: ${price:.2f} {change_emoji} {change_percent:+.2f}%\n"
        else:
            result += f"{name}: Данные недоступны\n"
    result += "-" * 20 + "\n"

    # Криптовалюты
    result += "💰 *Криптовалюты:*\n"
    for name, data in market_data["crypto"].items():
        price = data["price"]
        change_percent = data["change_percent"]
        if price is not None and change_percent is not None:
            change_emoji = "📈" if change_percent >= 0 else "📉"
            result += f"{name}: ${price:.2f} {change_emoji} {change_percent:+.2f}%\n"
        else:
            result += f"{name}: Данные недоступны\n"

    return result