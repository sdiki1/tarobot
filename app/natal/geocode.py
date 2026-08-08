"""Геокодинг места рождения (Nominatim/OSM) + IANA-таймзона по координатам."""
import httpx
from timezonefinder import TimezoneFinder

from app.config import get_settings

_tf = TimezoneFinder()


async def geocode(place: str, limit: int = 5) -> list[dict]:
    """Возвращает варианты [{name, lat, lon, tz_id}] — при неоднозначности бот даёт выбор."""
    s = get_settings()
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(
            s.geocoder_url,
            params={"q": place, "format": "json", "limit": limit, "accept-language": "ru"},
            headers={"User-Agent": s.geocoder_user_agent},
        )
        r.raise_for_status()
    results = []
    for item in r.json():
        lat, lon = float(item["lat"]), float(item["lon"])
        results.append({
            "name": item.get("display_name", place),
            "lat": lat,
            "lon": lon,
            "tz_id": _tf.timezone_at(lat=lat, lng=lon),
        })
    return results
