"""Расчёт натальной карты.

Исторический часовой пояс определяется через IANA tzdata (zoneinfo): для даты
рождения берётся реальный сдвиг UTC, действовавший в этом месте, включая
летнее/зимнее время. Для дат до 1970 года полнота tzdata не гарантируется —
в этом случае добавляется предупреждение в результат.

Астрономия — Swiss Ephemeris (pyswisseph). Библиотека ставится только при
наличии лицензии (AGPL или Professional); без неё модуль сообщает об ошибке.
"""
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

try:
    import swisseph as swe
    HAS_SWE = True
except ImportError:
    HAS_SWE = False

PLANETS = {
    "Солнце": 0, "Луна": 1, "Меркурий": 2, "Венера": 3, "Марс": 4,
    "Юпитер": 5, "Сатурн": 6, "Уран": 7, "Нептун": 8, "Плутон": 9,
}
SIGNS = ["Овен", "Телец", "Близнецы", "Рак", "Лев", "Дева",
         "Весы", "Скорпион", "Стрелец", "Козерог", "Водолей", "Рыбы"]

ASPECTS = {"соединение": 0, "секстиль": 60, "квадрат": 90, "трин": 120, "оппозиция": 180}
ASPECT_ORB = 6.0


def _sign(lon: float) -> str:
    return SIGNS[int(lon // 30) % 12]


def historic_utc_offset(tz_id: str, local_dt: datetime) -> tuple[float, list[str]]:
    """Исторический сдвиг UTC (в часах) для местного времени, с предупреждениями."""
    warnings = []
    try:
        tz = ZoneInfo(tz_id)
        offset = tz.utcoffset(local_dt.replace(tzinfo=None)) if local_dt.tzinfo is None \
            else tz.utcoffset(local_dt)
        if offset is None:
            offset = timedelta(0)
            warnings.append("Не удалось определить исторический часовой пояс; использован UTC.")
        hours = offset.total_seconds() / 3600
    except Exception:
        hours = 0.0
        warnings.append(f"Часовой пояс {tz_id} не найден; использован UTC.")
    if local_dt.year < 1970:
        warnings.append(
            "Дата рождения ранее 1970 года: исторические данные часовых поясов (IANA tzdata) "
            "могут быть неполными, возможна погрешность."
        )
    return hours, warnings


def calculate_natal(
    birth_date: date,
    birth_time: str | None,          # "HH:MM" либо None
    time_accuracy: str,              # exact | approx_hour | unknown
    lat: float,
    lon: float,
    tz_id: str,
) -> dict:
    """Возвращает {'data': {...}, 'warnings': [...], 'utc_offset_used': float}."""
    if not HAS_SWE:
        raise RuntimeError(
            "Swiss Ephemeris (pyswisseph) не установлен. Установка возможна только "
            "после оформления лицензии (AGPL или Professional License)."
        )

    warnings: list[str] = []
    time_known = time_accuracy != "unknown"

    if time_accuracy == "exact" and birth_time:
        hh, mm = map(int, birth_time.split(":"))
    elif time_accuracy == "approx_hour" and birth_time:
        hh, mm = int(birth_time.split(":")[0]), 30  # середина указанного часа
        warnings.append(
            "Время рождения указано приблизительно (расчёт на середину часа). "
            "Дома и Асцендент показаны с возможной погрешностью: изменение времени "
            "рождения может изменить дома и Асцендент."
        )
    else:
        hh, mm = 12, 0  # полдень; дома/ASC/MC не рассчитываются
        warnings.append(
            "Время рождения неизвестно: Асцендент, MC и дома не рассчитываются. "
            "Положение Луны приблизительно (за сутки Луна смещается до ~14°). "
            "Точность разбора снижена."
        )

    local = datetime(birth_date.year, birth_date.month, birth_date.day, hh, mm)
    offset_hours, tz_warnings = historic_utc_offset(tz_id, local)
    warnings.extend(tz_warnings)
    utc_dt = local - timedelta(hours=offset_hours)

    jd = swe.julday(utc_dt.year, utc_dt.month, utc_dt.day, utc_dt.hour + utc_dt.minute / 60)

    planets = {}
    for name, pid in PLANETS.items():
        pos, _ = swe.calc_ut(jd, pid)
        entry = {"lon": round(pos[0], 4), "sign": _sign(pos[0]),
                 "degree_in_sign": round(pos[0] % 30, 2), "retrograde": pos[3] < 0}
        if name == "Луна" and not time_known:
            entry["approximate"] = True
        planets[name] = entry

    data: dict = {"planets": planets, "utc_datetime": utc_dt.isoformat()}

    if time_known:
        cusps, ascmc = swe.houses(jd, lat, lon, b"P")  # Placidus
        data["ascendant"] = {"lon": round(ascmc[0], 4), "sign": _sign(ascmc[0])}
        data["mc"] = {"lon": round(ascmc[1], 4), "sign": _sign(ascmc[1])}
        data["houses"] = [round(c, 4) for c in cusps[:12]]

    aspects = []
    names = list(PLANETS)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            diff = abs(planets[a]["lon"] - planets[b]["lon"])
            diff = min(diff, 360 - diff)
            for asp_name, angle in ASPECTS.items():
                if abs(diff - angle) <= ASPECT_ORB:
                    aspects.append({"a": a, "b": b, "aspect": asp_name,
                                    "orb": round(abs(diff - angle), 2)})
    data["aspects"] = aspects

    return {"data": data, "warnings": warnings, "utc_offset_used": offset_hours}
