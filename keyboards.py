# keyboards
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from loguru import logger

# Главное меню с обновленным callback_data для котировок.
def main_menu(chat_type: str = 'private', is_admin: bool = False) -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton(text="📈 Котировки", callback_data="quotes_menu"),
            InlineKeyboardButton(text="💼 Портфель", callback_data="portfolio_view_default")
        ],
        [
            InlineKeyboardButton(text="🔔 Алерты", callback_data="alerts_menu"),
            InlineKeyboardButton(text="📅 Календарь", callback_data="calendar")
        ],
        [
            InlineKeyboardButton(text="📊 Рынок", callback_data="market"),
            InlineKeyboardButton(text="ℹ️ Помощь", callback_data="help")
        ]
    ]

    if chat_type in ['group', 'supergroup']:
        keyboard.append([InlineKeyboardButton(text="⚙️ Настройки", callback_data="settings_open")])

    keyboard.append([InlineKeyboardButton(text="🚫 Отмена", callback_data="cancel")])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def sub_account_select_keyboard(sub_accounts: list[str], action_prefix: str) -> InlineKeyboardMarkup:
    keyboard = []
    for name in sub_accounts:
        keyboard.append([InlineKeyboardButton(text=name, callback_data=f"{action_prefix}_select_{name}")])
    keyboard.append([InlineKeyboardButton(text="➕ Создать новый суб-счет", callback_data=f"{action_prefix}_new")])
    keyboard.append([InlineKeyboardButton(text="🚫 Отмена", callback_data="cancel")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def portfolio_view_keyboard(sub_accounts: list[str], current_sub_account: str, current_page: int, total_pages: int) -> InlineKeyboardMarkup:
    keyboard = []
    main_account_name = "Основной"

    if len(sub_accounts) > 1:
        sub_account_buttons = []
        try:
            current_index = sub_accounts.index(current_sub_account)
            has_prev = current_index > 0
            has_next = current_index < len(sub_accounts) - 1

            if has_prev:
                prev_sub = sub_accounts[current_index - 1]
                sub_account_buttons.append(InlineKeyboardButton(text=f"◀️ {prev_sub}", callback_data=f"p_sw_{prev_sub}"))
            if has_next:
                next_sub = sub_accounts[current_index + 1]
                sub_account_buttons.append(InlineKeyboardButton(text=f"{next_sub} ▶️", callback_data=f"p_sw_{next_sub}"))
            if sub_account_buttons:
                 keyboard.append(sub_account_buttons)
        except ValueError:
            logger.warning(f"Current sub-account '{current_sub_account}' not found in list: {sub_accounts}")

    asset_action_buttons = [
        InlineKeyboardButton(text="➕ Добавить сюда", callback_data=f"p_add_{current_sub_account}"),
        InlineKeyboardButton(text="🗑 Удалить отсюда", callback_data=f"p_rm_{current_sub_account}"),
        InlineKeyboardButton(text="🔔 Установить алерт", callback_data="set_alert")
    ]
    keyboard.append(asset_action_buttons)

    pagination_buttons = []
    if current_page > 1:
        pagination_buttons.append(InlineKeyboardButton(text="⬅️ Пред.", callback_data=f"p_pg_{current_sub_account}_{current_page - 1}"))
    if current_page < total_pages:
        pagination_buttons.append(InlineKeyboardButton(text="След. ➡️", callback_data=f"p_pg_{current_sub_account}_{current_page + 1}"))
    if pagination_buttons:
        keyboard.append(pagination_buttons)

    sub_account_management_buttons = [
         InlineKeyboardButton(text="➕ Новый суб-счет", callback_data="portfolio_add_sub_account_start")
    ]
    if len(sub_accounts) > 1:
         sub_account_management_buttons.append(
             InlineKeyboardButton(text="🗑 Удал. суб-счет...", callback_data="portfolio_remove_sub_account_start")
         )

    keyboard.append(sub_account_management_buttons)

    keyboard.append([InlineKeyboardButton(text="🔙 Назад в гл. меню", callback_data="main_menu")])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)

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

def settings_keyboard(chat_id: int, current_allow_all: bool) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(
                text=f"✅ Все пользователи" if current_allow_all else "⚪️ Все пользователи",
                callback_data=f"settings_set_all_{chat_id}"
            ),
            InlineKeyboardButton(
                text=f"✅ Только админы" if not current_allow_all else "⚪️ Только админы",
                callback_data=f"settings_set_admins_{chat_id}"
            )
        ],
         [
            InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def confirm_delete_sub_account_keyboard(sub_account_to_delete: str) -> InlineKeyboardMarkup:
     return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=f"✅ Да, удалить '{sub_account_to_delete}'", callback_data=f"p_conf_del_{sub_account_to_delete}"),
            InlineKeyboardButton(text="🚫 Нет, отмена", callback_data="cancel_sub_account_delete")
        ]
    ])


def sub_account_select_keyboard_for_delete(sub_accounts: list[str]) -> InlineKeyboardMarkup:
    main_account_name = "Основной"
    keyboard = []
    removable_accounts = [acc for acc in sub_accounts if acc != main_account_name]

    if not removable_accounts:
        keyboard.append([InlineKeyboardButton(text="Нет суб-счетов для удаления", callback_data="cancel")])
    else:
        for name in removable_accounts:
            keyboard.append([InlineKeyboardButton(text=name, callback_data=f"p_sel_del_{name}")])

    keyboard.append([InlineKeyboardButton(text="🚫 Отмена", callback_data="cancel")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)