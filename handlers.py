from datetime import datetime

from aiogram import Router, types, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, ChatMemberUpdated
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramAPIError

from bot import bot
from loguru import logger
from events_data import get_sample_events
from states import PortfolioState, AlertState, CalendarStates
from keyboards import main_menu, asset_type_keyboard, alert_condition_keyboard, alert_actions_keyboard, \
    portfolio_actions_keyboard, confirm_alert_keyboard, confirm_remove_asset_keyboard, alerts_menu_keyboard, \
    quotes_menu_keyboard, calendar_menu_keyboard, pagination_keyboard, get_category_keyboard, get_pagination_keyboard
from database import add_to_portfolio, get_portfolio, remove_from_portfolio, add_alert, get_alerts, remove_alert, \
    get_events, load_sample_events
from api import get_stock_price, get_crypto_price, fetch_asset_price, get_stock_history, get_crypto_history, \
    get_stock_price_with_retry, get_market_data
from utils import format_portfolio, format_alerts, format_events, format_market_prices, format_market_overview, EVENT_TYPES


router = Router()
CHANNEL_ID = "@offensivepoltergeist"

# Проверяет, подписан ли пользователь на канал.
async def check_subscription(user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return member.status in ['member', 'administrator', 'creator']
    except TelegramAPIError as e:
        logger.error(f"Ошибка при проверке подписки для пользователя {user_id}: {e}")
        return False

# Обработчик команды /start с проверкой подписки.
@router.message(Command("start"))
async def cmd_start(message: Message):
    user_id = message.from_user.id
    is_subscribed = await check_subscription(user_id)

    if not is_subscribed:
        await message.answer(
            "Для использования бота необходимо подписаться на канал!\n"
            f"Пожалуйста, подпишитесь на {CHANNEL_ID} и нажмите /start снова.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Подписаться", url=f"https://t.me/{CHANNEL_ID[1:]}")]
            ])
        )
        logger.info(f"Пользователь {user_id} не подписан на канал.")
        return

    await message.answer("Добро пожаловать! Выберите действие:", reply_markup=main_menu())
    logger.info(f"Пользователь {user_id} запустил бота (подписан).")


async def check_subscription_middleware(message: Message, state: FSMContext = None):
    user_id = message.from_user.id
    is_subscribed = await check_subscription(user_id)

    if not is_subscribed:
        await message.answer(
            "Для использования этой функции необходимо подписаться на канал!\n"
            f"Пожалуйста, подпишитесь на {CHANNEL_ID}.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Подписаться", url=f"https://t.me/{CHANNEL_ID[1:]}")]
            ])
        )
        logger.info(f"Пользователь {user_id} попытался использовать функцию без подписки.")
        # Очищаем состояние, если оно передано
        if state:
            await state.clear()
        return False
    return True

@router.message(Command("help"))
async def cmd_help(message: Message):
    """Обработчик команды /help."""
    help_text = """
📋 *Список доступных команд:*

/start - Начать работу с ботом  
/help - Показать список всех команд и инструкцию  
/quotes - Котировка в реальном времени  
/set_alert - Установить оповещение о достижении целевой цены  
/alerts - Просмотреть установленные алерты
/remove_alert - Удалить установленный алерт
/add_to_portfolio - Добавить актив в портфолио  
/remove_from_portfolio - Удалить актив из портфолио  
/portfolio - Показать текущее портфолио  
/market - Показать текущие рыночные цены активов в вашем портфеле  
/cancel - Отменить последний запрос

📝 *Инструкция:*  
1. Используйте /add_to_portfolio для добавления актива в портфолио  
2. Для удаления актива используйте /remove_from_portfolio  
3. Просматривайте свое портфолио с помощью /portfolio  
4. Следите за рыночными ценами через /market  
"""
    try:
        await message.answer(help_text, parse_mode=None)
    except Exception as e:
        logger.error(f"Ошибка при отправке текста помощи: {e}")
        await message.answer(
            "Произошла ошибка при отображении помощи. "
            "Пожалуйста, используйте команды:\n"
            "/start, /help, /quote, /set_alert, /add_asset, /remove_asset, /portfolio, /market",
            parse_mode=None
        )

@router.message(Command("quotes"))
async def cmd_quotes(message: Message, state: FSMContext):
    if not await check_subscription_middleware(message, state):
        return
    await message.answer("Выберите тип актива:", reply_markup=asset_type_keyboard())
    await state.set_state(PortfolioState.selecting_asset_type)
    logger.info(f"Пользователь {message.from_user.id} запросил котировки.")

# Обработчик выбора типа актива для котировок.
@router.callback_query(PortfolioState.selecting_asset_type)
async def select_asset_type(callback: CallbackQuery, state: FSMContext):
    await state.update_data(asset_type=callback.data)
    await callback.message.answer("Введите символ актива (например, AAPL или BTC/USDT):")
    await state.set_state(PortfolioState.selecting_symbol)
    await callback.answer()

# Обработчик ввода символа для получения котировок.
@router.message(PortfolioState.selecting_symbol)
async def get_quote(message: Message, state: FSMContext):
    symbol = message.text.strip().upper()
    data = await state.get_data()
    asset_type = data["asset_type"]

    if symbol.startswith('/'):
        await message.answer(
            "Пожалуйста, введите символ актива (например, AAPL или BTC/USDT), а не команду."
        )
        await state.clear()
        logger.info(f"Пользователь {message.from_user.id} ввел команду вместо символа: {symbol}")
        return

    price = None
    if asset_type == "stock":
        if not symbol.isalpha() and not symbol.endswith(".ME"):
            await message.answer(
                "Недопустимый тикер акции. Пожалуйста, введите символ, состоящий только из букв (например, AAPL) или с суффиксом .ME (например, SBER.ME)."
            )
            await state.clear()
            logger.warning(f"Недопустимый тикер акции: {symbol}")
            return
        price = await get_stock_price(symbol)
    elif asset_type == "crypto":
        if '/' not in symbol:
            await message.answer(
                "Недопустимый тикер криптовалюты. Пожалуйста, введите символ в формате 'BTC/USDT'."
            )
            await state.clear()
            logger.warning(f"Недопустимый тикер криптовалюты: {symbol}")
            return
        price = await get_crypto_price(symbol)

    if price is not None:
        await message.answer(f"Текущая цена {symbol}: ${price:.2f}")
    else:
        await message.answer(
            "Не удалось получить цену. Возможно, превышен лимит запросов к API, "
            "символ некорректен или возникла ошибка. Пожалуйста, попробуйте позже."
        )

    await state.clear()
    logger.info(f"Пользователь {message.from_user.id} запросил цену {symbol} ({asset_type}).")

