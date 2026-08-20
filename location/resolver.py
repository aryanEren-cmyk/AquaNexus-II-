"""Resolve user-facing place text into AquaNexus point or area geometry."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import tempfile
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


LON_MIN = 60.0
LON_MAX = 100.0
LAT_MIN = 0.0
LAT_MAX = 30.0

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_LIMIT = 5
NOMINATIM_MIN_INTERVAL_SECONDS = 1.0
NOMINATIM_USER_AGENT = os.getenv(
    "AQUANEXUS_NOMINATIM_USER_AGENT",
    "AquaNexus-II/1.0 location-resolver",
)

CACHE_PATH = Path(__file__).resolve().parent / "cache" / "locations.json"
POINT_MAX_SPAN_DEGREES = 0.5
AMBIGUOUS_SCORE_MARGIN = 0.01

_last_nominatim_request_at = 0.0


class LocationResolverError(RuntimeError):
    """Raised when a location cannot be resolved for AquaNexus data coverage."""


def resolve_location(location: str) -> dict[str, Any]:
    """Resolve direct coordinates or a named place into AquaNexus coverage geometry."""
    query = _normalize_query(location)
    cached = _cache_get(query)
    if cached is not None:
        return cached

    direct = _parse_direct_coordinates(query)
    if direct is not None:
        latitude, longitude = direct
        _validate_inside_coverage(latitude, longitude)
        resolved = {
            "query": location,
            "display_name": _format_coordinate_display(latitude, longitude),
            "type": "point",
            "latitude": latitude,
            "longitude": longitude,
            "bounding_box": {
                "south": latitude,
                "north": latitude,
                "west": longitude,
                "east": longitude,
            },
            "source": "direct_coordinates",
            "inside_aquanexus_coverage": True,
        }
        _cache_set(query, resolved)
        return resolved

    results = _search_nominatim(query, bounded=False)
    if not results:
        results = _search_nominatim(query, bounded=True)
    if not results:
        raise LocationResolverError(f"Unknown location: {location}")

    candidate = _choose_nominatim_result(results, query)
    resolved = _nominatim_result_to_location(candidate, location)
    _cache_set(query, resolved)
    return resolved


def get_location_search_geometry(location: str) -> dict[str, Any]:
    """Return normalized point or area geometry for ARGO/Copernicus tools."""
    resolved = resolve_location(location)
    if resolved["type"] == "point":
        return {
            "type": "point",
            "latitude": resolved["latitude"],
            "longitude": resolved["longitude"],
        }

    box = resolved["bounding_box"]
    return {
        "type": "area",
        "south": box["south"],
        "north": box["north"],
        "west": box["west"],
        "east": box["east"],
    }


def _normalize_query(location: str) -> str:
    if location is None:
        raise LocationResolverError("Location cannot be empty.")
    query = str(location).strip()
    if not query:
        raise LocationResolverError("Location cannot be empty.")
    return re.sub(r"\s+", " ", query).lower()


def _parse_direct_coordinates(query: str) -> tuple[float, float] | None:
    compact = query.replace("°", " ")
    hemisphere_pattern = re.compile(
        r"^\s*"
        r"(?P<lat>[+-]?\d+(?:\.\d+)?)\s*(?P<lat_hemi>[ns])\s*[, ]+\s*"
        r"(?P<lon>[+-]?\d+(?:\.\d+)?)\s*(?P<lon_hemi>[ew])"
        r"\s*$",
        re.IGNORECASE,
    )
    separated_pattern = re.compile(
        r"^\s*(?P<lat>[+-]?\d+(?:\.\d+)?)\s*,\s*"
        r"(?P<lon>[+-]?\d+(?:\.\d+)?)\s*$"
    )

    match = hemisphere_pattern.match(compact)
    if match:
        latitude = _apply_hemisphere(float(match.group("lat")), match.group("lat_hemi"))
        longitude = _apply_hemisphere(float(match.group("lon")), match.group("lon_hemi"))
        return latitude, longitude

    match = separated_pattern.match(compact)
    if match:
        return float(match.group("lat")), float(match.group("lon"))

    return None


def _apply_hemisphere(value: float, hemisphere: str) -> float:
    return -abs(value) if hemisphere.lower() in {"s", "w"} else abs(value)


def _validate_inside_coverage(latitude: float, longitude: float) -> None:
    if not LAT_MIN <= latitude <= LAT_MAX:
        raise LocationResolverError(
            f"Invalid coordinates: latitude must be inside {LAT_MIN:g} to {LAT_MAX:g}."
        )
    if not LON_MIN <= longitude <= LON_MAX:
        raise LocationResolverError(
            f"Invalid coordinates: longitude must be inside {LON_MIN:g} to {LON_MAX:g}."
        )


def _search_nominatim(query: str, *, bounded: bool) -> list[dict[str, Any]]:
    params: dict[str, Any] = {
        "q": query,
        "format": "jsonv2",
        "limit": NOMINATIM_LIMIT,
        "addressdetails": 1,
    }
    if bounded:
        params["viewbox"] = f"{LON_MIN},{LAT_MAX},{LON_MAX},{LAT_MIN}"
        params["bounded"] = 1
    else:
        params["viewbox"] = f"{LON_MIN},{LAT_MAX},{LON_MAX},{LAT_MIN}"

    url = f"{NOMINATIM_URL}?{urlencode(params)}"
    request = Request(
        url,
        headers={
            "User-Agent": NOMINATIM_USER_AGENT,
            "Accept": "application/json",
        },
    )

    _respect_nominatim_rate_limit()
    try:
        with urlopen(request, timeout=15) as response:
            payload = response.read().decode("utf-8")
    except (HTTPError, URLError, TimeoutError) as exc:
        raise LocationResolverError(f"External location service failure: {exc}") from exc

    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise LocationResolverError("External location service returned invalid JSON.") from exc
    if not isinstance(data, list):
        raise LocationResolverError("External location service returned an unexpected response.")
    return data


def _respect_nominatim_rate_limit() -> None:
    global _last_nominatim_request_at
    elapsed = time.monotonic() - _last_nominatim_request_at
    if elapsed < NOMINATIM_MIN_INTERVAL_SECONDS:
        time.sleep(NOMINATIM_MIN_INTERVAL_SECONDS - elapsed)
    _last_nominatim_request_at = time.monotonic()


def _choose_nominatim_result(
    results: list[dict[str, Any]],
    query: str,
) -> dict[str, Any]:

    scored = sorted(
        ((_result_score(result, query), result) for result in results),
        key=lambda item: item[0],
        reverse=True,
    )

    if not scored:
        raise LocationResolverError(f"Unknown location: {query}")

    # Only consider results that overlap AquaNexus coverage.
    inside_coverage = [
        item for item in scored
        if _result_overlaps_coverage(item[1])
    ]

    if not inside_coverage:
        raise LocationResolverError(
            "Location is outside AquaNexus data coverage."
        )

    best_score, best_result = inside_coverage[0]

    if len(inside_coverage) > 1:
        second_score, second_result = inside_coverage[1]

        if (
            not _same_search_geometry(best_result, second_result)
            and best_score - second_score < AMBIGUOUS_SCORE_MARGIN
        ):
            names = "; ".join(
                str(item[1].get("display_name", "unnamed"))
                for item in inside_coverage[:3]
            )

            raise LocationResolverError(
                f"Ambiguous location: {names}"
            )

    return best_result

def _same_search_geometry(
    first: dict[str, Any],
    second: dict[str, Any],
    *,
    tolerance: float = 1e-6,
) -> bool:
    first_box = _parse_nominatim_bounding_box(first)
    second_box = _parse_nominatim_bounding_box(second)
    if first_box is not None and second_box is not None:
        return all(
            abs(first_box[key] - second_box[key]) <= tolerance
            for key in ("south", "north", "west", "east")
        )

    first_lat = _safe_float(first.get("lat"))
    first_lon = _safe_float(first.get("lon"))
    second_lat = _safe_float(second.get("lat"))
    second_lon = _safe_float(second.get("lon"))
    if None in {first_lat, first_lon, second_lat, second_lon}:
        return False
    return abs(first_lat - second_lat) <= tolerance and abs(first_lon - second_lon) <= tolerance


def _result_score(result: dict[str, Any], query: str) -> float:
    importance = _safe_float(result.get("importance"), default=0.0)
    display_name = str(result.get("display_name", "")).lower()
    name = str(result.get("name") or result.get("localname") or "").lower()
    exact_bonus = 0.15 if query == name else 0.0
    prefix_bonus = 0.05 if display_name.startswith(query) else 0.0
    return importance + exact_bonus + prefix_bonus


def _nominatim_result_to_location(
    result: dict[str, Any],
    original_query: str,
) -> dict[str, Any]:
    latitude = _safe_float(result.get("lat"))
    longitude = _safe_float(result.get("lon"))
    if latitude is None or longitude is None:
        raise LocationResolverError("External location service did not return coordinates.")

    raw_box = _parse_nominatim_bounding_box(result)
    if raw_box is None:
        _validate_inside_coverage(latitude, longitude)
        clipped_box = {
            "south": latitude,
            "north": latitude,
            "west": longitude,
            "east": longitude,
        }
        geometry_type = "point"
    else:
        clipped_box = _clip_box_to_coverage(raw_box)
        if clipped_box is None:
            raise LocationResolverError("Location is outside AquaNexus data coverage.")
        geometry_type = _classify_result(result, raw_box)
        if geometry_type == "point" and not _point_inside_box(latitude, longitude, clipped_box):
            latitude = (clipped_box["south"] + clipped_box["north"]) / 2
            longitude = (clipped_box["west"] + clipped_box["east"]) / 2

    return {
        "query": original_query,
        "display_name": str(result.get("display_name") or original_query),
        "type": geometry_type,
        "latitude": latitude,
        "longitude": longitude,
        "bounding_box": clipped_box,
        "source": "nominatim",
        "inside_aquanexus_coverage": True,
    }


def _parse_nominatim_bounding_box(result: dict[str, Any]) -> dict[str, float] | None:
    raw = result.get("boundingbox")
    if not isinstance(raw, list) or len(raw) != 4:
        return None
    south = _safe_float(raw[0])
    north = _safe_float(raw[1])
    west = _safe_float(raw[2])
    east = _safe_float(raw[3])
    if None in {south, north, west, east}:
        return None
    return {
        "south": min(south, north),
        "north": max(south, north),
        "west": min(west, east),
        "east": max(west, east),
    }


def _result_overlaps_coverage(result: dict[str, Any]) -> bool:
    box = _parse_nominatim_bounding_box(result)
    if box is not None:
        return _clip_box_to_coverage(box) is not None

    latitude = _safe_float(result.get("lat"))
    longitude = _safe_float(result.get("lon"))
    if latitude is None or longitude is None:
        return False
    return LAT_MIN <= latitude <= LAT_MAX and LON_MIN <= longitude <= LON_MAX


def _clip_box_to_coverage(box: dict[str, float]) -> dict[str, float] | None:
    south = max(box["south"], LAT_MIN)
    north = min(box["north"], LAT_MAX)
    west = max(box["west"], LON_MIN)
    east = min(box["east"], LON_MAX)
    if south > north or west > east:
        return None
    return {
        "south": south,
        "north": north,
        "west": west,
        "east": east,
    }


def _classify_result(result: dict[str, Any], box: dict[str, float]) -> str:
    lat_span = abs(box["north"] - box["south"])
    lon_span = abs(box["east"] - box["west"])
    osm_class = str(result.get("category") or result.get("class") or "").lower()
    osm_type = str(result.get("type") or "").lower()
    place_rank = _safe_float(result.get("place_rank"), default=99.0)

    large_metadata = osm_class in {"boundary", "natural", "place"} and osm_type not in {
        "city",
        "town",
        "village",
        "hamlet",
        "suburb",
        "neighbourhood",
    }
    if lat_span > POINT_MAX_SPAN_DEGREES or lon_span > POINT_MAX_SPAN_DEGREES:
        return "area"
    if place_rank <= 12 and large_metadata:
        return "area"
    return "point"


def _point_inside_box(latitude: float, longitude: float, box: dict[str, float]) -> bool:
    return box["south"] <= latitude <= box["north"] and box["west"] <= longitude <= box["east"]


def _safe_float(value: Any, *, default: float | None = None) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed


def _format_coordinate_display(latitude: float, longitude: float) -> str:
    return f"{latitude:g}, {longitude:g}"


def _cache_get(query: str) -> dict[str, Any] | None:
    cache = _read_cache()
    value = cache.get(query)
    if value is None:
        return None
    if not isinstance(value, dict):
        raise LocationResolverError("Location cache is corrupted.")
    return value


def _cache_set(query: str, resolved: dict[str, Any]) -> None:
    cache = _read_cache()
    cache[query] = resolved
    _write_cache(cache)


def _read_cache() -> dict[str, dict[str, Any]]:
    if not CACHE_PATH.exists():
        return {}
    try:
        with CACHE_PATH.open("r", encoding="utf-8") as handle:
            cache = json.load(handle)
    except json.JSONDecodeError as exc:
        raise LocationResolverError("Location cache is corrupted.") from exc
    if not isinstance(cache, dict):
        raise LocationResolverError("Location cache is corrupted.")
    return cache


def _write_cache(cache: dict[str, dict[str, Any]]) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=CACHE_PATH.parent,
        delete=False,
        prefix=f"{CACHE_PATH.name}.",
        suffix=".tmp",
    ) as handle:
        json.dump(cache, handle, indent=2, sort_keys=True)
        handle.write("\n")
        temp_path = Path(handle.name)
    temp_path.replace(CACHE_PATH)
