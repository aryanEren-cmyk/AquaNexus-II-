"""Profile-level scientific analysis helpers for cleaned ARGO observations."""

from __future__ import annotations

from typing import Any

import numpy as np
import xarray as xr


POINT_DIM = "N_POINTS"


def get_temperature_at_pressure(profile: xr.Dataset, pressure: float) -> float | None:
    """Return temperature at a pressure using exact match or bounded linear interpolation."""
    return _value_at_pressure(profile, "TEMP", pressure)


def get_salinity_at_pressure(profile: xr.Dataset, pressure: float) -> float | None:
    """Return salinity at a pressure using exact match or bounded linear interpolation."""
    return _value_at_pressure(profile, "PSAL", pressure)


def calculate_temperature_gradient(profile: xr.Dataset) -> list[dict[str, float]]:
    """Calculate temperature gradients between consecutive valid pressure-temperature points."""
    pressure, temperature = _valid_xy(profile, "PRES", "TEMP")
    if pressure.size < 2:
        return []

    order = np.argsort(pressure)
    pressure = pressure[order]
    temperature = temperature[order]

    records: list[dict[str, float]] = []
    for idx in range(pressure.size - 1):
        pressure_start = pressure[idx]
        pressure_end = pressure[idx + 1]
        delta_pressure = pressure_end - pressure_start

        if delta_pressure <= 0:
            continue

        temperature_start = temperature[idx]
        temperature_end = temperature[idx + 1]
        delta_temperature = temperature_end - temperature_start

        records.append(
            {
                "pressure_start": _json_float(pressure_start),
                "pressure_end": _json_float(pressure_end),
                "temperature_start": _json_float(temperature_start),
                "temperature_end": _json_float(temperature_end),
                "delta_pressure": _json_float(delta_pressure),
                "delta_temperature": _json_float(delta_temperature),
                "gradient_c_per_dbar": _json_float(delta_temperature / delta_pressure),
            }
        )

    return records


def calculate_profile_statistics(profile: xr.Dataset) -> dict[str, float | int | None]:
    """Return basic profile statistics without fabricating missing measurements."""
    temperature = _valid_values(profile, "TEMP")
    salinity = _valid_values(profile, "PSAL")
    pressure = _valid_values(profile, "PRES")

    return {
        "valid_temperature_points": int(temperature.size),
        "valid_salinity_points": int(salinity.size),
        "min_temperature": _stat_or_none(temperature, np.min),
        "max_temperature": _stat_or_none(temperature, np.max),
        "mean_temperature": _stat_or_none(temperature, np.mean),
        "min_salinity": _stat_or_none(salinity, np.min),
        "max_salinity": _stat_or_none(salinity, np.max),
        "mean_salinity": _stat_or_none(salinity, np.mean),
        "min_pressure": _stat_or_none(pressure, np.min),
        "max_pressure": _stat_or_none(pressure, np.max),
    }


def detect_thermocline(profile: xr.Dataset, threshold: float = 0.05) -> dict[str, Any]:
    """Detect a simplified thermocline candidate from the strongest temperature gradient.

    This is a deterministic heuristic, not a formal scientific thermocline
    classification. It marks the segment with the largest absolute temperature
    gradient as detected only when that magnitude meets or exceeds ``threshold``.
    """
    gradients = calculate_temperature_gradient(profile)
    result: dict[str, Any] = {
        "detected": False,
        "pressure_start": None,
        "pressure_end": None,
        "gradient_c_per_dbar": None,
        "threshold": _json_float(threshold),
        "method": "strongest_temperature_gradient",
    }

    if not gradients:
        return result

    strongest = max(gradients, key=lambda item: abs(item["gradient_c_per_dbar"]))
    gradient = strongest["gradient_c_per_dbar"]
    result.update(
        {
            "detected": abs(gradient) >= threshold,
            "pressure_start": strongest["pressure_start"],
            "pressure_end": strongest["pressure_end"],
            "gradient_c_per_dbar": gradient,
        }
    )

    return result


def compare_profiles(profile_a: xr.Dataset, profile_b: xr.Dataset) -> dict[str, Any]:
    """Compare two ARGO profiles using summary fields and thermocline heuristic results."""
    summary_a = _comparison_summary(profile_a)
    summary_b = _comparison_summary(profile_b)

    return {
        "profile_a": summary_a,
        "profile_b": summary_b,
        "differences": {
            "surface_temperature": _difference(
                summary_a["surface_temperature"], summary_b["surface_temperature"]
            ),
            "surface_salinity": _difference(summary_a["surface_salinity"], summary_b["surface_salinity"]),
            "max_pressure": _difference(summary_a["max_pressure"], summary_b["max_pressure"]),
            "mean_temperature": _difference(
                summary_a["mean_temperature"], summary_b["mean_temperature"]
            ),
            "mean_salinity": _difference(summary_a["mean_salinity"], summary_b["mean_salinity"]),
        },
    }


