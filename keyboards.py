from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def main_menu() -> InlineKeyboardMarkup:
    """Создание главного меню (инлайн)."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📈 Котировки", callback_data="cmd_quotes"),
            InlineKeyboardButton(text="💼 Портфель", callback_data="cmd_portfolio")
        ],
        [
            InlineKeyboardButton(text="➕ Добавить в портфель", callback_data="cmd_add_to_portfolio"),
            InlineKeyboardButton(text="🔔 Установить алерт", callback_data="cmd_set_alert")
        ],
        [
            InlineKeyboardButton(text="📅 Календарь (скоро)", callback_data="cmd_calendar"), # Placeholder for calendar
            InlineKeyboardButton(text="❓ Помощь", callback_data="cmd_help")
        ]
    ])

def asset_type_keyboard() -> InlineKeyboardMarkup:
    """Создание клавиатуры для выбора типа актива (акции или криптовалюты)."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Акции", callback_data="stock")],
        [InlineKeyboardButton(text="Криптовалюты", callback_data="crypto")]
    ])

def alert_condition_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для выбора условия алерта."""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Выше", callback_data="above"),
            InlineKeyboardButton(text="Ниже", callback_data="below")
        ]
    ])
    return keyboard

def cancel_keyboard() -> InlineKeyboardMarkup:
    """Создание клавиатуры для отмены действия (инлайн)."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cmd_cancel")]
    ])