from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

# Главное меню с обновленным callback_data для котировок.
def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📈 Котировки", callback_data="quotes_menu"),
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

# Клавиатура для меню котировок.
def quotes_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔍 Запросить котировку", callback_data="quotes"),
            InlineKeyboardButton(text="💼 Цены портфеля", callback_data="portfolio_prices")
        ],
        [
            InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")
        ]
    ])

# Создание клавиатуры для выбора типа актива (акции или криптовалюты).
def asset_type_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Акции", callback_data="stock")],
        [InlineKeyboardButton(text="Криптовалюты", callback_data="crypto")]
    ])

# Клавиатура для выбора условия алерта.
def alert_condition_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Выше", callback_data="above"),
            InlineKeyboardButton(text="Ниже", callback_data="below")
        ]
    ])

# Создание клавиатуры для отмены действия.
def cancel_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Отмена")]],
        resize_keyboard=True,
        one_time_keyboard=True
    )

# Клавиатура для действий с портфелем с пагинацией.
def portfolio_actions_keyboard(current_page: int, total_pages: int) -> InlineKeyboardMarkup:
    return pagination_keyboard(current_page, total_pages, "portfolio")

# Клавиатура для действий с алертом.
def alert_actions_keyboard(alert_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🗑 Удалить", callback_data=f"remove_alert_{alert_id}"),
            InlineKeyboardButton(text="🔙 Назад", callback_data="alerts")
        ]
    ])

# Клавиатура для подтверждения установки алерта.
def confirm_alert_keyboard(symbol: str, target_price: float, condition: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"confirm_alert_{symbol}_{target_price}_{condition}"),
            InlineKeyboardButton(text="🚫 Отмена", callback_data="cancel")
        ]
    ])

# Клавиатура для подтверждения удаления актива.
def confirm_remove_asset_keyboard(symbol: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"confirm_remove_{symbol}"),
            InlineKeyboardButton(text="🚫 Отмена", callback_data="cancel")
        ]
    ])

# Клавиатура для меню алертов с пагинацией.
def alerts_menu_keyboard(current_page: int = 1, total_pages: int = 1) -> InlineKeyboardMarkup:
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


"""
Клавиатура для навигации по страницам.
prefix: 'portfolio', 'alerts' или 'calendar' для определения типа данных.
"""
def pagination_keyboard(current_page: int, total_pages: int, prefix: str) -> InlineKeyboardMarkup:
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

# Клавиатура для меню календаря событий.
def calendar_menu_keyboard() -> InlineKeyboardMarkup:
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

def get_pagination_keyboard(current_page: int, total_pages: int, category: str) -> InlineKeyboardMarkup:
    buttons = []
    if current_page > 1:
        buttons.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"calendar_prev_{category}_{current_page}"))
    if current_page < total_pages:
        buttons.append(InlineKeyboardButton(text="Вперед ➡️", callback_data=f"calendar_next_{category}_{current_page}"))

    keyboard = InlineKeyboardMarkup(inline_keyboard=[buttons] if buttons else [])
    return keyboard

def get_category_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="Криптовалюты", callback_data="calendar_category_crypto")],
        [InlineKeyboardButton(text="Инвестиции", callback_data="calendar_category_investments")],
        [InlineKeyboardButton(text="Все события", callback_data="calendar_category_all")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)