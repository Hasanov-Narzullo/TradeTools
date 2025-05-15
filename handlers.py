# handlers
from datetime import datetime

from aiogram import Router, types, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, ChatMemberUpdated, User, Chat, ChatMemberMember, ChatMemberAdministrator, ChatMemberOwner
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramAPIError

import asyncio
import functools
from typing import Union, Callable, Coroutine, Any
from bot import bot
from loguru import logger
from events_data import get_sample_events
from states import PortfolioState, AlertState, CalendarStates
from keyboards import main_menu, asset_type_keyboard, alert_condition_keyboard,  alerts_menu_keyboard, \
    quotes_menu_keyboard, calendar_menu_keyboard, pagination_keyboard, get_category_keyboard, get_pagination_keyboard, \
    settings_keyboard, portfolio_view_keyboard, confirm_delete_sub_account_keyboard, sub_account_select_keyboard_for_delete, \
    confirm_alert_keyboard 
from database import add_to_portfolio, get_portfolio, remove_from_portfolio, add_alert, get_alerts, remove_alert, \
    get_events, load_sample_events, get_or_create_chat_settings, update_chat_settings, get_sub_accounts, delete_sub_account
from api import get_stock_price, get_crypto_price, fetch_asset_price, get_stock_history, get_crypto_history, \
    get_stock_price_with_retry, get_market_data, fetch_asset_price_with_retry
from utils import format_portfolio, format_alerts, format_events, format_market_prices, format_market_overview, EVENT_TYPES, calculate_portfolio_summary


router = Router()
REQUIRED_CHANNEL_IDS = ["@offensivepoltergeist", "@LAD_Mayak"]

def common_handler_checks(check_subscription: bool = True):
    def decorator(func: Callable[[Union[Message, CallbackQuery], FSMContext], Coroutine[Any, Any, Any]]):
        @functools.wraps(func)
        async def wrapper(message_or_callback: Union[Message, CallbackQuery], state: FSMContext, *args, **kwargs):
            is_message = isinstance(message_or_callback, Message)
            user_id = message_or_callback.from_user.id

            target_message_for_context = message_or_callback if is_message else message_or_callback.message
            if not target_message_for_context:
                logger.error(f"Critical error: Cannot determine chat context for user {user_id} in handler {func.__name__}")
                if not is_message:
                    pass 
                return

            chat_id = target_message_for_context.chat.id
            message_id = message_or_callback.message_id if is_message else (target_message_for_context.message_id if target_message_for_context else None)

            if not is_message:
                try:
                    await message_or_callback.answer() 
                    logger.debug(f"Answered callback early for {message_or_callback.id} in {func.__name__}")
                except TelegramAPIError as e:
                    
                    if "query is too old" in str(e).lower() or "invalid query id" in str(e).lower():
                        logger.warning(f"Callback {message_or_callback.id} was already too old/invalid when trying to answer early in {func.__name__}. Error: {e}")
                         
                        return 
                    else:
                        logger.error(f"Error answering callback {message_or_callback.id} early in {func.__name__}: {e}")
            if not await is_user_allowed(message_or_callback):
                return

            if check_subscription:
                is_subscribed = await check_subscription_middleware(target_message_for_context, state) 
                if not is_subscribed:
                    return
                else:
                    logger.debug(f"Subscription check passed for user {user_id}. Handler {func.__name__} will proceed.")

            try:
                current_data = await state.get_data()
                if '_pending_action_details' in current_data:
                    pass 

                return await func(message_or_callback, state, *args, **kwargs)

            except Exception as e:
                logger.error(f"Error in handler {func.__name__}: {e}", exc_info=True)
                error_message = "Произошла ошибка. Пожалуйста, попробуйте позже."
                chat_id_for_error = chat_id 
                
                try:
                    if not is_message:
                         
                        await bot.send_message(chat_id_for_error, error_message)
                    else:
                        await message_or_callback.answer(error_message)

                except Exception as inner_e:
                    logger.error(f"Failed to send error message to user {user_id} in chat {chat_id_for_error}: {inner_e}")

                current_state_on_error = await state.get_state()
                if current_state_on_error is not None:
                    await state.clear()
                    logger.info(f"Cleared state for user {user_id} after error in {func.__name__}.")
                return 
        return wrapper
    return decorator

# Проверяет, подписан ли пользователь на канал.
async def check_subscription(user_id: int) -> bool:
    try:
        for channel_id in REQUIRED_CHANNEL_IDS:
            member = await bot.get_chat_member(chat_id=channel_id, user_id=user_id)
            if member.status not in ['member', 'administrator', 'creator']:
                logger.info(f"User {user_id} is not subscribed to {channel_id} (status: {member.status}).")
                return False
        logger.debug(f"User {user_id} is subscribed to all required channels.")
        return True
    except TelegramAPIError as e:
        logger.error(f"Error checking subscription for user {user_id}: {e}")
        if "user not found" in str(e).lower() or "chat not found" in str(e).lower():
            return False
        elif "bot was blocked by the user" in str(e).lower():
            return False
        
        return False
    except Exception as e:
        logger.error(f"Unexpected error checking subscription for user {user_id}: {e}")
        return False

# Обработчик команды /start с проверкой подписки.
@router.message(Command("start"))
@common_handler_checks(check_subscription=True)
async def cmd_start(message: Message, state: FSMContext):
    user_id = message.from_user.id
    chat_id = message.chat.id
    chat_type = message.chat.type

    is_admin = await is_user_admin(chat_id, user_id) if chat_type != 'private' else False

    await message.answer("""
👋 Добро пожаловать!
Я ваш финансовый помощник. Здесь вы можете:
📊 Следить за Рынком.
💼 Управлять своим Портфелем и настраивать Алерты.
⚙️ Изменять Настройки.
ℹ️ Получить Помощь.
👇 Просто выберите нужный раздел в меню ниже, чтобы начать!
                        """, reply_markup=main_menu(chat_type, is_admin))
    logger.info(f"Пользователь {user_id} запустил бота (подписан).")

async def check_subscription_middleware(message: Message, state: FSMContext = None):
    user_id = message.from_user.id
    missing_channels = []
    buttons = []
    invite_links = {"@offensivepoltergeist": "https://t.me/+v7bqzQj9zW80OTEy", "@LAD_Mayak": "https://t.me/+Xr1d53rLKMBmNDYy"}
    number_emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]

    logger.debug(f"Checking subscription for user {user_id} for {REQUIRED_CHANNEL_IDS}")
    all_subscribed = True
    for i, channel_id in enumerate(REQUIRED_CHANNEL_IDS):
        is_member = False
        display_name = str(channel_id)
        link = invite_links.get(channel_id)
        try:
            member = await bot.get_chat_member(chat_id=channel_id, user_id=user_id)
            if member.status in ['member', 'administrator', 'creator']:
                is_member = True
            else:
                if not link:
                    try:
                        info = await bot.get_chat(channel_id)
                        display_name = info.title or str(channel_id)
                        link = info.invite_link or (f"https://t.me/{channel_id[1:]}" if isinstance(channel_id, str) and channel_id.startswith('@') else f"https://t.me/search?q={str(channel_id).replace('-100','').replace('@','')}")
                    except Exception as e:
                        logger.warning(f"Could not get info/link for {channel_id}: {e}. Using default.")
                        link = f"https://t.me/{channel_id[1:]}" if isinstance(channel_id, str) and channel_id.startswith('@') else f"https://t.me/search?q={str(channel_id).replace('-100','').replace('@','')}"
        except TelegramAPIError as e:
            logger.error(f"API Error checking subscription for user {user_id} in {channel_id}: {e}")
            if "bot was blocked by the user" in str(e).lower(): return False # Cannot proceed
        except Exception as e:
            logger.error(f"Unexpected Error checking subscription for user {user_id} in {channel_id}: {e}")

        if not is_member:
            all_subscribed = False
            try: info = await bot.get_chat(channel_id); display_name = info.title or str(channel_id)
            except Exception: display_name = str(channel_id)
            missing_channels.append(display_name)
            if link and isinstance(link, str):
                emoji = number_emojis[i] if i < len(number_emojis) else "➡️"
                buttons.append([InlineKeyboardButton(text=f"{emoji} Подписаться", url=link)])
            else:
                 logger.error(f"No valid invite link found/generated for {display_name} ({channel_id}). Link: {link}")

    if all_subscribed:
        logger.debug(f"User {user_id} subscribed to all.")
        return True
    else:
        buttons.append([InlineKeyboardButton(text="✅ Я подписался, проверить", callback_data="recheck_subscription")])
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        await message.answer("Пожалуйста, подпишитесь и нажмите кнопку 'Я подписался' ниже.", reply_markup=keyboard)
        logger.info(f"User {user_id} prompted to subscribe: {missing_channels}")
        return False

