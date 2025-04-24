# handlers
from datetime import datetime

from aiogram import Router, types, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, ChatMemberUpdated
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramAPIError

import asyncio
from typing import Union
from bot import bot
from loguru import logger
from events_data import get_sample_events
from states import PortfolioState, AlertState, CalendarStates
from keyboards import main_menu, asset_type_keyboard, alert_condition_keyboard, alert_actions_keyboard, \
    portfolio_actions_keyboard, confirm_alert_keyboard, confirm_remove_asset_keyboard, alerts_menu_keyboard, \
    quotes_menu_keyboard, calendar_menu_keyboard, pagination_keyboard, get_category_keyboard, get_pagination_keyboard, \
    settings_keyboard, portfolio_view_keyboard, confirm_delete_sub_account_keyboard, sub_account_select_keyboard_for_delete
from database import add_to_portfolio, get_portfolio, remove_from_portfolio, add_alert, get_alerts, remove_alert, \
    get_events, load_sample_events, get_or_create_chat_settings, update_chat_settings, get_sub_accounts, delete_sub_account
from api import get_stock_price, get_crypto_price, fetch_asset_price, get_stock_history, get_crypto_history, \
    get_stock_price_with_retry, get_market_data, fetch_asset_price_with_retry
from utils import format_portfolio, format_alerts, format_events, format_market_prices, format_market_overview, EVENT_TYPES, calculate_portfolio_summary


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
async def cmd_start(message: Message, state: FSMContext):
    if not await is_user_allowed(message):
         return
    user_id = message.from_user.id
    chat_id = message.chat.id
    chat_type = message.chat.type


    if not await check_subscription_middleware(message, state):
         return


    is_admin = await is_user_admin(chat_id, user_id) if chat_type != 'private' else False

    await message.answer("Добро пожаловать! Выберите действие:", reply_markup=main_menu(chat_type, is_admin))
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

        if state:
            await state.clear()
        return False
    return True

async def display_portfolio(message_or_callback: Union[Message, CallbackQuery], state: FSMContext, user_id: int, target_sub_account: str, page: int = 1):
    """Helper function to calculate summary and display portfolio"""
    is_message = isinstance(message_or_callback, Message)
    chat = message_or_callback.chat if is_message else message_or_callback.message.chat

    full_portfolio_data = await get_portfolio(user_id)
    sub_accounts = await get_sub_accounts(user_id)

    if target_sub_account not in sub_accounts:
        logger.warning(f"Target sub-account '{target_sub_account}' not found for user {user_id}, defaulting to 'Основной'.")
        target_sub_account = "Основной"
        if target_sub_account not in sub_accounts:
            sub_accounts.insert(0, target_sub_account)

    total_value, total_purchase, total_pnl = await calculate_portfolio_summary(full_portfolio_data)
    prices_available = True

    assets_in_current_sub = full_portfolio_data.get(target_sub_account, [])

    page_assets_with_prices = []
    items_per_page = 4
    start_idx = (page - 1) * items_per_page
    end_idx = start_idx + items_per_page
    page_items_to_fetch = assets_in_current_sub[start_idx:end_idx]

    if page_items_to_fetch:
        tasks = [fetch_asset_price_with_retry(asset['symbol'], asset['asset_type']) for asset in page_items_to_fetch]
        logger.info(f"Запрос цен для {len(tasks)} активов на странице {page} суб-счета {target_sub_account}...")
        page_prices = await asyncio.gather(*tasks)
        logger.info("Цены для страницы портфеля получены.")

        for i, asset in enumerate(page_items_to_fetch):
            asset_copy = asset.copy()
            asset_copy['current_price'] = page_prices[i]
            page_assets_with_prices.append(asset_copy)
    else:
        page_assets_with_prices = []

    formatted_portfolio, total_pages = format_portfolio(
        page_assets_with_prices,
        page=page,
        items_per_page=items_per_page,
        total_portfolio_value=total_value,
        total_portfolio_pnl=total_pnl,
        prices_available_overall=prices_available
    )

    await state.set_state(PortfolioState.viewing_portfolio)
    await state.update_data(current_sub_account=target_sub_account, current_page=page)

    message_text = f"💼 Портфель: Суб-счет '{target_sub_account}'\n\n{formatted_portfolio}"
    reply_markup = portfolio_view_keyboard(sub_accounts, target_sub_account, page, total_pages)

    if is_message:
        await message_or_callback.answer(message_text, reply_markup=reply_markup)
    else:
        try:
            if message_or_callback.message.text != message_text or str(message_or_callback.message.reply_markup) != str(reply_markup):
                await message_or_callback.message.edit_text(message_text, reply_markup=reply_markup)
            else:
                await message_or_callback.answer()
        except TelegramAPIError as e:
            if "message is not modified" in str(e):
                await message_or_callback.answer()
            else:
                logger.error(f"Failed to edit message for portfolio view: {e}")
                await message_or_callback.message.answer(message_text, reply_markup=reply_markup)
                await message_or_callback.answer()