# Обработчик команды /portfolio для просмотра портфеля.
@router.message(Command("portfolio"))
async def cmd_portfolio(message: Message):
    if not await check_subscription_middleware(message):
        return
    portfolio = await get_portfolio(message.from_user.id)

    if not portfolio:
        await message.answer(
            "Ваш портфель сейчас пуст. 😔\n"
            "Используйте команду /add_to_portfolio, чтобы добавить активы в портфель."
        )
        logger.info(f"Пользователь {message.from_user.id} запросил портфель (пустой).")
        return

    portfolio_with_prices = []
    for asset in portfolio:
        try:
            symbol = asset['symbol']
            asset_type = asset['asset_type']
            amount = asset['amount']
            purchase_price = asset['purchase_price']

            current_price = await fetch_asset_price(symbol, asset_type)
            asset_data = {
                'symbol': symbol,
                'asset_type': asset_type,
                'amount': amount,
                'purchase_price': purchase_price,
                'current_price': current_price
            }
            portfolio_with_prices.append(asset_data)
        except KeyError as e:
            logger.error(f"Некорректная структура данных актива: {asset}. Отсутствует ключ: {e}")
            continue

    formatted_portfolio = format_portfolio(portfolio_with_prices)
    await message.answer(formatted_portfolio)
    logger.info(f"Пользователь {message.from_user.id} запросил портфель.")

@router.message(Command("add_to_portfolio"))
async def cmd_add_to_portfolio(message: Message, state: FSMContext):
    if not await check_subscription_middleware(message, state):
        return
    await message.answer("Выберите тип актива:", reply_markup=asset_type_keyboard())
    await state.set_state(PortfolioState.adding_asset_type)
    logger.info(f"Пользователь {message.from_user.id} начал добавление актива в портфель.")

# Обработчик выбора типа актива для добавления в портфель.
@router.callback_query(PortfolioState.adding_asset_type)
async def add_asset_type(callback: CallbackQuery, state: FSMContext):
    await state.update_data(asset_type=callback.data)
    await callback.message.answer("Введите символ актива (например, AAPL или BTC/USDT):")
    await state.set_state(PortfolioState.adding_symbol)
    await callback.answer()

@router.message(PortfolioState.selecting_symbol)
async def get_quote(message: Message, state: FSMContext):
    symbol = message.text.strip().upper()
    data = await state.get_data()
    asset_type = data["asset_type"]

    # ... (валидация символа)

    price = None
    try:
        if asset_type == "stock":
            price = await get_stock_price_with_retry(symbol)
        elif asset_type == "crypto":
            price = await get_crypto_price(symbol)
    except Exception as e:
        logger.error(f"Ошибка при получении цены {symbol}: {e}")
        await message.answer(
            "Произошла ошибка при получении цены. Возможно, превышен лимит запросов к API. "
            "Пожалуйста, попробуйте позже."
        )
        await state.clear()
        return

    if price is not None:
        await message.answer(f"Текущая цена {symbol}: ${price:.2f}")
    else:
        await message.answer(
            "Не удалось получить цену. Пожалуйста, проверьте символ и попробуйте снова."
        )
    await state.clear()

# Обработчик ввода символа актива для добавления в портфель.
@router.message(PortfolioState.adding_symbol)
async def add_symbol(message: Message, state: FSMContext):
    user_id = message.from_user.id
    symbol = message.text.strip().upper()
    data = await state.get_data()
    asset_type = data["asset_type"]

    # Проверяем, не является ли ввод командой
    if symbol.startswith('/'):
        await message.answer(
            "Пожалуйста, введите символ актива (например, AAPL или BTC/USDT), а не команду."
        )
        await state.clear()
        logger.info(f"Пользователь {user_id} ввел команду вместо символа: {symbol}")
        return

    # Валидация символа
    if asset_type == "stock":
        if not symbol.isalpha() and not symbol.endswith(".ME"):
            await message.answer(
                "Недопустимый тикер акции. Пожалуйста, введите символ, состоящий только из букв (например, AAPL) или с суффиксом .ME (например, SBER.ME)."
            )
            await state.clear()
            logger.warning(f"Недопустимый тикер акции: {symbol}")
            return
    elif asset_type == "crypto":
        if '/' not in symbol:
            await message.answer(
                "Недопустимый тикер криптовалюты. Пожалуйста, введите символ в формате 'BTC/USDT'."
            )
            await state.clear()
            logger.warning(f"Недопустимый тикер криптовалюты: {symbol}")
            return

    # Проверка существования актива через API
    price = await fetch_asset_price(symbol, asset_type)
    if price is None:
        await message.answer(
            "Не удалось проверить существование актива. Возможно, символ некорректен или возникла ошибка. "
            "Пожалуйста, проверьте символ и попробуйте снова."
        )
        await state.clear()
        logger.warning(f"Не удалось проверить существование актива: {symbol} ({asset_type})")
        return

    await state.update_data(symbol=symbol)
    await message.answer("Введите количество актива:")
    await state.set_state(PortfolioState.adding_amount)
    logger.info(f"Пользователь {user_id} ввел символ {symbol} для добавления в портфель.")

# Обработчик ввода количества актива.
@router.message(PortfolioState.adding_amount)
async def add_amount(message: Message, state: FSMContext):
    user_id = message.from_user.id
    try:
        amount = float(message.text)
        if amount <= 0:
            await message.answer("Количество актива должно быть положительным числом.")
            return
        await state.update_data(amount=amount)
        await message.answer("Введите цену покупки:")
        await state.set_state(PortfolioState.adding_price)
    except ValueError:
        await message.answer("Пожалуйста, введите число.")
    logger.info(f"Пользователь {user_id} ввел количество актива: {message.text}")

# Обработчик ввода цены покупки.
@router.message(PortfolioState.adding_price)
async def add_price(message: Message, state: FSMContext):
    user_id = message.from_user.id
    try:
        price = float(message.text)
        if price <= 0:
            await message.answer("Цена покупки должна быть положительным числом.")
            return
        data = await state.get_data()
        await add_to_portfolio(
            user_id=user_id,
            asset_type=data["asset_type"],
            symbol=data["symbol"],
            amount=data["amount"],
            purchase_price=price
        )
        await message.answer("Актив добавлен в портфель!", reply_markup=main_menu())
        await state.clear()
        logger.info(f"Пользователь {user_id} добавил актив в портфель: {data['symbol']} ({data['asset_type']})")
    except ValueError:
        await message.answer("Пожалуйста, введите число.")
        logger.warning(f"Пользователь {user_id} ввел некорректную цену: {message.text}")
    except Exception as e:
        logger.error(f"Ошибка при добавлении актива для пользователя {user_id}: {e}")
        await message.answer(
            "Произошла ошибка при добавлении актива. Пожалуйста, попробуйте позже.",
            reply_markup=main_menu()
        )
        await state.clear()

@router.message(Command("set_alert"))
async def cmd_set_alert(message: Message, state: FSMContext):
    if not await check_subscription_middleware(message, state):
        return
    await message.answer("Выберите тип актива:", reply_markup=asset_type_keyboard())
    await state.set_state(AlertState.selecting_asset_type)
    logger.info(f"Пользователь {message.from_user.id} начал настройку алерта.")

