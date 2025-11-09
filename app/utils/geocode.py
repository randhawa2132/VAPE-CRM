from __future__ import annotations

from typing import Optional

import httpx

from ..settings import settings


async def geocode_address(address: str) -> Optional[tuple[float, float, str]]:
    if not settings.google_maps_api_key:
        return None
    params = {"address": address, "key": settings.google_maps_api_key}
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get("https://maps.googleapis.com/maps/api/geocode/json", params=params)
        response.raise_for_status()
        data = response.json()
        results = data.get("results") or []
        if not results:
            return None
        location = results[0]["geometry"]["location"]
        place_id = results[0].get("place_id")
        return location["lat"], location["lng"], place_id
