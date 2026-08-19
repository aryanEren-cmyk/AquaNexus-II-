"""Fetch, cache, and query Copernicus Marine present-state ocean physics fields."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

import numpy as np
import xarray as xr


# AquaNexus ocean coverage
LON_MIN = 60.0
LON_MAX = 100.0
LAT_MIN = 0.0
LAT_MAX = 30.0
DEPTH_MIN = 0.0
DEPTH_MAX = 2000.0

SOURCE_NAME = "COPERNICUS_MARINE"
PRODUCT_ID = "GLOBAL_ANALYSISFORECAST_PHY_001_024"
DATASET_VARIABLES = {
    "cmems_mod_glo_phy-thetao_anfc_0.083deg_PT6H-i": ("thetao",),
    "cmems_mod_glo_phy-so_anfc_0.083deg_PT6H-i": ("so",),
    "cmems_mod_glo_phy-cur_anfc_0.083deg_PT6H-i": ("uo", "vo"),
}
DEFAULT_VARIABLES = ("thetao", "so", "uo", "vo")
REQUIRED_POINT_VARIABLES = ("thetao", "so")
DEFAULT_MAX_AGE_HOURS = 6.0
DEFAULT_LOOKBACK_DAYS = 7

PRESENT_DATA_PATH = (
    Path(__file__).resolve().parent
    / "data"
    / "present"
    / "latest_copernicus_physics.nc"
)


class CopernicusPresentStateError(RuntimeError):
    """Raised when Copernicus present-state refresh or cache access fails."""


def fetch_present_state(
    *,
    force: bool = False,
    max_age_hours: float = DEFAULT_MAX_AGE_HOURS,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    variables: tuple[str, ...] | list[str] = DEFAULT_VARIABLES,
) -> dict[str, Any]:
    """Fetch and cache the latest common 6-hourly Copernicus physics snapshot.

    The selected model time is the latest timestamp available in all requested
    datasets that is not later than the current UTC time. Only that timestamp is
    downloaded; a whole day of 6-hourly fields is intentionally avoided.
    """
    _validate_max_age_hours(max_age_hours)
    lookback_days = _validate_positive_int(lookback_days, "lookback_days")
    variables = _validate_variables(variables)

    if (
        PRESENT_DATA_PATH.exists()
        and not force
        and is_present_cache_fresh(max_age_hours)
        and _cache_has_variables(PRESENT_DATA_PATH, variables)
    ):
        dataset = xr.open_dataset(PRESENT_DATA_PATH)
        try:
            result = _dataset_metadata(dataset)
            result["status"] = "cached"
            result["output_path"] = str(PRESENT_DATA_PATH)
            return result
        finally:
            dataset.close()

    fetched_at = _utc_now()
    temp_path = PRESENT_DATA_PATH.with_name(
        f"{PRESENT_DATA_PATH.stem}.{uuid4().hex}.tmp.nc"
    )

    try:
        copernicusmarine = _get_copernicusmarine()
        model_time = _find_latest_common_model_time(
            copernicusmarine=copernicusmarine,
            fetched_at=fetched_at,
            lookback_days=lookback_days,
            variables=variables,
        )

        downloaded_path = _download_snapshot(
            copernicusmarine=copernicusmarine,
            temp_path=temp_path,
            fetched_at=fetched_at,
            model_time=model_time,
            variables=variables,
        )
        _validate_cache_file(downloaded_path, required_variables=variables)

        PRESENT_DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
        downloaded_path.replace(PRESENT_DATA_PATH)

        dataset = xr.open_dataset(PRESENT_DATA_PATH)
        try:
            result = _dataset_metadata(dataset)
            result["status"] = "updated"
            result["output_path"] = str(PRESENT_DATA_PATH)
            return result
        finally:
            dataset.close()

    except Exception as exc:
        if temp_path.exists():
            temp_path.unlink()

        cache_note = (
            f" Existing present-state cache was kept at {PRESENT_DATA_PATH}."
            if PRESENT_DATA_PATH.exists()
            else " No valid present-state cache is available."
        )
        if isinstance(exc, CopernicusPresentStateError):
            raise CopernicusPresentStateError(f"{exc}{cache_note}") from exc
        raise CopernicusPresentStateError(
            f"Failed to refresh Copernicus present-state data: {exc}.{cache_note}"
        ) from exc


def is_present_cache_fresh(max_age_hours: float = DEFAULT_MAX_AGE_HOURS) -> bool:
    """Return True when the cache is valid and was fetched recently."""
    _validate_max_age_hours(max_age_hours)
    if not PRESENT_DATA_PATH.exists():
        return False

    dataset: xr.Dataset | None = None
    try:
        dataset = xr.open_dataset(PRESENT_DATA_PATH)
        _validate_required_fields(dataset)
        fetched_at = _parse_utc_timestamp(dataset.attrs.get("fetched_at_utc"))
    except Exception:
        return False
    finally:
        if dataset is not None:
            dataset.close()

    age_hours = (_utc_now() - fetched_at).total_seconds() / 3600.0
    return age_hours < max_age_hours


def get_present_state_dataset(
    *,
    max_age_hours: float = DEFAULT_MAX_AGE_HOURS,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    variables: tuple[str, ...] | list[str] = DEFAULT_VARIABLES,
) -> xr.Dataset:
    """Open the present-state cache, refreshing it when missing/stale/incomplete."""
    variables = _validate_variables(variables)
    if (
        not is_present_cache_fresh(max_age_hours)
        or not _cache_has_variables(PRESENT_DATA_PATH, variables)
    ):
        fetch_present_state(
            force=True,
            max_age_hours=max_age_hours,
            lookback_days=lookback_days,
            variables=variables,
        )

    try:
        return xr.open_dataset(PRESENT_DATA_PATH)
    except Exception as exc:
        raise CopernicusPresentStateError(
            f"Copernicus present-state cache is missing or corrupted: {exc}"
        ) from exc


def get_present_state_summary() -> dict[str, Any]:
    """Return JSON-friendly metadata for the cached Copernicus snapshot."""
    if not PRESENT_DATA_PATH.exists():
        raise FileNotFoundError(
            f"Copernicus present-state cache does not exist: {PRESENT_DATA_PATH}"
        )

    dataset = xr.open_dataset(PRESENT_DATA_PATH)
    try:
        summary = _dataset_metadata(dataset)
        summary["cache_age_hours"] = _cache_age_hours(dataset)
        summary["model_age_hours"] = _model_age_hours(dataset)
        summary["temperature_available"] = "thetao" in dataset
        summary["salinity_available"] = "so" in dataset
        summary["currents_available"] = "uo" in dataset and "vo" in dataset
        return summary
    finally:
        dataset.close()


def get_copernicus_point(
    latitude: float,
    longitude: float,
    depth: float = 0,
) -> dict[str, Any]:
    """Return the nearest valid Copernicus ocean cell for a requested point.

    Copernicus values are gridded model analysis/forecast estimates, not direct
    in-situ measurements. The actual grid coordinates, depth level, and model
    timestamp used are always returned.
    """
    latitude_requested = _validate_coordinate(
        latitude, "latitude", LAT_MIN, LAT_MAX
    )
    longitude_requested = _validate_coordinate(
        longitude, "longitude", LON_MIN, LON_MAX
    )
    depth_requested = _validate_depth(depth)

    dataset = get_present_state_dataset(variables=DEFAULT_VARIABLES)
    try:
        _validate_point_cache(dataset)

        model_time = _latest_time_value(dataset)
        time_selected = (
            dataset.sel(time=model_time)
            if "time" in dataset.coords or "time" in dataset.variables
            else dataset
        )

        depth_selected, depth_used = _select_nearest_depth(
            time_selected, depth_requested
        )
        point = _nearest_valid_ocean_point(
            dataset=depth_selected,
            latitude=latitude_requested,
            longitude=longitude_requested,
        )

        return {
            "source": SOURCE_NAME,
            "product_id": PRODUCT_ID,
            "data_type": "gridded_analysis_forecast",
            "latitude_requested": latitude_requested,
            "longitude_requested": longitude_requested,
            "latitude_used": point["latitude"],
            "longitude_used": point["longitude"],
            "depth_requested_m": depth_requested,
            "depth_used_m": depth_used,
            "temperature_c": point["thetao"],
            "salinity": point["so"],
            "eastward_current_m_s": point.get("uo"),
            "northward_current_m_s": point.get("vo"),
            "model_time": _json_value(model_time),
            "fetched_at_utc": dataset.attrs.get("fetched_at_utc"),
            "terminology": "Copernicus Marine gridded analysis/forecast estimate",
        }
    finally:
        dataset.close()


def _find_latest_common_model_time(
    *,
    copernicusmarine: Any,
    fetched_at: datetime,
    lookback_days: int,
    variables: tuple[str, ...],
) -> np.datetime64:
    """Find the latest <= now timestamp shared by all requested datasets."""
    requested = _dataset_requests_for_variables(variables)
    if not requested:
        raise CopernicusPresentStateError("No Copernicus datasets were selected.")

    start = fetched_at - timedelta(days=lookback_days)
    end = fetched_at
    time_sets: list[np.ndarray] = []

    # Small open-ocean probe in the Arabian Sea. Only coordinates/time metadata
    # are needed here; open_dataset is remote/lazy and does not save a file.
    probe_lon = 70.0
    probe_lat = 10.0

    for dataset_id, dataset_variables in requested.items():
        probe: xr.Dataset | None = None
        try:
            probe = copernicusmarine.open_dataset(
                dataset_id=dataset_id,
                variables=[dataset_variables[0]],
                minimum_longitude=probe_lon,
                maximum_longitude=probe_lon,
                minimum_latitude=probe_lat,
                maximum_latitude=probe_lat,
                minimum_depth=0.0,
                maximum_depth=1.0,
                start_datetime=start.isoformat(),
                end_datetime=end.isoformat(),
                coordinates_selection_method="nearest",
                **_auth_kwargs(),
            )

            if "time" not in probe.coords and "time" not in probe.variables:
                raise CopernicusPresentStateError(
                    f"Dataset {dataset_id} has no time coordinate."
                )

            times = np.asarray(probe["time"].values).astype("datetime64[s]").ravel()
            times = times[~np.isnat(times)]
            if times.size == 0:
                raise CopernicusPresentStateError(
                    f"Dataset {dataset_id} has no timestamps in the last "
                    f"{lookback_days} days."
                )

            now64 = np.datetime64(fetched_at.replace(tzinfo=None), "s")
            times = np.unique(times[times <= now64])
            if times.size == 0:
                raise CopernicusPresentStateError(
                    f"Dataset {dataset_id} has no non-future timestamps in the "
                    f"last {lookback_days} days."
                )
            time_sets.append(times)
        finally:
            if probe is not None:
                probe.close()

    common = time_sets[0]
    for times in time_sets[1:]:
        common = np.intersect1d(common, times)

    if common.size == 0:
        latest_per_dataset = [str(times.max()) for times in time_sets]
        raise CopernicusPresentStateError(
            "Temperature, salinity, and current datasets did not expose a common "
            f"6-hourly timestamp. Latest per dataset: {latest_per_dataset}"
        )

    return common.max()


def _download_snapshot(
    *,
    copernicusmarine: Any,
    temp_path: Path,
    fetched_at: datetime,
    model_time: np.datetime64,
    variables: tuple[str, ...],
) -> Path:
    """Download one exact model timestamp for the AquaNexus coverage box."""
    PRESENT_DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    requested = _dataset_requests_for_variables(variables)
    model_time_text = _format_datetime64(model_time)

    part_paths: list[Path] = []
    cleanup_paths: set[Path] = set()

    try:
        for dataset_id, dataset_variables in requested.items():
            part_path = temp_path.with_name(
                f"{temp_path.stem}.{_safe_dataset_suffix(dataset_id)}.nc"
            )
            cleanup_paths.add(part_path)

            result = copernicusmarine.subset(
                dataset_id=dataset_id,
                variables=list(dataset_variables),
                minimum_longitude=LON_MIN,
                maximum_longitude=LON_MAX,
                minimum_latitude=LAT_MIN,
                maximum_latitude=LAT_MAX,
                minimum_depth=DEPTH_MIN,
                maximum_depth=DEPTH_MAX,
                start_datetime=model_time_text,
                end_datetime=model_time_text,
                coordinates_selection_method="inside",
                output_directory=str(part_path.parent),
                output_filename=part_path.name,
                file_format="netcdf",
                overwrite=True,
                disable_progress_bar=True,
                **_auth_kwargs(),
            )

            returned = getattr(result, "file_path", None)
            output_path = Path(returned) if returned else part_path
            cleanup_paths.add(output_path)

            if not output_path.exists():
                raise CopernicusPresentStateError(
                    f"Copernicus subset did not create expected file for {dataset_id}: "
                    f"{output_path}"
                )
            part_paths.append(output_path)

        _merge_downloaded_parts(
            part_paths=part_paths,
            output_path=temp_path,
            fetched_at=fetched_at,
            model_time=model_time,
            variables=variables,
            dataset_ids=tuple(requested),
        )
        return temp_path

    finally:
        for path in cleanup_paths:
            if path != temp_path and path.exists():
                try:
                    path.unlink()
                except OSError:
                    pass


def _merge_downloaded_parts(
    *,
    part_paths: list[Path],
    output_path: Path,
    fetched_at: datetime,
    model_time: np.datetime64,
    variables: tuple[str, ...],
    dataset_ids: tuple[str, ...],
) -> None:
    """Merge the atomized temperature/salinity/current datasets into one cache."""
    if not part_paths:
        raise CopernicusPresentStateError("No Copernicus subset files were downloaded.")

    datasets = [xr.open_dataset(path) for path in part_paths]
    merged: xr.Dataset | None = None
    try:
        loaded = [dataset.load() for dataset in datasets]
        merged = xr.merge(loaded, compat="override", join="exact")
        merged.attrs = _netcdf_safe_attrs(
            {
                **dict(merged.attrs),
                "source": SOURCE_NAME,
                "product_id": PRODUCT_ID,
                "dataset_ids": ",".join(dataset_ids),
                "fetched_at_utc": fetched_at.isoformat().replace("+00:00", "Z"),
                "model_time": _format_datetime64(model_time),
                "variables": ",".join(variables),
                "coverage_longitude_min": LON_MIN,
                "coverage_longitude_max": LON_MAX,
                "coverage_latitude_min": LAT_MIN,
                "coverage_latitude_max": LAT_MAX,
                "coverage_depth_min_m": DEPTH_MIN,
                "coverage_depth_max_m": DEPTH_MAX,
                "terminology": "Copernicus Marine gridded analysis/forecast estimate",
            }
        )
        merged.to_netcdf(output_path)
    finally:
        if merged is not None:
            merged.close()
        for dataset in datasets:
            dataset.close()


def _get_copernicusmarine() -> Any:
    try:
        import copernicusmarine
    except Exception as exc:
        raise CopernicusPresentStateError(
            "copernicusmarine is unavailable. Install the Copernicus Marine "
            "Toolbox in the active AquaNexus environment."
        ) from exc
    return copernicusmarine


def _auth_kwargs() -> dict[str, str]:
    """Use environment credentials when present; otherwise use Toolbox login."""
    _load_dotenv_if_available()
    username = os.getenv("COPERNICUSMARINE_USERNAME") or os.getenv(
        "COPERNICUSMARINE_SERVICE_USERNAME"
    )
    password = os.getenv("COPERNICUSMARINE_PASSWORD") or os.getenv(
        "COPERNICUSMARINE_SERVICE_PASSWORD"
    )

    if bool(username) ^ bool(password):
        raise CopernicusPresentStateError(
            "Only one Copernicus credential environment variable is set. Provide "
            "both username and password, or remove both and use `copernicusmarine login`."
        )

    if username and password:
        return {"username": username, "password": password}
    return {}


def _load_dotenv_if_available() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv()


def _validate_cache_file(
    path: Path,
    *,
    required_variables: tuple[str, ...] = REQUIRED_POINT_VARIABLES,
) -> None:
    dataset = xr.open_dataset(path)
    try:
        _validate_required_fields(dataset)
        missing = [name for name in required_variables if name not in dataset.variables]
        if missing:
            raise CopernicusPresentStateError(
                "Copernicus cache is missing requested variable(s): "
                + ", ".join(missing)
            )
        _ = _parse_utc_timestamp(dataset.attrs.get("fetched_at_utc"))
        _ = _latest_time_value(dataset)
    finally:
        dataset.close()


def _cache_has_variables(path: Path, variables: tuple[str, ...]) -> bool:
    if not path.exists():
        return False

    dataset: xr.Dataset | None = None
    try:
        dataset = xr.open_dataset(path)
        return all(variable in dataset.variables for variable in variables)
    except Exception:
        return False
    finally:
        if dataset is not None:
            dataset.close()


def _validate_required_fields(dataset: xr.Dataset) -> None:
    for coordinate in ("time", "latitude", "longitude"):
        if coordinate not in dataset.coords and coordinate not in dataset.variables:
            raise CopernicusPresentStateError(
                f"Copernicus cache is missing {coordinate!r}."
            )

    if not any(variable in dataset.variables for variable in DEFAULT_VARIABLES):
        raise CopernicusPresentStateError(
            "Copernicus cache contains none of the expected physics variables."
        )


def _validate_point_cache(dataset: xr.Dataset) -> None:
    missing = [name for name in REQUIRED_POINT_VARIABLES if name not in dataset.variables]
    if missing:
        raise CopernicusPresentStateError(
            "Copernicus cache is missing required point variable(s): "
            + ", ".join(missing)
        )
    _validate_required_fields(dataset)


def _latest_time_value(dataset: xr.Dataset) -> np.datetime64:
    if "time" not in dataset:
        raise CopernicusPresentStateError("Copernicus cache has no time coordinate.")
    values = np.asarray(dataset["time"].values).astype("datetime64[s]").ravel()
    values = values[~np.isnat(values)]
    if values.size == 0:
        raise CopernicusPresentStateError("Copernicus cache has no valid time values.")
    return values.max()


def _select_nearest_depth(
    dataset: xr.Dataset,
    requested_depth: float,
) -> tuple[xr.Dataset, float | None]:
    if "depth" not in dataset.coords and "depth" not in dataset.variables:
        return dataset, None

    depth_values = np.asarray(dataset["depth"].values, dtype=float).ravel()
    finite = np.isfinite(depth_values)
    if not finite.any():
        raise CopernicusPresentStateError("Copernicus cache has no valid depth values.")

    finite_indices = np.flatnonzero(finite)
    relative_index = int(np.argmin(np.abs(depth_values[finite] - requested_depth)))
    depth_index = int(finite_indices[relative_index])
    depth_used = float(depth_values[depth_index])
    return dataset.isel(depth=depth_index), depth_used


def _nearest_valid_ocean_point(
    *,
    dataset: xr.Dataset,
    latitude: float,
    longitude: float,
    search_radius: int = 6,
) -> dict[str, Any]:
    """Search the nearest local grid cells until a valid ocean cell is found."""
    latitude_values = np.asarray(dataset["latitude"].values, dtype=float).ravel()
    longitude_values = np.asarray(dataset["longitude"].values, dtype=float).ravel()

    latitude_index = _nearest_index(latitude_values, latitude)
    longitude_index = _nearest_index(longitude_values, longitude)

    candidates: list[tuple[float, int, int]] = []
    for lat_offset in range(-search_radius, search_radius + 1):
        lat_index = latitude_index + lat_offset
        if lat_index < 0 or lat_index >= latitude_values.size:
            continue

        for lon_offset in range(-search_radius, search_radius + 1):
            lon_index = longitude_index + lon_offset
            if lon_index < 0 or lon_index >= longitude_values.size:
                continue

            distance_km = _haversine_km(
                latitude,
                longitude,
                float(latitude_values[lat_index]),
                float(longitude_values[lon_index]),
            )
            candidates.append((distance_km, lat_index, lon_index))

    for _, lat_index, lon_index in sorted(candidates, key=lambda item: item[0]):
        point = _point_values_at(dataset, lat_index, lon_index)
        if point is not None:
            return point

    raise CopernicusPresentStateError(
        "No valid ocean cell was found near the requested Copernicus point."
    )


def _point_values_at(
    dataset: xr.Dataset,
    latitude_index: int,
    longitude_index: int,
) -> dict[str, Any] | None:
    thetao = _variable_value_at(dataset, "thetao", latitude_index, longitude_index)
    salinity = _variable_value_at(dataset, "so", latitude_index, longitude_index)
    if thetao is None or salinity is None:
        return None

    return {
        "thetao": thetao,
        "so": salinity,
        "uo": _variable_value_at(dataset, "uo", latitude_index, longitude_index)
        if "uo" in dataset
        else None,
        "vo": _variable_value_at(dataset, "vo", latitude_index, longitude_index)
        if "vo" in dataset
        else None,
        "latitude": float(dataset["latitude"].isel(latitude=latitude_index).values),
        "longitude": float(dataset["longitude"].isel(longitude=longitude_index).values),
    }


def _variable_value_at(
    dataset: xr.Dataset,
    variable: str,
    latitude_index: int,
    longitude_index: int,
) -> float | None:
    if variable not in dataset:
        return None

    values = dataset[variable].isel(
        latitude=latitude_index,
        longitude=longitude_index,
    ).values
    array = np.asarray(values)
    if array.size != 1:
        raise CopernicusPresentStateError(
            f"Expected scalar {variable!r} value after time/depth selection, "
            f"received shape {array.shape}."
        )

    scalar = array.item()
    if scalar is None:
        return None
    try:
        numeric = float(scalar)
    except (TypeError, ValueError):
        return None
    return numeric if np.isfinite(numeric) else None


def _nearest_index(values: np.ndarray, target: float) -> int:
    values = np.asarray(values, dtype=float).ravel()
    finite = np.isfinite(values)
    if not finite.any():
        raise CopernicusPresentStateError("Copernicus coordinate contains no valid values.")
    indices = np.flatnonzero(finite)
    relative = int(np.argmin(np.abs(values[finite] - target)))
    return int(indices[relative])


def _haversine_km(lat_a: float, lon_a: float, lat_b: float, lon_b: float) -> float:
    earth_radius_km = 6371.0088
    lat1, lon1, lat2, lon2 = np.radians([lat_a, lon_a, lat_b, lon_b])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2.0) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2.0) ** 2
    return float(2.0 * earth_radius_km * np.arcsin(np.sqrt(a)))


def _dataset_metadata(dataset: xr.Dataset) -> dict[str, Any]:
    variables = [name for name in DEFAULT_VARIABLES if name in dataset.variables]
    model_time = _latest_time_value(dataset)
    return {
        "source": SOURCE_NAME,
        "product_id": dataset.attrs.get("product_id", PRODUCT_ID),
        "dataset_ids": dataset.attrs.get("dataset_ids", ",".join(DATASET_VARIABLES)),
        "variables": variables,
        "model_time": _json_value(model_time),
        "grid_point_count": _grid_point_count(dataset),
        "time_start": _coord_min(dataset, "time"),
        "time_end": _coord_max(dataset, "time"),
        "depth_min": _coord_min(dataset, "depth"),
        "depth_max": _coord_max(dataset, "depth"),
        "latitude_min": _coord_min(dataset, "latitude"),
        "latitude_max": _coord_max(dataset, "latitude"),
        "longitude_min": _coord_min(dataset, "longitude"),
        "longitude_max": _coord_max(dataset, "longitude"),
        "fetched_at_utc": dataset.attrs.get("fetched_at_utc"),
    }


def _grid_point_count(dataset: xr.Dataset) -> int:
    count = 1
    for dim in ("time", "depth", "latitude", "longitude"):
        count *= int(dataset.sizes.get(dim, 1))
    return count


def _coord_min(dataset: xr.Dataset, name: str) -> Any:
    if name not in dataset:
        return None
    return _json_scalar(dataset[name].min())


def _coord_max(dataset: xr.Dataset, name: str) -> Any:
    if name not in dataset:
        return None
    return _json_scalar(dataset[name].max())


def _json_scalar(value: xr.DataArray) -> Any:
    return _json_value(value.values)


def _json_value(value: Any) -> Any:
    array = np.asarray(value)
    if np.issubdtype(array.dtype, np.datetime64):
        return str(np.datetime_as_string(array.astype("datetime64[s]"), unit="s"))

    scalar = array.item() if array.size == 1 else value
    if isinstance(scalar, (np.integer,)):
        return int(scalar)
    if isinstance(scalar, (np.floating,)):
        scalar = float(scalar)
        return scalar if np.isfinite(scalar) else None
    if hasattr(scalar, "isoformat"):
        return scalar.isoformat()
    return scalar


def _format_datetime64(value: np.datetime64) -> str:
    return str(np.datetime_as_string(value.astype("datetime64[s]"), unit="s"))


def _validate_positive_int(value: int, name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a positive integer.")
    try:
        numeric = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a positive integer.") from exc
    if numeric != value or numeric <= 0:
        raise ValueError(f"{name} must be a positive integer.")
    return numeric


def _validate_max_age_hours(value: float) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("max_age_hours must be a non-negative number.") from exc
    if not np.isfinite(numeric) or numeric < 0:
        raise ValueError("max_age_hours must be a non-negative number.")
    return numeric


def _validate_variables(variables: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    clean = tuple(
        str(variable).strip()
        for variable in variables
        if str(variable).strip()
    )
    if not clean:
        raise ValueError("At least one Copernicus variable is required.")

    supported = {
        variable
        for available_variables in DATASET_VARIABLES.values()
        for variable in available_variables
    }
    unsupported = sorted(set(clean) - supported)
    if unsupported:
        raise ValueError(
            "Unsupported Copernicus variable(s): "
            f"{', '.join(unsupported)}. Supported: {', '.join(sorted(supported))}."
        )

    # Preserve caller order while removing duplicates.
    return tuple(dict.fromkeys(clean))


def _dataset_requests_for_variables(
    variables: tuple[str, ...],
) -> dict[str, tuple[str, ...]]:
    requested_variables = set(variables)
    requests: dict[str, tuple[str, ...]] = {}
    for dataset_id, available_variables in DATASET_VARIABLES.items():
        selected = tuple(
            variable
            for variable in available_variables
            if variable in requested_variables
        )
        if selected:
            requests[dataset_id] = selected
    return requests


def _safe_dataset_suffix(dataset_id: str) -> str:
    return dataset_id.replace(".", "_").replace("-", "_")


def _validate_coordinate(
    value: float,
    name: str,
    minimum: float,
    maximum: float,
) -> float:
    try:
        coordinate = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be numeric.") from exc
    if not np.isfinite(coordinate):
        raise ValueError(f"{name} must be finite.")
    if coordinate < minimum or coordinate > maximum:
        raise ValueError(
            f"{name} must be inside AquaNexus coverage {minimum:g} to {maximum:g}."
        )
    return coordinate


def _validate_depth(value: float) -> float:
    try:
        depth = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("depth must be numeric.") from exc
    if not np.isfinite(depth):
        raise ValueError("depth must be finite.")
    if depth < DEPTH_MIN or depth > DEPTH_MAX:
        raise ValueError(
            f"depth must be inside {DEPTH_MIN:g} to {DEPTH_MAX:g} meters."
        )
    return depth


def _cache_age_hours(dataset: xr.Dataset) -> float | None:
    try:
        fetched_at = _parse_utc_timestamp(dataset.attrs.get("fetched_at_utc"))
    except Exception:
        return None
    return (_utc_now() - fetched_at).total_seconds() / 3600.0


def _model_age_hours(dataset: xr.Dataset) -> float | None:
    try:
        model_time = _latest_time_value(dataset)
        model_dt = model_time.astype("datetime64[s]").astype(datetime).replace(
            tzinfo=timezone.utc
        )
    except Exception:
        return None
    return (_utc_now() - model_dt).total_seconds() / 3600.0


def _parse_utc_timestamp(value: Any) -> datetime:
    if not value:
        raise ValueError("fetched_at_utc is missing.")
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _netcdf_safe_attrs(attrs: dict[str, Any]) -> dict[str, Any]:
    safe_attrs: dict[str, Any] = {}
    for key, value in attrs.items():
        if isinstance(value, (bool, np.bool_)):
            safe_attrs[key] = str(bool(value)).lower()
        elif isinstance(value, (int, float, str, np.integer, np.floating)):
            safe_attrs[key] = value.item() if hasattr(value, "item") else value
        elif isinstance(value, datetime):
            safe_attrs[key] = value.astimezone(timezone.utc).isoformat().replace(
                "+00:00", "Z"
            )
        elif isinstance(value, (tuple, list)):
            safe_attrs[key] = ",".join(str(item) for item in value)
        else:
            safe_attrs[key] = str(value)
    return safe_attrs