# Обработчик выбора типа актива для алерта.
@router.callback_query(AlertState.selecting_asset_type)
async def select_alert_asset_type(callback: CallbackQuery, state: FSMContext):
    await state.update_data(asset_type=callback.data)
    await callback.message.answer("Введите символ актива (например, AAPL или BTC/USDT):")
    await state.set_state(AlertState.selecting_symbol)
    await callback.answer()

# Обработчик ввода символа для алерта.
@router.message(AlertState.selecting_symbol)
async def select_alert_symbol(message: Message, state: FSMContext):
    user_id = message.from_user.id
    symbol = message.text.strip().upper()
    data = await state.get_data()
    asset_type = data["asset_type"]

    if symbol.startswith('/'):
        await message.answer(
            "Пожалуйста, введите символ актива (например, AAPL или BTC/USDT), а не команду.",
            reply_markup=main_menu()
        )
        await state.clear()
        logger.info(f"Пользователь {user_id} ввел команду вместо символа: {symbol}")
        return

    if asset_type == "stock":
        if not symbol.isalpha() and not symbol.endswith(".ME"):
            await message.answer(
                "Недопустимый тикер акции. Пожалуйста, введите символ, состоящий только из букв (например, AAPL) или с суффиксом .ME (например, SBER.ME).",
                reply_markup=main_menu()
            )
            await state.clear()
            logger.warning(f"Недопустимый тикер акции: {symbol}")
            return
    elif asset_type == "crypto":
        if '/' not in symbol:
            await message.answer(
                "Недопустимый тикер криптовалюты. Пожалуйста, введите символ в формате 'BTC/USDT'.",
                reply_markup=main_menu()
            )
            await state.clear()
            logger.warning(f"Недопустимый тикер криптовалюты: {symbol}")
            return

    price = await fetch_asset_price(symbol, asset_type)
    if price is None:
        await message.answer(
            "Не удалось проверить существование актива. Возможно, символ некорректен или возникла ошибка. "
            "Пожалуйста, проверьте символ и попробуйте снова.",
            reply_markup=main_menu()
        )
        await state.clear()
        logger.warning(f"Не удалось проверить существование актива: {symbol} ({asset_type})")
        return

    await state.update_data(symbol=symbol)
    await message.answer("Введите целевую цену для алерта:")
    await state.set_state(AlertState.selecting_price)
    logger.info(f"Пользователь {user_id} ввел символ {symbol} для алерта.")

# Обработчик ввода целевой цены для алерта.
@router.message(AlertState.selecting_price)
async def select_alert_price(message: Message, state: FSMContext):
    user_id = message.from_user.id
    try:
        target_price = float(message.text)
        if target_price <= 0:
            await message.answer("Целевая цена должна быть положительным числом.", reply_markup=main_menu())
            return
        await state.update_data(target_price=target_price)
        await message.answer("Выберите условие алерта:", reply_markup=alert_condition_keyboard())
        await state.set_state(AlertState.selecting_condition)
    except ValueError:
        await message.answer("Пожалуйста, введите число.", reply_markup=main_menu())
    logger.info(f"Пользователь {user_id} ввел целевую цену: {message.text}")

# Обработчик выбора условия алерта (above или below).
@router.callback_query(AlertState.selecting_condition, F.data.in_({"above", "below"}))
async def select_alert_condition(callback: CallbackQuery, state: FSMContext):
    condition = callback.data
    data = await state.get_data()
    symbol = data["symbol"]
    target_price = data["target_price"]
    await state.update_data(condition=condition)
    await callback.message.answer(
        f"Подтвердите алерт:\n"
        f"Актив: {symbol}\n"
        f"Целевая цена: ${target_price:.2f}\n"
        f"Условие: {'выше' if condition == 'above' else 'ниже'}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Подтвердить", callback_data="confirm_alert"),
                InlineKeyboardButton(text="🚫 Отмена", callback_data="cancel")
            ]
        ])
    )
    await callback.answer()
    logger.info(f"Пользователь {callback.from_user.id} выбрал условие алерта: {condition}")

@router.message(Command("calendar"))
async def show_calendar(message: Message, state: FSMContext):
    if not await check_subscription_middleware(message, state):
        return
    await message.answer("Выберите категорию событий:", reply_markup=get_category_keyboard())
    await state.set_state(CalendarStates.viewing_calendar)
    logger.info(f"Пользователь {message.from_user.id} запросил календарь событий.")

# Обработчик команды /remove_from_portfolio для удаления актива из портфеля.
@router.message(Command("remove_from_portfolio"))
async def cmd_remove_from_portfolio(message: Message, state: FSMContext):
    user_id = message.from_user.id
    portfolio = await get_portfolio(user_id)

    if not portfolio:
        await message.answer(
            "Ваш портфель сейчас пуст. 😔\n"
            "Используйте команду /add_to_portfolio, чтобы добавить активы в портфель."
        )
        logger.info(f"Пользователь {user_id} запросил удаление актива (портфель пуст).")
        return

    formatted_portfolio = format_portfolio(portfolio)
    await message.answer(
        f"Ваш портфель:\n{formatted_portfolio}\n"
        "Введите символ актива, который хотите удалить (например, AAPL или BTC/USDT):"
    )
    await state.set_state(PortfolioState.removing_symbol)
    logger.info(f"Пользователь {user_id} начал удаление актива из портфеля.")

# Обработчик ввода символа актива для удаления из портфеля.
@router.message(PortfolioState.removing_symbol)
async def remove_symbol_handler(message: Message, state: FSMContext):
    user_id = message.from_user.id
    symbol = message.text.strip().upper()

    if symbol.startswith('/'):
        await message.answer(
            "Пожалуйста, введите символ актива (например, AAPL или BTC/USDT), а не команду."
        )
        await state.clear()
        logger.info(f"Пользователь {user_id} ввел команду вместо символа: {symbol}")
        return

    try:
        portfolio = await get_portfolio(user_id)
        asset_exists = any(asset['symbol'] == symbol for asset in portfolio)

        if not asset_exists:
            await message.answer(
                f"Актив {symbol} не найден в вашем портфеле. "
                "Пожалуйста, проверьте символ и попробуйте снова."
            )
            await state.clear()
            logger.warning(f"Актив {symbol} не найден в портфеле пользователя {user_id}")
            return

        await remove_from_portfolio(user_id, symbol)
        await message.answer(f"Актив {symbol} успешно удален из портфеля.")
        logger.info(f"Пользователь {user_id} удалил актив {symbol} из портфеля.")
    except Exception as e:
        await message.answer("Произошла ошибка при удалении актива. Пожалуйста, попробуйте снова.")
        logger.error(f"Ошибка при удалении актива {symbol} для пользователя {user_id}: {e}")
    finally:
        await state.clear()

