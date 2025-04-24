# states
from aiogram.fsm.state import State, StatesGroup

class PortfolioState(StatesGroup):
    selecting_asset_type = State()
    selecting_symbol = State()
    adding_asset_type = State()
    adding_symbol = State()
    adding_amount = State()
    adding_price = State()
    adding_sub_account_selection = State()
    adding_sub_account_new_name = State()
    removing_sub_account_selection = State()
    removing_symbol = State()
    removing_sub_account_selection_for_delete = State()
    viewing_portfolio = State()

class AlertState(StatesGroup):
    selecting_asset_type = State()
    selecting_symbol = State()
    selecting_price = State()
    selecting_condition = State()
    removing_alert = State()

class CalendarStates(StatesGroup):
    viewing_calendar = State()