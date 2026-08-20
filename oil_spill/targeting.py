"""Select a nearby water-dominated SAR analysis target.

Named coastal locations often resolve to a point on land. For oil-slick
screening, AquaNexus may move the analysis center to a nearby mapped-water
location.

The shift is always reported explicitly and is never hidden from the user.
"""

from __future__ import annotations

from math import asin, cos, radians, sin, sqrt
from typing import Any

import numpy as np

from oil_spill.watermask import fetch_water_mask


DEFAULT_SEARCH_HALF_SIZE_DEGREES = 0.12
DEFAULT_SEARCH_MASK_SIZE = 256
DEFAULT_MIN_WATER_FRACTION = 0.70


class OceanTargetingError(RuntimeError):
    """Raised when nearby-ocean target selection cannot be completed."""


def choose_ocean_analysis_target(
    latitude: float,
    longitude: float,
    *,
    patch_half_size_degrees: float = 0.03,
    search_half_size_degrees: float = (
        DEFAULT_SEARCH_HALF_SIZE_DEGREES
    ),
    mask_size: int = DEFAULT_SEARCH_MASK_SIZE,
    minimum_water_fraction: float = (
        DEFAULT_MIN_WATER_FRACTION
    ),
) -> dict[str, Any]:
    """Choose the nearest water-dominated patch center.

    If the requested location already has sufficient mapped-water
    coverage, it is kept unchanged.

    Otherwise, a larger surrounding permanent-water mask is searched for
    the nearest center whose final analysis-sized neighborhood satisfies
    ``minimum_water_fraction``.

    If no such location exists, the original location is retained.
    """

    latitude = _validate_coordinate(
        latitude,
        "latitude",
        -90.0,
        90.0,
    )

    longitude = _validate_coordinate(
        longitude,
        "longitude",
        -180.0,
        180.0,
    )

    patch_half_size_degrees = _validate_positive_float(
        patch_half_size_degrees,
        "patch_half_size_degrees",
    )

    search_half_size_degrees = _validate_positive_float(
        search_half_size_degrees,
        "search_half_size_degrees",
    )

    minimum_water_fraction = _validate_fraction(
        minimum_water_fraction,
        "minimum_water_fraction",
    )

    mask_size = _validate_positive_int(
        mask_size,
        "mask_size",
    )

    if search_half_size_degrees <= patch_half_size_degrees:
        raise ValueError(
            "search_half_size_degrees must be larger than "
            "patch_half_size_degrees."
        )

    search_bbox = {
        "west": longitude - search_half_size_degrees,
        "south": latitude - search_half_size_degrees,
        "east": longitude + search_half_size_degrees,
        "north": latitude + search_half_size_degrees,
    }

    try:
        water = fetch_water_mask(
            search_bbox,
            mask_size,
            mask_size,
        )

    except Exception as exc:
        raise OceanTargetingError(
            "Nearby-ocean water-mask retrieval failed."
        ) from exc

    water_mask = np.asarray(
        water.get("water_mask"),
        dtype=bool,
    )

    if water_mask.shape != (
        mask_size,
        mask_size,
    ):
        raise OceanTargetingError(
            "Nearby-ocean water mask had unexpected dimensions."
        )

    pixel_width_degrees = (
        search_bbox["east"]
        - search_bbox["west"]
    ) / mask_size

    pixel_height_degrees = (
        search_bbox["north"]
        - search_bbox["south"]
    ) / mask_size

    half_cols = max(
        1,
        int(
            np.ceil(
                patch_half_size_degrees
                / pixel_width_degrees
            )
        ),
    )

    half_rows = max(
        1,
        int(
            np.ceil(
                patch_half_size_degrees
                / pixel_height_degrees
            )
        ),
    )

    local_fraction = _local_water_fraction(
        water_mask,
        half_rows,
        half_cols,
    )

    center_row = (
        mask_size - 1
    ) / 2.0

    center_col = (
        mask_size - 1
    ) / 2.0

    requested_fraction = _nearest_fraction(
        local_fraction,
        center_row,
        center_col,
    )

    # ---------------------------------------------------------
    # Requested point already has sufficient water context.
    # ---------------------------------------------------------

    if (
        requested_fraction is not None
        and requested_fraction
        >= minimum_water_fraction
    ):
        return {
            "latitude": latitude,
            "longitude": longitude,
            "shifted": False,
            "shift_distance_km": 0.0,
            "selection_status": (
                "requested_point_water_dominated"
            ),
            "estimated_water_fraction": round(
                requested_fraction,
                6,
            ),
            "minimum_water_fraction": (
                minimum_water_fraction
            ),
            "search_bbox": search_bbox,
            "source": water.get(
                "source"
            ),
            "data_notes": [
                (
                    "The requested location already had "
                    "sufficient mapped-water context."
                ),
                (
                    "Permanent-water reference data are used "
                    "only for analysis targeting and may not "
                    "represent recent shoreline changes."
                ),
            ],
        }

    # ---------------------------------------------------------
    # Find nearest water-dominated candidate.
    # ---------------------------------------------------------

    best: tuple[
        float,
        float,
        int,
        int,
    ] | None = None

    height, width = water_mask.shape

    for row in range(height):
        for col in range(width):
            fraction = local_fraction[
                row,
                col,
            ]

            if not np.isfinite(
                fraction
            ):
                continue

            if (
                fraction
                < minimum_water_fraction
            ):
                continue

            # Require the selected center itself to be mapped water.
            if not water_mask[
                row,
                col,
            ]:
                continue

            distance_squared = (
                (row - center_row) ** 2
                + (col - center_col) ** 2
            )

            candidate_key = (
                distance_squared,
                -float(fraction),
                row,
                col,
            )

            if (
                best is None
                or candidate_key < best
            ):
                best = candidate_key

    # ---------------------------------------------------------
    # No suitable nearby water-dominated patch.
    # Keep original point and report the limitation.
    # ---------------------------------------------------------

    if best is None:
        return {
            "latitude": latitude,
            "longitude": longitude,
            "shifted": False,
            "shift_distance_km": 0.0,
            "selection_status": (
                "no_nearby_water_dominated_patch"
            ),
            "estimated_water_fraction": (
                round(
                    requested_fraction,
                    6,
                )
                if requested_fraction
                is not None
                else None
            ),
            "minimum_water_fraction": (
                minimum_water_fraction
            ),
            "search_bbox": search_bbox,
            "source": water.get(
                "source"
            ),
            "data_notes": [
                (
                    "No nearby analysis-sized patch met "
                    "the requested mapped-water fraction, "
                    "so the original location was retained."
                ),
                (
                    "A land-dominated result should therefore "
                    "be treated as limited coastal context."
                ),
            ],
        }

    _, _, best_row, best_col = best

    selected_fraction = float(
        local_fraction[
            best_row,
            best_col,
        ]
    )

    selected_longitude = (
        search_bbox["west"]
        + (
            best_col + 0.5
        )
        * pixel_width_degrees
    )

    selected_latitude = (
        search_bbox["north"]
        - (
            best_row + 0.5
        )
        * pixel_height_degrees
    )

    shift_distance_km = _haversine_km(
        latitude,
        longitude,
        selected_latitude,
        selected_longitude,
    )

    return {
        "latitude": round(
            selected_latitude,
            6,
        ),
        "longitude": round(
            selected_longitude,
            6,
        ),
        "shifted": True,
        "shift_distance_km": round(
            shift_distance_km,
            3,
        ),
        "selection_status": (
            "shifted_to_nearby_water_dominated_patch"
        ),
        "estimated_water_fraction": round(
            selected_fraction,
            6,
        ),
        "minimum_water_fraction": (
            minimum_water_fraction
        ),
        "search_bbox": search_bbox,
        "source": water.get(
            "source"
        ),
        "data_notes": [
            (
                "The resolved place coordinate was not "
                "sufficiently water-dominated for SAR screening."
            ),
            (
                "The analysis center was shifted to the nearest "
                "mapped-water location whose surrounding analysis "
                "patch met the minimum water-context requirement."
            ),
            (
                "The shift is an analysis-targeting operation "
                "and does not imply the presence of an oil spill."
            ),
            (
                "Permanent-water reference data may not represent "
                "recent shoreline or reclamation changes."
            ),
        ],
    }


