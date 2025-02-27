from aiogram.fsm.state import State, StatesGroup

class PortfolioState(StatesGroup):
    selecting_asset_type = State()
    selecting_symbol = State()
    adding_asset_type = State()
    adding_symbol = State()
    adding_amount = State()
    adding_price = State()
    removing_symbol = State()

class AlertState(StatesGroup):
    selecting_asset_type = State()
    selecting_symbol = State()
    selecting_price = State()
    selecting_condition = State()
    removing_alert = State()

class CalendarStates(StatesGroup):
    viewing_calendar = State()