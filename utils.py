# utils
from datetime import datetime
from html import escape
from loguru import logger

from api import EVENT_TYPES, fetch_asset_price_with_retry
import asyncio

"""
Форматирует портфель для отображения на указанной странице.
Возвращает отформатированный текст и общее количество страниц.
"""
def format_portfolio(
    assets_in_sub_account: list,
    page: int = 1,
    items_per_page: int = 4,
    total_portfolio_value: float = 0.0,
    total_portfolio_pnl: float = 0.0,
    prices_available_overall: bool = True
) -> tuple[str, int]:
    total_items = len(assets_in_sub_account)
    total_pages = (total_items + items_per_page - 1) // items_per_page if total_items > 0 else 0

    if not assets_in_sub_account and total_pages == 0:
        result = "В этом суб-счете нет активов.\n\n"
    elif page < 1 or (total_pages > 0 and page > total_pages):
        result = f"Неверная страница ({page}). Всего страниц: {total_pages}.\n\n"
        page = 1
    else:
        start_idx = (page - 1) * items_per_page
        end_idx = start_idx + items_per_page
        page_items = assets_in_sub_account[start_idx:end_idx]

        result = f"(страница {page}/{total_pages})\n\n"
        for asset in page_items:
            try:
                symbol = asset['symbol']
                asset_type_str = "Акция" if asset['asset_type'] == "stock" else "Криптовалюта"
                amount = float(asset['amount'])
                purchase_price = float(asset['purchase_price'])
                current_price = asset.get('current_price')

                result += f"{symbol} ({asset_type_str})\n"
                result += f"Кол-во: {amount:.2f}\n"
                result += f"Цена покупки: ${purchase_price:.2f}\n"


                if current_price is not None:
                    try:
                        current_price_float = float(current_price)
                        current_value = amount * current_price_float
                        result += f"Тек. цена: ${current_price_float:.2f} (Стоимость: ${current_value:.2f})\n"
                        if purchase_price != 0:
                            percentage_change = ((current_price_float - purchase_price) / purchase_price) * 100
                            change_emoji = "📈" if percentage_change >= 0 else "📉"
                            result += f"Изм: {change_emoji} {percentage_change:+.2f}%\n"
                        else:
                            result += "Изм: Н/Д (цена покупки 0)\n"
                    except (ValueError, TypeError) as e:
                        logger.error(f"Некорректная тек. цена или расчет для {symbol}: {current_price}, {e}")
                        result += "Тек. цена: Ошибка\n"
                        result += "Изм: Н/Д\n"
                else:
                    result += "Тек. цена: Не получена\n"
                    result += "Изм: Н/Д\n"

                result += "-" * 20 + "\n"
            except (KeyError, ValueError, TypeError) as e:
                logger.error(f"Ошибка форматирования актива: {asset}. Ошибка: {e}")
                result += f"Ошибка обработки актива {asset.get('symbol', 'Неизвестный')}\n"
                result += "-" * 20 + "\n"

    result += f"\n💰 *Общая стоимость портфеля:* "
    if prices_available_overall:
        result += f"${total_portfolio_value:.2f}\n"
        pnl_emoji = "📈" if total_portfolio_pnl >= 0 else "📉"
        result += f"📊 *Общий PnL:* {pnl_emoji} ${total_portfolio_pnl:+.2f}\n"
    else:
        result += "(не удалось получить все цены)\n"
        result += f"📊 *Общий PnL:* (не удалось получить все цены)\n"


    return result, total_pages

"""
Форматирует список алертов для вывода на указанной странице.
Возвращает отформатированный текст и общее количество страниц.
"""
def format_alerts(alerts: list, page: int = 1, items_per_page: int = 4) -> tuple[str, int]:
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

