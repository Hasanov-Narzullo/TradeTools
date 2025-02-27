from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from loguru import logger
from keyboards import main_menu, asset_type_keyboard, alert_condition_keyboard, alert_actions_keyboard, \
    portfolio_actions_keyboard, confirm_alert_keyboard, confirm_remove_asset_keyboard, alerts_menu_keyboard, \
    quotes_menu_keyboard, calendar_menu_keyboard, pagination_keyboard
from states import PortfolioState, AlertState
from database import add_to_portfolio, get_portfolio, remove_from_portfolio, add_alert, get_alerts, remove_alert, \
    get_events
from api import get_stock_price, get_crypto_price, fetch_asset_price, get_stock_history, get_crypto_history, \
    get_stock_price_with_retry, get_market_data
from utils import format_portfolio, format_alerts, format_events, format_market_prices, format_market_overview

router = Router()


@router.message(Command("start"))
async def cmd_start(message: Message):
    """Обработчик команды /start."""
    await message.answer("Добро пожаловать! Выберите действие:", reply_markup=main_menu())
    logger.info(f"Пользователь {message.from_user.id} запустил бота.")

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
    """Обработчик команды /quotes для получения котировок."""
    await message.answer("Выберите тип актива:", reply_markup=asset_type_keyboard())
    await state.set_state(PortfolioState.selecting_asset_type)
    logger.info(f"Пользователь {message.from_user.id} запросил котировки.")

@router.callback_query(PortfolioState.selecting_asset_type)
async def select_asset_type(callback: CallbackQuery, state: FSMContext):
    """Обработчик выбора типа актива для котировок."""
    await state.update_data(asset_type=callback.data)
    await callback.message.answer("Введите символ актива (например, AAPL или BTC/USDT):")
    await state.set_state(PortfolioState.selecting_symbol)
    await callback.answer()

@router.message(PortfolioState.selecting_symbol)
async def get_quote(message: Message, state: FSMContext):
    """Обработчик ввода символа для получения котировок."""
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

@router.message(Command("portfolio"))
async def cmd_portfolio(message: Message):
    """Обработчик команды /portfolio для просмотра портфеля."""
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
    """Обработчик команды /add_to_portfolio для добавления актива."""
    await message.answer("Выберите тип актива:", reply_markup=asset_type_keyboard())
    await state.set_state(PortfolioState.adding_asset_type)
    logger.info(f"Пользователь {message.from_user.id} начал добавление актива в портфель.")

@router.callback_query(PortfolioState.adding_asset_type)
async def add_asset_type(callback: CallbackQuery, state: FSMContext):
    """Обработчик выбора типа актива для добавления в портфель."""
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

@router.message(PortfolioState.adding_symbol)
async def add_symbol(message: Message, state: FSMContext):
    """Обработчик ввода символа актива для добавления в портфель."""
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

@router.message(PortfolioState.adding_amount)
async def add_amount(message: Message, state: FSMContext):
    """Обработчик ввода количества актива."""
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

@router.message(PortfolioState.adding_price)
async def add_price(message: Message, state: FSMContext):
    """Обработчик ввода цены покупки."""
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
    """Обработчик команды /set_alert для настройки алерта."""
    await message.answer("Выберите тип актива:", reply_markup=asset_type_keyboard())
    await state.set_state(AlertState.selecting_asset_type)
    logger.info(f"Пользователь {message.from_user.id} начал настройку алерта.")

@router.callback_query(AlertState.selecting_asset_type)
async def select_alert_asset_type(callback: CallbackQuery, state: FSMContext):
    """Обработчик выбора типа актива для алерта."""
    await state.update_data(asset_type=callback.data)
    await callback.message.answer("Введите символ актива (например, AAPL или BTC/USDT):")
    await state.set_state(AlertState.selecting_symbol)
    await callback.answer()

@router.message(AlertState.selecting_symbol)
async def select_alert_symbol(message: Message, state: FSMContext):
    """Обработчик ввода символа для алерта."""
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

@router.message(AlertState.selecting_price)
async def select_alert_price(message: Message, state: FSMContext):
    """Обработчик ввода целевой цены для алерта."""
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

@router.callback_query(AlertState.selecting_condition, F.data.in_({"above", "below"}))
async def select_alert_condition(callback: CallbackQuery, state: FSMContext):
    """Обработчик выбора условия алерта (above или below)."""
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
async def cmd_calendar(message: Message):
    """Обработчик команды /calendar для просмотра календаря событий."""
    events = await get_events()
    if events:
        await message.answer(format_events(events))
    else:
        await message.answer("Календарь событий пуст.")
    logger.info(f"Пользователь {message.from_user.id} запросил календарь событий.")

@router.message(Command("remove_from_portfolio"))
async def cmd_remove_from_portfolio(message: Message, state: FSMContext):
    """Обработчик команды /remove_from_portfolio для удаления актива из портфеля."""
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

@router.message(PortfolioState.removing_symbol)
async def remove_symbol_handler(message: Message, state: FSMContext):
    """Обработчик ввода символа актива для удаления из портфеля."""
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

