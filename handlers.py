from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from loguru import logger
from keyboards import main_menu, asset_type_keyboard, alert_condition_keyboard
from states import PortfolioState, AlertState
from database import add_to_portfolio, get_portfolio, remove_from_portfolio, add_alert, get_alerts, remove_alert, \
    get_events
from api import get_stock_price, get_crypto_price, fetch_asset_price, get_stock_history, get_crypto_history, get_stock_price_with_retry
from utils import format_portfolio, format_alerts, format_events, format_market_prices

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

    # Проверяем, не является ли ввод командой
    if symbol.startswith('/'):
        await message.answer(
            "Пожалуйста, введите символ актива (например, AAPL или BTC/USDT), а не команду."
        )
        await state.clear()
        logger.info(f"Пользователь {message.from_user.id} ввел команду вместо символа: {symbol}")
        return

    price = None
    if asset_type == "stock":
        # Проверяем, является ли символ допустимым тикером для акций (только буквы)
        if not symbol.isalpha():
            await message.answer(
                "Недопустимый тикер акции. Пожалуйста, введите символ, состоящий только из букв (например, AAPL)."
            )
            await state.clear()
            logger.warning(f"Недопустимый тикер акции: {symbol}")
            return
        price = await get_stock_price(symbol)
    elif asset_type == "crypto":
        # Проверяем, является ли символ допустимым тикером для криптовалют (содержит '/')
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
            "Ваш портфель сейчас пуст. 😔<br/>"
            "Используйте команду /add_to_portfolio, чтобы добавить активы в портфель.",
            parse_mode="HTML"
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
    await message.answer(formatted_portfolio, parse_mode="HTML")
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
    symbol = message.text.strip().upper()
    data = await state.get_data()
    asset_type = data["asset_type"]

    # Валидация символа
    # ... (проверка на команду и формат символа, как выше)

    # Проверка существования актива
    price = None
    if asset_type == "stock":
        price = await get_stock_price(symbol)
    elif asset_type == "crypto":
        price = await get_crypto_price(symbol)

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

@router.message(PortfolioState.adding_amount)
async def add_amount(message: Message, state: FSMContext):
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

@router.message(PortfolioState.adding_price)
async def add_price(message: Message, state: FSMContext):
    try:
        price = float(message.text)
        if price <= 0:
            await message.answer("Цена покупки должна быть положительным числом.")
            return
        data = await state.get_data()
        await add_to_portfolio(
            user_id=message.from_user.id,
            asset_type=data["asset_type"],
            symbol=data["symbol"],
            amount=data["amount"],
            purchase_price=price
        )
        await message.answer("Актив добавлен в портфель!")
        await state.clear()
        logger.info(f"Пользователь {message.from_user.id} добавил актив в портфель.")
    except ValueError:
        await message.answer("Пожалуйста, введите число.")


@router.message(Command("set_alert"))
async def cmd_set_alert(message: Message, state: FSMContext):
    """Обработчик команды /set_alert для настройки алерта."""
    await message.answer("Выберите тип актива:", reply_markup=asset_type_keyboard())
    await state.set_state(AlertState.selecting_asset_type)
    logger.info(f"Пользователь {message.from_user.id} начал настройку алерта.")


@router.callback_query(AlertState.selecting_asset_type)
async def alert_asset_type(callback: CallbackQuery, state: FSMContext):
    """Обработчик выбора типа актива для алерта."""
    await state.update_data(asset_type=callback.data)
    await callback.message.answer("Введите символ актива (например, AAPL или BTC/USDT):")
    await state.set_state(AlertState.selecting_symbol)
    await callback.answer()