def profile_to_records(profile: xr.Dataset) -> list[dict[str, float | None]]:
    """Convert a profile into pressure-temperature-salinity records for visualization."""
    _require_variables(profile, ("PRES",))

    pressure = _array(profile["PRES"])
    temperature = _array(profile["TEMP"]) if "TEMP" in profile else np.full(pressure.shape, np.nan)
    salinity = _array(profile["PSAL"]) if "PSAL" in profile else np.full(pressure.shape, np.nan)

    records: list[dict[str, float | None]] = []
    for pressure_value, temperature_value, salinity_value in zip(pressure, temperature, salinity):
        if not np.isfinite(pressure_value):
            continue
        if not np.isfinite(temperature_value) and not np.isfinite(salinity_value):
            continue

        records.append(
            {
                "pressure": _json_float(pressure_value),
                "temperature": _json_float_or_none(temperature_value),
                "salinity": _json_float_or_none(salinity_value),
            }
        )

    return records


def _value_at_pressure(profile: xr.Dataset, variable_name: str, pressure: float) -> float | None:
    """Return an exact or interpolated profile value without extrapolation."""
    pressure_values, measured_values = _valid_xy(profile, "PRES", variable_name)
    if pressure_values.size == 0:
        return None

    target_pressure = float(pressure)
    order = np.argsort(pressure_values)
    pressure_values = pressure_values[order]
    measured_values = measured_values[order]

    exact_matches = np.isclose(pressure_values, target_pressure, rtol=0.0, atol=1e-9)
    if exact_matches.any():
        return _json_float(measured_values[exact_matches][0])

    unique_pressure, unique_indices = np.unique(pressure_values, return_index=True)
    unique_values = measured_values[unique_indices]
    if unique_pressure.size < 2:
        return None
    if target_pressure < unique_pressure[0] or target_pressure > unique_pressure[-1]:
        return None

    interpolated = np.interp(target_pressure, unique_pressure, unique_values)
    return _json_float(interpolated)


def _comparison_summary(profile: xr.Dataset) -> dict[str, Any]:
    """Build one side of a profile comparison payload."""
    stats = calculate_profile_statistics(profile)
    surface_pressure = stats["min_pressure"]

    return {
        "float_id": _first_unique_value(profile, "PLATFORM_NUMBER"),
        "cycle_number": _first_unique_value(profile, "CYCLE_NUMBER"),
        "surface_temperature": (
            get_temperature_at_pressure(profile, surface_pressure) if surface_pressure is not None else None
        ),
        "surface_salinity": (
            get_salinity_at_pressure(profile, surface_pressure) if surface_pressure is not None else None
        ),
        "max_pressure": stats["max_pressure"],
        "mean_temperature": stats["mean_temperature"],
        "mean_salinity": stats["mean_salinity"],
        "thermocline": detect_thermocline(profile),
    }


def _valid_xy(profile: xr.Dataset, x_name: str, y_name: str) -> tuple[np.ndarray, np.ndarray]:
    """Return finite paired values for two profile variables."""
    _require_variables(profile, (x_name, y_name))
    x_values = _array(profile[x_name])
    y_values = _array(profile[y_name])
    valid = np.isfinite(x_values) & np.isfinite(y_values)
    return x_values[valid], y_values[valid]


def _valid_values(profile: xr.Dataset, variable_name: str) -> np.ndarray:
    """Return finite values for a profile variable, or an empty array if absent."""
    if variable_name not in profile:
        return np.array([], dtype=float)

    values = _array(profile[variable_name])
    return values[np.isfinite(values)]


def _array(values: xr.DataArray) -> np.ndarray:
    """Return a flattened numeric NumPy array for one profile variable."""
    return np.asarray(values.values, dtype=float).ravel()


def _require_variables(profile: xr.Dataset, names: tuple[str, ...]) -> None:
    """Raise a clear error when a profile lacks required variables."""
    missing = [name for name in names if name not in profile.variables]
    if missing:
        raise ValueError(f"Profile is missing required variable(s): {', '.join(missing)}")


def _stat_or_none(values: np.ndarray, function: Any) -> float | None:
    """Return a JSON-friendly statistic or None for empty input."""
    if values.size == 0:
        return None
    return _json_float(function(values))


def _first_unique_value(profile: xr.Dataset, variable_name: str) -> Any:
    """Return a stable profile identifier when present and unambiguous enough."""
    if variable_name not in profile:
        return None

    values = np.asarray(profile[variable_name].values).ravel()
    values = values[~np.asarray(profile[variable_name].isnull().values).ravel()]
    if values.size == 0:
        return None

    scalar = values[0].item() if hasattr(values[0], "item") else values[0]
    if isinstance(scalar, float) and scalar.is_integer():
        return int(scalar)
    return scalar


def _difference(value_a: float | int | None, value_b: float | int | None) -> float | None:
    """Return b minus a when both values are available."""
    if value_a is None or value_b is None:
        return None
    return _json_float(float(value_b) - float(value_a))


def _json_float(value: Any) -> float:
    """Convert a numeric value to a plain Python float."""
    return float(value)


def _json_float_or_none(value: Any) -> float | None:
    """Convert finite numeric values to float and missing values to None."""
    return _json_float(value) if np.isfinite(value) else None
