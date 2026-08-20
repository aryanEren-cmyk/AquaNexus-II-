"""Combine location resolution, Copernicus state, and ARGO evidence."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import numpy as np
import xarray as xr

from argo.live.live_argo import LIVE_DATA_PATH
from argo.tools.argo_tools import find_nearest_profiles
from copernicus.present_state import PRESENT_DATA_PATH
from location.resolver import resolve_location


EARTH_RADIUS_KM = 6371.0088
POINT_DIM = "N_POINTS"
COPERNICUS_POINT_SEARCH_RADII = (3, 6, 12, 20)
COPERNICUS_MAX_GRID_DISTANCE_KM = 100.0
DATA_NOTES = [
    "Copernicus values are gridded analysis/forecast estimates.",
    "ARGO values are in-situ observations.",
    "ARGO pressure is reported in dbar and is not treated as exact depth in meters.",
]

_LIVE_DATASET: xr.Dataset | None = None
_COPERNICUS_DATASET: xr.Dataset | None = None
_LIVE_PROFILE_INDEX: list[dict[str, Any]] | None = None


class OceanConditionsError(RuntimeError):
    """Raised when a complete ocean-conditions request cannot be assembled."""


def get_ocean_conditions(
    location: str,
    depth_m: float = 0,
    argo_radius_km: float = 300,
) -> dict[str, Any]:
    """Return Copernicus state plus live and historical ARGO evidence for a location."""
    started_at = datetime.now(timezone.utc)
    requested_depth = _validate_non_negative_float(depth_m, "depth_m")
    radius = _validate_positive_float(argo_radius_km, "argo_radius_km")
    resolved = resolve_location(location)

    if resolved["type"] == "point":
        latitude = float(resolved["latitude"])
        longitude = float(resolved["longitude"])
        present_state = _source_result(
            lambda: _copernicus_point_from_existing_cache(latitude, longitude, requested_depth)
        )
        latest_argo = _latest_argo_for_point(latitude, longitude, radius)
        historical_context = _historical_context_for_point(latitude, longitude)
    elif resolved["type"] == "area":
        box = resolved["bounding_box"]
        present_state = _source_result(
            lambda: _copernicus_area_summary(box, requested_depth)
        )
        latest_argo = _latest_argo_for_area(box)
        historical_context = None
    else:
        raise OceanConditionsError(f"Unsupported resolved location type: {resolved['type']!r}")

    runtime_seconds = (datetime.now(timezone.utc) - started_at).total_seconds()
    return _json_clean(
        {
            "location": resolved,
            "requested_depth_m": requested_depth,
            "present_state": present_state,
            "latest_argo": latest_argo,
            "historical_context": historical_context,
            "data_notes": DATA_NOTES,
            "runtime_seconds": runtime_seconds,
        }
    )


def _source_result(callback: Any) -> dict[str, Any]:
    try:
        return callback()
    except Exception as exc:
        return {
            "available": False,
            "reason": str(exc),
        }


def _copernicus_area_summary(box: dict[str, float], depth_m: float) -> dict[str, Any]:
    dataset = _get_copernicus_dataset()
    _require_variables(dataset, ("time", "depth", "latitude", "longitude", "thetao", "so"))

    model_time = dataset["time"].max().values
    time_selected = dataset.sel(time=model_time)
    depth_index = _nearest_index(dataset["depth"].values, depth_m)
    depth_used = _json_value(dataset["depth"].isel(depth=depth_index).values)
    area = time_selected.isel(depth=depth_index).sel(
        latitude=slice(box["south"], box["north"]),
        longitude=slice(box["west"], box["east"]),
    )

    if int(area.sizes.get("latitude", 0)) == 0 or int(area.sizes.get("longitude", 0)) == 0:
        raise OceanConditionsError("No Copernicus grid cells exist in the location bounding box.")

    valid_mask = np.isfinite(np.asarray(area["thetao"].values, dtype=float)) & np.isfinite(
        np.asarray(area["so"].values, dtype=float)
    )
    valid_grid_cells = int(valid_mask.sum())
    if valid_grid_cells == 0:
        raise OceanConditionsError("No valid ocean cells exist in the location bounding box.")

    return {
        "source": "COPERNICUS_MARINE",
        "data_type": "gridded_analysis_forecast",
        "temperature_c": _variable_stats(area, "thetao"),
        "salinity": _variable_stats(area, "so"),
        "eastward_current_m_s": _variable_stats(area, "uo") if "uo" in area else None,
        "northward_current_m_s": _variable_stats(area, "vo") if "vo" in area else None,
        "valid_grid_cells": valid_grid_cells,
        "depth_used_m": depth_used,
        "model_time": _json_value(model_time),
        "fetched_at_utc": dataset.attrs.get("fetched_at_utc"),
    }


def _copernicus_point_from_existing_cache(
    latitude: float,
    longitude: float,
    depth_m: float,
) -> dict[str, Any]:
    dataset = _get_copernicus_dataset()
    _require_variables(dataset, ("time", "depth", "latitude", "longitude", "thetao", "so"))

    model_time = dataset["time"].max().values
    time_selected = dataset.sel(time=model_time)
    depth_index = _nearest_index(dataset["depth"].values, depth_m)
    depth_used = _json_value(dataset["depth"].isel(depth=depth_index).values)
    depth_selected = time_selected.isel(depth=depth_index)
    point = _nearest_valid_copernicus_point(
        dataset=depth_selected,
        latitude=latitude,
        longitude=longitude,
    )

    return {
        "source": "COPERNICUS_MARINE",
        "product_id": dataset.attrs.get("product_id"),
        "data_type": "gridded_analysis_forecast",
        "latitude_requested": latitude,
        "longitude_requested": longitude,
        "latitude_used": point["latitude"],
        "longitude_used": point["longitude"],
        "grid_distance_km": point["grid_distance_km"],
        "depth_requested_m": depth_m,
        "depth_used_m": depth_used,
        "temperature_c": point["thetao"],
        "salinity": point["so"],
        "eastward_current_m_s": point.get("uo"),
        "northward_current_m_s": point.get("vo"),
        "model_time": _json_value(model_time),
        "fetched_at_utc": dataset.attrs.get("fetched_at_utc"),
        "terminology": "Copernicus Marine gridded analysis/forecast estimate",
    }


def _nearest_valid_copernicus_point(
    *,
    dataset: xr.Dataset,
    latitude: float,
    longitude: float,
    search_radii: tuple[int, ...] = COPERNICUS_POINT_SEARCH_RADII,
    max_distance_km: float = COPERNICUS_MAX_GRID_DISTANCE_KM,
) -> dict[str, Any]:
    latitude_values = np.asarray(dataset["latitude"].values, dtype=float)
    longitude_values = np.asarray(dataset["longitude"].values, dtype=float)
    latitude_index = _nearest_index(latitude_values, latitude)
    longitude_index = _nearest_index(longitude_values, longitude)

    seen: set[tuple[int, int]] = set()
    for search_radius in search_radii:
        candidates: list[tuple[float, int, int]] = []
        for lat_offset in range(-search_radius, search_radius + 1):
            candidate_lat_index = latitude_index + lat_offset
            if candidate_lat_index < 0 or candidate_lat_index >= latitude_values.size:
                continue
            for lon_offset in range(-search_radius, search_radius + 1):
                candidate_lon_index = longitude_index + lon_offset
                if candidate_lon_index < 0 or candidate_lon_index >= longitude_values.size:
                    continue
                key = (candidate_lat_index, candidate_lon_index)
                if key in seen:
                    continue
                seen.add(key)
                grid_distance_km = _haversine_km(
                    latitude,
                    longitude,
                    latitude_values[candidate_lat_index],
                    longitude_values[candidate_lon_index],
                )
                candidates.append((grid_distance_km, candidate_lat_index, candidate_lon_index))

        for grid_distance_km, candidate_lat_index, candidate_lon_index in sorted(candidates):
            if grid_distance_km > max_distance_km:
                continue
            point = _copernicus_values_at(dataset, candidate_lat_index, candidate_lon_index)
            if point is not None:
                point["grid_distance_km"] = _json_float(grid_distance_km)
                return point

    raise OceanConditionsError(
        "No valid Copernicus ocean cell was found within "
        f"{max_distance_km:g} km of the requested point at the selected depth."
    )


def _copernicus_values_at(
    dataset: xr.Dataset,
    latitude_index: int,
    longitude_index: int,
) -> dict[str, Any] | None:
    thetao = _copernicus_variable_value_at(
        dataset,
        "thetao",
        latitude_index,
        longitude_index,
    )
    salinity = _copernicus_variable_value_at(
        dataset,
        "so",
        latitude_index,
        longitude_index,
    )
    if thetao is None or salinity is None:
        return None

    return {
        "latitude": _json_value(dataset["latitude"].isel(latitude=latitude_index).values),
        "longitude": _json_value(
            dataset["longitude"].isel(longitude=longitude_index).values
        ),
        "thetao": thetao,
        "so": salinity,
        "uo": _copernicus_variable_value_at(
            dataset,
            "uo",
            latitude_index,
            longitude_index,
        )
        if "uo" in dataset
        else None,
        "vo": _copernicus_variable_value_at(
            dataset,
            "vo",
            latitude_index,
            longitude_index,
        )
        if "vo" in dataset
        else None,
    }


def _copernicus_variable_value_at(
    dataset: xr.Dataset,
    variable: str,
    latitude_index: int,
    longitude_index: int,
) -> float | None:
    value = dataset[variable].isel(
        latitude=latitude_index,
        longitude=longitude_index,
    ).values
    parsed = _json_float_or_none(np.asarray(value).item())
    return parsed


def _latest_argo_for_point(
    latitude: float,
    longitude: float,
    radius_km: float,
) -> dict[str, Any] | None:
    try:
        dataset = _get_live_dataset()
        profiles = _get_live_profile_index()
        if not profiles:
            return {"available": False, "reason": "No live ARGO profiles are cached."}

        nearest = min(
            (
                {
                    **profile,
                    "distance_km": _haversine_km(
                        latitude,
                        longitude,
                        profile["latitude"],
                        profile["longitude"],
                    ),
                }
                for profile in profiles
            ),
            key=lambda item: item["distance_km"],
        )
        if nearest["distance_km"] > radius_km:
            return {
                "available": False,
                "reason": (
                    "Nearest live ARGO profile is farther than "
                    f"{radius_km:g} km from the requested location."
                ),
                "nearest_distance_km": _json_float(nearest["distance_km"]),
            }
        return _profile_payload(dataset, nearest, include_surface=True)
    except Exception as exc:
        return {
            "available": False,
            "reason": str(exc),
        }


def _latest_argo_for_area(box: dict[str, float]) -> dict[str, Any] | None:
    try:
        dataset = _get_live_dataset()
        profiles = [
            profile
            for profile in _get_live_profile_index()
            if box["south"] <= profile["latitude"] <= box["north"]
            and box["west"] <= profile["longitude"] <= box["east"]
        ]
        if not profiles:
            return {
                "available": False,
                "reason": "No live ARGO profiles are cached inside the resolved area.",
                "profile_count": 0,
                "unique_floats": 0,
                "latest_observation_time": None,
                "latest_profile": None,
            }

        latest = max(profiles, key=lambda item: _datetime64_or_min(item.get("observation_time")))
        unique_floats = {str(profile["float_id"]) for profile in profiles}
        return {
            "profile_count": len(profiles),
            "unique_floats": len(unique_floats),
            "latest_observation_time": latest.get("observation_time"),
            "latest_profile": _profile_payload(dataset, latest, include_surface=True),
        }
    except Exception as exc:
        return {
            "available": False,
            "reason": str(exc),
        }


def _historical_context_for_point(latitude: float, longitude: float) -> dict[str, Any] | None:
    try:
        nearest_result = find_nearest_profiles(latitude, longitude, limit=1)
        profiles = nearest_result.get("profiles") or []
        if not profiles:
            return {"available": False, "reason": "No historical ARGO profiles are cached."}
        nearest = profiles[0]
        return {
            "source": "ARGO_HISTORICAL",
            "float_id": nearest.get("platform_number"),
            "cycle": nearest.get("cycle_number"),
            "latitude": nearest.get("latitude"),
            "longitude": nearest.get("longitude"),
            "distance_km": nearest.get("distance_km"),
            "observation_time": nearest.get("time"),
        }
    except Exception as exc:
        return {
            "available": False,
            "reason": str(exc),
        }


def _profile_payload(
    dataset: xr.Dataset,
    profile: dict[str, Any],
    *,
    include_surface: bool,
) -> dict[str, Any]:
    payload = {
        "source": profile.get("source", "ARGO"),
        "float_id": profile["float_id"],
        "cycle": profile["cycle"],
        "latitude": profile["latitude"],
        "longitude": profile["longitude"],
        "distance_km": _json_float(profile["distance_km"]) if "distance_km" in profile else None,
        "observation_time": profile.get("observation_time"),
        "latest_observation_age_hours": _age_hours(profile.get("observation_time")),
    }
    if include_surface:
        surface = _surface_like_observation(dataset, profile["float_id"], profile["cycle"])
        payload["surface_like_observation"] = surface
    return payload


def _surface_like_observation(
    dataset: xr.Dataset,
    float_id: Any,
    cycle: Any,
) -> dict[str, Any] | None:
    profile = _select_profile(dataset, float_id, cycle)
    if int(profile.sizes.get(POINT_DIM, 0)) == 0:
        return None

    pressure = np.asarray(profile["PRES"].values, dtype=float).ravel()
    temperature = _float_array_or_nan(profile, "TEMP", pressure.shape)
    salinity = _float_array_or_nan(profile, "PSAL", pressure.shape)
    valid = np.isfinite(pressure) & (np.isfinite(temperature) | np.isfinite(salinity))
    if not valid.any():
        return None

    valid_indices = np.flatnonzero(valid)
    selected_index = int(valid_indices[np.argmin(pressure[valid])])
    return {
        "pressure_dbar": _json_float(pressure[selected_index]),
        "temperature_c": _json_float_or_none(temperature[selected_index]),
        "salinity": _json_float_or_none(salinity[selected_index]),
    }


def _select_profile(dataset: xr.Dataset, float_id: Any, cycle: Any) -> xr.Dataset:
    _require_variables(dataset, ("PLATFORM_NUMBER", "CYCLE_NUMBER"))
    return dataset.where(
        (dataset["PLATFORM_NUMBER"] == float_id) & (dataset["CYCLE_NUMBER"] == cycle),
        drop=True,
    )


def _get_live_dataset() -> xr.Dataset:
    global _LIVE_DATASET
    if _LIVE_DATASET is None:
        if not LIVE_DATA_PATH.exists():
            raise OceanConditionsError(f"Live ARGO cache is missing: {LIVE_DATA_PATH}")
        _LIVE_DATASET = xr.open_dataset(LIVE_DATA_PATH)
    return _LIVE_DATASET


def _get_copernicus_dataset() -> xr.Dataset:
    global _COPERNICUS_DATASET
    if _COPERNICUS_DATASET is None:
        if not PRESENT_DATA_PATH.exists():
            raise OceanConditionsError(f"Copernicus cache is missing: {PRESENT_DATA_PATH}")
        _COPERNICUS_DATASET = xr.open_dataset(PRESENT_DATA_PATH)
    return _COPERNICUS_DATASET


def _get_live_profile_index() -> list[dict[str, Any]]:
    global _LIVE_PROFILE_INDEX
    if _LIVE_PROFILE_INDEX is None:
        _LIVE_PROFILE_INDEX = _build_profile_index(_get_live_dataset(), source="ARGO_REALTIME")
    return _LIVE_PROFILE_INDEX


def _build_profile_index(dataset: xr.Dataset, *, source: str) -> list[dict[str, Any]]:
    _require_variables(dataset, ("PLATFORM_NUMBER", "CYCLE_NUMBER", "LATITUDE", "LONGITUDE"))

    platform = np.asarray(dataset["PLATFORM_NUMBER"].values).ravel()
    cycle = np.asarray(dataset["CYCLE_NUMBER"].values).ravel()
    latitude = np.asarray(dataset["LATITUDE"].values, dtype=float).ravel()
    longitude = np.asarray(dataset["LONGITUDE"].values, dtype=float).ravel()
    time_values = np.asarray(dataset["TIME"].values).ravel() if "TIME" in dataset else None

    profiles: dict[tuple[Any, Any], dict[str, Any]] = {}
    for idx, (platform_value, cycle_value, lat_value, lon_value) in enumerate(
        zip(platform, cycle, latitude, longitude)
    ):
        if not np.isfinite(lat_value) or not np.isfinite(lon_value):
            continue

        key = (_json_value(platform_value), _json_value(cycle_value))
        time_value = _json_value(time_values[idx]) if time_values is not None else None
        existing = profiles.get(key)
        if existing is not None:
            if _datetime64_or_min(time_value) > _datetime64_or_min(existing.get("observation_time")):
                existing["observation_time"] = time_value
            continue

        profiles[key] = {
            "source": source,
            "float_id": key[0],
            "cycle": key[1],
            "latitude": _json_float(lat_value),
            "longitude": _json_float(lon_value),
            "observation_time": time_value,
        }

    return list(profiles.values())


def _variable_stats(dataset: xr.Dataset, variable: str) -> dict[str, float | None]:
    values = np.asarray(dataset[variable].values, dtype=float)
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return {
            "mean": None,
            "min": None,
            "max": None,
        }
    return {
        "mean": _json_float(np.nanmean(finite)),
        "min": _json_float(np.nanmin(finite)),
        "max": _json_float(np.nanmax(finite)),
    }


def _float_array_or_nan(dataset: xr.Dataset, variable: str, shape: tuple[int, ...]) -> np.ndarray:
    if variable not in dataset:
        return np.full(shape, np.nan)
    return np.asarray(dataset[variable].values, dtype=float).ravel()


def _require_variables(dataset: xr.Dataset, variables: tuple[str, ...]) -> None:
    missing = [variable for variable in variables if variable not in dataset]
    if missing:
        raise OceanConditionsError(f"Dataset is missing required variable(s): {', '.join(missing)}")


def _nearest_index(values: np.ndarray, target: float) -> int:
    return int(np.nanargmin(np.abs(values.astype(float) - target)))


def _haversine_km(lat_a: float, lon_a: float, lat_b: float, lon_b: float) -> float:
    lat1, lon1, lat2, lon2 = np.radians([lat_a, lon_a, lat_b, lon_b])
    delta_lat = lat2 - lat1
    delta_lon = lon2 - lon1
    haversine = (
        np.sin(delta_lat / 2) ** 2
        + np.cos(lat1) * np.cos(lat2) * np.sin(delta_lon / 2) ** 2
    )
    return float(2 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(haversine)))


def _age_hours(value: Any) -> float | None:
    timestamp = _parse_datetime(value)
    if timestamp is None:
        return None
    return _json_float((datetime.now(timezone.utc) - timestamp).total_seconds() / 3600)


def _parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _datetime64_or_min(value: Any) -> np.datetime64:
    if value is None:
        return np.datetime64("1678-01-01T00:00:00")
    try:
        return np.datetime64(str(value))
    except ValueError:
        return np.datetime64("1678-01-01T00:00:00")


def _validate_non_negative_float(value: Any, name: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be numeric.") from exc
    if not np.isfinite(parsed) or parsed < 0:
        raise ValueError(f"{name} must be a finite non-negative number.")
    return _json_float(parsed)


def _validate_positive_float(value: Any, name: str) -> float:
    parsed = _validate_non_negative_float(value, name)
    if parsed <= 0:
        raise ValueError(f"{name} must be greater than 0.")
    return parsed


def _json_clean(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_clean(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_clean(item) for item in value]
    if isinstance(value, tuple):
        return [_json_clean(item) for item in value]
    return _json_value(value)


def _json_value(value: Any) -> Any:
    if isinstance(value, np.datetime64):
        return str(np.datetime_as_string(value, unit="s"))
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="ignore").strip()

    scalar = value.item() if hasattr(value, "item") else value
    if isinstance(scalar, np.datetime64):
        return str(np.datetime_as_string(scalar, unit="s"))
    if isinstance(scalar, bytes):
        return scalar.decode("utf-8", errors="ignore").strip()
    if isinstance(scalar, float):
        if not np.isfinite(scalar):
            return None
        return int(scalar) if scalar.is_integer() else scalar
    if isinstance(scalar, np.floating):
        float_value = float(scalar)
        if not np.isfinite(float_value):
            return None
        return int(float_value) if float_value.is_integer() else float_value
    if isinstance(scalar, np.integer):
        return int(scalar)
    if hasattr(scalar, "isoformat"):
        return scalar.isoformat()
    return scalar


def _json_float(value: Any) -> float:
    return float(value)


def _json_float_or_none(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(parsed):
        return None
    return parsed