@router.message(Command("help"))
async def cmd_help(message: Message):
    if not await is_user_allowed(message):
        return
    help_text = """
📋 *Список доступных команд:*

/start - Начать работу с ботом
/help - Показать список всех команд и инструкцию
/quotes - Котировка в реальном времени
/set_alert - Установить оповещение о достижении целевой цены
/alerts - Просмотреть установленные алерты
/remove_alert - Удалить установленный алерт
/add_to_portfolio - Добавить актив в портфолио (устарело, используйте меню)
/remove_from_portfolio - Удалить актив из портфолио (устарело, используйте меню)
/portfolio - Показать текущее портфолио
/market - Показать обзор рынка
/cancel - Отменить последнее действие
/settings - Настройки разрешений (в группах)
/calendar - Календарь событий
/load_sample_events - Загрузить тестовые события (для админа?)

📝 *Инструкция:*
1. Используйте кнопки меню для навигации.
2. /portfolio покажет ваше портфолио с возможностью добавления/удаления активов и суб-счетов.
3. /quotes покажет меню котировок.
4. /alerts покажет меню управления алертами.
5. /calendar покажет календарь экономических событий.
6. /market покажет обзор рынка (индексы, сырье, крипто).
7. /cancel отменит текущую операцию (например, добавление актива).
"""
    try:
        await message.answer(help_text, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Ошибка при отправке текста помощи: {e}")
        await message.answer(help_text, parse_mode=None)

@router.message(Command("quotes"))
async def cmd_quotes(message: Message, state: FSMContext):
    if not await is_user_allowed(message):
        return
    if not await check_subscription_middleware(message, state):
        return
    await message.answer("Выберите действие с котировками:", reply_markup=quotes_menu_keyboard())
    logger.info(f"Пользователь {message.from_user.id} запросил меню котировок через команду.")

# Обработчик выбора типа актива для котировок.
@router.callback_query(PortfolioState.selecting_asset_type)
async def select_asset_type(callback: CallbackQuery, state: FSMContext):
    if not await is_user_allowed(callback): return
    await state.update_data(asset_type=callback.data)
    await callback.message.answer("Введите символ актива (например, AAPL или BTC/USDT):")
    await state.set_state(PortfolioState.selecting_symbol)
    await callback.answer()

# Обработчик ввода символа для получения котировок.
@router.message(PortfolioState.selecting_symbol)
async def get_quote(message: Message, state: FSMContext):
    if not await is_user_allowed(message): return
    symbol = message.text.strip().upper()
    data = await state.get_data()
    asset_type = data.get("asset_type")

    if not asset_type:
        await message.answer("Ошибка состояния. Пожалуйста, начните заново.")
        await state.clear()
        logger.warning(f"User {message.from_user.id} in state selecting_symbol without asset_type.")
        return

    if symbol.startswith('/'):
        await message.answer("Пожалуйста, введите символ актива, а не команду.")

        return

    price = None
    if asset_type == "stock":
        if not symbol.isalpha() and not symbol.endswith(".ME") and "." not in symbol:
            await message.answer("Недопустимый тикер акции. Введите тикер (напр. AAPL, SBER.ME, BRK.B).")

            return
        price = await fetch_asset_price_with_retry(symbol, asset_type)
    elif asset_type == "crypto":
        if '/' not in symbol:
            await message.answer("Недопустимый тикер криптовалюты. Формат: 'BTC/USDT'.")

            return
        price = await fetch_asset_price_with_retry(symbol, asset_type)

    if price is not None:
        await message.answer(f"Текущая цена {symbol}: ${price:.2f}")
    else:
        await message.answer(f"Не удалось получить цену для {symbol}. Проверьте символ или попробуйте позже.")

    await state.clear()
    logger.info(f"Пользователь {message.from_user.id} запросил цену {symbol} ({asset_type}).")

# Обработчик выбора типа актива для добавления в портфель.
@router.callback_query(PortfolioState.adding_asset_type)
async def add_asset_type(callback: CallbackQuery, state: FSMContext):
    if not await is_user_allowed(callback): return
    await state.update_data(asset_type=callback.data)
    await callback.message.answer("Введите символ актива (например, AAPL или BTC/USDT):")
    await state.set_state(PortfolioState.adding_symbol)
    await callback.answer()


# Обработчик ввода символа актива для добавления в портфель.
@router.message(PortfolioState.adding_symbol)
async def add_symbol(message: Message, state: FSMContext):
    if not await is_user_allowed(message): return
    user_id = message.from_user.id
    symbol = message.text.strip().upper()
    data = await state.get_data()
    asset_type = data.get("asset_type")

    if not asset_type:
        await message.answer("Ошибка состояния (тип актива). Начните заново.")
        await state.clear()
        return

    if symbol.startswith('/'):
        await message.answer("Пожалуйста, введите символ актива, а не команду.")
        return

    if asset_type == "stock":
        if not symbol.isalpha() and not symbol.endswith(".ME") and "." not in symbol:
            await message.answer("Недопустимый тикер акции. Введите тикер (напр. AAPL, SBER.ME, BRK.B).")
            return
        
    elif asset_type == "crypto":
        if '/' not in symbol:
            await message.answer("Недопустимый тикер криптовалюты. Формат: 'BTC/USDT'.")
            return


    price = await fetch_asset_price_with_retry(symbol, asset_type)
    if price is None:
        await message.answer(f"Не удалось проверить актив {symbol}. Проверьте символ или попробуйте позже.")
        return

    await state.update_data(symbol=symbol)
    await message.answer("Введите количество актива:")
    await state.set_state(PortfolioState.adding_amount)
    logger.info(f"Пользователь {user_id} ввел символ {symbol} для добавления в портфель.")

# Обработчик ввода количества актива.
@router.message(PortfolioState.adding_amount)
async def add_amount(message: Message, state: FSMContext):
    if not await is_user_allowed(message): return
    user_id = message.from_user.id
    try:
        amount = float(message.text.replace(',', '.'))
        if amount <= 0:
            await message.answer("Количество актива должно быть положительным числом.")
            return
        await state.update_data(amount=amount)
        await message.answer("Введите цену покупки (за 1 единицу):")
        await state.set_state(PortfolioState.adding_price)
    except ValueError:
        await message.answer("Пожалуйста, введите число.")
    logger.info(f"Пользователь {user_id} ввел количество актива: {message.text}")

# Обработчик ввода цены покупки.
@router.message(PortfolioState.adding_price)
async def add_price(message: Message, state: FSMContext):
    if not await is_user_allowed(message): return
    user_id = message.from_user.id
    main_account_name = "Основной"
    try:
        price = float(message.text.replace(',', '.'))
        if price < 0:
            await message.answer("Цена покупки не может быть отрицательной.")
            return
        data = await state.get_data()
        target_sub_account = data.get("target_sub_account", main_account_name)
        asset_type = data.get("asset_type")
        symbol = data.get("symbol")
        amount = data.get("amount")

        if not all([target_sub_account, asset_type, symbol, amount]):
            await message.answer("Ошибка состояния. Не хватает данных для добавления актива. Начните заново.")
            await state.clear()
            logger.error(f"Incomplete state data in add_price for user {user_id}: {data}")
            return

        await add_to_portfolio(
            user_id=user_id,
            sub_account_name=target_sub_account,
            asset_type=asset_type,
            symbol=symbol,
            amount=amount,
            purchase_price=price
        )
        await message.answer(f"Актив {symbol} добавлен в суб-счет '{target_sub_account}'!")


        await display_portfolio(message, state, user_id, target_sub_account, page=1)
        logger.info(f"Пользователь {user_id} добавил актив в портфель: {symbol} ({asset_type}) в суб-счет '{target_sub_account}'")

    except ValueError:
        await message.answer("Пожалуйста, введите число (цену покупки).")
        logger.warning(f"Пользователь {user_id} ввел некорректную цену: {message.text}")
    except Exception as e:
        logger.error(f"Ошибка при добавлении актива для пользователя {user_id}: {e}")
        await message.answer("Произошла ошибка при добавлении актива. Пожалуйста, попробуйте позже.")
        await state.clear()

@router.message(Command("set_alert"))
async def cmd_set_alert(message: Message, state: FSMContext):
    if not await is_user_allowed(message): return
    if not await check_subscription_middleware(message, state): return
    await message.answer("Выберите тип актива для алерта:", reply_markup=asset_type_keyboard())
    await state.set_state(AlertState.selecting_asset_type)
    logger.info(f"Пользователь {message.from_user.id} из чата {message.chat.id} начал настройку алерта.")

# Обработчик выбора типа актива для алерта.
@router.callback_query(AlertState.selecting_asset_type)
async def select_alert_asset_type(callback: CallbackQuery, state: FSMContext):
    if not await is_user_allowed(callback): return
    await state.update_data(asset_type=callback.data)
    await callback.message.answer("Введите символ актива (например, AAPL или BTC/USDT):")
    await state.set_state(AlertState.selecting_symbol)
    await callback.answer()

# Обработчик ввода символа для алерта.
@router.message(AlertState.selecting_symbol)
async def select_alert_symbol(message: Message, state: FSMContext):
    if not await is_user_allowed(message): return
    chat_id = message.chat.id
    user_id = message.from_user.id
    symbol = message.text.strip().upper()
    data = await state.get_data()
    asset_type = data.get("asset_type")

    if not asset_type:
        await message.answer("Ошибка состояния (тип актива). Начните заново.")
        await state.clear()
        return

    if symbol.startswith('/'):
        await message.answer("Пожалуйста, введите символ актива, а не команду.")
        return

    if asset_type == "stock":
         if not symbol.isalpha() and not symbol.endswith(".ME") and "." not in symbol:
            await message.answer("Недопустимый тикер акции. Введите тикер (напр. AAPL, SBER.ME, BRK.B).")
            return
         
    elif asset_type == "crypto":
        if '/' not in symbol:
            await message.answer("Недопустимый тикер криптовалюты. Формат: 'BTC/USDT'.")
            return


    price = await fetch_asset_price_with_retry(symbol, asset_type)
    if price is None:
        await message.answer(f"Не удалось проверить актив {symbol}. Проверьте символ или попробуйте позже.")
        return

    await state.update_data(symbol=symbol)
    await message.answer(f"Текущая цена {symbol}: ${price:.2f}\nВведите целевую цену для алерта:")
    await state.set_state(AlertState.selecting_price)
    logger.info(f"Пользователь {user_id} ввел символ {symbol} для алерта в чате {chat_id}.")

# Обработчик ввода целевой цены для алерта.
@router.message(AlertState.selecting_price)
async def select_alert_price(message: Message, state: FSMContext):
    if not await is_user_allowed(message): return
    chat_id = message.chat.id
    user_id = message.from_user.id
    try:
        target_price = float(message.text.replace(',', '.'))
        if target_price <= 0:
            await message.answer("Целевая цена должна быть положительным числом.")
            return
        await state.update_data(target_price=target_price)
        await message.answer("Выберите условие алерта:", reply_markup=alert_condition_keyboard())
        await state.set_state(AlertState.selecting_condition)
    except ValueError:
        await message.answer("Пожалуйста, введите число.")
    logger.info(f"Пользователь {user_id} ввел целевую цену: {message.text} в чате {chat_id}")

# Обработчик выбора условия алерта (above или below).
@router.callback_query(AlertState.selecting_condition, F.data.in_({"above", "below"}))
async def select_alert_condition(callback: CallbackQuery, state: FSMContext):
    if not await is_user_allowed(callback): return
    chat_id = callback.message.chat.id
    user_id = callback.from_user.id
    condition = callback.data
    data = await state.get_data()
    symbol = data.get("symbol")
    target_price = data.get("target_price")

    if not symbol or target_price is None:
        await callback.message.answer("Ошибка состояния. Начните заново.")
        await state.clear()
        logger.error(f"Incomplete state data in select_alert_condition for chat {chat_id}: {data}")
        await callback.answer()
        return


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
    logger.info(f"Пользователь {user_id} выбрал условие алерта: {condition} в чате {chat_id}")

@router.message(Command("calendar"))
async def show_calendar(message: Message, state: FSMContext):
    if not await is_user_allowed(message): return
    if not await check_subscription_middleware(message, state): return
    await message.answer("Выберите категорию событий:", reply_markup=get_category_keyboard())
    await state.set_state(CalendarStates.viewing_calendar)
    logger.info(f"Пользователь {message.from_user.id} запросил календарь событий.")

@router.message(PortfolioState.removing_symbol)
async def handle_remove_asset_symbol_from_subaccount(message: Message, state: FSMContext):
    if not await is_user_allowed(message): return
    user_id = message.from_user.id
    symbol = message.text.strip().upper()
    data = await state.get_data()
    target_sub_account = data.get("target_sub_account")

    if not target_sub_account:
        await message.answer("Ошибка: не указан суб-счет. Пожалуйста, начните заново.")
        await state.clear()
        return

    if symbol.startswith('/'):
        await message.answer("Пожалуйста, введите символ актива, а не команду.")
        return

    portfolio_data = await get_portfolio(user_id)
    assets_in_sub = portfolio_data.get(target_sub_account, [])
    asset_exists = any(asset['symbol'] == symbol for asset in assets_in_sub)

    if not asset_exists:
        await message.answer(f"Актив {symbol} не найден в суб-счете '{target_sub_account}'.")
        return


    await state.update_data(symbol_to_remove=symbol)
    await message.answer(
        f"Вы уверены, что хотите удалить {symbol} из суб-счета '{target_sub_account}'?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"confirm_remove_{target_sub_account}_{symbol}"),
                InlineKeyboardButton(text="🚫 Нет, отмена", callback_data="cancel_remove")
            ]
        ])
    )
    logger.info(f"Пользователь {user_id} подтверждает удаление {symbol} из '{target_sub_account}'.")