# Обработчик команды /market для просмотра текущих рыночных цен.
@router.message(Command("market"))
async def cmd_market(message: Message):
    if not await check_subscription_middleware(message):
        return
    user_id = message.from_user.id
    portfolio = await get_portfolio(user_id)

    if not portfolio:
        await message.answer(
            "Ваш портфель сейчас пуст. 😔\n"
            "Используйте команду /add_to_portfolio, чтобы добавить активы в портфель."
        )
        logger.info(f"Пользователь {user_id} запросил рыночные цены (портфель пуст).")
        return

    portfolio_with_prices = []
    for asset in portfolio:
        try:
            symbol = asset['symbol']
            asset_type = asset['asset_type']
            current_price = await fetch_asset_price(symbol, asset_type)
            asset_data = {
                'symbol': symbol,
                'asset_type': asset_type,
                'current_price': current_price
            }
            portfolio_with_prices.append(asset_data)
        except KeyError as e:
            logger.error(f"Некорректная структура данных актива: {asset}. Отсутствует ключ: {e}")
            continue

    formatted_prices = format_market_prices(portfolio_with_prices)
    await message.answer(formatted_prices)
    logger.info(f"Пользователь {user_id} запросил рыночные цены.")

# Регистрация всех хэндлеров.
def register_handlers(dp: Router):
    dp.include_router(router)

@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is None:
        await message.answer("Нет активных операций для отмены.")
        return
    await state.clear()
    await message.answer("Операция отменена.")
    logger.info(f"Пользователь {message.from_user.id} отменил операцию.")

# Обработчик команды /alerts для просмотра установленных алертов.
@router.message(Command("alerts"))
async def cmd_alerts(message: Message):
    if not await check_subscription_middleware(message):
        return
    user_id = message.from_user.id
    alerts = await get_alerts(user_id)

    if not alerts:
        await message.answer(
            "У вас нет установленных алертов. 😔\n"
            "Используйте команду /set_alert, чтобы установить алерт."
        )
        logger.info(f"Пользователь {user_id} запросил алерты (список пуст).")
        return

    formatted_alerts = format_alerts(alerts)
    await message.answer(formatted_alerts)
    logger.info(f"Пользователь {user_id} запросил список алертов.")

# Обработчик команды /remove_alert для удаления алерта.
@router.message(Command("remove_alert"))
async def cmd_remove_alert(message: Message, state: FSMContext):
    user_id = message.from_user.id
    alerts = await get_alerts(user_id)

    if not alerts:
        await message.answer(
            "У вас нет установленных алертов. 😔\n"
            "Используйте команду /set_alert, чтобы установить алерт."
        )
        logger.info(f"Пользователь {user_id} запросил удаление алерта (список пуст).")
        return

    await message.answer(
        "Введите ID алерта, который хотите удалить. Список ваших алертов можно посмотреть с помощью /alerts."
    )
    await state.set_state(AlertState.removing_alert)

# Обработчик ввода ID алерта для удаления.
@router.message(AlertState.removing_alert)
async def remove_alert_handler(message: Message, state: FSMContext):
    user_id = message.from_user.id
    try:
        alert_id = int(message.text)
        alerts = await get_alerts(user_id)
        alert_ids = [alert[0] for alert in alerts]  # Получаем список ID алертов

        if alert_id not in alert_ids:
            await message.answer(
                "Неверный ID алерта. Пожалуйста, проверьте ID с помощью команды /alerts и попробуйте снова."
            )
            await state.clear()
            return

        await remove_alert(alert_id, user_id)
        await message.answer(f"Алерт с ID {alert_id} успешно удален.")
        logger.info(f"Пользователь {user_id} удалил алерт с ID {alert_id}.")
    except ValueError:
        await message.answer("Пожалуйста, введите числовой ID алерта.")
    except Exception as e:
        await message.answer("Произошла ошибка при удалении алерта. Пожалуйста, попробуйте снова.")
        logger.error(f"Ошибка при удалении алерта для пользователя {user_id}: {e}")
    finally:
        await state.clear()