async def display_portfolio(message_or_callback: Union[Message, CallbackQuery], state: FSMContext, user_id: int, target_sub_account: str, page: int = 1):
    is_message = isinstance(message_or_callback, Message)
    chat = message_or_callback.chat if is_message else message_or_callback.message.chat
    main_account_name = "Основной"

    full_portfolio_data = await get_portfolio(user_id)
    sub_accounts = await get_sub_accounts(user_id)


    if target_sub_account not in sub_accounts:
        logger.warning(f"Target sub-account '{target_sub_account}' not found for user {user_id}, defaulting to '{main_account_name}'.")
        target_sub_account = main_account_name


    total_value, total_purchase, total_pnl = await calculate_portfolio_summary(full_portfolio_data)
    prices_available = True

    assets_in_current_sub = full_portfolio_data.get(target_sub_account, [])
    items_per_page = 4
    total_items_in_sub = len(assets_in_current_sub)
    total_pages = (total_items_in_sub + items_per_page - 1) // items_per_page if total_items_in_sub > 0 else 1


    if page < 1: page = 1
    if page > total_pages: page = total_pages

    page_assets_with_prices = []
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


    formatted_portfolio = format_portfolio(
        page_assets_with_prices,
        page=page,
        total_pages=total_pages,
        total_portfolio_value=total_value,
        total_portfolio_pnl=total_pnl,
        prices_available_overall=prices_available
    )

    await state.set_state(PortfolioState.viewing_portfolio)
    await state.update_data(current_sub_account=target_sub_account, current_page=page)

    message_text = f"💼 Портфель: Суб-счет '{target_sub_account}'\n\n{formatted_portfolio}"
    reply_markup = portfolio_view_keyboard(sub_accounts, target_sub_account, page, total_pages)

    target_message = message_or_callback if is_message else message_or_callback.message
    if not target_message:
        logger.error(f"Cannot display portfolio for user {user_id}, message object is missing.")
        if not is_message: await message_or_callback.answer("Ошибка отображения портфеля.", show_alert=True)
        return

    try:
        if is_message:
            await target_message.answer(message_text, reply_markup=reply_markup)
        else:
            if target_message.text != message_text or str(target_message.reply_markup) != str(reply_markup):
                await target_message.edit_text(message_text, reply_markup=reply_markup)
            else:
                await message_or_callback.answer()
    except TelegramAPIError as e:
        if "message is not modified" in str(e):
            if not is_message: await message_or_callback.answer()
        elif "message to edit not found" in str(e):
            logger.warning(f"Message to edit not found for portfolio view (user {user_id}). Sending new message.")
            await bot.send_message(target_message.chat.id, message_text, reply_markup=reply_markup)
            if not is_message: await message_or_callback.answer()
        else:
            logger.error(f"Failed to send/edit message for portfolio view: {e}")
            if not is_message:
                await message_or_callback.answer("Ошибка отображения.", show_alert=True)
            else:
                await target_message.answer("Произошла ошибка при отображении портфеля.")

@router.message(Command("help"))
@common_handler_checks()
async def cmd_help(message: Message):
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
@common_handler_checks()
async def cmd_quotes(message: Message, state: FSMContext):
    await message.answer("Выберите действие с котировками:", reply_markup=quotes_menu_keyboard())
    logger.info(f"Пользователь {message.from_user.id} запросил меню котировок через команду.")

# Обработчик выбора типа актива для котировок.
@router.callback_query(PortfolioState.selecting_asset_type)
@common_handler_checks()
async def select_asset_type(callback: CallbackQuery, state: FSMContext):
    await state.update_data(asset_type=callback.data)
    await callback.message.answer("Введите символ актива (например, AAPL или BTC/USDT):")
    await state.set_state(PortfolioState.selecting_symbol)
    

# Обработчик ввода символа для получения котировок.
@router.message(PortfolioState.selecting_symbol)
@common_handler_checks()
async def get_quote(message: Message, state: FSMContext):
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
@router.callback_query(PortfolioState.adding_asset_type, F.data.in_(['stock', 'crypto']))
@common_handler_checks()
async def add_asset_type(callback: CallbackQuery, state: FSMContext):
    asset_type = callback.data
    await state.update_data(asset_type=asset_type)
    
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_portfolio_view")] 
    ])

    try:
        await callback.message.edit_text(
            f"Тип актива: {'Акции' if asset_type == 'stock' else 'Криптовалюты'}.\n"
            "Введите символ актива (например, AAPL или BTC/USDT):",
            reply_markup=markup
        )
    except TelegramAPIError as e:
         if "message is not modified" not in str(e): logger.error(f"Error editing message in add_asset_type: {e}")
         
    await state.set_state(PortfolioState.adding_symbol)


# Обработчик ввода символа актива для добавления в портфель.
@router.message(PortfolioState.adding_symbol)
@common_handler_checks()
async def add_symbol(message: Message, state: FSMContext):
    user_id = message.from_user.id
    symbol = message.text.strip().upper()
    data = await state.get_data()
    asset_type = data.get("asset_type")
    target_sub_account = data.get("target_sub_account")

    if not asset_type or not target_sub_account:
        await message.answer("Ошибка состояния. Начните заново /start.")
        await state.clear()
        return

    back_markup = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_add_asset_type")]])

    is_valid = False
    if asset_type == "stock": is_valid = bool(symbol.isalnum()) or symbol.endswith(".ME") or '.' in symbol
    elif asset_type == "crypto": is_valid = '/' in symbol
    if symbol.startswith('/') or not is_valid:
        await message.answer(f"Недопустимый символ '{symbol}'. Попробуйте снова или нажмите 'Назад'.", reply_markup=back_markup)
        return

    msg_to_delete = message.message_id
    try: await bot.delete_message(message.chat.id, msg_to_delete)
    except TelegramAPIError: pass

    price = await fetch_asset_price_with_retry(symbol, asset_type)
    if price is None:
        await bot.send_message(message.chat.id, f"Не удалось проверить {symbol}. Проверьте символ или попробуйте позже.", reply_markup=back_markup)
        return

    await state.update_data(symbol=symbol)
    await bot.send_message(message.chat.id, f"Актив: {symbol}\nВведите количество:", reply_markup=back_markup)
    await state.set_state(PortfolioState.adding_amount)
    logger.info(f"{user_id} entered symbol {symbol} for sub-account '{target_sub_account}'.")