# Обработчик команды /market для просмотра текущих рыночных цен.
@router.message(Command("market"))
async def cmd_market(message: Message):
    if not await is_user_allowed(message): return
    if not await check_subscription_middleware(message): return

    user_id = message.from_user.id
    chat_id = message.chat.id
    chat_type = message.chat.type
    is_admin = await is_user_admin(chat_id, user_id) if chat_type != 'private' else False

    market_data = await get_market_data()
    formatted_market = format_market_overview(market_data)

    await message.answer(formatted_market, reply_markup=main_menu(chat_type, is_admin), parse_mode="Markdown")
    logger.info(f"Пользователь {user_id} запросил обзор рынка.")

# Регистрация всех хэндлеров.
def register_handlers(dp: Router):
    dp.include_router(router)

@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    if not await is_user_allowed(message): return
    current_state = await state.get_state()
    if current_state is None:
        await message.answer("Нет активных операций для отмены.")
        return

    user_id = message.from_user.id
    chat_id = message.chat.id
    chat_type = message.chat.type
    is_admin = await is_user_admin(chat_id, user_id) if chat_type != 'private' else False

    await state.clear()
    await message.answer("Действие отменено.", reply_markup=main_menu(chat_type, is_admin))
    logger.info(f"Пользователь {message.from_user.id} отменил операцию ({current_state}).")


@router.message(Command("alerts"))
async def cmd_alerts(message: Message):
    if not await is_user_allowed(message): return
    if not await check_subscription_middleware(message): return
    chat_id = message.chat.id
    alerts = await get_alerts(chat_id)

    if not alerts:
        await message.answer(
            "У вас нет установленных алертов в этом чате. 😔\n"
            "Используйте команду /set_alert или меню 'Алерты', чтобы установить алерт."
        )
        logger.info(f"Пользователь {message.from_user.id} запросил алерты в чате {chat_id} (список пуст).")
        return

    await message.answer("Выберите действие с алертами:", reply_markup=alerts_menu_keyboard())
    logger.info(f"Пользователь {message.from_user.id} запросил меню алертов через команду в чате {chat_id}.")


@router.message(Command("remove_alert"))
async def cmd_remove_alert(message: Message, state: FSMContext):
    if not await is_user_allowed(message): return
    chat_id = message.chat.id
    user_id = message.from_user.id
    alerts = await get_alerts(chat_id)

    if not alerts:
        await message.answer("В этом чате нет установленных алертов для удаления.")
        logger.info(f"Пользователь {user_id} запросил удаление алерта в чате {chat_id} (список пуст).")
        return

    await message.answer(
        "Введите ID алерта, который хотите удалить из этого чата.\n"
        "Список алертов можно посмотреть через меню 'Алерты' -> 'Текущие алерты'."
    )
    await state.set_state(AlertState.removing_alert)


@router.callback_query(F.data == "quotes_menu")
async def handle_quotes_menu(callback: CallbackQuery, state: FSMContext):
    if not await is_user_allowed(callback): return
    await callback.message.answer("Выберите действие с котировками:", reply_markup=quotes_menu_keyboard())
    await callback.answer()
    logger.info(f"Пользователь {callback.from_user.id} открыл меню котировок.")


@router.callback_query(F.data == "quotes")
async def handle_quotes(callback: CallbackQuery, state: FSMContext):
    if not await is_user_allowed(callback): return
    if not await check_subscription_middleware(callback.message, state):
        await callback.answer()
        return
    await callback.message.answer("Выберите тип актива:", reply_markup=asset_type_keyboard())
    await state.set_state(PortfolioState.selecting_asset_type)
    await callback.answer()
    logger.info(f"Пользователь {callback.from_user.id} запросил котировки.")

@router.message(Command("portfolio"))
@router.callback_query(F.data == "portfolio_view_default")
async def handle_portfolio_view_start(message_or_callback: Union[Message, CallbackQuery], state: FSMContext):
    if not await is_user_allowed(message_or_callback): return

    is_message = isinstance(message_or_callback, Message)
    message = message_or_callback if is_message else message_or_callback.message
    user_id = message.from_user.id
    main_account_name = "Основной"

    if not await check_subscription_middleware(message, state):
        if not is_message: await message_or_callback.answer()
        return

    await display_portfolio(message_or_callback, state, user_id, main_account_name, page=1)

    if not is_message: await message_or_callback.answer()
    logger.info(f"Пользователь {user_id} открыл портфель.")


@router.callback_query(F.data == "portfolio_add_sub_account_start")
async def handle_add_sub_account_start(callback: CallbackQuery, state: FSMContext):
    if not await is_user_allowed(callback): return
    await callback.message.answer("Введите имя для нового суб-счета:")
    await state.set_state(PortfolioState.adding_sub_account_new_name)
    await callback.answer()
    logger.info(f"Пользователь {callback.from_user.id} начал создание нового суб-счета.")