# Обработчик кнопки 'Котировки' в главном меню.
@router.callback_query(F.data == "quotes_menu")
async def handle_quotes_menu(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("Выберите действие с котировками:", reply_markup=quotes_menu_keyboard())
    await callback.answer()
    logger.info(f"Пользователь {callback.from_user.id} открыл меню котировок.")

# Обработчик кнопки 'Запросить котировку'.
@router.callback_query(F.data == "quotes")
async def handle_quotes(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("Выберите тип актива:", reply_markup=asset_type_keyboard())
    await state.set_state(PortfolioState.selecting_asset_type)
    await callback.answer()
    logger.info(f"Пользователь {callback.from_user.id} запросил котировки.")

# Обработчик кнопки 'Портфель'.
@router.callback_query(F.data == "portfolio")
async def handle_portfolio(callback: CallbackQuery, state: FSMContext):
    portfolio = await get_portfolio(callback.from_user.id)
    if not portfolio:
        await callback.message.answer(
            "Ваш портфель сейчас пуст. 😔\n"
            "Используйте кнопку 'Добавить актив', чтобы добавить активы в портфель.",
            reply_markup=main_menu()
        )
        logger.info(f"Пользователь {callback.from_user.id} запросил портфель (пустой).")
        return

    portfolio_with_prices = []
    for asset in portfolio:
        try:
            symbol = asset['symbol']
            asset_type = asset['asset_type']
            amount = asset['amount']
            purchase_price = asset['purchase_price']
            current_price = await fetch_asset_price(symbol, asset_type)
            asset_data = {
                'symbol': symbol,
                'asset_type': asset_type,
                'amount': amount,
                'purchase_price': purchase_price,
                'current_price': current_price
            }
            portfolio_with_prices.append(asset_data)
        except KeyError as e:
            logger.error(f"Некорректная структура данных актива: {asset}. Отсутствует ключ: {e}")
            continue

    formatted_portfolio, total_pages = format_portfolio(portfolio_with_prices, page=1)
    await callback.message.answer(
        formatted_portfolio,
        reply_markup=portfolio_actions_keyboard(current_page=1, total_pages=total_pages)
    )
    await callback.answer()
    logger.info(f"Пользователь {callback.from_user.id} запросил портфель (страница 1).")

# Обработчик кнопки 'Добавить актив'.
@router.callback_query(F.data == "add_to_portfolio")
async def handle_add_to_portfolio(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("Выберите тип актива:", reply_markup=asset_type_keyboard())
    await state.set_state(PortfolioState.adding_asset_type)
    await callback.answer()
    logger.info(f"Пользователь {callback.from_user.id} начал добавление актива в портфель.")

# Обработчик кнопки 'Установить алерт'.
@router.callback_query(F.data == "set_alert")
async def handle_set_alert(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("Выберите тип актива:", reply_markup=asset_type_keyboard())
    await state.set_state(AlertState.selecting_asset_type)
    await callback.answer()
    logger.info(f"Пользователь {callback.from_user.id} начал установку алерта.")

# Обработчик кнопки 'Календарь' в главном меню.
@router.callback_query(F.data == "calendar")
async def handle_calendar_menu(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    try:
        all_events = get_sample_events()  # Получаем все события
        if not all_events:
            await callback.message.answer(
                "Событий не найдено. Попробуйте обновить календарь позже.",
                reply_markup=calendar_menu_keyboard()
            )
            logger.info(f"Пользователь {user_id} запросил календарь событий (пусто).")
            await callback.answer()
            return

        formatted_events, total_pages = format_events(all_events, page=1)
        await callback.message.answer(
            formatted_events,
            reply_markup=calendar_menu_keyboard()
        )
        await state.update_data(calendar_filter="all", current_page=1, total_pages=total_pages)
        await callback.answer()
        logger.info(f"Пользователь {user_id} открыл меню календаря (страница 1, событий: {len(all_events)}).")
    except Exception as e:
        logger.error(f"Ошибка при открытии меню календаря: {e}")
        await callback.message.answer(
            "Произошла ошибка при открытии календаря. Пожалуйста, попробуйте снова.",
            reply_markup=calendar_menu_keyboard()
        )
        await callback.answer()

# Обработчик кнопки 'Помощь'.
@router.callback_query(F.data == "help")
async def handle_help(callback: CallbackQuery):
    help_text = """
📋 *Список доступных действий:*

- 📈 Котировки: Получить текущую цену актива
- 💼 Портфель: Просмотреть текущее состояние портфеля
- ➕ Добавить актив: Добавить актив в портфель
- 🔔 Установить алерт: Установить оповещение о цене
- 📅 Календарь: Просмотреть календарь событий
- 📊 Рынок: Просмотреть текущие рыночные цены активов
- 🚫 Отмена: Отменить текущее действие

📝 *Инструкция:*
1. Используйте кнопки для навигации.
2. Следуйте подсказкам бота для ввода данных.
3. Для отмены действия нажмите 'Отмена'.
"""
    await callback.message.answer(help_text, reply_markup=main_menu())
    await callback.answer()
    logger.info(f"Пользователь {callback.from_user.id} запросил помощь.")

# Обработчик кнопки 'Рынок' для показа обзора рынка.
@router.callback_query(F.data == "market")
async def handle_market_overview(callback: CallbackQuery):
    market_data = await get_market_data()
    formatted_market = format_market_overview(market_data)
    await callback.message.answer(formatted_market, reply_markup=main_menu())
    await callback.answer()
    logger.info(f"Пользователь {callback.from_user.id} запросил обзор рынка.")

# Обработчик кнопки 'Удалить актив'.
@router.callback_query(F.data == "remove_asset")
async def handle_remove_asset_prompt(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите символ актива, который хотите удалить (например, AAPL или BTC/USDT):")
    await state.set_state(PortfolioState.removing_symbol)
    await callback.answer()
    logger.info(f"Пользователь {callback.from_user.id} начал удаление актива.")

# Обработчик кнопки 'Алерты'.
@router.callback_query(F.data == "alerts")
async def handle_alerts(callback: CallbackQuery):
    alerts = await get_alerts(callback.from_user.id)
    if not alerts:
        await callback.message.answer(
            "У вас нет установленных алертов. 😔\n"
            "Используйте кнопку 'Установить алерт', чтобы добавить алерт.",
            reply_markup=main_menu()
        )
        logger.info(f"Пользователь {callback.from_user.id} запросил алерты (пусто).")
        return

    formatted_alerts = format_alerts(alerts)
    for alert in alerts:
        alert_id = alert[0]
        await callback.message.answer(
            formatted_alerts,
            reply_markup=alert_actions_keyboard(alert_id)
        )
    await callback.answer()
    logger.info(f"Пользователь {callback.from_user.id} запросил алерты.")

# Обработчик кнопки 'Удалить алерт'.
@router.callback_query(F.data == "remove_alert")
async def handle_remove_alert_prompt(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите ID алерта, который хотите удалить:")
    await state.set_state(AlertState.removing_alert)
    await callback.answer()
    logger.info(f"Пользователь {callback.from_user.id} начал удаление алерта.")

# Обработчик подтверждения установки алерта.
@router.callback_query(F.data == "confirm_alert")
async def confirm_alert(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    data = await state.get_data()
    symbol = data.get("symbol")
    target_price = data.get("target_price")
    condition = data.get("condition")
    asset_type = data.get("asset_type")

    if not all([symbol, target_price, condition, asset_type]):
        await callback.message.answer(
            "Ошибка: не удалось установить алерт. Пожалуйста, начните заново.",
            reply_markup=main_menu()
        )
        await state.clear()
        await callback.answer()
        logger.error(f"Пользователь {user_id} попытался подтвердить алерт с неполными данными: {data}")
        return

    await add_alert(user_id, asset_type, symbol, target_price, condition)
    await callback.message.answer(f"Алерт установлен для {symbol}!", reply_markup=main_menu())
    await state.clear()
    await callback.answer()
    logger.info(f"Пользователь {user_id} установил алерт для {symbol}.")

# Обработчик кнопки 'Отмена'.
@router.callback_query(F.data == "cancel")
async def handle_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.answer("Действие отменено.", reply_markup=main_menu())
    await callback.answer()
    logger.info(f"Пользователь {callback.from_user.id} отменил действие.")

# Обработчик ввода символа для удаления актива.
@router.message(PortfolioState.removing_symbol)
async def handle_remove_asset_symbol(message: Message, state: FSMContext):
    user_id = message.from_user.id
    symbol = message.text.strip().upper()

    if symbol.startswith('/'):
        await message.answer(
            "Пожалуйста, введите символ актива (например, AAPL или BTC/USDT), а не команду.",
            reply_markup=main_menu()
        )
        await state.clear()
        logger.info(f"Пользователь {user_id} ввел команду вместо символа: {symbol}")
        return

    portfolio = await get_portfolio(user_id)
    if not any(asset['symbol'] == symbol for asset in portfolio):
        await message.answer(
            f"Актив {symbol} не найден в вашем портфеле.",
            reply_markup=main_menu()
        )
        await state.clear()
        logger.warning(f"Актив {symbol} не найден в портфеле пользователя {user_id}")
        return

    await state.update_data(symbol=symbol)
    await message.answer(
        f"Подтвердите удаление актива {symbol} из портфеля:",
        reply_markup=confirm_remove_asset_keyboard(symbol)
    )
    logger.info(f"Пользователь {user_id} запросил подтверждение удаления актива {symbol}")

# Обработчик подтверждения удаления актива.
@router.callback_query(F.data.startswith("confirm_remove_"))
async def confirm_remove_asset(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    symbol = callback.data.replace("confirm_remove_", "")
    await remove_from_portfolio(user_id, symbol)
    await callback.message.answer(f"Актив {symbol} удален из портфеля.", reply_markup=main_menu())
    await state.clear()
    await callback.answer()
    logger.info(f"Пользователь {user_id} удалил актив {symbol} из портфеля.")


@router.callback_query(F.data.in_({"quotes", "portfolio", "add_to_portfolio", "set_alert", "calendar", "market", "alerts_menu"}))
async def handle_menu_command(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    is_subscribed = await check_subscription(user_id)

    if not is_subscribed:
        await callback.message.answer(
            "Для использования этой функции необходимо подписаться на канал!\n"
            f"Пожалуйста, подпишитесь на {CHANNEL_ID}.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Подписаться", url=f"https://t.me/{CHANNEL_ID[1:]}")]
            ])
        )
        await callback.answer()
        logger.info(f"Пользователь {user_id} попытался использовать callback без подписки.")
        return

# Обработчик кнопки 'Алерты' в главном меню.
@router.callback_query(F.data == "alerts_menu")
async def handle_alerts_menu(callback: CallbackQuery):
    await callback.message.answer("Выберите действие с алертами:", reply_markup=alerts_menu_keyboard())
    await callback.answer()
    logger.info(f"Пользователь {callback.from_user.id} открыл меню алертов.")

# Обработчик кнопки 'Текущие алерты'.
@router.callback_query(F.data == "current_alerts")
async def handle_current_alerts(callback: CallbackQuery, state: FSMContext):
    alerts = await get_alerts(callback.from_user.id)
    if not alerts:
        await callback.message.answer(
            "У вас нет установленных алертов. 😔\n"
            "Используйте кнопку 'Добавить алерт', чтобы добавить алерт.",
            reply_markup=alerts_menu_keyboard()
        )
        logger.info(f"Пользователь {callback.from_user.id} запросил текущие алерты (пусто).")
        return

    formatted_alerts, total_pages = format_alerts(alerts, page=1)
    await callback.message.answer(
        formatted_alerts,
        reply_markup=alerts_menu_keyboard(current_page=1, total_pages=total_pages)
    )
    await callback.answer()
    logger.info(f"Пользователь {callback.from_user.id} запросил текущие алерты (страница 1).")

# Обработчик ввода ID алерта для удаления.
@router.message(AlertState.removing_alert)
async def handle_remove_alert_id(message: Message, state: FSMContext):
    user_id = message.from_user.id
    try:
        alert_id = int(message.text)
        alerts = await get_alerts(user_id)
        if not any(alert[0] == alert_id for alert in alerts):
            await message.answer(
                f"Алерт ID {alert_id} не найден.",
                reply_markup=alerts_menu_keyboard()
            )
            await state.clear()
            logger.warning(f"Алерт ID {alert_id} не найден для пользователя {user_id}")
            return

        await remove_alert(alert_id)
        await message.answer(f"Алерт ID {alert_id} удален.", reply_markup=alerts_menu_keyboard())
        await state.clear()
        logger.info(f"Пользователь {user_id} удалил алерт ID {alert_id}")
    except ValueError:
        await message.answer("Пожалуйста, введите числовой ID алерта.", reply_markup=alerts_menu_keyboard())
        logger.warning(f"Пользователь {user_id} ввел некорректный ID алерта: {message.text}")

# Обработчик кнопки 'Назад' в меню алертов.
@router.callback_query(F.data == "main_menu")
async def handle_main_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.answer("Главное меню:", reply_markup=main_menu())
    await callback.answer()
    logger.info(f"Пользователь {callback.from_user.id} вернулся в главное меню.")

# Обработчик кнопки 'Цены портфеля'.
@router.callback_query(F.data == "portfolio_prices")
async def handle_portfolio_prices(callback: CallbackQuery):
    portfolio = await get_portfolio(callback.from_user.id)
    if not portfolio:
        await callback.message.answer(
            "Ваш портфель сейчас пуст. 😔\n"
            "Используйте кнопку 'Добавить актив', чтобы добавить активы в портфель.",
            reply_markup=quotes_menu_keyboard()
        )
        logger.info(f"Пользователь {callback.from_user.id} запросил цены портфеля (пустой).")
        return

    portfolio_with_prices = []
    for asset in portfolio:
        try:
            symbol = asset['symbol']
            asset_type = asset['asset_type']
            current_price = await fetch_asset_price(symbol, asset_type)
            asset_data = {
                'symbol': symbol,
                'asset_type': asset_type,
                'current_price': current_price
            }
            portfolio_with_prices.append(asset_data)
        except KeyError as e:
            logger.error(f"Некорректная структура данных актива: {asset}. Отсутствует ключ: {e}")
            continue

    formatted_market = format_market_prices(portfolio_with_prices)
    await callback.message.answer(formatted_market, reply_markup=quotes_menu_keyboard())
    await callback.answer()
    logger.info(f"Пользователь {callback.from_user.id} запросил цены портфеля.")

# Обработчик навигации по страницам портфеля.
@router.callback_query(F.data.startswith("portfolio_page_"))
async def handle_portfolio_page(callback: CallbackQuery, state: FSMContext):
    page = int(callback.data.replace("portfolio_page_", ""))
    portfolio = await get_portfolio(callback.from_user.id)
    if not portfolio:
        await callback.message.answer(
            "Ваш портфель сейчас пуст. 😔\n"
            "Используйте кнопку 'Добавить актив', чтобы добавить активы в портфель.",
            reply_markup=main_menu()
        )
        logger.info(f"Пользователь {callback.from_user.id} запросил портфель (пустой).")
        return

    portfolio_with_prices = []
    for asset in portfolio:
        try:
            symbol = asset['symbol']
            asset_type = asset['asset_type']
            amount = asset['amount']
            purchase_price = asset['purchase_price']
            current_price = await fetch_asset_price(symbol, asset_type)
            asset_data = {
                'symbol': symbol,
                'asset_type': asset_type,
                'amount': amount,
                'purchase_price': purchase_price,
                'current_price': current_price
            }
            portfolio_with_prices.append(asset_data)
        except KeyError as e:
            logger.error(f"Некорректная структура данных актива: {asset}. Отсутствует ключ: {e}")
            continue

    formatted_portfolio, total_pages = format_portfolio(portfolio_with_prices, page=page)
    await callback.message.edit_text(
        formatted_portfolio,
        reply_markup=portfolio_actions_keyboard(current_page=page, total_pages=total_pages)
    )
    await callback.answer()
    logger.info(f"Пользователь {callback.from_user.id} перешел на страницу портфеля {page}.")

# Обработчик навигации по страницам алертов.
@router.callback_query(F.data.startswith("alerts_page_"))
async def handle_alerts_page(callback: CallbackQuery, state: FSMContext):
    page = int(callback.data.replace("alerts_page_", ""))
    alerts = await get_alerts(callback.from_user.id)
    if not alerts:
        await callback.message.answer(
            "У вас нет установленных алертов. 😔\n"
            "Используйте кнопку 'Добавить алерт', чтобы добавить алерт.",
            reply_markup=alerts_menu_keyboard()
        )
        logger.info(f"Пользователь {callback.from_user.id} запросил текущие алерты (пусто).")
        return

    formatted_alerts, total_pages = format_alerts(alerts, page=page)
    await callback.message.edit_text(
        formatted_alerts,
        reply_markup=alerts_menu_keyboard(current_page=page, total_pages=total_pages)
    )
    await callback.answer()
    logger.info(f"Пользователь {callback.from_user.id} перешел на страницу алертов {page}.")

# Обработчик фильтрации событий.
@router.callback_query(F.data.startswith("calendar_"))
async def handle_calendar_filter(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    current_message_text = callback.message.text
    current_reply_markup = callback.message.reply_markup

    try:
        data = callback.data

        # Проверяем, является ли callback пагинацией
        if "page_" in data:
            await handle_pagination(callback, state)
            return

        filter_type = data.replace("calendar_", "")
        await state.update_data(calendar_filter=filter_type, current_page=1)

        portfolio_only = filter_type == "portfolio"
        event_type = None

        if filter_type == "macro":
            event_type = "macro"
        elif filter_type == "dividends":
            event_type = "dividends"
        elif filter_type == "earnings":
            event_type = "earnings"
        elif filter_type == "press":
            event_type = "press"
        elif filter_type == "all":
            event_type = None
            portfolio_only = False

        events = await get_events(user_id=user_id, event_type=event_type, portfolio_only=portfolio_only)
        logger.info(f"Получено событий из БД: {len(events)} для фильтра {filter_type}")

        if not events:
            all_events = get_sample_events()
            crypto_symbols = {"BTC", "ETH", "BNB", "XRP", "ADA", "SOL", "DOGE", "DOT", "LTC", "LINK"}
            investment_symbols = {"AAPL", "MSFT", "AMZN", "GOOGL", "TSLA", "NVDA", "JPM", "GS", "V", "MA"}

            if filter_type == "portfolio":
                portfolio = await get_portfolio(user_id)
                portfolio_symbols = {asset['symbol'] for asset in portfolio}
                events = [e for e in all_events if e['symbol'] in portfolio_symbols]
            elif filter_type == "macro":
                events = [e for e in all_events if e['type'] == "macro"]
            elif filter_type == "dividends":
                events = [e for e in all_events if e['type'] == "dividends"]
            elif filter_type == "earnings":
                events = [e for e in all_events if e['type'] == "earnings"]
            elif filter_type == "press":
                events = [e for e in all_events if e['type'] == "press"]
            elif filter_type == "all":
                events = all_events
            logger.info(f"Получено sample событий: {len(events)} для фильтра {filter_type}")

        if not events:
            new_text = f"Событий не найдено для фильтра: {filter_type}"
            new_markup = calendar_menu_keyboard()

            if current_message_text != new_text or str(current_reply_markup) != str(new_markup):
                await callback.message.edit_text(
                    new_text,
                    reply_markup=new_markup
                )
            await callback.answer()
            logger.info(f"Пользователь {user_id} запросил события (пусто, фильтр: {filter_type}).")
            return

        events = sorted(
            events,
            key=lambda x: datetime.strptime(x['event_date'], "%Y-%m-%d %H:%M:%S")
        )
        await state.update_data(filtered_events=events)

        formatted_events, total_pages = format_events(events, page=1)
        new_markup = pagination_keyboard(current_page=1, total_pages=total_pages, prefix="calendar")

        if current_message_text != formatted_events or str(current_reply_markup) != str(new_markup):
            await callback.message.edit_text(
                formatted_events,
                reply_markup=new_markup
            )
        await state.update_data(total_pages=total_pages)
        await callback.answer()
        logger.info(
            f"Пользователь {user_id} запросил события (фильтр: {filter_type}, страница 1, событий: {len(events)}).")
    except Exception as e:
        logger.error(f"Ошибка при фильтрации событий: {e}")
        error_text = "Произошла ошибка при фильтрации событий."
        if current_message_text != error_text:
            await callback.message.edit_text(
                error_text,
                reply_markup=calendar_menu_keyboard()
            )
        await callback.answer()

# Обработчик навигации по страницам календаря.
@router.callback_query(F.data.startswith("calendar_page_"))
async def handle_calendar_page(callback: CallbackQuery, state: FSMContext):
    page = int(callback.data.replace("calendar_page_", ""))
    user_id = callback.from_user.id
    data = await state.get_data()
    filter_type = data.get("calendar_filter", "all")
    portfolio_only = filter_type == "portfolio"
    event_type = None

    if filter_type == "macro":
        event_type = "macro"
    elif filter_type == "dividends":
        event_type = "dividends"
    elif filter_type == "earnings":
        event_type = "earnings"
    elif filter_type == "press":
        event_type = "press"
    elif filter_type == "all":
        event_type = None
        portfolio_only = False

    events = await get_events(user_id=user_id, event_type=event_type, portfolio_only=portfolio_only)
    if not events:
        await callback.message.answer(
            "Событий не найдено.",
            reply_markup=calendar_menu_keyboard()
        )
        logger.info(f"Пользователь {user_id} запросил события (пусто, фильтр: {filter_type}).")
        return

    formatted_events, total_pages = format_events(events, page=page)
    await callback.message.edit_text(
        formatted_events,
        reply_markup=pagination_keyboard(current_page=page, total_pages=total_pages, prefix="calendar")
    )
    await callback.answer()
    logger.info(f"Пользователь {user_id} перешел на страницу календаря {page} (фильтр: {filter_type}).")

# Загружает пример событий в базу данных.
@router.message(Command("load_sample_events"))
async def load_sample_events_handler(message: types.Message):
    try:
        await load_sample_events()
        await message.answer("Пример событий успешно загружен. Используйте /calendar для просмотра.")
    except Exception as e:
        logger.error(f"Ошибка при загрузке примеров событий: {e}")
        await message.answer("Произошла ошибка при загрузке примеров событий.")

# Показывает выбор категории событий.
@router.message(Command("calendar"))
async def show_calendar(message: Message, state: FSMContext):
    user_id = message.from_user.id
    try:
        keyboard = get_category_keyboard()
        await message.answer("Выберите категорию событий:", reply_markup=keyboard)
        await state.set_state(CalendarStates.viewing_calendar)
        logger.info(f"Пользователь {user_id} запросил календарь событий.")
    except Exception as e:
        logger.error(f"Ошибка при отображении календаря: {e}")
        await message.answer("Произошла ошибка при отображении календаря.")

# Обработчик выбора категории с корректной сортировкой по дате.
@router.callback_query(lambda c: c.data.startswith("calendar_category_"))
async def handle_category_selection(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    try:
        category = callback.data.split("_")[-1]
        await state.update_data(category=category, current_page=1)

        all_events = get_sample_events()

        crypto_symbols = {"BTC", "ETH", "BNB", "XRP", "ADA", "SOL", "DOGE", "DOT", "LTC", "LINK"}
        investment_symbols = {"AAPL", "MSFT", "AMZN", "GOOGL", "TSLA", "NVDA", "JPM", "GS", "V", "MA"}

        if category == "crypto":
            filtered_events = [e for e in all_events if
                               e['symbol'] in crypto_symbols or
                               (e['symbol'] == "-" and e['type'] in ["macro", "press"])]
        elif category == "investments":
            filtered_events = [e for e in all_events if
                               e['symbol'] in investment_symbols or
                               (e['symbol'] == "-" and e['type'] in ["macro", "earnings"])]
        else:
            filtered_events = all_events

        filtered_events = sorted(
            filtered_events,
            key=lambda x: datetime.strptime(x['event_date'], "%Y-%m-%d %H:%M:%S")
        )

        if not filtered_events:
            await callback.message.edit_text(
                "Событий в выбранной категории нет.",
                reply_markup=calendar_menu_keyboard()
            )
            await callback.answer()
            logger.info(f"Пользователь {user_id} запросил события (пусто, категория: {category}).")
            return

        await state.update_data(filtered_events=filtered_events)

        text, total_pages = format_events(filtered_events, page=1)
        keyboard = get_pagination_keyboard(1, total_pages, category)

        category_display = {
            "crypto": "Криптовалюты",
            "investments": "Инвестиции",
            "all": "Все события"
        }.get(category, "Все события")

        await callback.message.edit_text(
            f"📅 Календарь событий ({category_display}):\n\n{text}",
            reply_markup=keyboard
        )
        await state.update_data(total_pages=total_pages)
        await callback.answer()
        logger.info(
            f"Пользователь {user_id} запросил события (категория: {category}, страница 1, событий: {len(filtered_events)}).")
    except Exception as e:
        logger.error(f"Ошибка при обработке категории: {e}")
        await callback.message.edit_text(
            "Произошла ошибка при обработке категории.",
            reply_markup=calendar_menu_keyboard()
        )
        await callback.answer()

# Обработчик пагинации с сохранением отфильтрованных событий.
@router.callback_query(lambda c: c.data.startswith("calendar_prev_") or c.data.startswith("calendar_next_"))
async def handle_pagination(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    current_message_text = callback.message.text
    current_reply_markup = callback.message.reply_markup

    try:
        data = await state.get_data()
        filter_type = data.get("calendar_filter", "all")
        filtered_events = data.get("filtered_events", [])
        current_page = data.get("current_page", 1)
        total_pages = data.get("total_pages", 1)

        action = callback.data.split("_")[1]
        new_page = current_page - 1 if action == "prev" else current_page + 1

        if new_page < 1 or new_page > total_pages:
            await callback.answer("Достигнут предел страниц.")
            return

        if not filtered_events:
            portfolio_only = filter_type == "portfolio"
            event_type = None
            if filter_type == "macro":
                event_type = "macro"
            elif filter_type == "dividends":
                event_type = "dividends"
            elif filter_type == "earnings":
                event_type = "earnings"
            elif filter_type == "press":
                event_type = "press"
            elif filter_type == "all":
                event_type = None
                portfolio_only = False

            filtered_events = await get_events(user_id=user_id, event_type=event_type, portfolio_only=portfolio_only)
            if not filtered_events:
                all_events = get_sample_events()
                crypto_symbols = {"BTC", "ETH", "BNB", "XRP", "ADA", "SOL", "DOGE", "DOT", "LTC", "LINK"}
                investment_symbols = {"AAPL", "MSFT", "AMZN", "GOOGL", "TSLA", "NVDA", "JPM", "GS", "V", "MA"}

                if filter_type == "portfolio":
                    portfolio = await get_portfolio(user_id)
                    portfolio_symbols = {asset['symbol'] for asset in portfolio}
                    filtered_events = [e for e in all_events if e['symbol'] in portfolio_symbols]
                elif filter_type == "macro":
                    filtered_events = [e for e in all_events if e['type'] == "macro"]
                elif filter_type == "dividends":
                    filtered_events = [e for e in all_events if e['type'] == "dividends"]
                elif filter_type == "earnings":
                    filtered_events = [e for e in all_events if e['type'] == "earnings"]
                elif filter_type == "press":
                    filtered_events = [e for e in all_events if e['type'] == "press"]
                elif filter_type == "all":
                    filtered_events = all_events

            if not filtered_events:
                new_text = f"Событий не найдено для фильтра: {filter_type}"
                new_markup = calendar_menu_keyboard()

                if current_message_text != new_text or str(current_reply_markup) != str(new_markup):
                    await callback.message.edit_text(
                        new_text,
                        reply_markup=new_markup
                    )
                await callback.answer()
                logger.info(f"Пользователь {user_id} запросил пагинацию (пусто, фильтр: {filter_type}).")
                return

            await state.update_data(filtered_events=filtered_events)

        formatted_events, total_pages = format_events(filtered_events, page=new_page)
        new_markup = pagination_keyboard(current_page=new_page, total_pages=total_pages, prefix="calendar")

        if current_message_text != formatted_events or str(current_reply_markup) != str(new_markup):
            await callback.message.edit_text(
                formatted_events,
                reply_markup=new_markup
            )
        await state.update_data(current_page=new_page, total_pages=total_pages)
        await callback.answer()
        logger.info(f"Пользователь {user_id} перешел на страницу календаря {new_page} (фильтр: {filter_type}).")
    except Exception as e:
        logger.error(f"Ошибка при пагинации: {e}")
        error_text = "Произошла ошибка при пагинации."
        if current_message_text != error_text:
            await callback.message.edit_text(
                error_text,
                reply_markup=calendar_menu_keyboard()
            )
        await callback.answer()

# Форматирует список событий для отображения с учетом дат.
def format_events(events, page=1, per_page=5):
    if not events:
        return "Событий не найдено.", 0

    total_events = len(events)
    total_pages = (total_events + per_page - 1) // per_page

    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    page_events = events[start_idx:end_idx]

    formatted = f"📅 *Календарь событий* (страница {page}/{total_pages}):\n\n"
    current_date = None

    for event in page_events:
        try:
            event_date = datetime.strptime(event['event_date'], "%Y-%m-%d %H:%M:%S")
            date_str = event_date.strftime("%Y-%m-%d")

            if date_str != current_date:
                formatted += f"\n📅 *{date_str}*\n"
                current_date = date_str

            event_type = EVENT_TYPES.get(event['type'], 'Неизвестный тип')
            formatted += (
                f"🔖 {event['title']}\n"
                f"📝 {event['description']}\n"
                f"📌 Тип: {event_type}\n"
                f"💹 Символ: {event['symbol']}\n"
                f"{'-' * 30}\n"
            )
        except ValueError as e:
            logger.error(f"Ошибка при обработке даты события {event['event_date']}: {e}")
            continue

    return formatted, total_pages