@router.message(Command("market"))
async def cmd_market(message: Message):
    """Обработчик команды /market для просмотра текущих рыночных цен."""
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

def register_handlers(dp: Router):
    """Регистрация всех хэндлеров."""
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

@router.message(Command("alerts"))
async def cmd_alerts(message: Message):
    """Обработчик команды /alerts для просмотра установленных алертов."""
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

@router.message(Command("remove_alert"))
async def cmd_remove_alert(message: Message, state: FSMContext):
    """Обработчик команды /remove_alert для удаления алерта."""
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

@router.message(AlertState.removing_alert)
async def remove_alert_handler(message: Message, state: FSMContext):
    """Обработчик ввода ID алерта для удаления."""
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

@router.callback_query(F.data == "quotes_menu")
async def handle_quotes_menu(callback: CallbackQuery, state: FSMContext):
    """Обработчик кнопки 'Котировки' в главном меню."""
    await callback.message.answer("Выберите действие с котировками:", reply_markup=quotes_menu_keyboard())
    await callback.answer()
    logger.info(f"Пользователь {callback.from_user.id} открыл меню котировок.")

@router.callback_query(F.data == "quotes")
async def handle_quotes(callback: CallbackQuery, state: FSMContext):
    """Обработчик кнопки 'Запросить котировку'."""
    await callback.message.answer("Выберите тип актива:", reply_markup=asset_type_keyboard())
    await state.set_state(PortfolioState.selecting_asset_type)
    await callback.answer()
    logger.info(f"Пользователь {callback.from_user.id} запросил котировки.")

@router.callback_query(F.data == "portfolio")
async def handle_portfolio(callback: CallbackQuery, state: FSMContext):
    """Обработчик кнопки 'Портфель'."""
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

@router.callback_query(F.data == "add_to_portfolio")
async def handle_add_to_portfolio(callback: CallbackQuery, state: FSMContext):
    """Обработчик кнопки 'Добавить актив'."""
    await callback.message.answer("Выберите тип актива:", reply_markup=asset_type_keyboard())
    await state.set_state(PortfolioState.adding_asset_type)
    await callback.answer()
    logger.info(f"Пользователь {callback.from_user.id} начал добавление актива в портфель.")

@router.callback_query(F.data == "set_alert")
async def handle_set_alert(callback: CallbackQuery, state: FSMContext):
    """Обработчик кнопки 'Установить алерт'."""
    await callback.message.answer("Выберите тип актива:", reply_markup=asset_type_keyboard())
    await state.set_state(AlertState.selecting_asset_type)
    await callback.answer()
    logger.info(f"Пользователь {callback.from_user.id} начал установку алерта.")

@router.callback_query(F.data == "calendar")
async def handle_calendar_menu(callback: CallbackQuery, state: FSMContext):
    """Обработчик кнопки 'Календарь' в главном меню."""
    await callback.message.answer("Выберите тип событий:", reply_markup=calendar_menu_keyboard())
    await callback.answer()
    logger.info(f"Пользователь {callback.from_user.id} открыл меню календаря.")

@router.callback_query(F.data == "help")
async def handle_help(callback: CallbackQuery):
    """Обработчик кнопки 'Помощь'."""
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

@router.callback_query(F.data == "market")
async def handle_market_overview(callback: CallbackQuery):
    """Обработчик кнопки 'Рынок' для показа обзора рынка."""
    market_data = await get_market_data()
    formatted_market = format_market_overview(market_data)
    await callback.message.answer(formatted_market, reply_markup=main_menu())
    await callback.answer()
    logger.info(f"Пользователь {callback.from_user.id} запросил обзор рынка.")

@router.callback_query(F.data == "remove_asset")
async def handle_remove_asset_prompt(callback: CallbackQuery, state: FSMContext):
    """Обработчик кнопки 'Удалить актив'."""
    await callback.message.answer("Введите символ актива, который хотите удалить (например, AAPL или BTC/USDT):")
    await state.set_state(PortfolioState.removing_symbol)
    await callback.answer()
    logger.info(f"Пользователь {callback.from_user.id} начал удаление актива.")

@router.callback_query(F.data == "alerts")
async def handle_alerts(callback: CallbackQuery):
    """Обработчик кнопки 'Алерты'."""
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

@router.callback_query(F.data == "remove_alert")
async def handle_remove_alert_prompt(callback: CallbackQuery, state: FSMContext):
    """Обработчик кнопки 'Удалить алерт'."""
    await callback.message.answer("Введите ID алерта, который хотите удалить:")
    await state.set_state(AlertState.removing_alert)
    await callback.answer()
    logger.info(f"Пользователь {callback.from_user.id} начал удаление алерта.")

@router.callback_query(F.data == "confirm_alert")
async def confirm_alert(callback: CallbackQuery, state: FSMContext):
    """Обработчик подтверждения установки алерта."""
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

