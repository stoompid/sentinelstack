"""
Proximity calculation — no external dependencies.

Haversine distance + alert tier assignment based on distance to
watchlist cities loaded from config/locations.json.

Thresholds:
  Flash    ≤  50 km
  Priority ≤ 200 km
  Routine  ≤ 500 km
  None     >  500 km
"""

import json
import math
from pathlib import Path
from typing import List, Optional

from analyst.models import ProximityResult

LOCATIONS_PATH = Path(__file__).parents[1] / "config" / "locations.json"

FLASH_KM = 50.0
PRIORITY_KM = 200.0
ROUTINE_KM = 500.0


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return great-circle distance in kilometres between two points."""
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def assign_alert_tier(distance_km: float) -> str:
    """Return alert tier string for a given distance."""
    if distance_km <= FLASH_KM:
        return "flash"
    if distance_km <= PRIORITY_KM:
        return "priority"
    if distance_km <= ROUTINE_KM:
        return "routine"
    return "none"


def load_locations() -> List[dict]:
    data = json.loads(LOCATIONS_PATH.read_text(encoding="utf-8"))
    return data.get("locations", [])


def score_proximity(
    event_lat: float,
    event_lon: float,
    locations: Optional[List[dict]] = None,
) -> Optional[ProximityResult]:
    """
    Find the nearest watchlist city and return a ProximityResult.

    Returns None if no city is within ROUTINE_KM.
    """
    if locations is None:
        locations = load_locations()

    nearest: Optional[ProximityResult] = None
    nearest_km = float("inf")

    for loc in locations:
        lat = loc.get("latitude")
        lon = loc.get("longitude")
        if lat is None or lon is None:
            continue
        km = haversine(event_lat, event_lon, lat, lon)
        if km < nearest_km:
            nearest_km = km
            nearest = ProximityResult(
                city_id=loc["id"],
                city_name=loc["city"],
                distance_km=round(km, 1),
                alert_tier=assign_alert_tier(km),
            )

    if nearest and nearest.alert_tier == "none":
        return None
    return nearest