# Обработчик ввода количества актива.
@router.message(PortfolioState.adding_amount)
@common_handler_checks()
async def add_amount(message: Message, state: FSMContext):
    chat_id = message.chat.id
    msg_to_delete = message.message_id
    back_markup = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_add_symbol")]])
    try: await bot.delete_message(chat_id, msg_to_delete)
    except TelegramAPIError: pass
    try:
        amount = float(message.text.replace(',', '.'))
        if amount <= 0: raise ValueError("Amount must be positive")
        await state.update_data(amount=amount)
        await bot.send_message(chat_id, f"Количество: {amount:.2f}\nВведите цену покупки:", reply_markup=back_markup)
        await state.set_state(PortfolioState.adding_price)
        logger.info(f"{message.from_user.id} entered amount: {amount}")
    except ValueError:
        await bot.send_message(chat_id, "Введите положительное числовое значение количества.", reply_markup=back_markup)

# Обработчик ввода цены покупки.
@router.message(PortfolioState.adding_price)
@common_handler_checks()
async def add_price(message: Message, state: FSMContext):
    user_id = message.from_user.id
    msg_to_delete = message.message_id
    back_markup = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_add_amount")]]) # Assuming back from price goes to amount
    try: await bot.delete_message(message.chat.id, msg_to_delete)
    except TelegramAPIError: pass
    try:
        price = float(message.text.replace(',', '.'))
        if price < 0: raise ValueError("Price cannot be negative")
        data = await state.get_data()
        sub_account = data.get("target_sub_account", "Основной")
        asset_type = data.get("asset_type")
        symbol = data.get("symbol")
        amount = data.get("amount")
        if not all([sub_account, asset_type, symbol, amount is not None]):
            raise ValueError("Incomplete state data")

        await add_to_portfolio(user_id, sub_account, asset_type, symbol, amount, price)
        await message.answer(f"Актив {symbol} добавлен в '{sub_account}'!")
        logger.info(f"{user_id} added {amount} {symbol} at {price} to '{sub_account}'.")
        await display_portfolio(message, state, user_id, sub_account, page=1)
    except ValueError as e:
        logger.warning(f"{user_id} entered invalid price/state error: {message.text}, Error: {e}")
        await message.answer(f"Ошибка: {e}. Введите корректное число (цену покупки)." if "state" not in str(e) else "Ошибка состояния. Начните заново.", reply_markup=back_markup)
        if "state" in str(e): await state.clear()
    except Exception as e:
        logger.error(f"Error adding asset for {user_id}: {e}")
        await message.answer("Ошибка при добавлении актива. Попробуйте позже.")
        await state.clear()

@router.message(Command("set_alert"))
@common_handler_checks()
async def cmd_set_alert(message: Message, state: FSMContext):
    await message.answer("Выберите тип актива для алерта:", reply_markup=asset_type_keyboard())
    await state.set_state(AlertState.selecting_asset_type)
    logger.info(f"Пользователь {message.from_user.id} из чата {message.chat.id} начал настройку алерта.")

# Обработчик выбора типа актива для алерта.
@router.callback_query(AlertState.selecting_asset_type, F.data.in_(['stock', 'crypto']))
@common_handler_checks()
async def select_alert_asset_type(callback: CallbackQuery, state: FSMContext):
    asset_type = callback.data
    await state.update_data(asset_type=asset_type)
    
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_alerts_menu")]
    ])
    
    try:
        await callback.message.edit_text(
            f"Тип актива: {'Акции' if asset_type == 'stock' else 'Криптовалюты'}.\n"
            "Введите символ актива (например, AAPL или BTC/USDT):",
            reply_markup=markup
        )
    except TelegramAPIError as e:
        if "message is not modified" not in str(e): logger.error(f"Error editing message in select_alert_asset_type: {e}")

    await state.set_state(AlertState.selecting_symbol)

# Обработчик ввода символа для алерта.
@router.message(AlertState.selecting_symbol)
@common_handler_checks()
async def select_alert_symbol(message: Message, state: FSMContext):
    chat_id = message.chat.id
    user_id = message.from_user.id
    symbol = message.text.strip().upper()
    data = await state.get_data()
    asset_type = data.get("asset_type")
    if not asset_type: await message.answer("Ошибка состояния. Начните заново /start."); await state.clear(); return

    back_markup = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_alert_asset_type")]])
    is_valid = False
    if asset_type == "stock": is_valid = bool(symbol.isalnum()) or symbol.endswith(".ME") or '.' in symbol
    elif asset_type == "crypto": is_valid = '/' in symbol
    if symbol.startswith('/') or not is_valid:
        await message.answer(f"Недопустимый символ '{symbol}'. Попробуйте снова или нажмите 'Назад'.", reply_markup=back_markup)
        return

    msg_to_delete = message.message_id
    try: await bot.delete_message(chat_id, msg_to_delete)
    except TelegramAPIError: pass

    price = await fetch_asset_price_with_retry(symbol, asset_type)
    if price is None:
        await bot.send_message(chat_id, f"Не удалось проверить {symbol}. Проверьте символ или попробуйте позже.", reply_markup=back_markup)
        return

    await state.update_data(symbol=symbol)
    await bot.send_message(chat_id, f"Актив: {symbol}\nТек. цена: ${price:.2f}\nВведите целевую цену:", reply_markup=back_markup)
    await state.set_state(AlertState.selecting_price)
    logger.info(f"{user_id} entered symbol {symbol} for alert in chat {chat_id}.")

# Обработчик ввода целевой цены для алерта.
@router.message(AlertState.selecting_price)
@common_handler_checks()
async def select_alert_price(message: Message, state: FSMContext):
    chat_id = message.chat.id
    msg_to_delete = message.message_id
    back_markup = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_alert_symbol_input")]])
    try: await bot.delete_message(chat_id, msg_to_delete)
    except TelegramAPIError: pass
    try:
        target_price = float(message.text.replace(',', '.'))
        if target_price <= 0: raise ValueError("Target price must be positive")
        await state.update_data(target_price=target_price)
        await bot.send_message(chat_id, f"Целевая цена: ${target_price:.2f}\nВыберите условие:", reply_markup=alert_condition_keyboard(back_callback="back_to_alert_symbol_input"))
        await state.set_state(AlertState.selecting_condition)
        logger.info(f"{message.from_user.id} entered target price: {target_price} in chat {chat_id}")
    except ValueError:
        await bot.send_message(chat_id, "Введите положительное числовое значение цены.", reply_markup=back_markup)