def _local_water_fraction(
    mask: np.ndarray,
    half_rows: int,
    half_cols: int,
) -> np.ndarray:
    """Calculate local mapped-water fractions using an integral image."""

    height, width = mask.shape

    values = mask.astype(
        np.float64
    )

    integral = np.pad(
        np.cumsum(
            np.cumsum(
                values,
                axis=0,
            ),
            axis=1,
        ),
        (
            (1, 0),
            (1, 0),
        ),
        mode="constant",
        constant_values=0.0,
    )

    result = np.full(
        mask.shape,
        np.nan,
        dtype=np.float64,
    )

    for row in range(
        half_rows,
        height - half_rows,
    ):
        row_start = (
            row - half_rows
        )

        row_end = (
            row + half_rows + 1
        )

        for col in range(
            half_cols,
            width - half_cols,
        ):
            col_start = (
                col - half_cols
            )

            col_end = (
                col + half_cols + 1
            )

            water_count = (
                integral[
                    row_end,
                    col_end,
                ]
                - integral[
                    row_start,
                    col_end,
                ]
                - integral[
                    row_end,
                    col_start,
                ]
                + integral[
                    row_start,
                    col_start,
                ]
            )

            total_count = (
                (
                    row_end
                    - row_start
                )
                * (
                    col_end
                    - col_start
                )
            )

            result[
                row,
                col,
            ] = (
                water_count
                / total_count
            )

    return result


