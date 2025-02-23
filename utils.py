from loguru import logger
from datetime import datetime
from html import escape


def format_portfolio(portfolio):
    """
    Форматирует портфель для отображения пользователю в Telegram с использованием HTML.
    """
    if not portfolio:
        return "Портфель пуст."

    result = "<b>📊 Ваш портфель:</b><br/>"
    for asset in portfolio:
        try:
            symbol = asset['symbol']
            asset_type = "Акция" if asset['asset_type'] == "stock" else "Криптовалюта"
            amount = float(asset['amount'])
            purchase_price = float(asset['purchase_price'])
            current_price = asset.get('current_price')

            result += f"<b>{escape(symbol)}</b> ({escape(asset_type)})<br/>"
            result += f"Количество: {amount:.2f}<br/>"
            result += f"Цена покупки: ${purchase_price:.2f}<br/>"

            if current_price is not None:
                try:
                    current_price_float = float(current_price)
                    result += f"Текущая цена: ${current_price_float:.2f}<br/>"
                except (ValueError, TypeError):
                    logger.error(f"Некорректное значение текущей цены для {symbol}: {current_price}")
                    result += "Текущая цена: Не удалось получить<br/>"
            else:
                result += "Текущая цена: Не удалось получить<br/>"

            if current_price is not None and purchase_price != 0:
                try:
                    percentage_change = ((current_price_float - purchase_price) / purchase_price) * 100
                    change_emoji = "📈" if percentage_change >= 0 else "📉"
                    result += f"Изменение: {change_emoji} {percentage_change:+.2f}%<br/>"
                except (ValueError, TypeError) as e:
                    logger.error(f"Ошибка при расчете процента изменения для {symbol}: {e}")
                    result += "Изменение: Н/Д<br/>"
            else:
                result += "Изменение: Н/Д<br/>"

            result += "-" * 20 + "<br/>"
        except KeyError as e:
            logger.error(f"Некорректная структура данных актива: {asset}. Отсутствует ключ: {e}")
            result += f"Ошибка при обработке актива {escape(asset.get('symbol', 'Неизвестный'))}<br/>"
            result += "-" * 20 + "<br/>"
        except (ValueError, TypeError) as e:
            logger.error(f"Ошибка при форматировании данных актива {asset.get('symbol', 'Неизвестный')}: {e}")
            result += f"Ошибка при обработке актива {escape(asset.get('symbol', 'Неизвестный'))}<br/>"
            result += "-" * 20 + "<br/>"

    return result


def format_alerts(alerts: list) -> str:
    """Форматирование списка алертов для вывода в формате HTML."""
    if not alerts:
        return "Алерты не установлены."

    result = "<b>🔔 Ваши алерты:</b><br/>"
    for alert in alerts:
        alert_id, user_id, asset_type, symbol, target_price, condition, created_at = alert
        asset_type_display = "Акция" if asset_type == "stock" else "Криптовалюта"
        condition_display = "выше" if condition == "above" else "ниже"
        result += (
            f"ID: {escape(str(alert_id))}<br/>"
            f"Актив: {escape(symbol)} ({escape(asset_type_display)})<br/>"
            f"Целевая цена: {escape(str(target_price))}<br/>"
            f"Условие: {escape(condition_display)}<br/>"
            f"Дата создания: {escape(str(created_at))}<br/>"
            f"{'-' * 30}<br/>"
        )
    return result


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
    Использует HTML для форматирования.
    """
    if not portfolio:
        return "Портфель пуст."

    result = "<b>📈 Текущие рыночные цены:</b><br/>"
    for asset in portfolio:
        try:
            symbol = asset['symbol']
            current_price = asset.get('current_price')

            if current_price is not None:
                try:
                    current_price_float = float(current_price)
                    result += f"<b>{escape(symbol)}</b> | ${current_price_float:.2f}<br/>"
                except (ValueError, TypeError):
                    logger.error(f"Некорректное значение текущей цены для {symbol}: {current_price}")
                    result += f"<b>{escape(symbol)}</b> | Не удалось получить<br/>"
            else:
                result += f"<b>{escape(symbol)}</b> | Не удалось получить<br/>"

            result += "-" * 20 + "<br/>"
        except KeyError as e:
            logger.error(f"Некорректная структура данных актива: {asset}. Отсутствует ключ: {e}")
            result += f"Ошибка при обработке актива {escape(asset.get('symbol', 'Неизвестный'))}<br/>"
            result += "-" * 20 + "<br/>"

    return result


def escape_markdown_v2(text: str) -> str:
    """
    Экранирует зарезервированные символы для MarkdownV2.
    """
    reserved_chars = r'_[]()~`>#+-=|{}.!'
    for char in reserved_chars:
        text = text.replace(char, f'\\{char}')
    return text