# Обработчик выбора условия алерта (above или below).
@router.callback_query(AlertState.selecting_condition, F.data.in_({"above", "below"}))
@common_handler_checks()
async def select_alert_condition(callback: CallbackQuery, state: FSMContext):
    condition = callback.data
    data = await state.get_data()
    symbol, target_price, asset_type = data.get("symbol"), data.get("target_price"), data.get("asset_type")

    if not all([symbol, target_price is not None, asset_type]):
        await callback.message.answer("Ошибка состояния. Начните заново /start.")
        await state.clear()
        logger.error(f"Incomplete state in select_alert_condition for chat {callback.message.chat.id}: {data}")
        return

    await state.update_data(condition=condition)
    asset_type_str = 'Акция' if asset_type == 'stock' else 'Криптовалюта'
    condition_str = 'выше' if condition == 'above' else 'ниже'
    text = f"Подтвердите алерт:\nАктив: {symbol} ({asset_type_str})\nЦелевая цена: ${target_price:.2f}\nУсловие: {condition_str}"
    try:
        await callback.message.edit_text(text, reply_markup=confirm_alert_keyboard())
    except TelegramAPIError as e:
        if "message is not modified" not in str(e): logger.error(f"Error editing confirm alert message: {e}")
    logger.info(f"{callback.from_user.id} selected condition {condition} for {symbol}. Waiting confirmation.")

@router.message(Command("calendar"))
@common_handler_checks()
async def show_calendar(message: Message, state: FSMContext):
    await message.answer("Выберите категорию событий:", reply_markup=get_category_keyboard())
    await state.set_state(CalendarStates.viewing_calendar)
    logger.info(f"Пользователь {message.from_user.id} запросил календарь событий.")

@router.message(PortfolioState.removing_symbol)
@common_handler_checks()
async def handle_remove_asset_symbol_from_subaccount(message: Message, state: FSMContext):
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
@common_handler_checks()
async def cmd_market(message: Message):
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

async def cancel_and_go_back(message_or_callback: Union[Message, CallbackQuery], state: FSMContext):
    current_state_str = await state.get_state()
    user_id = message_or_callback.from_user.id
    is_message = isinstance(message_or_callback, Message)
    target_message = message_or_callback if is_message else message_or_callback.message
    
    
    if not target_message:
        logger.error(f"Cannot perform cancel for user {user_id}, message object is missing.")
        if not is_message:
            try:
                await message_or_callback.answer("Ошибка при отмене.", show_alert=True)
            except Exception as e:
                logger.error(f"Failed to answer callback during cancel with missing message: {e}")
        await state.clear() 
        return

    chat_id = target_message.chat.id
    chat_type = target_message.chat.type
    
    is_admin = await is_user_admin(chat_id, user_id) if chat_type != 'private' else False

    logger.info(f"User {user_id} initiated cancel from state: {current_state_str}.")

    data_before_clear = await state.get_data()
    await state.clear()
    logger.debug(f"State cleared for user {user_id} due to cancel. Data before clear: {data_before_clear}")

    back_message = "Главное меню:"
    back_markup = main_menu(chat_type, is_admin)

    if current_state_str:
        if current_state_str.startswith(PortfolioState.__name__) and current_state_str != PortfolioState.viewing_portfolio.state:
            logger.debug(f"Cancel context: Portfolio process ({current_state_str}). Returning to portfolio view.")
            await display_portfolio(message_or_callback, state, user_id, data_before_clear.get("current_sub_account", "Основной"), page=data_before_clear.get("current_page", 1))
            if not is_message: await message_or_callback.answer("Действие отменено.")
            return

        elif current_state_str.startswith(AlertState.__name__):
            origin = data_before_clear.get('alert_origin')
            
            if origin == 'portfolio':
                logger.debug(f"Cancel context: Alerts ({current_state_str}) from Portfolio. Returning to portfolio view.")
                await display_portfolio(message_or_callback, state, user_id, data_before_clear.get("current_sub_account", "Основной"), page=data_before_clear.get("current_page", 1))
                if not is_message: await message_or_callback.answer("Действие отменено.")
                return
            else:
                logger.debug(f"Cancel context: Alerts ({current_state_str}) from direct access/unknown. Returning to alerts menu.")
                back_message = "Действие отменено. Меню Алертов:"
                back_markup = alerts_menu_keyboard()

        elif current_state_str.startswith(CalendarStates.__name__):
            logger.debug(f"Cancel context: Calendar ({current_state_str}). Returning to calendar category selection.")
            back_message = "Действие отменено. Выберите категорию событий:"
            back_markup = get_category_keyboard() 

        else:
            logger.debug(f"Cancel context: Viewing state ({current_state_str}) or unknown. Returning to main menu.")
            back_message = "Действие отменено. Возврат в главное меню." 

    else:
        logger.debug(f"Cancel context: No active state. Returning to main menu.")
        back_message = "Главное меню:"

    try:
        if is_message:
            await target_message.answer(back_message, reply_markup=back_markup)

        else:
            if target_message.text != back_message or str(target_message.reply_markup) != str(back_markup):
                await target_message.edit_text(back_message, reply_markup=back_markup)
            else:
                await message_or_callback.answer("Отменено")
                return
            await message_or_callback.answer("Отменено") 
            
    except TelegramAPIError as e:
        logger.warning(f"Could not send/edit cancel confirmation for user {user_id}: {e}. State was: {current_state_str}")
        if "message is not modified" in str(e):
            if not is_message: await message_or_callback.answer("Отменено")
        elif "message to edit not found" in str(e) or "message can't be edited" in str(e):
            
            await bot.send_message(chat_id, back_message, reply_markup=back_markup)
            if not is_message: await message_or_callback.answer("Отменено") 
        else:
            if not is_message: await message_or_callback.answer("Ошибка при отмене", show_alert=True)
    except Exception as e:
        logger.error(f"Unexpected error during cancel_and_go_back for user {user_id}: {e}")
        if not is_message: await message_or_callback.answer("Ошибка при отмене", show_alert=True)

