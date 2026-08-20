"""Sentinel-1 scene discovery for future slick-candidate analysis.

This module only searches real Sentinel-1 GRD scene metadata from the
Copernicus Data Space STAC catalog. It does not download SAR rasters, classify
dark features, or claim oil-spill detection.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


STAC_ROOT_URL = "https://stac.dataspace.copernicus.eu/v1/"
STAC_SEARCH_URL = f"{STAC_ROOT_URL}search"
STAC_COLLECTION = "sentinel-1-grd"
USER_AGENT = "AquaNexus-II/1.0 Sentinel-1 scene discovery"
BBOX_HALF_SIZE_DEGREES = 0.15
MAX_DAYS = 365
MAX_LIMIT = 100
HTTP_TIMEOUT_SECONDS = 20


class SentinelSearchError(RuntimeError):
    """Raised when Sentinel-1 STAC scene discovery cannot be completed."""


def search_sentinel1_scenes(
    latitude: float,
    longitude: float,
    days: int = 14,
    limit: int = 10,
) -> dict[str, Any]:
    """Search recent Sentinel-1 GRD scenes around a coordinate.

    The returned value is JSON-serializable metadata only. Scene availability
    establishes that a Sentinel-1 SAR observation exists for the queried
    space/time region; it is not oil-spill evidence by itself.
    """

    lat = _validate_coordinate(latitude, "latitude", -90.0, 90.0)
    lon = _validate_coordinate(longitude, "longitude", -180.0, 180.0)
    search_days = _validate_positive_int(days, "days", max_value=MAX_DAYS)
    search_limit = _validate_positive_int(limit, "limit", max_value=MAX_LIMIT)

    bbox = _build_bbox(lat, lon)
    start_time, end_time = _build_datetime_range(search_days)
    payload = _build_search_payload(
        bbox=bbox,
        start_time=start_time,
        end_time=end_time,
        limit=search_limit,
    )

    response = _request_stac(payload)
    features = response.get("features")

    if not isinstance(features, list):
        raise SentinelSearchError("STAC response did not contain a valid features list.")

    scenes = [_normalize_scene(feature) for feature in features]
    scenes.sort(key=_scene_sort_key, reverse=True)
    scenes = scenes[:search_limit]

    return {
        "source": {
            "name": "Copernicus Sentinel-1 GRD",
            "provider": "Copernicus Data Space Ecosystem",
            "catalog": "STAC",
            "collection": STAC_COLLECTION,
            "api_url": STAC_ROOT_URL,
        },
        "query": {
            "latitude": lat,
            "longitude": lon,
            "bounding_box": {
                "west": bbox[0],
                "south": bbox[1],
                "east": bbox[2],
                "north": bbox[3],
            },
            "days": search_days,
            "limit": search_limit,
            "start_time": start_time,
            "end_time": end_time,
        },
        "scene_count": len(scenes),
        "scenes": scenes,
        "data_notes": _data_notes(),
    }


def _validate_coordinate(
    value: Any,
    name: str,
    minimum: float,
    maximum: float,
) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be numeric.")

    try:
        coordinate = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be numeric.") from exc

    if not minimum <= coordinate <= maximum:
        raise ValueError(f"{name} must be between {minimum:g} and {maximum:g}.")

    return coordinate


def _validate_positive_int(value: Any, name: str, max_value: int) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a positive integer.")

    if isinstance(value, float) and not value.is_integer():
        raise ValueError(f"{name} must be a positive integer.")

    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a positive integer.") from exc

    if parsed <= 0:
        raise ValueError(f"{name} must be greater than 0.")

    if parsed > max_value:
        if name == "limit":
            return max_value
        raise ValueError(f"{name} must be less than or equal to {max_value}.")

    return parsed


def _build_bbox(latitude: float, longitude: float) -> list[float]:
    return [
        max(-180.0, longitude - BBOX_HALF_SIZE_DEGREES),
        max(-90.0, latitude - BBOX_HALF_SIZE_DEGREES),
        min(180.0, longitude + BBOX_HALF_SIZE_DEGREES),
        min(90.0, latitude + BBOX_HALF_SIZE_DEGREES),
    ]


def _build_datetime_range(days: int) -> tuple[str, str]:
    end = datetime.now(UTC)
    start = end - timedelta(days=days)
    return _format_datetime(start), _format_datetime(end)


def _format_datetime(value: datetime) -> str:
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


def _build_search_payload(
    bbox: list[float],
    start_time: str,
    end_time: str,
    limit: int,
) -> dict[str, Any]:
    return {
        "collections": [STAC_COLLECTION],
        "bbox": bbox,
        "datetime": f"{start_time}/{end_time}",
        "sortby": [
            {
                "field": "datetime",
                "direction": "desc",
            }
        ],
        "limit": limit,
    }


def _request_stac(payload: dict[str, Any]) -> dict[str, Any]:
    request_body = json.dumps(payload).encode("utf-8")
    request = Request(
        STAC_SEARCH_URL,
        data=request_body,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
            body = response.read()
    except HTTPError as exc:
        raise SentinelSearchError(
            f"Copernicus STAC request failed with HTTP {exc.code}."
        ) from exc
    except (TimeoutError, URLError, OSError) as exc:
        raise SentinelSearchError("Copernicus STAC request failed.") from exc

    try:
        parsed = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SentinelSearchError("Copernicus STAC response was not valid JSON.") from exc

    if not isinstance(parsed, dict):
        raise SentinelSearchError("Copernicus STAC response had an unexpected structure.")

    return parsed


def _normalize_scene(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise SentinelSearchError("STAC item had an unexpected structure.")

    item_id = item.get("id")
    if not isinstance(item_id, str) or not item_id:
        raise SentinelSearchError("STAC item was missing a valid scene id.")

    properties = item.get("properties") or {}
    if not isinstance(properties, dict):
        raise SentinelSearchError(f"STAC item {item_id} properties were malformed.")

    geometry = item.get("geometry")
    bbox = item.get("bbox")
    acquisition_time = _first_string(
        properties,
        ["datetime", "start_datetime", "end_datetime"],
    )

    polarizations = properties.get("sar:polarizations")
    if not isinstance(polarizations, list):
        polarizations = []

    return {
        "id": item_id,
        "acquisition_time": acquisition_time,
        "platform": _first_string(properties, ["platform"]),
        "constellation": _first_string(properties, ["constellation"]),
        "instrument_mode": _first_string(properties, ["sar:instrument_mode"]),
        "polarizations": _json_safe(polarizations),
        "product_type": _first_string(properties, ["product:type", "product_type"]),
        "geometry": _json_safe(geometry),
        "bbox": _json_safe(bbox),
        "properties": _curated_properties(properties),
        "assets": _extract_assets(item.get("assets")),
        "links": _extract_links(item.get("links")),
    }


def _first_string(source: dict[str, Any], keys: list[str]) -> str | None:
    for key in keys:
        value = source.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _curated_properties(properties: dict[str, Any]) -> dict[str, Any]:
    useful_keys = [
        "datetime",
        "start_datetime",
        "end_datetime",
        "platform",
        "constellation",
        "instruments",
        "sar:instrument_mode",
        "sar:polarizations",
        "processing:level",
        "product:type",
    ]
    return {
        key: _json_safe(properties[key])
        for key in useful_keys
        if key in properties
    }


def _extract_links(links: Any) -> dict[str, Any]:
    if not isinstance(links, list):
        return {}

    useful_rels = {"self", "product", "canonical", "alternate"}
    extracted: dict[str, Any] = {}

    for link in links:
        if not isinstance(link, dict):
            continue

        rel = link.get("rel")
        href = link.get("href")

        if not isinstance(rel, str) or rel not in useful_rels:
            continue
        if not isinstance(href, str) or not href:
            continue

        entry = {"href": href}
        link_type = link.get("type")
        title = link.get("title")

        if isinstance(link_type, str):
            entry["type"] = link_type
        if isinstance(title, str):
            entry["title"] = title

        if rel == "alternate":
            extracted.setdefault("alternate", []).append(entry)
        elif rel not in extracted:
            extracted[rel] = entry

    return extracted


def _extract_assets(assets: Any) -> dict[str, Any]:
    if not isinstance(assets, dict):
        return {}

    extracted: dict[str, Any] = {}

    for asset_key, asset in assets.items():
        if not isinstance(asset_key, str) or not isinstance(asset, dict):
            continue

        href = asset.get("href")
        if not isinstance(href, str) or not href:
            continue

        polarization = _infer_asset_polarization(asset_key, asset)
        if not polarization and not _is_useful_sar_asset(asset):
            continue

        normalized = {
            "key": asset_key,
            "href": href,
        }

        asset_type = asset.get("type")
        title = asset.get("title")
        roles = asset.get("roles")

        if isinstance(asset_type, str):
            normalized["type"] = asset_type
        if isinstance(title, str):
            normalized["title"] = title
        if isinstance(roles, list):
            normalized["roles"] = _json_safe(roles)
        if polarization:
            normalized["polarization"] = polarization

        file_metadata = _extract_file_metadata(asset)
        if file_metadata:
            normalized["file"] = file_metadata

        extra_metadata = _extract_asset_science_metadata(asset)
        if extra_metadata:
            normalized["metadata"] = extra_metadata

        extracted[asset_key] = normalized

    return extracted


def _infer_asset_polarization(asset_key: str, asset: dict[str, Any]) -> str | None:
    candidates = [asset_key]

    for key in ("title", "description", "name"):
        value = asset.get(key)
        if isinstance(value, str):
            candidates.append(value)

    for key in ("sar:polarizations", "polarizations"):
        value = asset.get(key)
        if isinstance(value, str):
            candidates.append(value)
        elif isinstance(value, list):
            candidates.extend(item for item in value if isinstance(item, str))

    bands = asset.get("eo:bands")
    if isinstance(bands, list):
        for band in bands:
            if not isinstance(band, dict):
                continue
            for key in ("name", "common_name", "description"):
                value = band.get(key)
                if isinstance(value, str):
                    candidates.append(value)

    matches = {
        polarization
        for candidate in candidates
        for polarization in _polarization_tokens(candidate)
    }

    if len(matches) == 1:
        return next(iter(matches))

    return None


def _polarization_tokens(value: str) -> set[str]:
    normalized = value.upper()
    tokens = set()

    for polarization in ("VV", "VH"):
        if _contains_clear_token(normalized, polarization):
            tokens.add(polarization)

    return tokens


def _contains_clear_token(value: str, token: str) -> bool:
    index = value.find(token)

    while index != -1:
        before = value[index - 1] if index > 0 else ""
        after_index = index + len(token)
        after = value[after_index] if after_index < len(value) else ""

        if not before.isalpha() and not after.isalpha():
            return True

        index = value.find(token, index + 1)

    return False


def _is_useful_sar_asset(asset: dict[str, Any]) -> bool:
    roles = asset.get("roles")
    role_values = {
        role.lower()
        for role in roles
        if isinstance(role, str)
    } if isinstance(roles, list) else set()

    asset_type = asset.get("type")
    type_value = asset_type.lower() if isinstance(asset_type, str) else ""

    title = asset.get("title")
    description = asset.get("description")
    text = " ".join(
        value.lower()
        for value in (title, description)
        if isinstance(value, str)
    )

    has_measurement_role = bool(role_values & {"data", "measurement"})
    has_raster_type = any(
        marker in type_value
        for marker in ("tiff", "geotiff", "cog", "octet-stream")
    )
    mentions_measurement = any(
        marker in text
        for marker in ("measurement", "backscatter", "sigma", "sar")
    )

    return has_measurement_role and (has_raster_type or mentions_measurement)


def _extract_file_metadata(asset: dict[str, Any]) -> dict[str, Any]:
    file_keys = [
        "file:size",
        "file:checksum",
        "file:header_size",
        "file:byte_order",
    ]

    return {
        key: _json_safe(asset[key])
        for key in file_keys
        if key in asset
    }


def _extract_asset_science_metadata(asset: dict[str, Any]) -> dict[str, Any]:
    metadata_keys = [
        "sar:polarizations",
        "sar:instrument_mode",
        "sar:frequency_band",
        "sar:product_type",
        "processing:level",
        "raster:bands",
        "eo:bands",
    ]

    return {
        key: _json_safe(asset[key])
        for key in metadata_keys
        if key in asset
    }


def _scene_sort_key(scene: dict[str, Any]) -> tuple[int, datetime]:
    parsed = _parse_datetime(scene.get("acquisition_time"))
    if parsed is None:
        return (0, datetime.min.replace(tzinfo=UTC))
    return (1, parsed)


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None

    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)

    return parsed.astimezone(UTC)


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, str | int | float | bool):
        return value

    if isinstance(value, datetime):
        return _format_datetime(value.astimezone(UTC))

    if isinstance(value, dict):
        return {
            str(key): _json_safe(nested_value)
            for key, nested_value in value.items()
        }

    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]

    return str(value)


def _data_notes() -> list[str]:
    return [
        "Sentinel-1 GRD contains Synthetic Aperture Radar satellite observations.",
        "Scene availability only establishes that a Sentinel-1 observation exists for the queried space/time region.",
        "This scene-search function does not detect oil spills.",
        "Dark SAR signatures require additional image processing and can have non-oil causes.",
        "Sentinel-1 observations occur at discrete satellite acquisition times; this is not continuous real-time sensing.",
        "Any future oil-slick analysis must report the acquisition timestamp and preserve the source/provenance.",
    ]
