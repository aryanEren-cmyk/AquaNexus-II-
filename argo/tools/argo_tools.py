"""Public JSON-friendly tools for ARGO profile access and comparison."""

from __future__ import annotations

from typing import Any

import numpy as np
import xarray as xr

from argo.analysis.anomaly_analysis import analyze_profile_temperature_anomaly
from argo.analysis.profile_analysis import (
    calculate_profile_statistics,
    compare_profiles,
    detect_thermocline,
    get_salinity_at_pressure,
    get_temperature_at_pressure,
    profile_to_records,
)
from argo.processor import get_available_cycles, get_clean_dataset, get_float_data, get_profile


SOURCE = "ARGO"
EARTH_RADIUS_KM = 6371.0088
_DATASET: xr.Dataset | None = None


def get_float_profile(platform_number: int, cycle_number: int) -> dict[str, Any]:
    """Return metadata, statistics, thermocline heuristic, and records for one profile."""
    dataset = _get_dataset()
    profile = _get_profile_or_raise(dataset, platform_number, cycle_number)

    return {
        "source": SOURCE,
        "platform_number": _json_value(platform_number),
        "cycle_number": _json_value(cycle_number),
        "latitude": _first_valid(profile, "LATITUDE"),
        "longitude": _first_valid(profile, "LONGITUDE"),
        "time": _first_valid(profile, "TIME"),
        "direction": _first_valid(profile, "DIRECTION"),
        "data_mode": _first_valid(profile, "DATA_MODE"),
        "statistics": calculate_profile_statistics(profile),
        "thermocline": detect_thermocline(profile),
        "profile": profile_to_records(profile),
    }


def get_value_at_pressure(platform_number: int, cycle_number: int, pressure: float) -> dict[str, Any]:
    """Return bounded interpolated temperature and salinity for one profile pressure."""
    requested_pressure = _validate_pressure(pressure)
    dataset = _get_dataset()
    profile = _get_profile_or_raise(dataset, platform_number, cycle_number)

    return {
        "source": SOURCE,
        "platform_number": _json_value(platform_number),
        "cycle_number": _json_value(cycle_number),
        "requested_pressure_dbar": requested_pressure,
        "temperature_c": get_temperature_at_pressure(profile, requested_pressure),
        "salinity_psu": get_salinity_at_pressure(profile, requested_pressure),
        "latitude": _first_valid(profile, "LATITUDE"),
        "longitude": _first_valid(profile, "LONGITUDE"),
        "time": _first_valid(profile, "TIME"),
    }


def list_float_cycles(platform_number: int) -> dict[str, Any]:
    """Return all available cycle numbers for one ARGO float."""
    dataset = _get_dataset()
    _get_float_data_or_raise(dataset, platform_number)
    cycles = [_json_value(cycle) for cycle in get_available_cycles(dataset, platform_number)]

    return {
        "source": SOURCE,
        "platform_number": _json_value(platform_number),
        "cycles": cycles,
        "cycle_count": len(cycles),
    }


def get_float_summary(platform_number: int) -> dict[str, Any]:
    """Return observation coverage metadata for one ARGO float."""
    dataset = _get_dataset()
    float_data = _get_float_data_or_raise(dataset, platform_number)

    return {
        "source": SOURCE,
        "platform_number": _json_value(platform_number),
        "cycle_count": len(get_available_cycles(dataset, platform_number)),
        "first_observation": _stat_value(float_data, "TIME", np.nanmin),
        "latest_observation": _stat_value(float_data, "TIME", np.nanmax),
        "latitude_range": _range(float_data, "LATITUDE"),
        "longitude_range": _range(float_data, "LONGITUDE"),
    }


def find_nearest_profiles(latitude: float, longitude: float, limit: int = 5) -> dict[str, Any]:
    """Find nearest ARGO profiles to a coordinate using profile-level Haversine distance."""
    query_latitude, query_longitude = _validate_coordinate(latitude, longitude)
    result_limit = _validate_limit(limit)
    dataset = _get_dataset()

    profile_index = _profile_index(dataset)
    if not profile_index:
        profiles: list[dict[str, Any]] = []
    else:
        profiles = sorted(
            (
                {
                    **profile,
                    "distance_km": _json_float(
                        _haversine_km(
                            query_latitude,
                            query_longitude,
                            profile["latitude"],
                            profile["longitude"],
                        )
                    ),
                }
                for profile in profile_index
            ),
            key=lambda item: item["distance_km"],
        )[:result_limit]

    return {
        "source": SOURCE,
        "query": {
            "latitude": query_latitude,
            "longitude": query_longitude,
        },
        "profiles": profiles,
    }


def compare_float_profiles(
    float_a: int, cycle_a: int, float_b: int, cycle_b: int
) -> dict[str, Any]:
    """Compare two ARGO float profiles using the profile analysis module."""
    dataset = _get_dataset()
    profile_a = _get_profile_or_raise(dataset, float_a, cycle_a)
    profile_b = _get_profile_or_raise(dataset, float_b, cycle_b)

    return {
        "source": SOURCE,
        "comparison": compare_profiles(profile_a, profile_b),
    }


def get_temperature_anomaly(
    platform_number: int, cycle_number: int, pressure: float
) -> dict[str, Any]:
    """Return historical temperature anomaly analysis for one profile pressure."""
    dataset = _get_dataset()
    return analyze_profile_temperature_anomaly(
        dataset,
        platform_number=platform_number,
        cycle_number=cycle_number,
        pressure=pressure,
    )


