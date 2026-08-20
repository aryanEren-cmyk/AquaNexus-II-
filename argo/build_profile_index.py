"""Build the persistent historical ARGO profile-level spatial index."""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import time
from typing import Any

import numpy as np
import xarray as xr


if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from argo.processor import PROCESSED_DATA_PATH


PROFILE_INDEX_PATH = (
    Path(__file__).resolve().parent
    / "data"
    / "processed"
    / "historical_profile_index.npz"
)
REQUIRED_VARIABLES = (
    "PLATFORM_NUMBER",
    "CYCLE_NUMBER",
    "LATITUDE",
    "LONGITUDE",
    "TIME",
)


def build_profile_index() -> dict[str, Any]:
    """Build one index row per historical ARGO float-cycle profile."""
    if not PROCESSED_DATA_PATH.exists():
        raise FileNotFoundError(
            f"Historical processed ARGO cache is missing: {PROCESSED_DATA_PATH}"
        )

    started_at = time.perf_counter()
    dataset = xr.open_dataset(PROCESSED_DATA_PATH)
    try:
        _require_variables(dataset, REQUIRED_VARIABLES)
        platform = np.asarray(dataset["PLATFORM_NUMBER"].values, dtype=float).ravel()
        cycle = np.asarray(dataset["CYCLE_NUMBER"].values, dtype=float).ravel()
        latitude = np.asarray(dataset["LATITUDE"].values, dtype=float).ravel()
        longitude = np.asarray(dataset["LONGITUDE"].values, dtype=float).ravel()
        observation_time = np.asarray(dataset["TIME"].values).astype("datetime64[s]").ravel()

        valid = (
            np.isfinite(platform)
            & np.isfinite(cycle)
            & np.isfinite(latitude)
            & np.isfinite(longitude)
            & ~np.isnat(observation_time)
        )
        if not valid.any():
            raise ValueError("Historical processed ARGO cache has no valid profiles.")

        keys = np.empty(valid.sum(), dtype=[("platform", "f8"), ("cycle", "f8")])
        keys["platform"] = platform[valid]
        keys["cycle"] = cycle[valid]
        _, first_indices = np.unique(keys, return_index=True)

        valid_indices = np.flatnonzero(valid)[first_indices]
        order = np.lexsort((cycle[valid_indices], platform[valid_indices]))
        profile_indices = valid_indices[order]

        index = {
            "platform_number": platform[profile_indices].astype("float64"),
            "cycle_number": cycle[profile_indices].astype("float64"),
            "latitude": latitude[profile_indices].astype("float64"),
            "longitude": longitude[profile_indices].astype("float64"),
            "observation_time": observation_time[profile_indices].astype("datetime64[s]"),
        }
        _write_npz_atomic(PROFILE_INDEX_PATH, index)
    finally:
        dataset.close()

    return {
        "output_path": str(PROFILE_INDEX_PATH),
        "profile_count": int(index["platform_number"].size),
        "runtime_seconds": time.perf_counter() - started_at,
    }


def _require_variables(dataset: xr.Dataset, variables: tuple[str, ...]) -> None:
    missing = [variable for variable in variables if variable not in dataset.variables]
    if missing:
        raise ValueError(f"Dataset is missing required variable(s): {', '.join(missing)}")


def _write_npz_atomic(path: Path, arrays: dict[str, np.ndarray]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "wb",
        dir=path.parent,
        delete=False,
        prefix=f"{path.name}.",
        suffix=".tmp",
    ) as handle:
        np.savez_compressed(handle, **arrays)
        temp_path = Path(handle.name)
    temp_path.replace(path)


def main() -> None:
    result = build_profile_index()
    print(result)


if __name__ == "__main__":
    main()
