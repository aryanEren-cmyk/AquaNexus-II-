"""Historical temperature anomaly helpers for cleaned ARGO observations.

This module implements a practical hackathon baseline method. It is useful for
quick comparison against nearby historical observations, but it is not formal
climatology and it does not provide statistical significance testing.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import xarray as xr

from argo.analysis.profile_analysis import get_temperature_at_pressure
from argo.processor import get_profile


SOURCE = "ARGO"
EARTH_RADIUS_KM = 6371.0088
METHODOLOGY = (
    "Practical hackathon baseline: same calendar month, nearby observations "
    "within the requested radius, and pressure within tolerance. The profile's "
    "own year is excluded when available. This is not formal climatology, a "
    "p-value, or statistical significance testing."
)


def build_temperature_baseline(
    dataset: xr.Dataset,
    latitude: float,
    longitude: float,
    pressure: float,
    month: int,
    exclude_year: int | None = None,
    radius_km: float = 250,
    pressure_tolerance_dbar: float = 10,
    min_samples: int = 10,
) -> dict[str, Any]:
    """Build a nearby same-month temperature baseline from ARGO point observations."""
    _require_variables(dataset, ("LATITUDE", "LONGITUDE", "TIME", "PRES", "TEMP"))
    lat_value, lon_value = _validate_coordinate(latitude, longitude)
    pressure_value = _validate_non_negative_float(pressure, "pressure")
    month_value = _validate_month(month)
    radius_value = _validate_positive_float(radius_km, "radius_km")
    tolerance_value = _validate_non_negative_float(
        pressure_tolerance_dbar, "pressure_tolerance_dbar"
    )
    sample_floor = _validate_min_samples(min_samples)
    excluded_year = _validate_year(exclude_year) if exclude_year is not None else None

    temperatures = np.asarray(dataset["TEMP"].values, dtype=float).ravel()
    valid_temperature = np.isfinite(temperatures)

    pressure_values = np.asarray(dataset["PRES"].values, dtype=float).ravel()
    pressure_mask = (
        np.isfinite(pressure_values)
        & (pressure_values >= pressure_value - tolerance_value)
        & (pressure_values <= pressure_value + tolerance_value)
    )

    latitudes = np.asarray(dataset["LATITUDE"].values, dtype=float).ravel()
    longitudes = np.asarray(dataset["LONGITUDE"].values, dtype=float).ravel()
    coordinate_mask = np.isfinite(latitudes) & np.isfinite(longitudes)

    years, months = _time_year_month(dataset["TIME"])
    time_mask = months == month_value
    if excluded_year is not None:
        time_mask = time_mask & (years != excluded_year)

    pre_distance_mask = valid_temperature & pressure_mask & coordinate_mask & time_mask
    if not pre_distance_mask.any():
        return _insufficient_baseline(
            0,
            [],
            radius_value,
            pressure_value,
            tolerance_value,
            sample_floor,
        )

    distances = _haversine_km(
        lat_value,
        lon_value,
        latitudes[pre_distance_mask],
        longitudes[pre_distance_mask],
    )
    distance_mask = distances <= radius_value
    baseline_temperatures = temperatures[pre_distance_mask][distance_mask]
    baseline_years = years[pre_distance_mask][distance_mask]
    baseline_years = baseline_years[baseline_years > 0]

    sample_count = int(baseline_temperatures.size)
    years_used = _json_years(baseline_years)
    if sample_count < sample_floor:
        return _insufficient_baseline(
            sample_count,
            years_used,
            radius_value,
            pressure_value,
            tolerance_value,
            sample_floor,
        )

    return {
        "sufficient_data": True,
        "sample_count": sample_count,
        "mean_temperature_c": _json_float(np.mean(baseline_temperatures)),
        "std_temperature_c": _json_float(np.std(baseline_temperatures)),
        "min_temperature_c": _json_float(np.min(baseline_temperatures)),
        "max_temperature_c": _json_float(np.max(baseline_temperatures)),
        "years_used": years_used,
        "radius_km": radius_value,
        "pressure_dbar": pressure_value,
        "pressure_tolerance_dbar": tolerance_value,
    }


def calculate_temperature_anomaly(
    observed_temperature: float,
    baseline_mean: float,
    baseline_std: float | None,
) -> dict[str, float | None]:
    """Calculate anomaly and optional z-score from an observation and baseline."""
    observed = _validate_finite_float(observed_temperature, "observed_temperature")
    baseline = _validate_finite_float(baseline_mean, "baseline_mean")
    std = _json_float_or_none(baseline_std)
    anomaly = observed - baseline

    return {
        "observed_temperature_c": observed,
        "baseline_temperature_c": baseline,
        "anomaly_c": _json_float(anomaly),
        "z_score": _json_float(anomaly / std) if std is not None and std > 0 else None,
    }


def analyze_profile_temperature_anomaly(
    dataset: xr.Dataset,
    platform_number: Any,
    cycle_number: Any,
    pressure: float,
    *,
    radius_km: float = 250,
    pressure_tolerance_dbar: float = 10,
    min_samples: int = 10,
) -> dict[str, Any]:
    """Compare one profile temperature against a nearby same-month historical baseline."""
    requested_pressure = _validate_non_negative_float(pressure, "pressure")
    profile = get_profile(dataset, platform_number, cycle_number)
    observed_temperature = get_temperature_at_pressure(profile, requested_pressure)
    if observed_temperature is None:
        raise ValueError(
            "No valid temperature is available at the requested pressure within this profile."
        )

    latitude = _first_valid(profile, "LATITUDE")
    longitude = _first_valid(profile, "LONGITUDE")
    time_value = _first_valid(profile, "TIME")
    if latitude is None or longitude is None:
        raise ValueError("Profile is missing valid latitude/longitude metadata.")
    if time_value is None:
        raise ValueError("Profile is missing valid time metadata.")

    year, month = _year_month_from_value(time_value)
    baseline = build_temperature_baseline(
        dataset,
        latitude=latitude,
        longitude=longitude,
        pressure=requested_pressure,
        month=month,
        exclude_year=year,
        radius_km=radius_km,
        pressure_tolerance_dbar=pressure_tolerance_dbar,
        min_samples=min_samples,
    )

    anomaly = None
    if baseline.get("sufficient_data"):
        anomaly = calculate_temperature_anomaly(
            observed_temperature,
            baseline["mean_temperature_c"],
            baseline["std_temperature_c"],
        )

    return {
        "source": SOURCE,
        "platform_number": _json_value(platform_number),
        "cycle_number": _json_value(cycle_number),
        "latitude": latitude,
        "longitude": longitude,
        "time": _json_value(time_value),
        "requested_pressure_dbar": requested_pressure,
        "observed_temperature_c": observed_temperature,
        "baseline": baseline,
        "anomaly": anomaly,
        "methodology": METHODOLOGY,
    }


def _insufficient_baseline(
    sample_count: int,
    years_used: list[int],
    radius_km: float,
    pressure: float,
    pressure_tolerance_dbar: float,
    min_samples: int,
) -> dict[str, Any]:
    """Return the standard insufficient-data baseline payload."""
    return {
        "sufficient_data": False,
        "reason": "insufficient_baseline_data",
        "sample_count": int(sample_count),
        "min_samples": int(min_samples),
        "mean_temperature_c": None,
        "std_temperature_c": None,
        "min_temperature_c": None,
        "max_temperature_c": None,
        "years_used": years_used,
        "radius_km": radius_km,
        "pressure_dbar": pressure,
        "pressure_tolerance_dbar": pressure_tolerance_dbar,
    }


def _time_year_month(values: xr.DataArray) -> tuple[np.ndarray, np.ndarray]:
    """Return vectorized year and month arrays from an ARGO time variable."""
    time_values = np.asarray(values.values).ravel()
    if np.issubdtype(time_values.dtype, np.datetime64):
        valid = ~np.isnat(time_values)
    else:
        valid = ~np.asarray(values.isnull().values).ravel()

    years = np.zeros(time_values.shape, dtype=int)
    months = np.zeros(time_values.shape, dtype=int)
    if not valid.any():
        return years, months

    valid_times = time_values[valid].astype("datetime64[M]")
    years[valid] = valid_times.astype("datetime64[Y]").astype(int) + 1970
    months[valid] = valid_times.astype(int) % 12 + 1
    return years, months


def _year_month_from_value(value: Any) -> tuple[int, int]:
    """Extract a JSON-friendly year and month from one scalar time value."""
    timestamp = np.datetime64(value, "s")
    if np.isnat(timestamp):
        raise ValueError("Invalid profile time metadata.")

    month_value = timestamp.astype("datetime64[M]")
    year = int(month_value.astype("datetime64[Y]").astype(int) + 1970)
    month = int(month_value.astype(int) % 12 + 1)
    return year, month


def _haversine_km(
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


def _first_valid(dataset: xr.Dataset, variable_name: str) -> Any:
    """Return the first non-null value as a JSON-friendly scalar."""
    if variable_name not in dataset:
        return None

    values = np.asarray(dataset[variable_name].values).ravel()
    nulls = np.asarray(dataset[variable_name].isnull().values).ravel()
    valid_values = values[~nulls]
    if valid_values.size == 0:
        return None

    return _json_value(valid_values[0])


def _require_variables(dataset: xr.Dataset, names: tuple[str, ...]) -> None:
    """Raise a clear error when expected variables are unavailable."""
    missing = [name for name in names if name not in dataset.variables]
    if missing:
        raise ValueError(f"Dataset is missing required variable(s): {', '.join(missing)}")


def _validate_coordinate(latitude: float, longitude: float) -> tuple[float, float]:
    """Validate latitude and longitude inputs."""
    lat_value = _validate_finite_float(latitude, "latitude")
    lon_value = _validate_finite_float(longitude, "longitude")
    if lat_value < -90 or lat_value > 90:
        raise ValueError(f"Invalid latitude: {latitude!r}")
    if lon_value < -180 or lon_value > 360:
        raise ValueError(f"Invalid longitude: {longitude!r}")
    return lat_value, lon_value


def _validate_month(month: int) -> int:
    """Validate a calendar month number."""
    try:
        month_value = int(month)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid month: {month!r}") from exc
    if month_value < 1 or month_value > 12:
        raise ValueError(f"Invalid month: {month!r}")
    return month_value


def _validate_year(year: int | None) -> int:
    """Validate a calendar year number."""
    try:
        year_value = int(year)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid exclude_year: {year!r}") from exc
    return year_value


def _validate_min_samples(min_samples: int) -> int:
    """Validate the minimum sample count."""
    try:
        value = int(min_samples)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid min_samples: {min_samples!r}") from exc
    if value < 1:
        raise ValueError(f"Invalid min_samples: {min_samples!r}")
    return value


def _validate_positive_float(value: float, name: str) -> float:
    """Validate a positive finite float."""
    numeric = _validate_finite_float(value, name)
    if numeric <= 0:
        raise ValueError(f"Invalid {name}: {value!r}")
    return numeric


def _validate_non_negative_float(value: float, name: str) -> float:
    """Validate a non-negative finite float."""
    numeric = _validate_finite_float(value, name)
    if numeric < 0:
        raise ValueError(f"Invalid {name}: {value!r}")
    return numeric


def _validate_finite_float(value: float, name: str) -> float:
    """Validate a finite numeric value."""
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid {name}: {value!r}") from exc
    if not np.isfinite(numeric):
        raise ValueError(f"Invalid {name}: {value!r}")
    return _json_float(numeric)


def _json_years(values: np.ndarray) -> list[int]:
    """Return sorted unique year values."""
    if values.size == 0:
        return []
    return [int(value) for value in np.unique(values)]


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
    """Convert a numeric value to a plain Python float."""
    return float(value)


def _json_float_or_none(value: Any) -> float | None:
    """Convert finite numeric values to float and missing values to None."""
    if value is None:
        return None
    try:
        float_value = float(value)
    except (TypeError, ValueError):
        return None
    return _json_float(float_value) if np.isfinite(float_value) else None