"""
Форматирует список событий для вывода на указанной странице.
Возвращает отформатированный текст и общее количество страниц.
"""
def format_events(events: list, page: int = 1, items_per_page: int = 4) -> tuple[str, int]:
    if not events:
        return "Календарь событий пуст.", 0

    # Вычисляем общее количество страниц
    total_pages = (len(events) + items_per_page - 1) // items_per_page
    if page < 1:
        page = 1
    if page > total_pages:
        page = total_pages

    # Определяем диапазон элементов для текущей страницы
    start_idx = (page - 1) * items_per_page
    end_idx = start_idx + items_per_page
    page_items = events[start_idx:end_idx]

    result = f"📅 Календарь событий (страница {page}/{total_pages}):\n\n"
    for event in page_items:
        event_id, event_date, title, description, source, event_type, symbol = event
        event_type_display = EVENT_TYPES.get(event_type, "Неизвестный тип")
        result += (
            f"Тип: {event_type_display}\n"
            f"Дата: {event_date}\n"
            f"Название: {title}\n"
            f"Описание: {description}\n"
            f"Источник: {source}\n"
            f"Актив: {symbol if symbol else 'Общее'}\n"
            f"{'-' * 30}\n"
        )

    return result, total_pages

# Проверка корректности символа актива.
def validate_symbol(symbol: str, asset_type: str) -> bool:
    if not symbol:
        return False
    if asset_type == "stock":
        return symbol.isalnum()  # Простая проверка для акций
    elif asset_type == "crypto":
        return "/" in symbol  # Проверка формата для криптовалют (например, BTC/USDT)
    return False

# Логирование ошибок.
def log_error(user_id: int, error: str):
    logger.error(f"Ошибка для пользователя {user_id}: {error}")

# Форматирование цены для вывода.
def format_price(price: float) -> str:
    return f"{price:.2f}"

"""
Форматирует текущие рыночные цены активов в формате 'Тикер | Стоимость' для команды /market.
Использует обычный текст для форматирования.
"""
def format_market_prices(portfolio):
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

# Экранирует зарезервированные символы для MarkdownV2.
def escape_markdown_v2(text: str) -> str:
    reserved_chars = r'_[]()~`>#+-=|{}.!'
    for char in reserved_chars:
        text = text.replace(char, f'\\{char}')
    return text

# Форматирование обзора рынка.
def format_market_overview(market_data: dict) -> str:
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

async def calculate_portfolio_summary(portfolio_data: dict) -> tuple[float, float, float]:
    total_current_value = 0.0
    total_purchase_value = 0.0
    prices_fetched = True

    if not portfolio_data:
        return 0.0, 0.0, 0.0

    tasks = []
    asset_details = []

    for sub_account, assets in portfolio_data.items():
        for asset in assets:
            try:
                symbol = asset['symbol']
                asset_type = asset['asset_type']
                amount = float(asset['amount'])
                purchase_price = float(asset['purchase_price'])
                tasks.append(fetch_asset_price_with_retry(symbol, asset_type))
                asset_details.append({'symbol': symbol, 'amount': amount, 'purchase_price': purchase_price})
            except (KeyError, ValueError, TypeError) as e:
                logger.error(f"Ошибка обработки актива в calculate_portfolio_summary: {asset}. Ошибка: {e}")
                prices_fetched = False

    if not tasks:
         return 0.0, 0.0, 0.0

    logger.info(f"Запрос цен для {len(tasks)} активов для расчета сводки портфеля...")
    current_prices = await asyncio.gather(*tasks)
    logger.info("Цены для сводки портфеля получены.")


    for i, price in enumerate(current_prices):
        details = asset_details[i]
        purchase_value = details['amount'] * details['purchase_price']
        total_purchase_value += purchase_value

        if price is not None:
            current_value = details['amount'] * price
            total_current_value += current_value
        else:
            logger.warning(f"Не удалось получить цену для {details['symbol']} при расчете сводки портфеля.")
            prices_fetched = False


    total_pnl = total_current_value - total_purchase_value

    if not prices_fetched:
        logger.warning("Не удалось получить цены для одного или нескольких активов при расчете сводки портфеля.")


    return total_current_value, total_purchase_value, total_pnl

