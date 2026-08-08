"""Стандартная колода из 78 карт Таро (Райдер—Уэйт)."""

MAJOR = [
    ("Шут", "The Fool"),
    ("Маг", "The Magician"),
    ("Верховная Жрица", "The High Priestess"),
    ("Императрица", "The Empress"),
    ("Император", "The Emperor"),
    ("Иерофант", "The Hierophant"),
    ("Влюблённые", "The Lovers"),
    ("Колесница", "The Chariot"),
    ("Сила", "Strength"),
    ("Отшельник", "The Hermit"),
    ("Колесо Фортуны", "Wheel of Fortune"),
    ("Справедливость", "Justice"),
    ("Повешенный", "The Hanged Man"),
    ("Смерть", "Death"),
    ("Умеренность", "Temperance"),
    ("Дьявол", "The Devil"),
    ("Башня", "The Tower"),
    ("Звезда", "The Star"),
    ("Луна", "The Moon"),
    ("Солнце", "The Sun"),
    ("Суд", "Judgement"),
    ("Мир", "The World"),
]

SUITS = [
    ("Жезлов", "Wands", "wands"),
    ("Кубков", "Cups", "cups"),
    ("Мечей", "Swords", "swords"),
    ("Пентаклей", "Pentacles", "pentacles"),
]

RANKS = [
    ("Туз", "Ace"), ("Двойка", "Two"), ("Тройка", "Three"), ("Четвёрка", "Four"),
    ("Пятёрка", "Five"), ("Шестёрка", "Six"), ("Семёрка", "Seven"), ("Восьмёрка", "Eight"),
    ("Девятка", "Nine"), ("Десятка", "Ten"),
    ("Паж", "Page"), ("Рыцарь", "Knight"), ("Королева", "Queen"), ("Король", "King"),
]


def build_deck() -> list[dict]:
    """Возвращает 78 карт с техническими номерами 0..77."""
    deck = []
    for i, (ru, en) in enumerate(MAJOR):
        deck.append({"id": i, "name_ru": ru, "name_en": en, "arcana": "major", "suit": None})
    idx = len(MAJOR)
    for suit_ru, suit_en, suit_code in SUITS:
        for rank_ru, rank_en in RANKS:
            deck.append({
                "id": idx,
                "name_ru": f"{rank_ru} {suit_ru}",
                "name_en": f"{rank_en} of {suit_en}",
                "arcana": "minor",
                "suit": suit_code,
            })
            idx += 1
    return deck