@router.callback_query(F.data == "cancel")
async def handle_cancel(callback: CallbackQuery, state: FSMContext):
    """Обработчик кнопки 'Отмена'."""
    await state.clear()
    await callback.message.answer("Действие отменено.", reply_markup=main_menu())
    await callback.answer()
    logger.info(f"Пользователь {callback.from_user.id} отменил действие.")

@router.message(PortfolioState.removing_symbol)
async def handle_remove_asset_symbol(message: Message, state: FSMContext):
    """Обработчик ввода символа для удаления актива."""
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

@router.callback_query(F.data.startswith("confirm_remove_"))
async def confirm_remove_asset(callback: CallbackQuery, state: FSMContext):
    """Обработчик подтверждения удаления актива."""
    user_id = callback.from_user.id
    symbol = callback.data.replace("confirm_remove_", "")
    await remove_from_portfolio(user_id, symbol)
    await callback.message.answer(f"Актив {symbol} удален из портфеля.", reply_markup=main_menu())
    await state.clear()
    await callback.answer()
    logger.info(f"Пользователь {user_id} удалил актив {symbol} из портфеля.")

@router.callback_query(F.data.in_({"quotes", "portfolio", "add_to_portfolio", "set_alert", "calendar", "help", "market"}))
async def handle_menu_command(callback: CallbackQuery, state: FSMContext):
    """Обработчик команд из главного меню, сбрасывающий текущее состояние."""
    current_state = await state.get_state()
    if current_state:
        await state.clear()
        logger.info(f"Пользователь {callback.from_user.id} сбросил состояние {current_state} для выполнения команды {callback.data}")

    command = callback.data
    if command == "quotes":
        await handle_quotes_menu(callback, state)
    elif command == "portfolio":
        await handle_portfolio(callback)
    elif command == "add_to_portfolio":
        await handle_add_to_portfolio(callback, state)
    elif command == "set_alert":
        await handle_set_alert(callback, state)
    elif command == "calendar":
        await handle_calendar_menu(callback)
    elif command == "help":
        await handle_help(callback)
    elif command == "market":
        await handle_market_overview(callback)

@router.callback_query(F.data == "alerts_menu")
async def handle_alerts_menu(callback: CallbackQuery):
    """Обработчик кнопки 'Алерты' в главном меню."""
    await callback.message.answer("Выберите действие с алертами:", reply_markup=alerts_menu_keyboard())
    await callback.answer()
    logger.info(f"Пользователь {callback.from_user.id} открыл меню алертов.")

@router.callback_query(F.data == "current_alerts")
async def handle_current_alerts(callback: CallbackQuery, state: FSMContext):
    """Обработчик кнопки 'Текущие алерты'."""
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

@router.message(AlertState.removing_alert)
async def handle_remove_alert_id(message: Message, state: FSMContext):
    """Обработчик ввода ID алерта для удаления."""
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

@router.callback_query(F.data == "main_menu")
async def handle_main_menu(callback: CallbackQuery, state: FSMContext):
    """Обработчик кнопки 'Назад' в меню алертов."""
    await state.clear()
    await callback.message.answer("Главное меню:", reply_markup=main_menu())
    await callback.answer()
    logger.info(f"Пользователь {callback.from_user.id} вернулся в главное меню.")

@router.callback_query(F.data == "portfolio_prices")
async def handle_portfolio_prices(callback: CallbackQuery):
    """Обработчик кнопки 'Цены портфеля'."""
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

@router.callback_query(F.data.startswith("portfolio_page_"))
async def handle_portfolio_page(callback: CallbackQuery, state: FSMContext):
    """Обработчик навигации по страницам портфеля."""
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

@router.callback_query(F.data.startswith("alerts_page_"))
async def handle_alerts_page(callback: CallbackQuery, state: FSMContext):
    """Обработчик навигации по страницам алертов."""
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

@router.callback_query(F.data.startswith("calendar_"))
async def handle_calendar_filter(callback: CallbackQuery, state: FSMContext):
    """Обработчик фильтрации событий."""
    filter_type = callback.data.replace("calendar_", "")
    user_id = callback.from_user.id
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
    logger.info(f"Получено {len(events)} событий для фильтра {filter_type}")
    if not events:
        await callback.message.answer(
            "Событий не найдено. Попробуйте обновить календарь позже.",
            reply_markup=calendar_menu_keyboard()
        )
        logger.info(f"Пользователь {user_id} запросил события (пусто, фильтр: {filter_type}).")
        return

    formatted_events, total_pages = format_events(events, page=1)
    await callback.message.answer(
        formatted_events,
        reply_markup=pagination_keyboard(current_page=1, total_pages=total_pages, prefix="calendar")
    )
    await state.update_data(calendar_filter=filter_type)
    await callback.answer()
    logger.info(f"Пользователь {user_id} запросил события (фильтр: {filter_type}, страница 1, событий: {len(events)}).")

@router.callback_query(F.data.startswith("calendar_page_"))
async def handle_calendar_page(callback: CallbackQuery, state: FSMContext):
    """Обработчик навигации по страницам календаря."""
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
