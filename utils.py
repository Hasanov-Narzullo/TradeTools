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
    assets_in_sub_account_page: list, page: int = 1, total_pages: int = 1,
    total_portfolio_value: float = 0.0, total_portfolio_pnl: float = 0.0,
    prices_available_overall: bool = True
) -> str:
    if not assets_in_sub_account_page and page == 1 and total_pages <= 1: result = "В этом суб-счете нет активов.\n\n"
    elif page < 1 or page > total_pages: result = f"Неверная страница ({page}/{total_pages}).\n\n"
    else:
        result = f"(страница {page}/{total_pages})\n\n"
        for asset in assets_in_sub_account_page:
            try:
                symbol, type_str = asset['symbol'], "Акция" if asset['asset_type'] == "stock" else "Криптовалюта"
                amount, purch_price = float(asset['amount']), float(asset['purchase_price'])
                curr_price = asset.get('current_price')
                result += f"{symbol} ({type_str})\nКол-во: {amount:.2f}\nЦена покупки: ${purch_price:.2f}\n"
                if curr_price is not None:
                    try:
                        curr_price_f = float(curr_price)
                        curr_val = amount * curr_price_f
                        result += f"Тек. цена: ${curr_price_f:.2f} (Ст-сть: ${curr_val:.2f})\n"
                        if purch_price != 0:
                            change = ((curr_price_f - purch_price) / purch_price) * 100
                            emoji = "📈" if change >= 0 else "📉"
                            result += f"Изм: {emoji} {change:+.2f}%\n"
                        else: result += "Изм: Н/Д (цена 0)\n"
                    except (ValueError, TypeError) as e:
                        logger.error(f"Invalid current price/calc for {symbol}: {curr_price}, {e}")
                        result += "Тек. цена: Ошибка\nИзм: Н/Д\n"
                else: result += "Тек. цена: Н/Д\nИзм: Н/Д\n"
                result += "-" * 20 + "\n"
            except (KeyError, ValueError, TypeError) as e:
                logger.error(f"Error formatting asset {asset}: {e}")
                result += f"Ошибка актива {asset.get('symbol', '?')}\n" + "-" * 20 + "\n"

    result += f"\n💰 *Общая стоимость портфеля:* "
    result += f"${total_portfolio_value:.2f}\n" if prices_available_overall else "(не все цены)\n"
    result += f"📊 *Общий PnL:* "
    pnl_emoji = "📈" if total_portfolio_pnl >= 0 else "📉"
    result += f"{pnl_emoji} ${total_portfolio_pnl:+.2f}\n" if prices_available_overall else "(не все цены)\n"
    return result

"""
Форматирует список алертов для вывода на указанной странице.
Возвращает отформатированный текст и общее количество страниц.
"""
def format_alerts(alerts: list, page: int = 1, items_per_page: int = 4) -> tuple[str, int]:
    if not alerts: return "Алерты не установлены.", 0
    total_pages = (len(alerts) + items_per_page - 1) // items_per_page
    page = max(1, min(page, total_pages))
    start, end = (page - 1) * items_per_page, page * items_per_page
    page_items = alerts[start:end]
    result = f"🔔 Ваши алерты (стр. {page}/{total_pages}):\n\n"
    for alert_id, _, asset_type, symbol, target_price, condition, created_at in page_items:
        type_d = "Акция" if asset_type == "stock" else "Крипто"
        cond_d = "выше" if condition == "above" else "ниже"
        created_str = str(created_at).split('.')[0]
        result += f"ID: {alert_id} | {symbol} ({type_d}) | {cond_d} ${target_price:.2f} | {created_str}\n"
    return result, total_pages

"""
Форматирует список событий для вывода на указанной странице.
Возвращает отформатированный текст и общее количество страниц.
"""
def format_events(events: list, page: int = 1, items_per_page: int = 4) -> tuple[str, int]:
    if not events: return "Календарь событий пуст.", 0
    total_pages = (len(events) + items_per_page - 1) // items_per_page
    page = max(1, min(page, total_pages))
    start, end = (page - 1) * items_per_page, page * items_per_page
    page_items = events[start:end]
    result = f"📅 Календарь событий (стр. {page}/{total_pages}):\n\n"
    for _, event_date, title, desc, source, ev_type, symbol in page_items:
        type_d = EVENT_TYPES.get(ev_type, ev_type.capitalize())
        date_str = str(event_date).split(' ')[0] # Date only
        symbol_str = f" ({symbol})" if symbol else ""
        result += f"*{date_str}* - {title}{symbol_str}\n"
        result += f"  Тип: {type_d}, Источник: {source}\n"
        result += f"  Инфо: {desc}\n" + "-" * 20 + "\n"
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
    if not portfolio: return "Портфель пуст."
    result = "📈 Текущие цены портфеля:\n\n"
    for asset in portfolio:
        try:
            symbol, curr_price = asset['symbol'], asset.get('current_price')
            price_str = f"${float(curr_price):.2f}" if curr_price is not None else "Н/Д"
            result += f"{symbol}: {price_str}\n"
        except (KeyError, ValueError, TypeError) as e:
            logger.error(f"Error formatting market price for {asset}: {e}")
            result += f"{asset.get('symbol', '?')}: Ошибка\n"
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
    sections = {
        "indices": ("📊 Индексы:", market_data.get("indices", {})),
        "commodities": ("🛢 Сырье:", market_data.get("commodities", {})),
        "crypto": ("💰 Крипто:", market_data.get("crypto", {}))
    }
    for title, assets in sections.values():
        result += f"*{title}*\n"
        if not assets: result += "  Данные недоступны\n"
        for name, data in assets.items():
            price, change = data.get("price"), data.get("change_percent")
            if price is not None and change is not None:
                emoji = "📈" if change >= 0 else "📉"
                result += f"  {name}: ${price:.2f} {emoji} {change:+.2f}%\n"
            else: result += f"  {name}: Н/Д\n"
        result += "\n"
    return result.strip()

async def calculate_portfolio_summary(portfolio_data: dict) -> tuple[float, float, float]:
    total_current, total_purchase = 0.0, 0.0
    prices_ok = True
    if not portfolio_data: return 0.0, 0.0, 0.0

    tasks, details = [], []
    for assets in portfolio_data.values():
        for asset in assets:
            try:
                amount, purch_price = float(asset['amount']), float(asset['purchase_price'])
                tasks.append(fetch_asset_price_with_retry(asset['symbol'], asset['asset_type']))
                details.append({'symbol': asset['symbol'], 'amount': amount, 'purchase_price': purch_price})
            except (KeyError, ValueError, TypeError) as e:
                logger.error(f"Error processing asset {asset} in summary calc: {e}")
                prices_ok = False

    if not tasks: return 0.0, 0.0, 0.0

    logger.info(f"Requesting {len(tasks)} prices for portfolio summary...")
    current_prices = await asyncio.gather(*tasks)
    logger.info("Summary prices fetched.")

    for i, price in enumerate(current_prices):
        d = details[i]
        total_purchase += d['amount'] * d['purchase_price']
        if price is not None:
            total_current += d['amount'] * price
        else:
            logger.warning(f"Failed to get price for {d['symbol']} in summary calc.")
            prices_ok = False

    if not prices_ok: logger.warning("Some prices failed in portfolio summary calc.")
    return total_current, total_purchase, total_current - total_purchase