def _nearest_fraction(
    fractions: np.ndarray,
    row: float,
    col: float,
) -> float | None:
    selected_row = int(
        round(row)
    )

    selected_col = int(
        round(col)
    )

    selected_row = max(
        0,
        min(
            selected_row,
            fractions.shape[0] - 1,
        ),
    )

    selected_col = max(
        0,
        min(
            selected_col,
            fractions.shape[1] - 1,
        ),
    )

    value = fractions[
        selected_row,
        selected_col,
    ]

    if not np.isfinite(
        value
    ):
        return None

    return float(
        value
    )


def _haversine_km(
    latitude_a: float,
    longitude_a: float,
    latitude_b: float,
    longitude_b: float,
) -> float:
    radius_km = 6371.0088

    lat1 = radians(
        latitude_a
    )

    lat2 = radians(
        latitude_b
    )

    delta_lat = radians(
        latitude_b
        - latitude_a
    )

    delta_lon = radians(
        longitude_b
        - longitude_a
    )

    value = (
        sin(
            delta_lat / 2
        ) ** 2
        + cos(lat1)
        * cos(lat2)
        * sin(
            delta_lon / 2
        ) ** 2
    )

    return (
        2
        * radius_km
        * asin(
            sqrt(value)
        )
    )


def _validate_coordinate(
    value: Any,
    name: str,
    minimum: float,
    maximum: float,
) -> float:
    parsed = _validate_float(
        value,
        name,
    )

    if not (
        minimum
        <= parsed
        <= maximum
    ):
        raise ValueError(
            f"{name} must be between "
            f"{minimum} and {maximum}."
        )

    return parsed


def _validate_positive_float(
    value: Any,
    name: str,
) -> float:
    parsed = _validate_float(
        value,
        name,
    )

    if parsed <= 0:
        raise ValueError(
            f"{name} must be greater than 0."
        )

    return parsed


def _validate_fraction(
    value: Any,
    name: str,
) -> float:
    parsed = _validate_float(
        value,
        name,
    )

    if not (
        0.0
        <= parsed
        <= 1.0
    ):
        raise ValueError(
            f"{name} must be between 0 and 1."
        )

    return parsed


def _validate_float(
    value: Any,
    name: str,
) -> float:
    if isinstance(
        value,
        (bool, np.bool_),
    ):
        raise ValueError(
            f"{name} must be numeric."
        )

    try:
        parsed = float(
            value
        )

    except (
        TypeError,
        ValueError,
    ) as exc:
        raise ValueError(
            f"{name} must be numeric."
        ) from exc

    if not np.isfinite(
        parsed
    ):
        raise ValueError(
            f"{name} must be finite."
        )

    return parsed


def _validate_positive_int(
    value: Any,
    name: str,
) -> int:
    if isinstance(
        value,
        (bool, np.bool_),
    ):
        raise ValueError(
            f"{name} must be a positive integer."
        )

    try:
        numeric = float(
            value
        )

    except (
        TypeError,
        ValueError,
    ) as exc:
        raise ValueError(
            f"{name} must be a positive integer."
        ) from exc

    if (
        not np.isfinite(numeric)
        or not numeric.is_integer()
        or numeric <= 0
    ):
        raise ValueError(
            f"{name} must be a positive integer."
        )

    return int(
        numeric
    )