@router.message(PortfolioState.adding_sub_account_new_name)
async def handle_add_sub_account_name(message: Message, state: FSMContext):
    if not await is_user_allowed(message): return
    user_id = message.from_user.id
    new_sub_account_name = message.text.strip()
    main_account_name = "Основной"

    if not new_sub_account_name:
        await message.answer("Имя суб-счета не может быть пустым. Попробуйте снова или нажмите /cancel.")
        return

    if new_sub_account_name == main_account_name:
        await message.answer(f"Имя '{main_account_name}' зарезервировано. Выберите другое имя.")
        return

    if "/" in new_sub_account_name or "_" in new_sub_account_name:
        await message.answer("Имя суб-счета не должно содержать символы '/' или '_'. Попробуйте снова.")
        return

    existing_sub_accounts = await get_sub_accounts(user_id)
    if new_sub_account_name in existing_sub_accounts:
        await message.answer(f"Суб-счет с именем '{new_sub_account_name}' уже существует.")

        return


    await display_portfolio(message, state, user_id, new_sub_account_name, page=1)
    logger.info(f"Пользователь {user_id} создал (концептуально) суб-счет '{new_sub_account_name}' и переключился на него.")


@router.callback_query(PortfolioState.removing_sub_account_selection_for_delete, F.data.startswith("p_sel_del_"))
async def handle_remove_sub_account_select_for_delete(callback: CallbackQuery, state: FSMContext):
    if not await is_user_allowed(callback): return
    sub_account_to_delete = callback.data.replace("p_sel_del_", "")
    main_account_name = "Основной"

    if sub_account_to_delete == main_account_name:
        await callback.answer(f"Нельзя удалить '{main_account_name}'.", show_alert=True)
        return

    try:
        await callback.message.edit_text(
            f"Вы уверены, что хотите удалить суб-счет '{sub_account_to_delete}' и ВСЕ активы в нем? Это действие необратимо.",
            reply_markup=confirm_delete_sub_account_keyboard(sub_account_to_delete)
        )
    except TelegramAPIError as e:
         if "message is not modified" not in str(e): logger.error(f"Error editing message in handle_remove_sub_account_select_for_delete: {e}")

    await callback.answer()

@router.callback_query(F.data == "cancel_sub_account_delete")
async def handle_cancel_sub_account_delete(callback: CallbackQuery, state: FSMContext):
    if not await is_user_allowed(callback): return
    user_id = callback.from_user.id
    current_data = await state.get_data()

    await display_portfolio(callback, state, user_id, "Основной", page=1)

    await callback.answer("Удаление отменено")
    logger.info(f"Пользователь {user_id} отменил удаление суб-счета.")

@router.callback_query(F.data.startswith("p_conf_del_"))
async def handle_confirm_sub_account_delete(callback: CallbackQuery, state: FSMContext):
    if not await is_user_allowed(callback): return
    user_id = callback.from_user.id
    sub_account_to_delete = callback.data.replace("p_conf_del_", "")
    main_account_name = "Основной"


    if sub_account_to_delete == main_account_name:
        await callback.answer(f"Нельзя удалить '{main_account_name}'.", show_alert=True)
        return

    try:
        await delete_sub_account(user_id, sub_account_to_delete)
        await callback.message.edit_text(f"Суб-счет '{sub_account_to_delete}' успешно удален.")
        logger.info(f"Пользователь {user_id} удалил суб-счет '{sub_account_to_delete}'.")


        await display_portfolio(callback, state, user_id, main_account_name, page=1)

    except ValueError as ve:
        logger.warning(f"ValueError during sub-account delete confirmation for {user_id}, account '{sub_account_to_delete}': {ve}")
        await callback.message.edit_text(f"Не удалось удалить суб-счет: {ve}")
        await state.clear()
    except Exception as e:
        logger.error(f"Ошибка при удалении суб-счета '{sub_account_to_delete}' для {user_id}: {e}")
        await callback.message.edit_text("Произошла ошибка при удалении суб-счета.")
        await state.clear()

    await callback.answer()

@router.callback_query(F.data == "portfolio_remove_sub_account_start")
async def handle_remove_sub_account_start(callback: CallbackQuery, state: FSMContext):
    if not await is_user_allowed(callback): return
    user_id = callback.from_user.id
    sub_accounts = await get_sub_accounts(user_id)
    removable_accounts = [acc for acc in sub_accounts if acc != "Основной"]

    if not removable_accounts:
        await callback.answer("Нет суб-счетов, которые можно удалить.", show_alert=True)
        return

    await callback.message.answer(
        "Выберите суб-счет, который хотите удалить (вместе со всеми активами в нем):",
        reply_markup=sub_account_select_keyboard_for_delete(sub_accounts)
    )
    await state.set_state(PortfolioState.removing_sub_account_selection_for_delete)
    await callback.answer()
    logger.info(f"Пользователь {user_id} начал удаление суб-счета.")


@router.callback_query(F.data == "set_alert")
async def handle_set_alert(callback: CallbackQuery, state: FSMContext):
    if not await is_user_allowed(callback): return
    if not await check_subscription_middleware(callback.message, state):
        await callback.answer()
        return

    await callback.message.answer("Выберите тип актива для алерта:", reply_markup=asset_type_keyboard())
    await state.set_state(AlertState.selecting_asset_type)
    await callback.answer()
    logger.info(f"Пользователь {callback.from_user.id} начал установку алерта в чате {callback.message.chat.id} (из меню).")


@router.callback_query(F.data == "calendar")
async def handle_calendar_menu(callback: CallbackQuery, state: FSMContext):
    if not await is_user_allowed(callback): return
    if not await check_subscription_middleware(callback.message, state):
        await callback.answer()
        return
    user_id = callback.from_user.id
    try:

        await callback.message.edit_text("Выберите категорию событий:", reply_markup=get_category_keyboard())
        await state.set_state(CalendarStates.viewing_calendar)
        await callback.answer()
        logger.info(f"Пользователь {user_id} открыл меню календаря.")
    except Exception as e:
        logger.error(f"Ошибка при открытии меню календаря: {e}")
        await callback.message.answer("Произошла ошибка при открытии календаря.")
        await callback.answer()


@router.callback_query(F.data == "help")
async def handle_help(callback: CallbackQuery):
    if not await is_user_allowed(callback): return
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id
    chat_type = callback.message.chat.type
    is_admin = await is_user_admin(chat_id, user_id) if chat_type != 'private' else False
    help_text = """
📋 *Список доступных действий:*

- 📈 Котировки: Получить текущую цену актива
- 💼 Портфель: Просмотреть/управлять портфелем и суб-счетами
- 🔔 Алерты: Управлять оповещениями о цене
- 📅 Календарь: Просмотреть календарь событий
- 📊 Рынок: Обзор рынка (индексы, сырье, крипто)
- ℹ️ Помощь: Показать это сообщение
- ⚙️ Настройки: Управление разрешениями (в группах)
- 🚫 Отмена: Отменить текущее действие (ввод данных)

📝 *Инструкция:*
1. Используйте кнопки для навигации.
2. Следуйте подсказкам бота для ввода данных (символы, цены, количество).
3. Для отмены ввода данных нажмите 'Отмена' или используйте команду /cancel.
"""
    try:
        await callback.message.edit_text(help_text, reply_markup=main_menu(chat_type, is_admin), parse_mode="Markdown")
    except TelegramAPIError as e:
         if "message is not modified" not in str(e): logger.error(f"Error editing help message: {e}")

    await callback.answer()
    logger.info(f"Пользователь {callback.from_user.id} запросил помощь.")

