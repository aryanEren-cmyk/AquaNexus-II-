"""Fetch and cache latest near-real-time ARGO physical observations."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import numpy as np
import xarray as xr

from argo.processor import clean_dataset


LON_MIN = 60
LON_MAX = 100
LAT_MIN = 0
LAT_MAX = 30
PRES_MIN = 0
PRES_MAX = 2000

SOURCE_NAME = "ARGO_REALTIME"
ERDDAP_SOURCE = "IFREMER ERDDAP via argopy"
POINT_DIM = "N_POINTS"
LIVE_DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "live" / "latest_argo.nc"


class LiveArgoError(RuntimeError):
    """Raised when live ARGO refresh or cache access fails."""


def fetch_live_argo(lookback_days: int = 15, force: bool = False) -> dict[str, Any]:
    """Fetch latest near-real-time ARGO observations and update the live NetCDF cache."""
    lookback_days = _validate_lookback_days(lookback_days)

    if LIVE_DATA_PATH.exists() and not force and is_live_cache_fresh():
        dataset = xr.open_dataset(LIVE_DATA_PATH)
        try:
            result = _dataset_metadata(dataset)
            result["status"] = "cached"
            result["output_path"] = str(LIVE_DATA_PATH)
            return result
        finally:
            dataset.close()

    fetched_at = _utc_now()
    end_date = fetched_at
    start_date = end_date - timedelta(days=lookback_days)
    query_start = _format_query_date(start_date)
    query_end = _format_query_date(end_date + timedelta(days=1))

    raw_dataset: xr.Dataset | None = None
    cleaned_dataset: xr.Dataset | None = None
    temp_path = LIVE_DATA_PATH.with_name(f"{LIVE_DATA_PATH.stem}.{uuid4().hex}.tmp.nc")

    try:
        box = [
            LON_MIN,
            LON_MAX,
            LAT_MIN,
            LAT_MAX,
            PRES_MIN,
            PRES_MAX,
            query_start,
            query_end,
        ]
        data_fetcher = _get_data_fetcher()
        raw_dataset = (
            data_fetcher(src="erddap", ds="phy", parallel=True)
            .region(box)
            .to_xarray()
        )

        cleaned_dataset = clean_dataset(raw_dataset)
        if _point_count(cleaned_dataset) == 0:
            raise LiveArgoError(
                "No latest ARGO observations were found for the requested "
                f"{lookback_days}-day window ({query_start} to {query_end})."
            )

        cleaned_dataset.attrs = _netcdf_safe_attrs(
            {
                **dict(cleaned_dataset.attrs),
                "source": SOURCE_NAME,
                "source_detail": ERDDAP_SOURCE,
                "fetched_at_utc": fetched_at.isoformat().replace("+00:00", "Z"),
                "query_start": query_start,
                "query_end": query_end,
                "lookback_days": lookback_days,
                "coverage_longitude_min": LON_MIN,
                "coverage_longitude_max": LON_MAX,
                "coverage_latitude_min": LAT_MIN,
                "coverage_latitude_max": LAT_MAX,
                "coverage_pressure_min_dbar": PRES_MIN,
                "coverage_pressure_max_dbar": PRES_MAX,
                "terminology": "near-real-time ARGO data; latest ARGO observation",
            }
        )

        LIVE_DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
        cleaned_dataset.to_netcdf(temp_path)
        _validate_cache_file(temp_path)
        temp_path.replace(LIVE_DATA_PATH)

        result = _dataset_metadata(cleaned_dataset)
        result["status"] = "updated"
        result["output_path"] = str(LIVE_DATA_PATH)
        return result
    except Exception as exc:
        if temp_path.exists():
            temp_path.unlink()
        cache_note = (
            f" Existing live cache was kept at {LIVE_DATA_PATH}."
            if LIVE_DATA_PATH.exists()
            else " No valid live cache is available."
        )
        if isinstance(exc, LiveArgoError):
            raise LiveArgoError(f"{exc}{cache_note}") from exc
        raise LiveArgoError(f"Failed to refresh near-real-time ARGO data: {exc}.{cache_note}") from exc
    finally:
        if cleaned_dataset is not None:
            cleaned_dataset.close()
        if raw_dataset is not None:
            raw_dataset.close()


def is_live_cache_fresh(max_age_hours: float = 6) -> bool:
    """Return True when the live ARGO cache was fetched within max_age_hours."""
    if max_age_hours < 0:
        raise ValueError("max_age_hours must be greater than or equal to 0.")
    if not LIVE_DATA_PATH.exists():
        return False

    dataset: xr.Dataset | None = None
    try:
        dataset = xr.open_dataset(LIVE_DATA_PATH)
        fetched_at = _parse_utc_timestamp(dataset.attrs.get("fetched_at_utc"))
    except Exception:
        return False
    finally:
        if dataset is not None:
            dataset.close()

    age_hours = (_utc_now() - fetched_at).total_seconds() / 3600
    return age_hours < max_age_hours


def get_live_argo_dataset(max_age_hours: float = 6, lookback_days: int = 15) -> xr.Dataset:
    """Open the live ARGO cache, refreshing it first when missing or stale."""
    if not _cache_is_valid_and_fresh(max_age_hours):
        fetch_live_argo(lookback_days=lookback_days, force=True)

    try:
        return xr.open_dataset(LIVE_DATA_PATH)
    except Exception as exc:
        raise LiveArgoError(f"Live ARGO cache is missing or corrupted: {exc}") from exc


def get_live_argo_summary() -> dict[str, Any]:
    """Return JSON-friendly metadata for the cached live ARGO observations."""
    if not LIVE_DATA_PATH.exists():
        raise FileNotFoundError(f"Live ARGO cache does not exist: {LIVE_DATA_PATH}")

    dataset = xr.open_dataset(LIVE_DATA_PATH)
    try:
        summary = _dataset_metadata(dataset)
        summary["source"] = SOURCE_NAME
        summary["age_hours"] = _cache_age_hours(dataset)
        return summary
    finally:
        dataset.close()


def _cache_is_valid_and_fresh(max_age_hours: float) -> bool:
    if not is_live_cache_fresh(max_age_hours=max_age_hours):
        return False
    try:
        _validate_cache_file(LIVE_DATA_PATH)
    except Exception:
        return False
    return True


def _get_data_fetcher():
    try:
        from argopy import DataFetcher
    except Exception as exc:
        raise LiveArgoError(
            "argopy DataFetcher is unavailable. Check that argopy and erddapy "
            "are installed in compatible versions before refreshing live ARGO data."
        ) from exc

    return DataFetcher


def _validate_cache_file(path: Path) -> None:
    dataset = xr.open_dataset(path)
    try:
        if _point_count(dataset) == 0:
            raise LiveArgoError(f"Live ARGO cache has no observations: {path}")
        _ = _parse_utc_timestamp(dataset.attrs.get("fetched_at_utc"))
    finally:
        dataset.close()


def _dataset_metadata(dataset: xr.Dataset) -> dict[str, Any]:
    return {
        "point_count": _point_count(dataset),
        "unique_floats": _unique_count(dataset["PLATFORM_NUMBER"])
        if "PLATFORM_NUMBER" in dataset
        else 0,
        "earliest_observation": _datetime_scalar(dataset["TIME"].min())
        if "TIME" in dataset
        else None,
        "latest_observation": _datetime_scalar(dataset["TIME"].max())
        if "TIME" in dataset
        else None,
        "fetched_at_utc": dataset.attrs.get("fetched_at_utc"),
    }


def _validate_lookback_days(lookback_days: int) -> int:
    if isinstance(lookback_days, bool) or int(lookback_days) != lookback_days:
        raise ValueError("lookback_days must be a positive integer.")
    if lookback_days <= 0:
        raise ValueError("lookback_days must be greater than 0.")
    return int(lookback_days)


def _cache_age_hours(dataset: xr.Dataset) -> float | None:
    try:
        fetched_at = _parse_utc_timestamp(dataset.attrs.get("fetched_at_utc"))
    except Exception:
        return None
    return (_utc_now() - fetched_at).total_seconds() / 3600


def _parse_utc_timestamp(value: Any) -> datetime:
    if not value:
        raise ValueError("fetched_at_utc is missing.")
    text = str(value).replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _format_query_date(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%d")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _point_count(dataset: xr.Dataset) -> int:
    return int(dataset.sizes.get(POINT_DIM, 0))


def _unique_count(values: xr.DataArray) -> int:
    array = np.asarray(values.values).ravel()
    array = array[~np.asarray(values.isnull().values).ravel()]
    return int(np.unique(array.astype(str)).size)


def _datetime_scalar(value: xr.DataArray) -> str:
    return str(np.datetime_as_string(value.values, unit="s"))


def _netcdf_safe_attrs(attrs: dict[str, Any]) -> dict[str, Any]:
    safe_attrs: dict[str, Any] = {}
    for key, value in attrs.items():
        if isinstance(value, (bool, np.bool_)):
            safe_attrs[key] = str(bool(value)).lower()
        elif isinstance(value, (int, float, str, np.integer, np.floating)):
            safe_attrs[key] = value.item() if hasattr(value, "item") else value
        elif isinstance(value, datetime):
            safe_attrs[key] = value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        else:
            safe_attrs[key] = str(value)
    return safe_attrs
