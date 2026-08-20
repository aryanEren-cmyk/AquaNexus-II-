"""Cleaning and selection helpers for ARGO observations."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import xarray as xr

from argo.loader import load_raw_dataset


GOOD_QC_FLAG = "1"
POINT_DIM = "N_POINTS"
PROCESSED_DATA_PATH = (
    Path(__file__).resolve().parent / "data" / "processed" / "india_argo_cleaned_2021_2025.nc"
)


def clean_dataset(dataset: xr.Dataset, *, inplace: bool = False) -> xr.Dataset:
    """Clean ARGO point observations while preserving measurements unless QC rejects them."""
    cleaned = dataset if inplace else dataset.copy(deep=False)

    _require_variables(cleaned, ("LATITUDE", "LONGITUDE", "TIME", "PRES"))

    valid_rows = (
        cleaned["LATITUDE"].notnull()
        & cleaned["LONGITUDE"].notnull()
        & cleaned["TIME"].notnull()
        & cleaned["PRES"].notnull()
        & (cleaned["LATITUDE"] >= -90)
        & (cleaned["LATITUDE"] <= 90)
        & (cleaned["LONGITUDE"] >= -180)
        & (cleaned["LONGITUDE"] <= 360)
        & (cleaned["PRES"] >= 0)
    )

    if "POSITION_QC" in cleaned:
        valid_rows = valid_rows & _qc_is_good(cleaned["POSITION_QC"])
    if "TIME_QC" in cleaned:
        valid_rows = valid_rows & _qc_is_good(cleaned["TIME_QC"])

    cleaned = cleaned.where(valid_rows, drop=True)

    qc_targets = {
        "PRES_QC": "PRES",
        "TEMP_QC": "TEMP",
        "PSAL_QC": "PSAL",
    }
    for qc_name, variable_name in qc_targets.items():
        if qc_name in cleaned and variable_name in cleaned:
            cleaned[variable_name] = cleaned[variable_name].where(_qc_is_good(cleaned[qc_name]))

    cleaned.attrs = dict(dataset.attrs)
    cleaned.attrs["argo_cleaned"] = True
    cleaned.attrs["qc_policy"] = "ARGO QC flag 1 accepted as good data"

    return cleaned


def get_float_ids(dataset: xr.Dataset) -> list[Any]:
    """Return sorted unique ARGO platform IDs from a dataset."""
    _require_variables(dataset, ("PLATFORM_NUMBER",))
    return _sorted_unique(dataset["PLATFORM_NUMBER"])


def get_float_data(dataset: xr.Dataset, platform_number: Any) -> xr.Dataset:
    """Return observations for one ARGO float, raising if the float is absent."""
    _require_variables(dataset, ("PLATFORM_NUMBER",))
    float_data = dataset.where(dataset["PLATFORM_NUMBER"] == platform_number, drop=True)

    if _point_count(float_data) == 0:
        raise ValueError(f"ARGO float {platform_number!r} was not found in the dataset.")

    return float_data


def get_profile(dataset: xr.Dataset, platform_number: Any, cycle_number: Any) -> xr.Dataset:
    """Return one float-cycle profile sorted by pressure with missing pressure rows removed."""
    _require_variables(dataset, ("PLATFORM_NUMBER", "CYCLE_NUMBER", "PRES"))

    float_data = get_float_data(dataset, platform_number)
    profile = float_data.where(float_data["CYCLE_NUMBER"] == cycle_number, drop=True)
    profile = profile.where(profile["PRES"].notnull(), drop=True)

    if _point_count(profile) == 0:
        raise ValueError(
            f"ARGO profile for float {platform_number!r}, cycle {cycle_number!r} was not found."
        )

    return profile.sortby("PRES")


def get_available_cycles(dataset: xr.Dataset, platform_number: Any) -> list[Any]:
    """Return sorted unique cycle numbers for one ARGO float."""
    _require_variables(dataset, ("CYCLE_NUMBER",))
    float_data = get_float_data(dataset, platform_number)
    return _sorted_unique(float_data["CYCLE_NUMBER"])


def build_processed_dataset(force: bool = False) -> dict[str, Any]:
    """Build the persistent cleaned ARGO dataset cache when needed."""
    output_path = PROCESSED_DATA_PATH
    if output_path.exists() and not force:
        dataset = xr.open_dataset(output_path)
        try:
            return {
                "rebuilt": False,
                "output_path": str(output_path),
                "point_count": _point_count(dataset),
            }
        finally:
            dataset.close()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    raw_dataset: xr.Dataset | None = None
    cleaned_dataset: xr.Dataset | None = None

    try:
        raw_dataset = load_raw_dataset()
        cleaned_dataset = clean_dataset(raw_dataset)
        cleaned_dataset.attrs = _netcdf_safe_attrs(cleaned_dataset.attrs)
        cleaned_dataset.to_netcdf(output_path)

        return {
            "rebuilt": True,
            "output_path": str(output_path),
            "point_count": _point_count(cleaned_dataset),
        }
    finally:
        if cleaned_dataset is not None:
            cleaned_dataset.close()
        if raw_dataset is not None:
            raw_dataset.close()


def get_clean_dataset() -> xr.Dataset:
    """Open the persistent cleaned ARGO dataset, building it once if missing."""
    if not PROCESSED_DATA_PATH.exists():
        build_processed_dataset()

    return xr.open_dataset(PROCESSED_DATA_PATH)


def _require_variables(dataset: xr.Dataset, names: tuple[str, ...]) -> None:
    """Raise a clear error when expected variables are unavailable."""
    missing = [name for name in names if name not in dataset.variables]
    if missing:
        raise ValueError(f"Dataset is missing required variable(s): {', '.join(missing)}")


def _qc_is_good(flags: xr.DataArray) -> xr.DataArray:
    """Return a boolean mask where ARGO QC flags normalize to the good-data flag."""
    return xr.apply_ufunc(
        _normalize_qc_flag,
        flags,
        vectorize=True,
        dask="allowed",
        output_dtypes=[str],
    ) == GOOD_QC_FLAG


def _normalize_qc_flag(value: Any) -> str:
    """Normalize integer, string, byte, and missing QC flag values for comparison."""
    if value is None:
        return ""

    if isinstance(value, bytes):
        return value.decode("utf-8", errors="ignore").strip()

    try:
        if np.issubdtype(type(value), np.floating) and np.isnan(value):
            return ""
    except TypeError:
        pass

    text = str(value).strip()
    return text[:-2] if text.endswith(".0") else text


def _netcdf_safe_attrs(attrs: dict[Any, Any]) -> dict[Any, Any]:
    """Convert dataset attributes to NetCDF-safe scalar/list values."""
    safe_attrs: dict[Any, Any] = {}
    for key, value in attrs.items():
        if isinstance(value, (bool, np.bool_)):
            safe_attrs[key] = str(bool(value)).lower()
        else:
            safe_attrs[key] = value
    return safe_attrs


def _sorted_unique(values: xr.DataArray) -> list[Any]:
    """Return sorted unique non-null values as plain Python objects."""
    array = np.asarray(values.values).ravel()
    array = array[~np.asarray(values.isnull().values).ravel()]
    unique_values = [_to_python_value(value) for value in np.unique(array)]
    return sorted(unique_values)


def _to_python_value(value: Any) -> Any:
    """Convert NumPy scalar IDs into stable Python scalar values."""
    scalar = value.item() if hasattr(value, "item") else value
    if isinstance(scalar, float) and scalar.is_integer():
        return int(scalar)
    return scalar


def _point_count(dataset: xr.Dataset) -> int:
    """Return the number of point observations in a dataset."""
    return int(dataset.sizes.get(POINT_DIM, 0))
