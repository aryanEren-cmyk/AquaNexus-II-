"""Public JSON-friendly tools for ARGO profile access and comparison."""

from __future__ import annotations

from pathlib import Path
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
PROFILE_INDEX_PATH = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "processed"
    / "historical_profile_index.npz"
)
_DATASET: xr.Dataset | None = None
_PROFILE_INDEX: dict[str, np.ndarray] | None = None


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
    profile_index = _get_profile_index()
    profiles = _nearest_profiles_from_index(
        profile_index,
        latitude=query_latitude,
        longitude=query_longitude,
        limit=result_limit,
    )

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


def _get_profile_index() -> dict[str, np.ndarray]:
    """Load and cache the persistent historical profile-level spatial index."""
    global _PROFILE_INDEX
    if _PROFILE_INDEX is not None:
        return _PROFILE_INDEX
    if not PROFILE_INDEX_PATH.exists():
        raise FileNotFoundError(
            "Historical ARGO profile index is missing. Build it once with: "
            "python argo/build_profile_index.py"
        )

    with np.load(PROFILE_INDEX_PATH, allow_pickle=False) as loaded:
        required = ("platform_number", "cycle_number", "latitude", "longitude", "observation_time")
        missing = [name for name in required if name not in loaded.files]
        if missing:
            raise ValueError(
                "Historical ARGO profile index is missing field(s): "
                f"{', '.join(missing)}. Rebuild with: python argo/build_profile_index.py"
            )
        _PROFILE_INDEX = {name: loaded[name] for name in required}

    return _PROFILE_INDEX


def _nearest_profiles_from_index(
    profile_index: dict[str, np.ndarray],
    *,
    latitude: float,
    longitude: float,
    limit: int,
) -> list[dict[str, Any]]:
    latitudes = np.asarray(profile_index["latitude"], dtype=float)
    longitudes = np.asarray(profile_index["longitude"], dtype=float)
    if latitudes.size == 0:
        return []

    distances = _haversine_distances_km(latitude, longitude, latitudes, longitudes)
    finite = np.isfinite(distances)
    if not finite.any():
        return []

    finite_indices = np.flatnonzero(finite)
    finite_distances = distances[finite]
    selected_count = min(limit, finite_distances.size)
    nearest_positions = np.argpartition(finite_distances, selected_count - 1)[
        :selected_count
    ]
    nearest_indices = finite_indices[nearest_positions]
    nearest_indices = nearest_indices[np.argsort(distances[nearest_indices])]

    return [
        {
            "platform_number": _json_value(profile_index["platform_number"][idx]),
            "cycle_number": _json_value(profile_index["cycle_number"][idx]),
            "latitude": _json_float(latitudes[idx]),
            "longitude": _json_float(longitudes[idx]),
            "time": _json_value(profile_index["observation_time"][idx]),
            "distance_km": _json_float(distances[idx]),
        }
        for idx in nearest_indices
    ]


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


def _haversine_distances_km(
    latitude: float,
    longitude: float,
    latitudes: np.ndarray,
    longitudes: np.ndarray,
) -> np.ndarray:
    """Calculate vectorized great-circle distances in kilometers."""
    lat1 = np.radians(latitude)
    lon1 = np.radians(longitude)
    lat2 = np.radians(latitudes)
    lon2 = np.radians(longitudes)
    delta_lat = lat2 - lat1
    delta_lon = lon2 - lon1
    haversine = (
        np.sin(delta_lat / 2) ** 2
        + np.cos(lat1) * np.cos(lat2) * np.sin(delta_lon / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(haversine))


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
