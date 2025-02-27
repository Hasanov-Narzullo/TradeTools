from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def main_menu() -> InlineKeyboardMarkup:
    """Главное меню с обновленным callback_data для котировок."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📈 Котировки", callback_data="quotes_menu"),  # Изменено на quotes_menu
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

def quotes_menu_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для меню котировок."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔍 Запросить котировку", callback_data="quotes"),  # Оставляем quotes
            InlineKeyboardButton(text="💼 Цены портфеля", callback_data="portfolio_prices")
        ],
        [
            InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")
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

def portfolio_actions_keyboard(current_page: int, total_pages: int) -> InlineKeyboardMarkup:
    """Клавиатура для действий с портфелем с пагинацией."""
    return pagination_keyboard(current_page, total_pages, "portfolio")

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

def alerts_menu_keyboard(current_page: int = 1, total_pages: int = 1) -> InlineKeyboardMarkup:
    """Клавиатура для меню алертов с пагинацией."""
    buttons = [
        [
            InlineKeyboardButton(text="📋 Текущие алерты", callback_data="current_alerts"),
            InlineKeyboardButton(text="➕ Добавить алерт", callback_data="set_alert")
        ],
        [
            InlineKeyboardButton(text="🗑 Удалить алерт", callback_data="remove_alert"),
            InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")
        ]
    ]
    if total_pages > 1:
        pagination_row = []
        if current_page > 1:
            pagination_row.append(InlineKeyboardButton(text="⬅️ Предыдущая", callback_data=f"alerts_page_{current_page - 1}"))
        if current_page < total_pages:
            pagination_row.append(InlineKeyboardButton(text="Следующая ➡️", callback_data=f"alerts_page_{current_page + 1}"))
        buttons.append(pagination_row)

    return InlineKeyboardMarkup(inline_keyboard=buttons)

def pagination_keyboard(current_page: int, total_pages: int, prefix: str) -> InlineKeyboardMarkup:
    """
    Клавиатура для навигации по страницам.
    prefix: 'portfolio', 'alerts' или 'calendar' для определения типа данных.
    """
    buttons = []
    if current_page > 1:
        buttons.append(InlineKeyboardButton(text="⬅️ Предыдущая", callback_data=f"{prefix}_page_{current_page - 1}"))
    if current_page < total_pages:
        buttons.append(InlineKeyboardButton(text="Следующая ➡️", callback_data=f"{prefix}_page_{current_page + 1}"))

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        buttons,
        [InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu" if prefix in ["portfolio", "calendar"] else "alerts_menu")]
    ])
    return keyboard

def calendar_menu_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для меню календаря событий."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📅 Все события", callback_data="calendar_all"),
            InlineKeyboardButton(text="💼 События портфеля", callback_data="calendar_portfolio")
        ],
        [
            InlineKeyboardButton(text="🌍 Общеэкономические", callback_data="calendar_macro"),
            InlineKeyboardButton(text="💸 Дивиденды", callback_data="calendar_dividends")
        ],
        [
            InlineKeyboardButton(text="📈 Отчетности", callback_data="calendar_earnings"),
            InlineKeyboardButton(text="🎤 Пресс-конференции", callback_data="calendar_press")
        ],
        [
            InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")
        ]
    ])