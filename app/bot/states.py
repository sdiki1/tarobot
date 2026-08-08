from aiogram.fsm.state import State, StatesGroup


class TarotOrder(StatesGroup):
    collecting = State()   # сбор обязательных полей услуги
    promo = State()        # ввод промокода


class NatalOrder(StatesGroup):
    name = State()
    birth_date = State()
    time_accuracy = State()
    birth_time = State()
    place = State()
    place_choice = State()
    promo = State()


class DeleteData(StatesGroup):
    confirm = State()