def _get_dataset() -> xr.Dataset:
    """Load and cache the cleaned ARGO dataset on first use."""
    global _DATASET
    if _DATASET is None:
        _DATASET = get_clean_dataset()
    return _DATASET


def _get_float_data_or_raise(dataset: xr.Dataset, platform_number: int) -> xr.Dataset:
    """Return float observations or raise a clear unknown-float error."""
    try:
        return get_float_data(dataset, platform_number)
    except ValueError as exc:
        raise ValueError(f"Unknown ARGO float: {platform_number!r}") from exc


def _get_profile_or_raise(dataset: xr.Dataset, platform_number: int, cycle_number: int) -> xr.Dataset:
    """Return a profile or raise a clear unknown-float/cycle error."""
    _get_float_data_or_raise(dataset, platform_number)
    try:
        return get_profile(dataset, platform_number, cycle_number)
    except ValueError as exc:
        raise ValueError(
            f"Unknown ARGO cycle {cycle_number!r} for float {platform_number!r}"
        ) from exc


def _profile_index(dataset: xr.Dataset) -> list[dict[str, Any]]:
    """Return one metadata row per float-cycle profile."""
    required = ("PLATFORM_NUMBER", "CYCLE_NUMBER", "LATITUDE", "LONGITUDE")
    missing = [name for name in required if name not in dataset.variables]
    if missing:
        raise ValueError(f"Dataset is missing required variable(s): {', '.join(missing)}")

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
        if key in profiles:
            continue

        profiles[key] = {
            "platform_number": key[0],
            "cycle_number": key[1],
            "latitude": _json_float(lat_value),
            "longitude": _json_float(lon_value),
            "time": _json_value(time_values[idx]) if time_values is not None else None,
        }

    return list(profiles.values())


def _first_valid(dataset: xr.Dataset, variable_name: str) -> Any:
    """Return the first non-null variable value as a JSON-friendly scalar."""
    if variable_name not in dataset:
        return None

    values = np.asarray(dataset[variable_name].values).ravel()
    nulls = np.asarray(dataset[variable_name].isnull().values).ravel()
    valid_values = values[~nulls]
    if valid_values.size == 0:
        return None

    return _json_value(valid_values[0])


def _stat_value(dataset: xr.Dataset, variable_name: str, function: Any) -> Any:
    """Return a JSON-friendly min/max value for a variable, or None when unavailable."""
    if variable_name not in dataset:
        return None

    values = np.asarray(dataset[variable_name].values).ravel()
    nulls = np.asarray(dataset[variable_name].isnull().values).ravel()
    valid_values = values[~nulls]
    if valid_values.size == 0:
        return None

    return _json_value(function(valid_values))


def _range(dataset: xr.Dataset, variable_name: str) -> list[float | None]:
    """Return a JSON-friendly numeric range for a variable."""
    if variable_name not in dataset:
        return [None, None]

    values = np.asarray(dataset[variable_name].values, dtype=float).ravel()
    values = values[np.isfinite(values)]
    if values.size == 0:
        return [None, None]

    return [_json_float(np.min(values)), _json_float(np.max(values))]


def _validate_pressure(pressure: float) -> float:
    """Validate pressure input for bounded interpolation tools."""
    try:
        value = float(pressure)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid pressure input: {pressure!r}") from exc

    if not np.isfinite(value) or value < 0:
        raise ValueError(f"Invalid pressure input: {pressure!r}")

    return _json_float(value)


def _validate_coordinate(latitude: float, longitude: float) -> tuple[float, float]:
    """Validate latitude and longitude inputs."""
    try:
        lat_value = float(latitude)
        lon_value = float(longitude)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid coordinate: latitude={latitude!r}, longitude={longitude!r}") from exc

    if not np.isfinite(lat_value) or lat_value < -90 or lat_value > 90:
        raise ValueError(f"Invalid latitude: {latitude!r}")
    if not np.isfinite(lon_value) or lon_value < -180 or lon_value > 360:
        raise ValueError(f"Invalid longitude: {longitude!r}")

    return _json_float(lat_value), _json_float(lon_value)


def _validate_limit(limit: int) -> int:
    """Validate nearest-profile result limit."""
    try:
        value = int(limit)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid limit: {limit!r}") from exc

    if value < 1:
        raise ValueError(f"Invalid limit: {limit!r}")

    return value


def _haversine_km(lat_a: float, lon_a: float, lat_b: float, lon_b: float) -> float:
    """Calculate great-circle distance in kilometers."""
    lat1, lon1, lat2, lon2 = np.radians([lat_a, lon_a, lat_b, lon_b])
    delta_lat = lat2 - lat1
    delta_lon = lon2 - lon1
    haversine = (
        np.sin(delta_lat / 2) ** 2
        + np.cos(lat1) * np.cos(lat2) * np.sin(delta_lon / 2) ** 2
    )
    return float(2 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(haversine)))


def _json_value(value: Any) -> Any:
    """Convert NumPy/xarray scalar values into JSON-friendly Python values."""
    if isinstance(value, np.datetime64):
        return str(np.datetime_as_string(value, unit="s"))

    scalar = value.item() if hasattr(value, "item") else value

    if isinstance(scalar, bytes):
        return scalar.decode("utf-8", errors="ignore").strip()
    if hasattr(scalar, "isoformat"):
        return scalar.isoformat()
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

    return scalar


def _json_float(value: Any) -> float:
    """Convert a finite numeric value to a plain Python float."""
    return float(value)