# Обработчик кнопки 'Рынок' для показа обзора рынка.
@router.callback_query(F.data == "market")
async def handle_market_overview(callback: CallbackQuery):
    if not await is_user_allowed(callback): return
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id
    chat_type = callback.message.chat.type
    is_admin = await is_user_admin(chat_id, user_id) if chat_type != 'private' else False
    market_data = await get_market_data()
    formatted_market = format_market_overview(market_data)
    try:
        await callback.message.edit_text(formatted_market, reply_markup=main_menu(chat_type, is_admin), parse_mode="Markdown")
    except TelegramAPIError as e:
         if "message is not modified" not in str(e): logger.error(f"Error editing market overview message: {e}")

    await callback.answer()
    logger.info(f"Пользователь {callback.from_user.id} запросил обзор рынка.")


@router.callback_query(F.data == "remove_asset")
async def handle_remove_asset_prompt(callback: CallbackQuery, state: FSMContext):
    if not await is_user_allowed(callback): return
    await callback.message.answer("Эта кнопка устарела. Используйте меню 'Портфель' -> '🗑 Удалить отсюда'.")
    await callback.answer()
    logger.info(f"Пользователь {callback.from_user.id} нажал устаревшую кнопку 'Удалить актив'.")


@router.callback_query(F.data == "alerts")
async def handle_alerts(callback: CallbackQuery):
    if not await is_user_allowed(callback): return
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id

    alerts = await get_alerts(chat_id) # Alerts are chat-specific

    try:
        if not alerts:
             await callback.message.edit_text(
                "В этом чате нет установленных алертов. 😔\n"
                "Используйте кнопку 'Добавить алерт', чтобы добавить.",
                reply_markup=alerts_menu_keyboard() # Show menu anyway
            )
             logger.info(f"Пользователь {user_id} открыл меню алертов в чате {chat_id} (пусто).")
        else:
             await callback.message.edit_text("Выберите действие с алертами:", reply_markup=alerts_menu_keyboard())
             logger.info(f"Пользователь {user_id} открыл меню алертов в чате {chat_id} (есть алерты).")
    except TelegramAPIError as e:
         if "message is not modified" not in str(e): logger.error(f"Error editing alerts menu message: {e}")


    await callback.answer()


@router.callback_query(F.data == "remove_alert")
async def handle_remove_alert_prompt(callback: CallbackQuery, state: FSMContext):
    if not await is_user_allowed(callback): return
    chat_id = callback.message.chat.id
    alerts = await get_alerts(chat_id)
    if not alerts:
         await callback.answer("В этом чате нет алертов для удаления.", show_alert=True)
         return

    await callback.message.answer("Введите ID алерта из этого чата, который хотите удалить (ID можно увидеть в 'Текущие алерты'):")
    await state.set_state(AlertState.removing_alert)
    await callback.answer()
    logger.info(f"Пользователь {callback.from_user.id} начал удаление алерта в чате {chat_id}.")


@router.callback_query(F.data == "confirm_alert")
async def confirm_alert(callback: CallbackQuery, state: FSMContext):
    if not await is_user_allowed(callback): return
    chat_id = callback.message.chat.id
    user_id = callback.from_user.id
    chat_type = callback.message.chat.type
    is_admin = await is_user_admin(chat_id, user_id) if chat_type != 'private' else False
    data = await state.get_data()
    symbol = data.get("symbol")
    target_price = data.get("target_price")
    condition = data.get("condition")
    asset_type = data.get("asset_type")

    if not all([symbol, target_price is not None, condition, asset_type]): # Check target_price explicitly
        try:
            await callback.message.edit_text(
                "Ошибка: не удалось установить алерт (не хватает данных). Пожалуйста, начните заново.",
                reply_markup=main_menu(chat_type, is_admin)
            )
        except TelegramAPIError as e:
             if "message is not modified" not in str(e): logger.error(f"Error editing confirm_alert error message: {e}")

        await state.clear()
        await callback.answer("Ошибка данных", show_alert=True)
        logger.error(f"Пользователь {user_id} попытался подтвердить алерт с неполными данными: {data} в чате {chat_id}")
        return

    try:
        await add_alert(chat_id, asset_type, symbol, target_price, condition)
        await callback.message.edit_text(f"Алерт установлен для {symbol}!", reply_markup=main_menu(chat_type, is_admin))
        await state.clear()
        await callback.answer("Алерт установлен!")
        logger.info(f"Пользователь {user_id} установил алерт для {symbol} в чате {chat_id}.")
    except Exception as e:
        logger.error(f"Ошибка добавления алерта в БД для чата {chat_id}, {symbol}: {e}")
        await callback.message.edit_text("Ошибка при сохранении алерта. Попробуйте снова.", reply_markup=main_menu(chat_type, is_admin))
        await state.clear()
        await callback.answer("Ошибка сохранения", show_alert=True)

# Обработчик кнопки 'Отмена'.
@router.callback_query(F.data == "cancel")
async def handle_cancel(callback: CallbackQuery, state: FSMContext):
    if not await is_user_allowed(callback): return
    current_state = await state.get_state()
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id
    chat_type = callback.message.chat.type
    is_admin = await is_user_admin(chat_id, user_id) if chat_type != 'private' else False

    await state.clear()
    message_text = "Действие отменено."
    reply_markup = main_menu(chat_type, is_admin)

    try:
        # Don't try to edit if the message was already deleted or inaccessible
        if callback.message:
             await callback.message.edit_text(message_text, reply_markup=reply_markup)
    except TelegramAPIError as e:
        if "message to edit not found" in str(e) or "message can't be edited" in str(e):
            # If editing fails, send a new message
            await bot.send_message(chat_id, message_text, reply_markup=reply_markup)
        elif "message is not modified" not in str(e):
             logger.error(f"Error editing cancel message: {e}")
             # Fallback to sending a new message for other errors too
             await bot.send_message(chat_id, message_text, reply_markup=reply_markup)


    await callback.answer("Отменено")
    logger.info(f"Пользователь {user_id} отменил действие ({current_state}).")


@router.callback_query(F.data == "settings_open")
async def handle_settings_open(callback: CallbackQuery):

    user_id = callback.from_user.id
    chat_id = callback.message.chat.id

    if callback.message.chat.type == 'private':
        await callback.answer("Настройки разрешений доступны только в групповых чатах.", show_alert=True)
        logger.info(f"User {user_id} clicked settings_open in private chat {chat_id}.")
        return


    can_change = await is_user_admin(chat_id, user_id)

    allow_all, = await get_or_create_chat_settings(chat_id)
    setting_text = "Разрешить всем пользователям" if allow_all else "Разрешить только администраторам"

    info_text = f"⚙️ Настройки разрешений для чата:\n\n" \
                f"Текущая настройка: *{setting_text}*\n\n" \
                f"Кто может отправлять команды/нажимать кнопки бота в этом чате?"

    reply_markup = settings_keyboard(chat_id, allow_all) if can_change else None

    if not can_change:
        info_text += "\n\n_(Только администраторы могут изменять эти настройки.)_"


    try:
        await callback.message.edit_text(info_text, reply_markup=reply_markup, parse_mode="Markdown")
    except TelegramAPIError as e:
         if "message is not modified" not in str(e): logger.error(f"Error editing settings open message: {e}")

    await callback.answer()
    logger.info(f"User {user_id} opened settings via button in group {chat_id} (Admin: {can_change}).")


