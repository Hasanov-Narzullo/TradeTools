from datetime import datetime
from html import escape
from loguru import logger
from api import get_exchange_rate


async def format_portfolio(portfolio):
    """
    Форматирует портфель для отображения пользователю в Telegram с учетом сумм вложений и текущих стоимостей.
    Показывает суммы в рублях и долларах.
    """
    if not portfolio:
        return "Портфель пуст."

    # Инициализируем переменные для сумм
    total_invested_usd = 0.0  # Сумма вложений в долларах
    total_value_usd = 0.0     # Текущая стоимость портфеля в долларах
    stocks_invested_usd = 0.0  # Сумма вложений в акции в долларах
    stocks_value_usd = 0.0     # Текущая стоимость акций в долларах
    crypto_invested_usd = 0.0  # Сумма вложений в криптовалюты в долларах
    crypto_value_usd = 0.0     # Текущая стоимость криптовалют в долларах

    # Получаем курс USD/RUB
    usd_to_rub = await get_exchange_rate("USD", "RUB")

    result = "📊 Ваш портфель:\n\n"
    for asset in portfolio:
        try:
            symbol = asset['symbol']
            asset_type = "Акция" if asset['asset_type'] == "stock" else "Криптовалюта"
            amount = float(asset['amount'])
            purchase_price = float(asset['purchase_price'])
            current_price = asset.get('current_price')

            # Рассчитываем сумму вложений для актива
            invested_usd = amount * purchase_price
            value_usd = amount * current_price if current_price is not None else 0.0

            # Обновляем общие суммы
            total_invested_usd += invested_usd
            if current_price is not None:
                total_value_usd += value_usd

            # Обновляем суммы по типам активов
            if asset['asset_type'] == "stock":
                stocks_invested_usd += invested_usd
                if current_price is not None:
                    stocks_value_usd += value_usd
            elif asset['asset_type'] == "crypto":
                crypto_invested_usd += invested_usd
                if current_price is not None:
                    crypto_value_usd += value_usd

            # Форматируем информацию об активе
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
        except (ValueError, TypeError) as e:
            logger.error(f"Ошибка при форматировании данных актива {asset.get('symbol', 'Неизвестный')}: {e}")
            result += f"Ошибка при обработке актива {asset.get('symbol', 'Неизвестный')}\n"
            result += "-" * 20 + "\n"

    # Конвертируем суммы в рубли
    total_invested_rub = total_invested_usd * usd_to_rub
    total_value_rub = total_value_usd * usd_to_rub
    stocks_invested_rub = stocks_invested_usd * usd_to_rub
    stocks_value_rub = stocks_value_usd * usd_to_rub
    crypto_invested_rub = crypto_invested_usd * usd_to_rub
    crypto_value_rub = crypto_value_usd * usd_to_rub

    # Добавляем итоговые суммы
    result += "\n💰 Итоговые суммы:\n"
    result += f"Сумма вложений: {total_invested_rub:.2f} руб | ${total_invested_usd:.2f}\n"
    result += f"Текущая стоимость портфеля: {total_value_rub:.2f} руб | ${total_value_usd:.2f}\n"
    result += f"Текущая стоимость акций: {stocks_value_rub:.2f} руб | ${stocks_value_usd:.2f}\n"
    result += f"Текущая стоимость криптовалют: {crypto_value_rub:.2f} руб | ${crypto_value_usd:.2f}\n"

    return result

def format_alerts(alerts: list) -> str:
    """Форматирование списка алертов для вывода в формате обычного текста."""
    if not alerts:
        return "Алерты не установлены."

    result = "🔔 Ваши алерты:\n\n"
    for alert in alerts:
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