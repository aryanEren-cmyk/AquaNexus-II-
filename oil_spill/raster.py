"""Decode and summarize Sentinel-1 SAR raster patches.

This module reads the in-memory GeoTIFF returned by Sentinel Hub and converts
calibrated VV/VH linear-power values into dB for later slick-candidate
analysis.

It does not classify or detect oil spills.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from rasterio.io import MemoryFile


class SarRasterError(RuntimeError):
    """Raised when a Sentinel-1 SAR raster cannot be decoded safely."""


def decode_sentinel1_patch(
    patch: dict[str, Any],
) -> dict[str, Any]:
    """Decode a 3-band Sentinel Hub GeoTIFF into NumPy arrays.

    Expected band order:
        1 -> VV linear power
        2 -> VH linear power
        3 -> dataMask

    The returned object contains NumPy arrays and is therefore intended only
    for internal scientific processing, not direct JSON/API serialization.
    """

    if not isinstance(patch, dict):
        raise ValueError("patch must be a dictionary.")

    content = patch.get("content")

    if not isinstance(content, (bytes, bytearray)):
        raise SarRasterError(
            "SAR patch does not contain valid GeoTIFF bytes."
        )

    if not content:
        raise SarRasterError(
            "SAR patch contains an empty GeoTIFF."
        )

    try:
        with MemoryFile(bytes(content)) as memory_file:
            with memory_file.open() as dataset:
                if dataset.count < 3:
                    raise SarRasterError(
                        "Expected at least 3 raster bands "
                        "(VV, VH, dataMask)."
                    )

                vv_linear = dataset.read(1).astype(
                    np.float64,
                    copy=False,
                )
                vh_linear = dataset.read(2).astype(
                    np.float64,
                    copy=False,
                )
                data_mask_raw = dataset.read(3).astype(
                    np.float64,
                    copy=False,
                )

                if (
                    vv_linear.shape != vh_linear.shape
                    or vv_linear.shape != data_mask_raw.shape
                ):
                    raise SarRasterError(
                        "SAR raster bands have inconsistent dimensions."
                    )

                data_mask = (
                    np.isfinite(data_mask_raw)
                    & (data_mask_raw > 0.5)
                )

                vv_valid = (
                    data_mask
                    & np.isfinite(vv_linear)
                    & (vv_linear > 0)
                )

                vh_valid = (
                    data_mask
                    & np.isfinite(vh_linear)
                    & (vh_linear > 0)
                )

                joint_valid = vv_valid & vh_valid

                vv_db = np.full(
                    vv_linear.shape,
                    np.nan,
                    dtype=np.float64,
                )

                vh_db = np.full(
                    vh_linear.shape,
                    np.nan,
                    dtype=np.float64,
                )

                vv_db[vv_valid] = (
                    10.0
                    * np.log10(
                        vv_linear[vv_valid]
                    )
                )

                vh_db[vh_valid] = (
                    10.0
                    * np.log10(
                        vh_linear[vh_valid]
                    )
                )

                bounds = dataset.bounds

                return {
                    "vv_linear": vv_linear,
                    "vh_linear": vh_linear,
                    "vv_db": vv_db,
                    "vh_db": vh_db,
                    "data_mask": data_mask,
                    "vv_valid_mask": vv_valid,
                    "vh_valid_mask": vh_valid,
                    "joint_valid_mask": joint_valid,
                    "width": int(dataset.width),
                    "height": int(dataset.height),
                    "band_count": int(dataset.count),
                    "dtype": str(dataset.dtypes[0]),
                    "crs": (
                        dataset.crs.to_string()
                        if dataset.crs is not None
                        else None
                    ),
                    "bounds": {
                        "left": float(bounds.left),
                        "bottom": float(bounds.bottom),
                        "right": float(bounds.right),
                        "top": float(bounds.top),
                    },
                    "transform": tuple(
                        float(value)
                        for value in dataset.transform
                    ),
                }

    except SarRasterError:
        raise

    except Exception as exc:
        raise SarRasterError(
            "Unable to decode Sentinel-1 GeoTIFF."
        ) from exc


def summarize_sentinel1_patch(
    patch: dict[str, Any],
) -> dict[str, Any]:
    """Return JSON-safe descriptive statistics for a SAR patch.

    Statistics are descriptive only. They are not an oil-spill
    classification and no detection threshold is applied.
    """

    decoded = decode_sentinel1_patch(patch)

    vv_linear = decoded["vv_linear"]
    vh_linear = decoded["vh_linear"]
    vv_db = decoded["vv_db"]
    vh_db = decoded["vh_db"]

    data_mask = decoded["data_mask"]
    vv_valid = decoded["vv_valid_mask"]
    vh_valid = decoded["vh_valid_mask"]
    joint_valid = decoded["joint_valid_mask"]

    total_pixels = int(data_mask.size)
    data_mask_pixels = int(
        np.count_nonzero(data_mask)
    )
    vv_valid_pixels = int(
        np.count_nonzero(vv_valid)
    )
    vh_valid_pixels = int(
        np.count_nonzero(vh_valid)
    )
    joint_valid_pixels = int(
        np.count_nonzero(joint_valid)
    )

    return {
        "source": patch.get("source"),
        "acquisition_time": patch.get(
            "acquisition_time"
        ),
        "requested_bbox": patch.get("bbox"),
        "raster": {
            "width": decoded["width"],
            "height": decoded["height"],
            "band_count": decoded["band_count"],
            "dtype": decoded["dtype"],
            "crs": decoded["crs"],
            "bounds": decoded["bounds"],
        },
        "pixels": {
            "total": total_pixels,
            "data_mask_valid": data_mask_pixels,
            "vv_positive_valid": vv_valid_pixels,
            "vh_positive_valid": vh_valid_pixels,
            "joint_positive_valid": joint_valid_pixels,
            "data_mask_valid_fraction": _fraction(
                data_mask_pixels,
                total_pixels,
            ),
            "joint_valid_fraction": _fraction(
                joint_valid_pixels,
                total_pixels,
            ),
        },
        "vv": {
            "units": {
                "linear": "linear_power",
                "db": "dB",
            },
            "linear_power": _statistics(
                vv_linear[vv_valid]
            ),
            "db": _statistics(
                vv_db[vv_valid]
            ),
        },
        "vh": {
            "units": {
                "linear": "linear_power",
                "db": "dB",
            },
            "linear_power": _statistics(
                vh_linear[vh_valid]
            ),
            "db": _statistics(
                vh_db[vh_valid]
            ),
        },
        "vv_minus_vh_db": _statistics(
            (
                vv_db[joint_valid]
                - vh_db[joint_valid]
            )
        ),
        "data_notes": [
            (
                "VV and VH are calibrated Sentinel-1 "
                "SAR backscatter measurements."
            ),
            (
                "Linear-power backscatter is converted "
                "to dB using 10 * log10(value) only "
                "for finite positive pixels."
            ),
            (
                "dataMask identifies valid Sentinel Hub "
                "raster coverage; it is not a land/ocean mask."
            ),
            (
                "These statistics describe SAR "
                "backscatter only and do not classify "
                "an oil spill."
            ),
            (
                "Low-backscatter pixels can have "
                "non-oil causes including calm water, "
                "natural surfactants, rain effects and "
                "other ocean-atmosphere phenomena."
            ),
        ],
    }


def _statistics(
    values: np.ndarray,
) -> dict[str, float | int | None]:
    """Return JSON-safe descriptive statistics."""

    array = np.asarray(
        values,
        dtype=np.float64,
    )

    finite = array[
        np.isfinite(array)
    ]

    if finite.size == 0:
        return {
            "count": 0,
            "min": None,
            "p05": None,
            "p25": None,
            "median": None,
            "mean": None,
            "p75": None,
            "p95": None,
            "max": None,
            "std": None,
        }

    return {
        "count": int(finite.size),
        "min": _float(
            np.min(finite)
        ),
        "p05": _float(
            np.percentile(finite, 5)
        ),
        "p25": _float(
            np.percentile(finite, 25)
        ),
        "median": _float(
            np.median(finite)
        ),
        "mean": _float(
            np.mean(finite)
        ),
        "p75": _float(
            np.percentile(finite, 75)
        ),
        "p95": _float(
            np.percentile(finite, 95)
        ),
        "max": _float(
            np.max(finite)
        ),
        "std": _float(
            np.std(finite)
        ),
    }


def _fraction(
    numerator: int,
    denominator: int,
) -> float | None:
    if denominator <= 0:
        return None

    return round(
        numerator / denominator,
        6,
    )


def _float(
    value: Any,
) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None

    if not np.isfinite(parsed):
        return None

    return round(
        parsed,
        6,
    )