from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

def main_menu() -> ReplyKeyboardMarkup:
    """Создание главного меню."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="/quotes"), KeyboardButton(text="/portfolio")],
            [KeyboardButton(text="/add_to_portfolio"), KeyboardButton(text="/set_alert")],
            [KeyboardButton(text="/calendar"), KeyboardButton(text="/help")]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )

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

def cancel_keyboard() -> ReplyKeyboardMarkup:
    """Создание клавиатуры для отмены действия."""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Отмена")]],
        resize_keyboard=True,
        one_time_keyboard=True)