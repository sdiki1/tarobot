"""Геокодинг места рождения (Nominatim/OSM) + IANA-таймзона по координатам."""
import httpx
from timezonefinder import TimezoneFinder

from app.config import get_settings

_tf = TimezoneFinder()

_NOMINATIM_HEADERS = {
    "accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,"
        "image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7"
    ),
    "accept-language": "en,ru;q=0.9,zh;q=0.8",
    "cache-control": "max-age=0",
    "priority": "u=0, i",
    "sec-ch-ua": '"Chromium";v="148", "YaBrowser";v="26.6", '
                 '"Not/A)Brand";v="99", "Yowser";v="2.5"',
    "sec-ch-ua-mobile": "?1",
    "sec-ch-ua-platform": '"Android"',
    "sec-fetch-dest": "document",
    "sec-fetch-mode": "navigate",
    "sec-fetch-site": "none",
    "sec-fetch-user": "?1",
    "upgrade-insecure-requests": "1",
    "user-agent": (
        "Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 "
        "Mobile Safari/537.36"
    ),
}


async def geocode(place: str, limit: int = 5) -> list[dict]:
    """Возвращает варианты [{name, lat, lon, tz_id}] — при неоднозначности бот даёт выбор."""
    s = get_settings()
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(
            s.geocoder_url,
            params={"q": place, "format": "json", "limit": limit, "accept-language": "ru"},
            headers=_NOMINATIM_HEADERS,
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