@router.callback_query(F.data.startswith("confirm_remove_"))
async def handle_confirm_remove_asset_from_subaccount(callback: CallbackQuery, state: FSMContext):
    if not await is_user_allowed(callback): return
    user_id = callback.from_user.id
    try:
        parts = callback.data.split("_")
        # confirm_remove_SUBNAME_SYMBOL -> parts[2]=SUBNAME, parts[3]=SYMBOL
        if len(parts) < 4: raise IndexError("Incorrect callback format")
        symbol_to_remove = parts[-1] # Assume symbol is last part
        sub_account_name = "_".join(parts[2:-1]) # Join parts between confirm_remove_ and symbol
        if not sub_account_name: raise IndexError("Sub-account name missing")

    except IndexError:
        logger.error(f"Некорректный callback подтверждения удаления: {callback.data}")
        await callback.answer("Ошибка подтверждения.", show_alert=True)
        await state.clear()
        return

    try:
        await remove_from_portfolio(user_id, sub_account_name, symbol_to_remove)
        await callback.message.edit_text(f"Актив {symbol_to_remove} удален из суб-счета '{sub_account_name}'.")
        logger.info(f"Пользователь {user_id} удалил актив {symbol_to_remove} из суб-счета '{sub_account_name}'.")


        await display_portfolio(callback, state, user_id, sub_account_name, page=1)

    except Exception as e:
        logger.error(f"Ошибка при удалении актива {symbol_to_remove} из '{sub_account_name}' для {user_id}: {e}")
        await callback.message.edit_text("Произошла ошибка при удалении актива.")
        await state.clear()


    await callback.answer()


@router.callback_query(F.data == "alerts_menu")
async def handle_alerts_menu(callback: CallbackQuery):
    if not await is_user_allowed(callback): return
    await callback.message.answer("Выберите действие с алертами:", reply_markup=alerts_menu_keyboard())
    await callback.answer()
    logger.info(f"Пользователь {callback.from_user.id} открыл меню алертов.")


@router.callback_query(F.data == "current_alerts")
async def handle_current_alerts(callback: CallbackQuery, state: FSMContext):
    if not await is_user_allowed(callback): return
    chat_id = callback.message.chat.id
    alerts = await get_alerts(chat_id)
    if not alerts:
        await callback.message.answer(
            "В этом чате нет установленных алертов. 😔",
            reply_markup=alerts_menu_keyboard()
        )
        logger.info(f"Пользователь {callback.from_user.id} запросил текущие алерты в чате {chat_id} (пусто).")
        await callback.answer()
        return

    formatted_alerts, total_pages = format_alerts(alerts, page=1)
    try:
        await callback.message.edit_text(
            formatted_alerts,
            reply_markup=alerts_menu_keyboard(current_page=1, total_pages=total_pages)
        )
    except TelegramAPIError as e:
         if "message is not modified" not in str(e): logger.error(f"Error editing current alerts message: {e}")

    await callback.answer()
    logger.info(f"Пользователь {callback.from_user.id} запросил текущие алерты в чате {chat_id} (страница 1).")


@router.message(AlertState.removing_alert)
async def handle_remove_alert_id(message: Message, state: FSMContext):
    if not await is_user_allowed(message): return
    chat_id = message.chat.id
    user_id = message.from_user.id
    try:
        alert_id_to_remove = int(message.text)
        alerts_in_chat = await get_alerts(chat_id)
        alert_exists = False
        for alert in alerts_in_chat:
            if alert[0] == alert_id_to_remove:
                 alert_exists = True
                 break

        if not alert_exists:
            await message.answer(
                f"Алерт с ID {alert_id_to_remove} не найден в этом чате.",
                reply_markup=alerts_menu_keyboard()
            )
            await state.clear() # Clear state even if not found
            logger.warning(f"Алерт ID {alert_id_to_remove} не найден для чата {chat_id} (попытка пользователя {user_id})")
            return

        await remove_alert(alert_id_to_remove)
        await message.answer(f"Алерт ID {alert_id_to_remove} удален.", reply_markup=alerts_menu_keyboard())
        await state.clear()
        logger.info(f"Пользователь {user_id} удалил алерт ID {alert_id_to_remove} из чата {chat_id}")
    except ValueError:
        await message.answer("Пожалуйста, введите числовой ID алерта.", reply_markup=alerts_menu_keyboard())
        logger.warning(f"Пользователь {user_id} ввел некорректный ID алерта: {message.text} в чате {chat_id}")

    except Exception as e:
         logger.error(f"Ошибка при удалении алерта {message.text} для чата {chat_id}: {e}")
         await message.answer("Произошла ошибка при удалении алерта.", reply_markup=alerts_menu_keyboard())
         await state.clear()

# Обработчик кнопки 'Назад' в меню алертов.
@router.callback_query(F.data == "main_menu")
async def handle_main_menu(callback: CallbackQuery, state: FSMContext):
    if not await is_user_allowed(callback): return
    await state.clear()
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id
    chat_type = callback.message.chat.type
    is_admin = await is_user_admin(chat_id, user_id) if chat_type != 'private' else False
    try:
        await callback.message.edit_text("Главное меню:", reply_markup=main_menu(chat_type, is_admin))
    except TelegramAPIError as e:
        if "message is not modified" not in str(e): logger.error(f"Error editing main menu message: {e}")
    await callback.answer()
    logger.info(f"Пользователь {callback.from_user.id} вернулся в главное меню.")


@router.callback_query(F.data == "portfolio_prices")
async def handle_portfolio_prices(callback: CallbackQuery):
    if not await is_user_allowed(callback): return
    user_id = callback.from_user.id
    portfolio_data = await get_portfolio(user_id)
    if not portfolio_data:
        await callback.message.answer(
            "Ваш портфель сейчас пуст. 😔",
            reply_markup=quotes_menu_keyboard()
        )
        logger.info(f"Пользователь {user_id} запросил цены портфеля (пустой).")
        await callback.answer()
        return

    portfolio_with_prices = []
    tasks = []
    asset_symbols = []

    for sub_account, assets in portfolio_data.items():
         for asset in assets:
            try:
                symbol = asset['symbol']
                asset_type = asset['asset_type']
                tasks.append(fetch_asset_price_with_retry(symbol, asset_type))
                asset_symbols.append(symbol)
            except (KeyError, ValueError, TypeError) as e:
                logger.error(f"Ошибка обработки актива в handle_portfolio_prices: {asset}. Ошибка: {e}")

    if not tasks:
        await callback.message.answer("Не найдено активов для запроса цен.", reply_markup=quotes_menu_keyboard())
        await callback.answer()
        return

    logger.info(f"Запрос цен для {len(tasks)} активов для показа цен портфеля...")
    current_prices = await asyncio.gather(*tasks)
    logger.info("Цены для показа цен портфеля получены.")

    for i, price in enumerate(current_prices):
         portfolio_with_prices.append({'symbol': asset_symbols[i], 'current_price': price})


    formatted_market = format_market_prices(portfolio_with_prices)
    try:
        await callback.message.edit_text(formatted_market, reply_markup=quotes_menu_keyboard())
    except TelegramAPIError as e:
         if "message is not modified" not in str(e): logger.error(f"Error editing portfolio prices message: {e}")
         else: # If not modified, still answer
              pass
    await callback.answer()
    logger.info(f"Пользователь {user_id} запросил цены портфеля.")


@router.callback_query(F.data.startswith("alerts_page_"))
async def handle_alerts_page(callback: CallbackQuery, state: FSMContext):
    if not await is_user_allowed(callback): return
    page = int(callback.data.replace("alerts_page_", ""))
    chat_id = callback.message.chat.id
    alerts = await get_alerts(chat_id)
    if not alerts:
        await callback.message.answer(
            "В этом чате нет установленных алертов. 😔",
            reply_markup=alerts_menu_keyboard()
        )
        logger.info(f"Пользователь {callback.from_user.id} запросил текущие алерты в чате {chat_id} (пусто).")
        await callback.answer()
        return

    formatted_alerts, total_pages = format_alerts(alerts, page=page)

    if page < 1 or page > total_pages:
         await callback.answer(f"Неверная страница {page}", show_alert=True)
         return

    try:
        await callback.message.edit_text(
            formatted_alerts,
            reply_markup=alerts_menu_keyboard(current_page=page, total_pages=total_pages)
        )
    except TelegramAPIError as e:
         if "message is not modified" not in str(e): logger.error(f"Error editing alerts page message: {e}")

    await callback.answer()
    logger.info(f"Пользователь {callback.from_user.id} перешел на страницу алертов {page} в чате {chat_id}.")