@router.callback_query(F.data == "alerts_from_portfolio")
@common_handler_checks()
async def handle_alerts_from_portfolio(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id
    logger.info(f"User {user_id} entering alerts menu from portfolio context (Chat: {chat_id}).")

    await state.update_data(alert_origin='portfolio')

    alerts = await get_alerts(chat_id)
    try:
        if not alerts:
             await callback.message.edit_text(
                "В этом чате нет установленных алертов. 😔\n"
                "Используйте кнопку 'Добавить алерт', чтобы добавить.",
                reply_markup=alerts_menu_keyboard()
            )
        else:
             await callback.message.edit_text("Выберите действие с алертами:", reply_markup=alerts_menu_keyboard())

    except TelegramAPIError as e:
         if "message is not modified" not in str(e): logger.error(f"Error editing alerts menu message from portfolio: {e}")

    

@router.message(Command("cancel"))
@common_handler_checks()
async def cmd_cancel(message: Message, state: FSMContext):
    await cancel_and_go_back(message, state)


@router.message(Command("alerts"))
@common_handler_checks()
async def cmd_alerts(message: Message):
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
@common_handler_checks()
async def cmd_remove_alert(message: Message, state: FSMContext):
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
@common_handler_checks()
async def handle_quotes_menu(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("Выберите действие с котировками:", reply_markup=quotes_menu_keyboard())
    
    logger.info(f"Пользователь {callback.from_user.id} открыл меню котировок.")


@router.callback_query(F.data == "quotes")
@common_handler_checks()
async def handle_quotes(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("Выберите тип актива:", reply_markup=asset_type_keyboard())
    await state.set_state(PortfolioState.selecting_asset_type)
    
    logger.info(f"Пользователь {callback.from_user.id} запросил котировки.")

@router.message(Command("portfolio"))
@router.callback_query(F.data == "portfolio_view_default")
@common_handler_checks()
async def handle_portfolio_view_start(message_or_callback: Union[Message, CallbackQuery], state: FSMContext):
    is_message = isinstance(message_or_callback, Message)
    user_id = message_or_callback.from_user.id
    main_account_name = "Основной"

    if not is_message:
        try:
            await message_or_callback.message.edit_text("⏳ Загрузка портфеля...", reply_markup=None)
        except Exception as e:
            logger.warning(f"Could not edit to loading message for portfolio view: {e}")

    full_portfolio_data = await get_portfolio(user_id)
    sub_accounts = await get_sub_accounts(user_id)

    target_sub_account = main_account_name

    if not full_portfolio_data.get(main_account_name):
        first_non_empty_sub_account = None
        for acc_name in sub_accounts:
            if acc_name != main_account_name and full_portfolio_data.get(acc_name):
                first_non_empty_sub_account = acc_name
                break
        if first_non_empty_sub_account:
            target_sub_account = first_non_empty_sub_account
            logger.info(f"Основной суб-счет пуст, переключаемся на первый непустой: {target_sub_account}")

    await display_portfolio(message_or_callback, state, user_id, target_sub_account, page=1)

    logger.info(f"Пользователь {user_id} открыл портфель (суб-счет: {target_sub_account}).")


@router.callback_query(F.data == "portfolio_add_sub_account_start")
@common_handler_checks()
async def handle_add_sub_account_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите имя для нового суб-счета:")
    await state.set_state(PortfolioState.adding_sub_account_new_name)
    logger.info(f"Пользователь {callback.from_user.id} начал создание нового суб-счета.")

@router.message(PortfolioState.adding_sub_account_new_name)
@common_handler_checks()
async def handle_add_sub_account_name(message: Message, state: FSMContext):
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
@common_handler_checks()
async def handle_remove_sub_account_select_for_delete(callback: CallbackQuery, state: FSMContext):
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

@router.callback_query(F.data.startswith("p_conf_del_"))
@common_handler_checks()
async def handle_confirm_sub_account_delete(callback: CallbackQuery, state: FSMContext):
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

    

@router.callback_query(F.data == "portfolio_remove_sub_account_start")
@common_handler_checks()
async def handle_remove_sub_account_start(callback: CallbackQuery, state: FSMContext):
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
    
    logger.info(f"Пользователь {user_id} начал удаление суб-счета.")


@router.callback_query(F.data == "set_alert")
@common_handler_checks()
async def handle_set_alert(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.message.edit_text(
            "Выберите тип актива для алерта:",
            reply_markup=asset_type_keyboard(back_callback="alerts_menu") 
        )
    except TelegramAPIError as e:
         if "message is not modified" not in str(e): logger.error(f"Error editing message in handle_set_alert: {e}")

    await state.set_state(AlertState.selecting_asset_type)
    
    logger.info(f"Пользователь {callback.from_user.id} начал установку алерта в чате {callback.message.chat.id} (из меню).")


@router.callback_query(F.data == "help")
@common_handler_checks()
async def handle_help(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id
    chat_type = callback.message.chat.type
    is_admin = await is_user_admin(chat_id, user_id) if chat_type != 'private' else False
    help_text = """
📋 *Список доступных действий:*

- 📊 Рынок: Посмотреть котировки и календарь событий
- 💼 Портфель: Просмотреть/управлять портфелем, суб-счетами и алертами
- ⚙️ Настройки: Управление разрешениями (в группах)
- ℹ️ Помощь: Показать это сообщение

📝 *Инструкция:*
1. Используйте кнопки для навигации.
2. Следуйте подсказкам бота для ввода данных (символы, цены, количество).
3. Для отмены ввода данных используйте команду /cancel.
"""
    try:
        await callback.message.edit_text(help_text, reply_markup=main_menu(chat_type, is_admin), parse_mode="Markdown")
    except TelegramAPIError as e:
         if "message is not modified" not in str(e): logger.error(f"Error editing help message: {e}")

    
    logger.info(f"Пользователь {callback.from_user.id} запросил помощь.")

@router.callback_query(F.data == "market_submenu")
@common_handler_checks()
async def handle_market_submenu(callback: CallbackQuery, state: FSMContext):
    from keyboards import market_submenu_keyboard
    try:
        await callback.message.edit_text(
            "Выберите раздел:",
            reply_markup=market_submenu_keyboard()
        )
    except TelegramAPIError as e:
        if "message is not modified" not in str(e):
            logger.error(f"Error editing message for market submenu: {e}")
    
    logger.info(f"User {callback.from_user.id} opened market submenu.")

@common_handler_checks()
async def handle_remove_asset_prompt(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("Эта кнопка устарела. Используйте меню 'Портфель' -> '🗑 Удалить отсюда'.")
    
    logger.info(f"Пользователь {callback.from_user.id} нажал устаревшую кнопку 'Удалить актив'.")


@router.callback_query(F.data == "alerts")
@common_handler_checks()
async def handle_alerts(callback: CallbackQuery):
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id

    alerts = await get_alerts(chat_id)

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


    


@router.callback_query(F.data == "remove_alert")
@common_handler_checks()
async def handle_remove_alert_prompt(callback: CallbackQuery, state: FSMContext):
    chat_id = callback.message.chat.id
    alerts = await get_alerts(chat_id)
    if not alerts:
        await callback.answer("В этом чате нет алертов для удаления.", show_alert=True)
        return

    await callback.message.answer("Введите ID алерта из этого чата, который хотите удалить (ID можно увидеть в 'Текущие алерты'):")
    await state.set_state(AlertState.removing_alert)
    
    logger.info(f"Пользователь {callback.from_user.id} начал удаление алерта в чате {chat_id}.")

@router.callback_query(F.data == "confirm_alert")
@common_handler_checks()
async def confirm_alert(callback: CallbackQuery, state: FSMContext):
    chat_id = callback.message.chat.id
    user_id = callback.from_user.id
    chat_type = callback.message.chat.type
    is_admin = await is_user_admin(chat_id, user_id) if chat_type != 'private' else False
    menu = main_menu(chat_type, is_admin)
    data = await state.get_data()
    symbol, target_price, condition, asset_type = data.get("symbol"), data.get("target_price"), data.get("condition"), data.get("asset_type")

    if not all([symbol, target_price is not None, condition, asset_type]):
        logger.error(f"{user_id} tried confirming alert with incomplete data: {data} in chat {chat_id}")
        await callback.answer("Ошибка данных", show_alert=True)
        try: await callback.message.edit_text("Ошибка установки алерта (нет данных). Начните заново.", reply_markup=menu)
        except TelegramAPIError as e: pass
        await state.clear()
        return
    try:
        await add_alert(chat_id, asset_type, symbol, target_price, condition)
        await callback.answer("Алерт установлен!", show_alert=False)
        await callback.message.edit_text(f"✅ Алерт установлен для {symbol}!", reply_markup=menu)
        logger.info(f"{user_id} set alert for {symbol} in chat {chat_id}.")
    except Exception as e:
        logger.error(f"Error adding alert to DB for chat {chat_id}, {symbol}: {e}")
        await callback.answer("Ошибка сохранения", show_alert=True)
        await callback.message.edit_text("Ошибка при сохранении алерта. Попробуйте снова.", reply_markup=menu)
    finally:
        await state.clear()

# Обработчик кнопки 'Отмена'.
@router.callback_query(F.data == "cancel")
@common_handler_checks()
async def handle_cancel(callback: CallbackQuery, state: FSMContext):
    current_state = await state.get_state()
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id
    chat_type = callback.message.chat.type
    is_admin = await is_user_admin(chat_id, user_id) if chat_type != 'private' else False

    await state.clear()
    message_text = "Действие отменено."
    reply_markup = main_menu(chat_type, is_admin)

    try:
        if callback.message:
             await callback.message.edit_text(message_text, reply_markup=reply_markup)
    except TelegramAPIError as e:
        if "message to edit not found" in str(e) or "message can't be edited" in str(e):
            await bot.send_message(chat_id, message_text, reply_markup=reply_markup)
        elif "message is not modified" not in str(e):
            logger.error(f"Error editing cancel message: {e}")
            await bot.send_message(chat_id, message_text, reply_markup=reply_markup)

    await callback.answer("Отменено")
    logger.info(f"Пользователь {user_id} отменил действие ({current_state}).")


@router.callback_query(F.data == "settings_open")
@common_handler_checks()
async def handle_settings_open(callback: CallbackQuery, state: FSMContext):
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

    
    logger.info(f"User {user_id} opened settings via button in group {chat_id} (Admin: {can_change}).")


@router.callback_query(F.data.startswith("confirm_remove_"))
@common_handler_checks()
async def handle_confirm_remove_asset_from_subaccount(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    try:
        parts = callback.data.split("_")
        if len(parts) < 4: raise IndexError("Incorrect callback format")
        symbol_to_remove = parts[-1]
        sub_account_name = "_".join(parts[2:-1])
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


    


@router.callback_query(F.data == "alerts_menu")
@common_handler_checks()
async def handle_alerts_menu(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("Выберите действие с алертами:", reply_markup=alerts_menu_keyboard())
    
    logger.info(f"Пользователь {callback.from_user.id} открыл меню алертов.")


@router.callback_query(F.data == "current_alerts")
@common_handler_checks()
async def handle_current_alerts(callback: CallbackQuery, state: FSMContext):
    chat_id = callback.message.chat.id
    alerts = await get_alerts(chat_id)
    if not alerts:
        await callback.message.answer(
            "В этом чате нет установленных алертов. 😔",
            reply_markup=alerts_menu_keyboard()
        )
        logger.info(f"Пользователь {callback.from_user.id} запросил текущие алерты в чате {chat_id} (пусто).")
        
        return

    formatted_alerts, total_pages = format_alerts(alerts, page=1)
    try:
        await callback.message.edit_text(
            formatted_alerts,
            reply_markup=alerts_menu_keyboard(current_page=1, total_pages=total_pages)
        )
    except TelegramAPIError as e:
         if "message is not modified" not in str(e): logger.error(f"Error editing current alerts message: {e}")

    
    logger.info(f"Пользователь {callback.from_user.id} запросил текущие алерты в чате {chat_id} (страница 1).")


@router.message(AlertState.removing_alert)
@common_handler_checks()
async def handle_remove_alert_id(message: Message, state: FSMContext):
    chat_id = message.chat.id
    user_id = message.from_user.id
    menu = alerts_menu_keyboard()
    try:
        alert_id = int(message.text)
        alerts = await get_alerts(chat_id)
        if not any(a[0] == alert_id for a in alerts):
             await message.answer(f"Алерт с ID {alert_id} не найден в этом чате.", reply_markup=menu)
             logger.warning(f"Alert ID {alert_id} not found for chat {chat_id} (user {user_id})")
        else:
            await remove_alert(alert_id)
            await message.answer(f"Алерт ID {alert_id} удален.", reply_markup=menu)
            logger.info(f"{user_id} removed alert ID {alert_id} from chat {chat_id}")
        await state.clear()
    except ValueError:
        await message.answer("Введите числовой ID алерта.", reply_markup=menu)
    except Exception as e:
        logger.error(f"Error removing alert {message.text} for chat {chat_id}: {e}")
        await message.answer("Ошибка при удалении алерта.", reply_markup=menu)
        await state.clear()

# Обработчик кнопки 'Назад' в меню алертов.
@router.callback_query(F.data == "main_menu")
@common_handler_checks()
async def handle_main_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id
    chat_type = callback.message.chat.type
    is_admin = await is_user_admin(chat_id, user_id) if chat_type != 'private' else False
    try:
        await callback.message.edit_text("Главное меню:", reply_markup=main_menu(chat_type, is_admin))
    except TelegramAPIError as e:
        if "message is not modified" not in str(e): logger.error(f"Error editing main menu message: {e}")
    
    logger.info(f"Пользователь {callback.from_user.id} вернулся в главное меню.")

@router.callback_query(F.data == "portfolio_prices")
@common_handler_checks()
async def handle_portfolio_prices(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    portfolio_data = await get_portfolio(user_id)
    menu = quotes_menu_keyboard()
    if not portfolio_data:
        await callback.answer("Портфель пуст.", show_alert=True)
        try: await callback.message.edit_text("Портфель пуст. 😔", reply_markup=menu)
        except TelegramAPIError: pass
        logger.info(f"{user_id} requested portfolio prices (empty).")
        return

    tasks, asset_symbols = [], []
    for assets in portfolio_data.values():
        for asset in assets:
            try: tasks.append(fetch_asset_price_with_retry(asset['symbol'], asset['asset_type'])); asset_symbols.append(asset['symbol'])
            except (KeyError, ValueError, TypeError) as e: logger.error(f"Error processing asset {asset}: {e}")

    if not tasks: await callback.answer("Нет активов для запроса цен.", show_alert=True); return

    logger.info(f"Requesting prices for {len(tasks)} assets for portfolio prices...")
    current_prices = await asyncio.gather(*tasks)
    logger.info("Portfolio prices fetched.")

    priced_assets = [{'symbol': asset_symbols[i], 'current_price': price} for i, price in enumerate(current_prices)]
    formatted_text = format_market_prices(priced_assets)
    try:
        await callback.message.edit_text(formatted_text, reply_markup=menu)
    except TelegramAPIError as e:
         if "message is not modified" not in str(e): logger.error(f"Error editing portfolio prices message: {e}")
    logger.info(f"{user_id} requested portfolio prices.")

@router.callback_query(F.data.startswith("alerts_page_"))
@common_handler_checks()
async def handle_alerts_page(callback: CallbackQuery, state: FSMContext):
    page = int(callback.data.replace("alerts_page_", ""))
    chat_id = callback.message.chat.id
    alerts = await get_alerts(chat_id)
    if not alerts:
        await callback.message.answer(
            "В этом чате нет установленных алертов. 😔",
            reply_markup=alerts_menu_keyboard()
        )
        logger.info(f"Пользователь {callback.from_user.id} запросил текущие алерты в чате {chat_id} (пусто).")
        
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

    
    logger.info(f"Пользователь {callback.from_user.id} перешел на страницу алертов {page} в чате {chat_id}.")


@router.callback_query(lambda c: c.data.startswith("calendar_category_"))
@common_handler_checks()
async def handle_category_selection(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    try:
        category = callback.data.split("_")[-1]
        await state.update_data(category=category, current_page=1)

        portfolio_symbols = set()
        if category == "portfolio":
            portfolio_data = await get_portfolio(user_id)
            for sub_account, assets in portfolio_data.items():
                for asset in assets:
                    portfolio_symbols.add(asset['symbol'])
            if not portfolio_symbols:
                await callback.message.edit_text("Ваш портфель пуст, нет событий для отображения по портфелю.", reply_markup=get_category_keyboard())
                
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
@common_handler_checks()
async def handle_calendar_page(callback: CallbackQuery, state: FSMContext):
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
        
        logger.info(f"Пользователь {user_id} перешел на страницу календаря {page} (категория: {category}).")
    except Exception as e:
        logger.error(f"Ошибка при пагинации календаря: {e}", exc_info=True)
        await callback.message.edit_text(
            "Произошла ошибка при пагинации.",
            reply_markup=get_category_keyboard()
        )
        await callback.answer("Ошибка", show_alert=True)


@router.message(Command("load_sample_events"))
@common_handler_checks()
async def load_sample_events_handler(message: types.Message):
    try:
        await load_sample_events()
        await message.answer("Пример событий успешно загружен. Используйте меню 'Календарь' для просмотра.")
    except Exception as e:
        logger.error(f"Ошибка при загрузке примеров событий: {e}")
        await message.answer("Произошла ошибка при загрузке примеров событий.")

# Обработчик выбора категории с корректной сортировкой по дате.
@router.callback_query(lambda c: c.data.startswith("calendar_category_"))
@common_handler_checks()
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
        
        logger.info(
            f"Пользователь {user_id} запросил события (категория: {category}, страница 1, событий: {len(filtered_events)}).")
    except Exception as e:
        logger.error(f"Ошибка при обработке категории: {e}")
        await callback.message.edit_text(
            "Произошла ошибка при обработке категории.",
            reply_markup=calendar_menu_keyboard()
        )
        

# Обработчик пагинации с сохранением отфильтрованных событий.
@router.callback_query(lambda c: c.data.startswith("calendar_prev_") or c.data.startswith("calendar_next_"))
@common_handler_checks()
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
        
        logger.info(f"Пользователь {user_id} перешел на страницу календаря {new_page} (фильтр: {filter_type}).")
    except Exception as e:
        logger.error(f"Ошибка при пагинации: {e}")
        error_text = "Произошла ошибка при пагинации."
        if current_message_text != error_text:
            await callback.message.edit_text(
                error_text,
                reply_markup=calendar_menu_keyboard()
            )
        

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
@common_handler_checks()
async def cmd_settings(message: Message):
    user_id = message.from_user.id
    chat_id = message.chat.id

    if message.chat.type == 'private':
        await message.answer("Настройки разрешений доступны только в групповых чатах.")
        logger.info(f"User {user_id} tried /settings in private chat {chat_id}.")
        return
    
    if not await is_user_allowed(message): return

    can_change = await is_user_admin(chat_id, user_id)

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
@common_handler_checks()
async def handle_settings_change(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    try:
        parts = callback.data.split('_')
        action = parts[2]
        chat_id = int(parts[3])
    except (IndexError, ValueError):
        logger.error(f"Invalid settings callback data: {callback.data}")
        await callback.answer("Ошибка обработки данных.", show_alert=True)
        return

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
        await callback.answer("Не удалось обновить настройки.", show_alert=True)
    except Exception as e:
        logger.error(f"Failed to update settings for chat {chat_id}: {e}")
        await callback.answer("Не удалось обновить настройки.", show_alert=True)


@router.callback_query(PortfolioState.viewing_portfolio, F.data.startswith("p_sw_"))
@common_handler_checks()
async def handle_portfolio_switch_sub_account(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    target_sub_account = callback.data.replace("p_sw_", "")

    await display_portfolio(callback, state, user_id, target_sub_account, page=1)

    
    logger.info(f"Пользователь {user_id} переключился на суб-счет '{target_sub_account}' (страница 1).")


@router.callback_query(PortfolioState.viewing_portfolio, F.data.startswith("p_pg_"))
@common_handler_checks()
async def handle_portfolio_sub_account_page(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    try:
        parts = callback.data.split("_")
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
        target_sub_account = sub_account
    else:
        target_sub_account = current_sub_account_state

    portfolio_data = await get_portfolio(user_id)
    assets_in_current_sub = portfolio_data.get(target_sub_account, [])
    items_per_page=4
    total_pages = (len(assets_in_current_sub) + items_per_page - 1) // items_per_page if assets_in_current_sub else 0


    if page < 1 or (total_pages > 0 and page > total_pages):
        logger.warning(f"Запрошена неверная страница {page} для суб-счета '{target_sub_account}'. Всего страниц: {total_pages}.")
        await callback.answer("Неверная страница.", show_alert=True)
        return


    await display_portfolio(callback, state, user_id, target_sub_account, page=page)

    
    logger.info(f"Пользователь {user_id} перешел на страницу {page} суб-счета '{target_sub_account}'.")

@router.callback_query(F.data.startswith("p_add_"))
@common_handler_checks()
async def handle_add_asset_start(callback: CallbackQuery, state: FSMContext):
    target_sub_account = callback.data.replace("p_add_", "")

    user_id = callback.from_user.id
    sub_accounts = await get_sub_accounts(user_id)
    if target_sub_account not in sub_accounts:
        logger.warning(f"Attempt to add asset to non-existent sub-account '{target_sub_account}' by user {user_id}. Allowing creation flow.")
        
    data = await state.get_data()
    current_page = data.get('current_page', 1)
    
    await state.update_data(target_sub_account=target_sub_account, portfolio_return_page=current_page)

    try:
        await callback.message.edit_text(
            f"Добавление в суб-счет: '{target_sub_account}'\nВыберите тип актива:",
            reply_markup=asset_type_keyboard(back_callback="back_to_portfolio_view")
        )
    except TelegramAPIError as e:
         if "message is not modified" not in str(e): logger.error(f"Error editing message in handle_add_asset_start: {e}")
         
    await state.set_state(PortfolioState.adding_asset_type)
    
    logger.info(f"Пользователь {callback.from_user.id} начал добавление актива в суб-счет '{target_sub_account}'.")

@router.callback_query(F.data.startswith("p_rm_"))
@common_handler_checks()
async def handle_remove_asset_start(callback: CallbackQuery, state: FSMContext):
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
    
    logger.info(f"Пользователь {user_id} начал удаление актива из суб-счета '{target_sub_account}'.")


@router.callback_query(F.data == "cancel_remove")
@common_handler_checks()
async def handle_cancel_remove(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    data = await state.get_data()
    target_sub_account = data.get("target_sub_account", "Основной") # Default if state was weird


    await display_portfolio(callback, state, user_id, target_sub_account, page=1)

    await callback.answer("Удаление отменено")
    logger.info(f"Пользователь {user_id} отменил удаление актива.")


@router.callback_query(F.data == "recheck_subscription")
async def handle_recheck_subscription(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    logger.info(f"User {user_id} clicked recheck_subscription.")
    if not callback.message:
        logger.warning(f"Cannot recheck subscription for user {user_id}, original message missing.")
        await callback.answer("Ошибка проверки. Попробуйте снова.", show_alert=True)
        return

    chat_id = callback.message.chat.id
    chat_type = callback.message.chat.type
    is_admin = await is_user_admin(chat_id, user_id) if chat_type != 'private' else False

    is_subscribed_now = await check_subscription_middleware(callback.message, state)

    if is_subscribed_now:
        logger.info(f"Subscription recheck successful for user {user_id}.")
        data = await state.get_data()
        pending_action = data.get('_pending_action_details')
        await state.update_data(_pending_action_details=None)

        try: await callback.message.delete()
        except TelegramAPIError as e: logger.error(f"Error deleting prompt message for {user_id}: {e}")

        await callback.answer("Спасибо за подписку! Выполняю...", show_alert=False)

        action_executed = False
        if pending_action:
            logger.info(f"Attempting to execute pending action for {user_id}: {pending_action}")
            action_type = pending_action.get('type')
            target_chat_id = pending_action.get('chat_id', chat_id)
            target_message_id = pending_action.get('message_id')

            try:
                if action_type == 'command':
                    command = pending_action.get('name', '').lstrip('/')
                    handler = dp.message_handlers.find(Command(command))
                    if handler:
                        
                        mock_message = types.Message(
                            message_id=target_message_id,
                            chat=types.Chat(id=target_chat_id, type=chat_type),
                            from_user=callback.from_user,
                            date=datetime.now(),
                            text=pending_action.get('name')
                        )

                        await handler.handler(mock_message, state)
                        action_executed = True
                    else: logger.warning(f"No handler found for pending command: {command}")

                elif action_type == 'callback':
                     callback_data = pending_action.get('data')
                     handler = dp.callback_query_handlers.find(F.data == callback_data)
                     if handler:
                         
                         mock_callback = types.CallbackQuery(
                            id=f"recheck_{callback.id}",
                            from_user=callback.from_user,
                            message=callback.message,
                            chat_instance=callback.chat_instance,
                            data=callback_data
                         )
                         if callback.message and target_message_id:
                            callback.message.message_id = target_message_id

                         await handler.handler(mock_callback, state)
                         action_executed = True
                     else: logger.warning(f"No handler found for pending callback: {callback_data}")

            except Exception as e:
                logger.error(f"Error auto-executing action {pending_action}: {e}", exc_info=True)

            if not action_executed:
                logger.warning(f"Could not auto-execute {pending_action}. Prompting user.")
                await bot.send_message(chat_id, "✅ Подписка подтверждена! Пожалуйста, повторите ваше действие.")
        else:
             logger.info(f"Subscription confirmed for {user_id}, no pending action found.")
             await bot.send_message(chat_id, "✅ Подписка подтверждена! Пожалуйста, повторите ваше действие.")
    else:
        await callback.answer("Пожалуйста, убедитесь, что вы подписались на все каналы.", show_alert=True)
        logger.info(f"User {user_id} failed recheck.")

@router.callback_query(F.data == "back_to_alerts_menu")
@common_handler_checks()
async def handle_back_to_alerts_menu(callback: CallbackQuery, state: FSMContext):
    
    await state.clear() 
    chat_id = callback.message.chat.id
    alerts = await get_alerts(chat_id)
    try:
        if not alerts:
             await callback.message.edit_text(
                "В этом чате нет установленных алертов. 😔\n"
                "Используйте кнопку 'Добавить алерт', чтобы добавить.",
                reply_markup=alerts_menu_keyboard()
            )
        else:
             await callback.message.edit_text("Меню Алертов:", reply_markup=alerts_menu_keyboard())
    except TelegramAPIError as e:
         if "message is not modified" not in str(e): logger.error(f"Error editing message in back_to_alerts_menu: {e}")


@router.callback_query(F.data == "back_to_alert_asset_type")
@common_handler_checks()
async def handle_back_to_alert_asset_type(callback: CallbackQuery, state: FSMContext):
    
    data = await state.get_data()
    origin = data.get('alert_origin')
    back_cb = "back_to_portfolio_view" if origin == 'portfolio' else "back_to_alerts_menu"
    
    try:
        await callback.message.edit_text(
            "Выберите тип актива для алерта:",
            reply_markup=asset_type_keyboard(back_callback=back_cb)
        )
        await state.set_state(AlertState.selecting_asset_type)
    except TelegramAPIError as e:
        if "message is not modified" not in str(e): logger.error(f"Error editing message in back_to_alert_asset_type: {e}")

@router.callback_query(F.data == "back_to_alert_symbol_input")
@common_handler_checks()
async def handle_back_to_alert_symbol_input(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    asset_type = data.get("asset_type")
    if not asset_type:
        await callback.answer("Ошибка состояния. Начните заново.", show_alert=True)
        await state.clear()
        await handle_back_to_alerts_menu(callback, state) 
        return

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_alert_asset_type")]
    ])

    try:
        await callback.message.edit_text(
            f"Тип актива: {'Акции' if asset_type == 'stock' else 'Криптовалюты'}.\n"
            "Введите символ актива (например, AAPL или BTC/USDT):",
            reply_markup=markup
        )
        await state.set_state(AlertState.selecting_symbol)
    except TelegramAPIError as e:
        if "message is not modified" not in str(e): logger.error(f"Error editing message in back_to_alert_symbol_input: {e}")


@router.callback_query(F.data == "back_to_alert_condition")
@common_handler_checks()
async def handle_back_to_alert_condition(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    target_price = data.get("target_price") 
    
    if target_price is None:
        await callback.answer("Ошибка состояния. Начните заново.", show_alert=True)
        await state.clear()
        await handle_back_to_alerts_menu(callback, state)
        return

    try:
        await callback.message.edit_text(
            f"Целевая цена: ${target_price:.2f}\nВыберите условие алерта:",
            reply_markup=alert_condition_keyboard(back_callback="back_to_alert_symbol_input")
        )
        await state.set_state(AlertState.selecting_condition)
    except TelegramAPIError as e:
        if "message is not modified" not in str(e): logger.error(f"Error editing message in back_to_alert_condition: {e}")


@router.callback_query(F.data == "back_to_portfolio_view")
@common_handler_checks()
async def handle_back_to_portfolio_view(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    data = await state.get_data()
    target_sub_account = data.get("target_sub_account", "Основной")
    page = data.get("portfolio_return_page", 1) 
    
    
    
    
    await state.set_state(PortfolioState.viewing_portfolio) 
    await display_portfolio(callback, state, user_id, target_sub_account, page=page)
    
    

@router.callback_query(F.data == "back_to_add_asset_type")
@common_handler_checks()
async def handle_back_to_add_asset_type(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    target_sub_account = data.get("target_sub_account")
    
    if not target_sub_account:
         await callback.answer("Ошибка состояния. Начните заново.", show_alert=True)
         await state.clear()
         await handle_back_to_portfolio_view(callback, state) 
         return

    try:
        await callback.message.edit_text(
            f"Добавление в суб-счет: '{target_sub_account}'\nВыберите тип актива:",
            reply_markup=asset_type_keyboard(back_callback="back_to_portfolio_view")
        )
        await state.set_state(PortfolioState.adding_asset_type)
    except TelegramAPIError as e:
         if "message is not modified" not in str(e): logger.error(f"Error editing message in back_to_add_asset_type: {e}")
    

@router.callback_query(F.data == "back_to_add_symbol")
@common_handler_checks()
async def handle_back_to_add_symbol(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    asset_type = data.get("asset_type")
    if not asset_type:
        await callback.answer("Ошибка состояния. Начните заново.", show_alert=True)
        await state.clear()
        await handle_back_to_portfolio_view(callback, state) 
        return

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_add_asset_type")]
    ])

    try:
        await callback.message.edit_text(
             f"Тип актива: {'Акции' if asset_type == 'stock' else 'Криптовалюты'}.\n"
            "Введите символ актива (например, AAPL или BTC/USDT):",
            reply_markup=markup
        )
        await state.set_state(PortfolioState.adding_symbol)
    except TelegramAPIError as e:
         if "message is not modified" not in str(e): logger.error(f"Error editing message in back_to_add_symbol: {e}")

    