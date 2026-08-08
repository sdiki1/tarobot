"""Выбор карт на сервере криптографически стойким ГСЧ. ИИ карты не выбирает."""
import secrets

DECK_SIZE = 78


def draw_cards(count: int, allow_reversed: bool = True, allow_duplicates: bool = False) -> list[dict]:
    """Возвращает [{card_id, is_reversed}] — без повторов, если не разрешено иное."""
    rng = secrets.SystemRandom()
    if allow_duplicates:
        ids = [rng.randrange(DECK_SIZE) for _ in range(count)]
    else:
        if count > DECK_SIZE:
            raise ValueError("count > deck size")
        ids = rng.sample(range(DECK_SIZE), count)
    return [
        {"card_id": cid, "is_reversed": allow_reversed and rng.random() < 0.5}
        for cid in ids
    ]