@router.callback_query(lambda c: c.data.startswith("calendar_category_"))
async def handle_category_selection(callback: CallbackQuery, state: FSMContext):
    if not await is_user_allowed(callback): return
    user_id = callback.from_user.id
    try:
        category = callback.data.split("_")[-1]
        await state.update_data(category=category, current_page=1) # Reset page on category change

        portfolio_symbols = set()
        if category == "portfolio":
            portfolio_data = await get_portfolio(user_id)
            for sub_account, assets in portfolio_data.items():
                for asset in assets:
                     portfolio_symbols.add(asset['symbol'])
            if not portfolio_symbols:
                 await callback.message.edit_text("Ваш портфель пуст, нет событий для отображения по портфелю.", reply_markup=get_category_keyboard())
                 await callback.answer()
                 return


        events = await get_events(user_id=user_id, event_type=None, portfolio_only=(category == "portfolio")) # Get all types initially, filter later if needed

        if not events: # Fallback to sample if DB is empty
             logger.warning("No events found in DB, falling back to sample events for calendar.")
             events = get_sample_events() # This returns raw dicts, need to convert format if DB returns tuples
             # Convert sample events format if necessary, assuming DB returns tuples like (id, date, title, desc, src, type, sym)
             events_tuples = []
             for i, e in enumerate(events):
                  events_tuples.append(
                      (i + 1, e["event_date"], e["title"], e["description"], e["source"], e["type"], e["symbol"])
                  )
             events = events_tuples


        filtered_events = []
        if category == "all":
            filtered_events = events
        elif category == "portfolio":
            filtered_events = [e for e in events if e[6] in portfolio_symbols] # index 6 is symbol
        elif category == "macro":
            filtered_events = [e for e in events if e[5] == "macro"] # index 5 is type
        elif category == "dividends":
            filtered_events = [e for e in events if e[5] == "dividends"]
        elif category == "earnings":
            filtered_events = [e for e in events if e[5] == "earnings"]
        elif category == "press":
            filtered_events = [e for e in events if e[5] == "press"]
        else: # Default to all if category unknown
            filtered_events = events


        filtered_events = sorted(
            filtered_events,
            key=lambda x: datetime.strptime(x[1], "%Y-%m-%d %H:%M:%S") # index 1 is date
        )


        if not filtered_events:
            category_display = EVENT_TYPES.get(category, category.capitalize()) if category != "portfolio" else "Портфель"
            await callback.message.edit_text(
                f"Событий в категории '{category_display}' не найдено.",
                reply_markup=get_category_keyboard()
            )
            await callback.answer()
            logger.info(f"Пользователь {user_id} запросил события (пусто, категория: {category}).")
            return

        await state.update_data(filtered_events=filtered_events) # Store filtered list for pagination

        text, total_pages = format_events(filtered_events, page=1) # Format page 1
        keyboard = pagination_keyboard(1, total_pages, "calendar") # Use generic pagination

        category_display = EVENT_TYPES.get(category, category.capitalize()) if category != "portfolio" else "Портфель"

        try:
            await callback.message.edit_text(
                f"📅 Календарь ({category_display}):\n\n{text}",
                reply_markup=keyboard
            )
        except TelegramAPIError as e:
             if "message is not modified" not in str(e): logger.error(f"Error editing calendar category selection message: {e}")

        await state.update_data(total_pages=total_pages)
        await callback.answer()
        logger.info(
            f"Пользователь {user_id} запросил события (категория: {category}, страница 1, событий: {len(filtered_events)}).")
    except Exception as e:
        logger.error(f"Ошибка при обработке категории календаря: {e}", exc_info=True)
        await callback.message.edit_text(
            "Произошла ошибка при обработке категории.",
            reply_markup=get_category_keyboard() # Back to category selection
        )
        await callback.answer("Ошибка", show_alert=True)

# Обработчик навигации по страницам календаря.
@router.callback_query(F.data.startswith("calendar_page_"))
async def handle_calendar_page(callback: CallbackQuery, state: FSMContext):
    if not await is_user_allowed(callback): return
    user_id = callback.from_user.id

    try:
        page = int(callback.data.split("_")[-1])
    except (ValueError, IndexError):
        logger.error(f"Invalid calendar pagination callback: {callback.data}")
        await callback.answer("Ошибка пагинации.", show_alert=True)
        return

    try:
        data = await state.get_data()
        filtered_events = data.get("filtered_events")
        category = data.get("category", "all") # Get category from state
        total_pages_state = data.get("total_pages")

        if filtered_events is None:
            logger.warning(f"No filtered_events in state for user {user_id} on calendar pagination. Re-filtering.")
            await handle_category_selection(callback, state)
            return

        if page < 1 or (total_pages_state and page > total_pages_state):
            await callback.answer("Неверная страница.", show_alert=True)
            return


        formatted_events, total_pages = format_events(filtered_events, page=page)
        new_markup = pagination_keyboard(current_page=page, total_pages=total_pages, prefix="calendar")
        category_display = EVENT_TYPES.get(category, category.capitalize()) if category != "portfolio" else "Портфель"

        try:
            await callback.message.edit_text(
                f"📅 Календарь ({category_display}):\n\n{formatted_events}",
                reply_markup=new_markup
            )
        except TelegramAPIError as e:
            if "message is not modified" not in str(e): logger.error(f"Error editing calendar page message: {e}")

        await state.update_data(current_page=page) # Update current page in state
        await callback.answer()
        logger.info(f"Пользователь {user_id} перешел на страницу календаря {page} (категория: {category}).")
    except Exception as e:
        logger.error(f"Ошибка при пагинации календаря: {e}", exc_info=True)
        await callback.message.edit_text(
            "Произошла ошибка при пагинации.",
            reply_markup=get_category_keyboard()
        )
        await callback.answer("Ошибка", show_alert=True)


@router.message(Command("load_sample_events"))
async def load_sample_events_handler(message: types.Message):
    if not await is_user_allowed(message): return
    try:
        await load_sample_events()
        await message.answer("Пример событий успешно загружен. Используйте меню 'Календарь' для просмотра.")
    except Exception as e:
        logger.error(f"Ошибка при загрузке примеров событий: {e}")
        await message.answer("Произошла ошибка при загрузке примеров событий.")

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

async def is_user_allowed(message_or_callback: Union[Message, CallbackQuery]) -> bool:
    is_message = isinstance(message_or_callback, Message)
    chat = message_or_callback.chat if is_message else message_or_callback.message.chat
    user = message_or_callback.from_user

    if chat.type == 'private':
        return True

    if chat.type in ['group', 'supergroup']:
        chat_id = chat.id
        user_id = user.id
        allow_all, = await get_or_create_chat_settings(chat_id)

        if allow_all:
            return True
        else:
            try:
                is_admin_user = await is_user_admin(chat_id, user_id)
                if is_admin_user:
                    return True
                else:
                    if is_message:
                        await message_or_callback.reply("У вас нет прав для использования команд бота в этом чате.", disable_notification=True)
                    else:
                        await message_or_callback.answer("У вас нет прав для выполнения этого действия.", show_alert=True)

                    logger.info(f"User {user_id} denied access in group {chat_id} (not admin).")
                    return False
            except Exception as e:
                logger.error(f"Error checking chat member status for user {user_id} in chat {chat_id}: {e}")
                if is_message:
                    await message_or_callback.reply("Ошибка проверки прав. Попробуйте позже.", disable_notification=True)
                else:
                    await message_or_callback.answer("Ошибка проверки прав.", show_alert=True)
                return False
    return False

