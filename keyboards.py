from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def main_menu() -> InlineKeyboardMarkup:
    """Обновленное главное меню с разделом алертов."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📈 Котировки", callback_data="quotes"),
            InlineKeyboardButton(text="💼 Портфель", callback_data="portfolio")
        ],
        [
            InlineKeyboardButton(text="➕ Добавить актив", callback_data="add_to_portfolio"),
            InlineKeyboardButton(text="🔔 Алерты", callback_data="alerts_menu")
        ],
        [
            InlineKeyboardButton(text="📅 Календарь", callback_data="calendar"),
            InlineKeyboardButton(text="ℹ️ Помощь", callback_data="help")
        ],
        [
            InlineKeyboardButton(text="📊 Рынок", callback_data="market"),
            InlineKeyboardButton(text="🚫 Отмена", callback_data="cancel")
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

def cancel_keyboard() -> ReplyKeyboardMarkup:
    """Создание клавиатуры для отмены действия."""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Отмена")]],
        resize_keyboard=True,
        one_time_keyboard=True)

def portfolio_actions_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для действий с портфелем."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🗑 Удалить актив", callback_data="remove_asset"),
            InlineKeyboardButton(text="🔙 Назад", callback_data="portfolio")
        ]
    ])

def alert_actions_keyboard(alert_id: int) -> InlineKeyboardMarkup:
    """Клавиатура для действий с алертом."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🗑 Удалить", callback_data=f"remove_alert_{alert_id}"),
            InlineKeyboardButton(text="🔙 Назад", callback_data="alerts")
        ]
    ])

def confirm_alert_keyboard(symbol: str, target_price: float, condition: str) -> InlineKeyboardMarkup:
    """Клавиатура для подтверждения установки алерта."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"confirm_alert_{symbol}_{target_price}_{condition}"),
            InlineKeyboardButton(text="🚫 Отмена", callback_data="cancel")
        ]
    ])

def confirm_remove_asset_keyboard(symbol: str) -> InlineKeyboardMarkup:
    """Клавиатура для подтверждения удаления актива."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"confirm_remove_{symbol}"),
            InlineKeyboardButton(text="🚫 Отмена", callback_data="cancel")
        ]
    ])

def alerts_menu_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для меню алертов."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📋 Текущие алерты", callback_data="current_alerts"),
            InlineKeyboardButton(text="➕ Добавить алерт", callback_data="set_alert")
        ],
        [
            InlineKeyboardButton(text="🗑 Удалить алерт", callback_data="remove_alert"),
            InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")
        ]
    ])

def quotes_menu_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для меню котировок."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔍 Запросить котировку", callback_data="quotes"),
            InlineKeyboardButton(text="💼 Цены портфеля", callback_data="portfolio_prices")
        ],
        [
            InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")
        ]
    ])