@router.message(AlertState.selecting_symbol)
async def alert_symbol(message: Message, state: FSMContext):
    """Обработчик ввода символа для алерта."""
    symbol = message.text.strip().upper()
    data = await state.get_data()
    asset_type = data["asset_type"]

    # Проверяем, не является ли ввод командой
    if symbol.startswith('/'):
        await message.answer(
            "Пожалуйста, введите символ актива (например, AAPL или BTC/USDT), а не команду."
        )
        await state.clear()
        logger.info(f"Пользователь {message.from_user.id} ввел команду вместо символа: {symbol}")
        return

    # Валидация символа
    if asset_type == "stock" and not symbol.isalpha():
        await message.answer(
            "Недопустимый тикер акции. Пожалуйста, введите символ, состоящий только из букв (например, AAPL)."
        )
        await state.clear()
        logger.warning(f"Недопустимый тикер акции: {symbol}")
        return
    elif asset_type == "crypto" and '/' not in symbol:
        await message.answer(
            "Недопустимый тикер криптовалюты. Пожалуйста, введите символ в формате 'BTC/USDT'."
        )
        await state.clear()
        logger.warning(f"Недопустимый тикер криптовалюты: {symbol}")
        return

    # Проверка существования актива
    price = None
    try:
        if asset_type == "stock":
            price = await get_stock_price(symbol)
        elif asset_type == "crypto":
            price = await get_crypto_price(symbol)
    except Exception as e:
        logger.error(f"Ошибка при проверке существования актива {symbol} ({asset_type}): {e}")
        await message.answer(
            "Не удалось проверить существование актива. Возможно, символ некорректен или возникла ошибка. "
            "Пожалуйста, проверьте символ и попробуйте снова."
        )
        await state.clear()
        return

    if price is None:
        await message.answer(
            "Не удалось получить цену актива. Возможно, символ некорректен или превышен лимит запросов к API. "
            "Пожалуйста, проверьте символ и попробуйте снова."
        )
        await state.clear()
        logger.warning(f"Не удалось проверить существование актива: {symbol} ({asset_type})")
        return

    await state.update_data(symbol=symbol)
    await message.answer("Введите целевую цену:")
    await state.set_state(AlertState.selecting_price)


@router.message(AlertState.selecting_price)
async def alert_price(message: Message, state: FSMContext):
    """Обработчик ввода целевой цены для алерта."""
    try:
        target_price = float(message.text)
        if target_price <= 0:
            await message.answer("Целевая цена должна быть положительным числом.")
            return
        await state.update_data(target_price=target_price)
        await message.answer(
            "Выберите условие алерта:",
            reply_markup=alert_condition_keyboard()
        )
        await state.set_state(AlertState.selecting_condition)
    except ValueError:
        await message.answer("Пожалуйста, введите число.")


@router.callback_query(AlertState.selecting_condition)
async def alert_condition(callback: CallbackQuery, state: FSMContext):
    """Обработчик выбора условия для алерта."""
    condition = callback.data  # 'above' или 'below'
    data = await state.get_data()
    user_id = callback.from_user.id
    asset_type = data["asset_type"]
    symbol = data["symbol"]
    target_price = data["target_price"]

    try:
        await add_alert(
            user_id=user_id,
            asset_type=asset_type,
            symbol=symbol,
            target_price=target_price,
            condition=condition
        )
        await callback.message.answer(
            f"Алерт установлен: {symbol} ({asset_type}) - "
            f"{'выше' if condition == 'above' else 'ниже'} ${target_price:.2f}"
        )
        logger.info(f"Пользователь {user_id} установил алерт: {symbol} ({asset_type}) - {condition} ${target_price:.2f}")
    except Exception as e:
        await callback.message.answer(
            "Произошла ошибка при установке алерта. Пожалуйста, попробуйте снова."
        )
        logger.error(f"Ошибка при установке алерта для пользователя {user_id}: {e}")
    finally:
        await state.clear()
    await callback.answer()


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

    # Показываем пользователю список активов в портфеле
    formatted_portfolio = format_portfolio(portfolio)
    await message.answer(
        f"Ваш портфель:\n{formatted_portfolio}\n"
        "Введите символ актива, который хотите удалить (например, AAPL или BTC/USDT):",
        parse_mode="MarkdownV2"
    )
    await state.set_state(PortfolioState.removing_symbol)

@router.message(PortfolioState.removing_symbol)
async def remove_symbol_handler(message: Message, state: FSMContext):
    """Обработчик ввода символа актива для удаления из портфеля."""
    user_id = message.from_user.id
    symbol = message.text.strip().upper()

    # Проверяем, не является ли ввод командой
    if symbol.startswith('/'):
        await message.answer(
            "Пожалуйста, введите символ актива (например, AAPL или BTC/USDT), а не команду."
        )
        await state.clear()
        logger.info(f"Пользователь {user_id} ввел команду вместо символа: {symbol}")
        return

    try:
        # Проверяем, есть ли актив в портфеле
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

        # Удаляем актив из портфеля
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
            "Ваш портфель сейчас пуст. 😔<br>"
            "Используйте команду /add_to_portfolio, чтобы добавить активы в портфель.",
            parse_mode="HTML"
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
    await message.answer(formatted_prices, parse_mode="HTML")
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
    await message.answer(formatted_alerts, parse_mode="HTML")
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