async def is_user_admin(chat_id: int, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
        return member.status in ['administrator', 'creator']
    except Exception as e:
        logger.error(f"Error checking admin status for user {user_id} in chat {chat_id}: {e}")
        return False

@router.message(Command("settings"))
async def cmd_settings(message: Message):

    user_id = message.from_user.id
    chat_id = message.chat.id

    if message.chat.type == 'private':
        await message.answer("Настройки разрешений доступны только в групповых чатах.")
        logger.info(f"User {user_id} tried /settings in private chat {chat_id}.")
        return

    # Check if user invoking the command is allowed (admin check is inside this)
    if not await is_user_allowed(message): return

    can_change = await is_user_admin(chat_id, user_id) # is_user_allowed already confirmed admin if needed, but check again for safety

    allow_all, = await get_or_create_chat_settings(chat_id)
    setting_text = "Разрешить всем пользователям" if allow_all else "Разрешить только администраторам"

    info_text = f"⚙️ Настройки разрешений для чата:\n\n" \
                f"Текущая настройка: *{setting_text}*\n\n" \
                f"Кто может отправлять команды/нажимать кнопки бота в этом чате?"

    reply_markup = settings_keyboard(chat_id, allow_all) if can_change else None

    if not can_change:
        info_text += "\n\n_(Только администраторы могут изменять эти настройки.)_"

    await message.answer(info_text, reply_markup=reply_markup, parse_mode="Markdown")
    logger.info(f"User {user_id} viewed settings in group {chat_id} (Admin: {can_change}).")

@router.callback_query(F.data.startswith("settings_set_"))
async def handle_settings_change(callback: CallbackQuery):

    user_id = callback.from_user.id
    try:
        parts = callback.data.split('_')
        action = parts[2] # all or admins
        chat_id = int(parts[3])
    except (IndexError, ValueError):
        logger.error(f"Invalid settings callback data: {callback.data}")
        await callback.answer("Ошибка обработки данных.", show_alert=True)
        return

    # Check if the user clicking the button is allowed (admin check is inside)
    if not await is_user_allowed(callback): return

    # Double check if the user initiating the change is still an admin
    if not await is_user_admin(chat_id, user_id):
        await callback.answer("Только администраторы могут изменять настройки.", show_alert=True)
        logger.warning(f"User {user_id} (no longer admin?) tried to change settings via callback in group {chat_id}.")
        return

    new_allow_all = (action == "all")

    try:
        await update_chat_settings(chat_id, new_allow_all)
        setting_text = "Разрешить всем пользователям" if new_allow_all else "Разрешить только администраторам"
        new_info_text = (
             f"⚙️ Настройки разрешений для чата:\n\n"
            f"Текущая настройка: *{setting_text}*\n\n"
            f"Кто может отправлять команды/нажимать кнопки бота в этом чате?"
        )
        new_reply_markup = settings_keyboard(chat_id, new_allow_all)

        if callback.message.text != new_info_text or str(callback.message.reply_markup) != str(new_reply_markup):
             await callback.message.edit_text(
                 new_info_text,
                 reply_markup=new_reply_markup,
                 parse_mode="Markdown"
             )
        await callback.answer("Настройки обновлены!")
        logger.info(f"Admin {user_id} changed settings in group {chat_id} to allow_all={new_allow_all}.")
    except TelegramAPIError as e:
        if "message is not modified" not in str(e): logger.error(f"Error editing settings change message: {e}")
        await callback.answer("Не удалось обновить настройки.", show_alert=True) # Inform user even if no edit
    except Exception as e:
        logger.error(f"Failed to update settings for chat {chat_id}: {e}")
        await callback.answer("Не удалось обновить настройки.", show_alert=True)


@router.callback_query(PortfolioState.viewing_portfolio, F.data.startswith("p_sw_"))
async def handle_portfolio_switch_sub_account(callback: CallbackQuery, state: FSMContext):
    if not await is_user_allowed(callback): return
    user_id = callback.from_user.id
    target_sub_account = callback.data.replace("p_sw_", "")


    await display_portfolio(callback, state, user_id, target_sub_account, page=1)

    await callback.answer()
    logger.info(f"Пользователь {user_id} переключился на суб-счет '{target_sub_account}' (страница 1).")


@router.callback_query(PortfolioState.viewing_portfolio, F.data.startswith("p_pg_"))
async def handle_portfolio_sub_account_page(callback: CallbackQuery, state: FSMContext):
    if not await is_user_allowed(callback): return
    user_id = callback.from_user.id
    try:
        parts = callback.data.split("_")
        # p_pg_SUBNAME_PAGE -> parts[-1]=PAGE, parts[2:-1]=SUBNAME
        page = int(parts[-1])
        sub_account = "_".join(parts[2:-1])
        if not sub_account: raise IndexError("Sub-account name missing")
    except (ValueError, IndexError):
        logger.error(f"Некорректный callback пагинации портфеля: {callback.data}")
        await callback.answer("Ошибка пагинации.", show_alert=True)
        return

    state_data = await state.get_data()
    current_sub_account_state = state_data.get("current_sub_account")


    if sub_account != current_sub_account_state:
        logger.warning(f"Запрос пагинации для '{sub_account}', но текущий суб-счет '{current_sub_account_state}'. Переключаемся.")
        target_sub_account = sub_account # Switch to the requested sub-account
    else:
         target_sub_account = current_sub_account_state

    # Fetch portfolio data again to ensure it's current (might have changed since last view)
    portfolio_data = await get_portfolio(user_id)
    assets_in_current_sub = portfolio_data.get(target_sub_account, [])
    items_per_page=4
    total_pages = (len(assets_in_current_sub) + items_per_page - 1) // items_per_page if assets_in_current_sub else 0


    if page < 1 or (total_pages > 0 and page > total_pages):
        logger.warning(f"Запрошена неверная страница {page} для суб-счета '{target_sub_account}'. Всего страниц: {total_pages}.")
        await callback.answer("Неверная страница.", show_alert=True)
        return


    await display_portfolio(callback, state, user_id, target_sub_account, page=page)

    await callback.answer()
    logger.info(f"Пользователь {user_id} перешел на страницу {page} суб-счета '{target_sub_account}'.")

@router.callback_query(F.data.startswith("p_add_"))
async def handle_add_asset_start(callback: CallbackQuery, state: FSMContext):
    if not await is_user_allowed(callback): return
    target_sub_account = callback.data.replace("p_add_", "")

    user_id = callback.from_user.id
    sub_accounts = await get_sub_accounts(user_id)
    if target_sub_account not in sub_accounts:
        pass

    await state.update_data(target_sub_account=target_sub_account)

    await callback.message.answer("Выберите тип актива:", reply_markup=asset_type_keyboard())
    await state.set_state(PortfolioState.adding_asset_type)
    await callback.answer()
    logger.info(f"Пользователь {callback.from_user.id} начал добавление актива в суб-счет '{target_sub_account}'.")

@router.callback_query(F.data.startswith("p_rm_"))
async def handle_remove_asset_start(callback: CallbackQuery, state: FSMContext):
    if not await is_user_allowed(callback): return
    target_sub_account = callback.data.replace("p_rm_", "")
    user_id = callback.from_user.id

    portfolio_data = await get_portfolio(user_id)
    assets_in_sub_account = portfolio_data.get(target_sub_account, [])

    if not assets_in_sub_account:
        await callback.answer(f"В суб-счете '{target_sub_account}' нет активов для удаления.", show_alert=True)
        return

    await state.update_data(target_sub_account=target_sub_account)
    await callback.message.answer(f"Введите символ актива для удаления из суб-счета '{target_sub_account}':")
    await state.set_state(PortfolioState.removing_symbol)
    await callback.answer()
    logger.info(f"Пользователь {user_id} начал удаление актива из суб-счета '{target_sub_account}'.")


@router.callback_query(F.data == "cancel_remove")
async def handle_cancel_remove(callback: CallbackQuery, state: FSMContext):
    if not await is_user_allowed(callback): return
    user_id = callback.from_user.id
    data = await state.get_data()
    target_sub_account = data.get("target_sub_account", "Основной") # Default if state was weird


    await display_portfolio(callback, state, user_id, target_sub_account, page=1)

    await callback.answer("Удаление отменено")
    logger.info(f"Пользователь {user_id} отменил удаление актива.")