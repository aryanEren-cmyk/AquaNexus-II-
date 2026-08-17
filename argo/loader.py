"""Utilities for loading raw ARGO NetCDF datasets."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import xarray as xr


RAW_DATA_DIR = Path(__file__).resolve().parent / "data" / "raw"
REQUIRED_VARIABLES = (
    "PLATFORM_NUMBER",
    "CYCLE_NUMBER",
    "LATITUDE",
    "LONGITUDE",
    "TIME",
    "PRES",
    "TEMP",
    "PSAL",
)


def list_raw_files(raw_dir: Path | str = RAW_DATA_DIR) -> list[Path]:
    """Return sorted raw ARGO NetCDF files from the raw data directory."""
    raw_path = Path(raw_dir)
    files = sorted(raw_path.glob("*.nc"))

    if not files:
        raise FileNotFoundError(f"No NetCDF files found in raw ARGO directory: {raw_path}")

    return files


def load_raw_dataset(raw_dir: Path | str = RAW_DATA_DIR) -> xr.Dataset:
    """Open, validate, and lazily combine all raw ARGO NetCDF files into one dataset."""
    files = list_raw_files(raw_dir)
    datasets: list[xr.Dataset] = []

    try:
        for file_path in files:
            dataset = xr.open_dataset(file_path)
            _validate_required_variables(dataset, file_path)
            datasets.append(_prepare_for_concat(dataset))

        combined = xr.concat(
            datasets,
            dim="N_POINTS",
            data_vars="all",
            coords="minimal",
            compat="override",
            combine_attrs="drop_conflicts",
        )
    except Exception:
        for dataset in datasets:
            dataset.close()
        raise

    combined.attrs["source_file_count"] = len(files)
    combined.attrs["source_files"] = [path.name for path in files]

    return combined


def get_dataset_summary(raw_dir: Path | str = RAW_DATA_DIR) -> dict[str, Any]:
    """Return key coverage and volume metrics for the unified raw ARGO dataset."""
    files = list_raw_files(raw_dir)
    dataset = load_raw_dataset(raw_dir)

    try:
        return {
            "file_count": len(files),
            "total_points": int(dataset.sizes.get("N_POINTS", 0)),
            "unique_floats": _unique_count(dataset["PLATFORM_NUMBER"]),
            "min_time": _to_python_scalar(dataset["TIME"].min()),
            "max_time": _to_python_scalar(dataset["TIME"].max()),
            "latitude_range": _range(dataset["LATITUDE"]),
            "longitude_range": _range(dataset["LONGITUDE"]),
            "pressure_range": _range(dataset["PRES"]),
        }
    finally:
        dataset.close()


def _validate_required_variables(dataset: xr.Dataset, file_path: Path) -> None:
    """Raise a clear error if a source file is missing required ARGO fields."""
    available = set(dataset.variables)
    missing = [name for name in REQUIRED_VARIABLES if name not in available]

    if missing:
        missing_names = ", ".join(missing)
        raise ValueError(f"{file_path.name} is missing required variable(s): {missing_names}")


def _prepare_for_concat(dataset: xr.Dataset) -> xr.Dataset:
    """Normalize point indexing before concatenating monthly point datasets."""
    if "N_POINTS" in dataset.coords:
        dataset = dataset.drop_vars("N_POINTS")
    return dataset


def _range(values: xr.DataArray) -> tuple[Any, Any]:
    """Return minimum and maximum values as plain Python scalars."""
    return (_to_python_scalar(values.min(skipna=True)), _to_python_scalar(values.max(skipna=True)))


def _unique_count(values: xr.DataArray) -> int:
    """Return the number of unique non-null values in an array."""
    array = np.asarray(values.values).ravel()
    array = array[~np.asarray(values.isnull().values).ravel()]
    return int(np.unique(array.astype(str)).size)


def _to_python_scalar(value: xr.DataArray) -> Any:
    """Convert an xarray scalar value into a JSON-friendly Python value."""
    if np.issubdtype(value.dtype, np.datetime64):
        return str(np.datetime_as_string(value.values, unit="s"))

    scalar = value.item()
    return scalar.isoformat() if hasattr(scalar, "isoformat") else scalar
