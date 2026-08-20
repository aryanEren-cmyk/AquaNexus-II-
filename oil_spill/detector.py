"""Adaptive Sentinel-1 SAR dark-slick candidate detection.

This module identifies spatially coherent low-backscatter regions in
Sentinel-1 SAR imagery.

Such regions are only slick-like SAR anomalies. They are NOT confirmed
oil spills.

The detector is intentionally heuristic and evidence-preserving.
"""

from __future__ import annotations

from collections import deque
from typing import Any

import numpy as np

from oil_spill.raster import decode_sentinel1_patch


class SlickDetectionError(RuntimeError):
    """Raised when slick-candidate analysis cannot be completed."""


def detect_dark_slick_candidates(
    patch: dict[str, Any],
    *,
    water_mask: np.ndarray | None = None,
    dark_percentile: float = 10.0,
    min_local_contrast_db: float = 1.5,
    min_component_pixels: int = 20,
    smoothing_window: int = 3,
    context_window: int = 21,
) -> dict[str, Any]:
    """Identify coherent low-backscatter SAR candidate regions.

    If ``water_mask`` is supplied, only pixels classified as water are
    eligible for candidate analysis.

    If no water mask is supplied, analysis is performed on all valid VV
    pixels, but those pixels must NOT be assumed to be ocean.

    IMPORTANT:
    Candidates are low-backscatter SAR anomalies only.
    They are not confirmed oil spills.
    """

    # ---------------------------------------------------------
    # VALIDATE CONFIGURATION
    # ---------------------------------------------------------

    dark_percentile = _validate_percentile(
        dark_percentile
    )

    min_local_contrast_db = _validate_positive_float(
        min_local_contrast_db,
        "min_local_contrast_db",
    )

    min_component_pixels = _validate_positive_int(
        min_component_pixels,
        "min_component_pixels",
    )

    smoothing_window = _validate_odd_window(
        smoothing_window,
        "smoothing_window",
    )

    context_window = _validate_odd_window(
        context_window,
        "context_window",
    )

    if context_window <= smoothing_window:
        raise ValueError(
            "context_window must be larger than smoothing_window."
        )

    # ---------------------------------------------------------
    # DECODE SAR DATA
    # ---------------------------------------------------------

    decoded = decode_sentinel1_patch(patch)

    vv_db = np.asarray(
        decoded["vv_db"],
        dtype=np.float64,
    )

    vh_db = np.asarray(
        decoded["vh_db"],
        dtype=np.float64,
    )

    vv_valid = np.asarray(
        decoded["vv_valid_mask"],
        dtype=bool,
    )

    vh_valid = np.asarray(
        decoded["vh_valid_mask"],
        dtype=bool,
    )

    if vv_db.ndim != 2:
        raise SlickDetectionError(
            "Sentinel-1 VV raster must be two-dimensional."
        )

    if (
        vh_db.shape != vv_db.shape
        or vv_valid.shape != vv_db.shape
        or vh_valid.shape != vv_db.shape
    ):
        raise SlickDetectionError(
            "Sentinel-1 raster arrays have inconsistent dimensions."
        )

    # ---------------------------------------------------------
    # WATER MASK
    # ---------------------------------------------------------

    if water_mask is None:
        analysis_mask = np.ones(
            vv_db.shape,
            dtype=bool,
        )

        water_mask_applied = False

    else:
        analysis_mask = np.asarray(
            water_mask,
            dtype=bool,
        )

        if analysis_mask.shape != vv_db.shape:
            raise ValueError(
                "water_mask dimensions must match "
                "the Sentinel-1 raster."
            )

        water_mask_applied = True

    # VV must be valid AND, when supplied, the pixel must be water.
    analysis_valid = (
        vv_valid
        & analysis_mask
    )

    total_pixel_count = int(
        vv_db.size
    )

    analysis_pixel_count = int(
        np.count_nonzero(
            analysis_valid
        )
    )

    # Only report actual water statistics when a real water mask exists.
    if water_mask_applied:
        water_pixel_count: int | None = int(
            np.count_nonzero(
                analysis_mask
            )
        )

        water_fraction: float | None = (
            water_pixel_count / total_pixel_count
            if total_pixel_count
            else None
        )

    else:
        water_pixel_count = None
        water_fraction = None

    # Operational context-quality flag. This is not an oil-risk threshold.
    # "land_dominated" simply means more than half of the mapped patch is land.
    if not water_mask_applied:
        analysis_context = "unknown_without_water_mask"
        land_dominated: bool | None = None

    elif water_fraction is not None and water_fraction < 0.5:
        analysis_context = "limited_land_dominated"
        land_dominated = True

    else:
        analysis_context = "water_dominated"
        land_dominated = False

    if analysis_pixel_count < 100:
        if water_mask_applied:
            raise SlickDetectionError(
                "Too few valid water VV pixels for "
                "SAR candidate analysis."
            )

        raise SlickDetectionError(
            "Too few valid VV pixels for SAR candidate analysis."
        )

    # ---------------------------------------------------------
    # SMALL-SCALE VV SMOOTHING
    # ---------------------------------------------------------

    vv_smoothed = _nan_box_mean(
        vv_db,
        analysis_valid,
        smoothing_window,
    )

    # Even though smoothing can generate a value next to a valid pixel,
    # only original eligible analysis pixels may participate.
    smoothed_valid = (
        np.isfinite(vv_smoothed)
        & analysis_valid
    )

    valid_values = vv_smoothed[
        smoothed_valid
    ]

    if valid_values.size < 100:
        raise SlickDetectionError(
            "Too few valid smoothed pixels for "
            "SAR candidate analysis."
        )

    # ---------------------------------------------------------
    # SCENE-ADAPTIVE DARK THRESHOLD
    # ---------------------------------------------------------

    global_dark_threshold = float(
        np.percentile(
            valid_values,
            dark_percentile,
        )
    )

    # ---------------------------------------------------------
    # LOCAL BACKGROUND
    # ---------------------------------------------------------

    local_background = _nan_box_mean(
        vv_smoothed,
        smoothed_valid,
        context_window,
    )

    # Positive value means current pixel is darker than its
    # surrounding local SAR background.
    local_contrast_db = (
        local_background
        - vv_smoothed
    )

    # ---------------------------------------------------------
    # RAW DARK-CANDIDATE MASK
    # ---------------------------------------------------------

    raw_candidate_mask = (
        analysis_valid
        & smoothed_valid
        & np.isfinite(
            local_background
        )
        & (
            vv_smoothed
            <= global_dark_threshold
        )
        & (
            local_contrast_db
            >= min_local_contrast_db
        )
    )

    # ---------------------------------------------------------
    # CONNECTED COMPONENTS
    # ---------------------------------------------------------

    components = _connected_components(
        raw_candidate_mask
    )

    accepted_components = [
        component
        for component in components
        if len(component)
        >= min_component_pixels
    ]

    candidate_mask = np.zeros(
        vv_db.shape,
        dtype=bool,
    )

    candidate_records: list[
        dict[str, Any]
    ] = []

    # ---------------------------------------------------------
    # DESCRIBE EACH ACCEPTED REGION
    # ---------------------------------------------------------

    for candidate_id, component in enumerate(
        accepted_components,
        start=1,
    ):
        rows = np.asarray(
            [
                pixel[0]
                for pixel in component
            ],
            dtype=int,
        )

        cols = np.asarray(
            [
                pixel[1]
                for pixel in component
            ],
            dtype=int,
        )

        candidate_mask[
            rows,
            cols,
        ] = True

        # Original SAR values.
        vv_values = vv_db[
            rows,
            cols,
        ]

        # Smoothed VV values are what actually participated in the
        # adaptive threshold.
        smoothed_vv_values = vv_smoothed[
            rows,
            cols,
        ]

        contrast_values = local_contrast_db[
            rows,
            cols,
        ]

        # VH is supporting information only.
        vh_available = vh_valid[
            rows,
            cols,
        ]

        vh_rows = rows[
            vh_available
        ]

        vh_cols = cols[
            vh_available
        ]

        vh_values = vh_db[
            vh_rows,
            vh_cols,
        ]

        vh_available_count = int(
            np.count_nonzero(
                vh_available
            )
        )

        row_min = int(
            np.min(rows)
        )
        row_max = int(
            np.max(rows)
        )
        col_min = int(
            np.min(cols)
        )
        col_max = int(
            np.max(cols)
        )

        centroid_row = float(
            np.mean(rows)
        )
        centroid_col = float(
            np.mean(cols)
        )

        centroid_lon, centroid_lat = (
            _pixel_center_to_lon_lat(
                centroid_row,
                centroid_col,
                decoded["bounds"],
                decoded["width"],
                decoded["height"],
            )
        )

        geographic_bounds = (
            _pixel_bounds_to_geographic_bounds(
                row_min=row_min,
                row_max=row_max,
                col_min=col_min,
                col_max=col_max,
                bounds=decoded["bounds"],
                width=decoded["width"],
                height=decoded["height"],
            )
        )

        candidate_records.append(
            {
                "candidate_id": candidate_id,

                "pixel_count": int(
                    len(component)
                ),

                "pixel_bounds": {
                    "row_min": row_min,
                    "row_max": row_max,
                    "col_min": col_min,
                    "col_max": col_max,
                },

                "centroid_pixel": {
                    "row": round(
                        centroid_row,
                        6,
                    ),
                    "col": round(
                        centroid_col,
                        6,
                    ),
                },

                "centroid": {
                    "latitude": round(
                        centroid_lat,
                        6,
                    ),
                    "longitude": round(
                        centroid_lon,
                        6,
                    ),
                },

                "geographic_bounds": geographic_bounds,

                "vv_db": _stats(
                    vv_values
                ),

                "smoothed_vv_db": _stats(
                    smoothed_vv_values
                ),

                "local_dark_contrast_db": _stats(
                    contrast_values
                ),

                "vh_db_when_available": _stats(
                    vh_values
                ),

                "vh_available_fraction": round(
                    vh_available_count
                    / len(component),
                    6,
                ),
            }
        )

    # ---------------------------------------------------------
    # FINAL STATISTICS
    # ---------------------------------------------------------

    candidate_pixels = int(
        np.count_nonzero(
            candidate_mask
        )
    )

    candidate_fraction = (
        candidate_pixels
        / analysis_pixel_count
        if analysis_pixel_count
        else None
    )

    # ---------------------------------------------------------
    # RESULT
    # ---------------------------------------------------------

    return {
        "analysis_type": (
            "adaptive_sar_dark_slick_candidate_screening"
        ),

        "classification": (
            "candidate_screening_only"
        ),

        "has_dark_slick_candidates": bool(
            candidate_records
        ),

        "candidate_count": len(
            candidate_records
        ),

        "candidates": candidate_records,

        "analysis_context": {
            "status": analysis_context,
            "land_dominated": land_dominated,
            "definition": (
                "land_dominated means mapped water fraction is below 0.5; "
                "this is an operational context-quality flag, not an "
                "oil-spill probability or hazard threshold."
            ),
        },

        "statistics": {
            "total_pixels": total_pixel_count,

            "water_mask_applied": (
                water_mask_applied
            ),

            # None means no real land/water mask was supplied.
            "water_pixels": (
                water_pixel_count
            ),

            "water_fraction": (
                round(
                    water_fraction,
                    6,
                )
                if water_fraction
                is not None
                else None
            ),

            "valid_analysis_vv_pixels": (
                analysis_pixel_count
            ),

            # Only meaningful if a real water mask was supplied.
            "valid_ocean_vv_pixels": (
                analysis_pixel_count
                if water_mask_applied
                else None
            ),

            "candidate_pixels": (
                candidate_pixels
            ),

            "candidate_fraction_of_analysis": (
                round(
                    candidate_fraction,
                    6,
                )
                if candidate_fraction
                is not None
                else None
            ),

            "candidate_fraction_of_ocean": (
                round(
                    candidate_fraction,
                    6,
                )
                if (
                    candidate_fraction
                    is not None
                    and water_mask_applied
                )
                else None
            ),
        },

        "thresholds": {
            "method": (
                "scene_adaptive_dark_tail_plus_local_contrast"
            ),

            "dark_percentile": (
                dark_percentile
            ),

            "derived_vv_threshold_db": round(
                global_dark_threshold,
                6,
            ),

            "minimum_local_contrast_db": (
                min_local_contrast_db
            ),

            "minimum_component_pixels": (
                min_component_pixels
            ),

            "smoothing_window_pixels": (
                smoothing_window
            ),

            "context_window_pixels": (
                context_window
            ),
        },

        "raster": {
            "width": decoded["width"],
            "height": decoded["height"],
            "bounds": decoded["bounds"],
            "crs": decoded["crs"],
        },

        "acquisition_time": patch.get(
            "acquisition_time"
        ),

        "source": patch.get(
            "source"
        ),

        "data_notes": [
            (
                "Candidates are coherent low-backscatter "
                "SAR anomalies and are not confirmed oil spills."
            ),
            (
                "When supplied, the Copernicus permanent-water "
                "mask restricts analysis to mapped water pixels."
            ),
            (
                "If no water mask is supplied, valid SAR pixels "
                "must not automatically be interpreted as ocean."
            ),
            (
                "The permanent-water reference layer may not "
                "represent recent shoreline or reclamation changes."
            ),
            (
                "A land-dominated patch is marked as limited analysis "
                "context when mapped water occupies less than half of "
                "the raster. This is an operational quality flag only."
            ),
            (
                "Candidate centroids and geographic bounds are derived "
                "from the raster georeferencing and are suitable for "
                "map display, not as surveyed spill boundaries."
            ),
            (
                "The VV dark threshold is derived adaptively "
                "from eligible pixels in the current SAR patch."
            ),
            (
                "Local contrast requires candidate pixels to "
                "be darker than their surrounding SAR context."
            ),
            (
                "VH is supporting information only and is not "
                "required for candidate detection."
            ),
            (
                "Calm water, natural surfactants, biological films, "
                "rain effects, current boundaries, atmospheric "
                "effects and other phenomena can produce similar "
                "low-backscatter SAR signatures."
            ),
            (
                "This detector performs candidate screening only "
                "and does not establish the presence of petroleum."
            ),
        ],
    }


# =============================================================
# SPATIAL / GEOREFERENCING HELPERS
# =============================================================


def _pixel_center_to_lon_lat(
    row: float,
    col: float,
    bounds: dict[str, float],
    width: int,
    height: int,
) -> tuple[float, float]:
    """Convert a raster pixel center to longitude/latitude.

    AquaNexus Sentinel Hub patches are requested in geographic CRS and
    currently decode as EPSG:4326. Raster rows increase downward from the
    northern edge, while columns increase eastward from the western edge.
    """

    if width <= 0 or height <= 0:
        raise ValueError(
            "Raster width and height must be positive."
        )

    left = float(
        bounds["left"]
    )
    bottom = float(
        bounds["bottom"]
    )
    right = float(
        bounds["right"]
    )
    top = float(
        bounds["top"]
    )

    pixel_width = (
        right - left
    ) / width

    pixel_height = (
        top - bottom
    ) / height

    longitude = (
        left
        + (float(col) + 0.5)
        * pixel_width
    )

    latitude = (
        top
        - (float(row) + 0.5)
        * pixel_height
    )

    return (
        float(longitude),
        float(latitude),
    )


def _pixel_bounds_to_geographic_bounds(
    *,
    row_min: int,
    row_max: int,
    col_min: int,
    col_max: int,
    bounds: dict[str, float],
    width: int,
    height: int,
) -> dict[str, float]:
    """Convert inclusive pixel bounds to geographic outer-edge bounds."""

    if width <= 0 or height <= 0:
        raise ValueError(
            "Raster width and height must be positive."
        )

    if not (
        0 <= row_min <= row_max < height
        and 0 <= col_min <= col_max < width
    ):
        raise ValueError(
            "Candidate pixel bounds fall outside the raster."
        )

    left = float(
        bounds["left"]
    )
    bottom = float(
        bounds["bottom"]
    )
    right = float(
        bounds["right"]
    )
    top = float(
        bounds["top"]
    )

    pixel_width = (
        right - left
    ) / width

    pixel_height = (
        top - bottom
    ) / height

    west = (
        left
        + col_min
        * pixel_width
    )

    east = (
        left
        + (col_max + 1)
        * pixel_width
    )

    north = (
        top
        - row_min
        * pixel_height
    )

    south = (
        top
        - (row_max + 1)
        * pixel_height
    )

    return {
        "north": round(
            float(north),
            6,
        ),
        "south": round(
            float(south),
            6,
        ),
        "west": round(
            float(west),
            6,
        ),
        "east": round(
            float(east),
            6,
        ),
    }


# =============================================================
# SPATIAL FILTERING HELPERS
# =============================================================


def _nan_box_mean(
    values: np.ndarray,
    valid_mask: np.ndarray,
    window: int,
) -> np.ndarray:
    """Compute a validity-aware moving box mean.

    Integral images allow the local mean to be calculated efficiently
    without requiring SciPy.
    """

    if values.ndim != 2:
        raise ValueError(
            "values must be a two-dimensional array."
        )

    if valid_mask.shape != values.shape:
        raise ValueError(
            "valid_mask dimensions must match values."
        )

    radius = window // 2

    finite = (
        valid_mask
        & np.isfinite(values)
    )

    clean = np.where(
        finite,
        values,
        0.0,
    )

    counts = finite.astype(
        np.float64
    )

    padded_values = np.pad(
        clean,
        radius,
        mode="constant",
        constant_values=0.0,
    )

    padded_counts = np.pad(
        counts,
        radius,
        mode="constant",
        constant_values=0.0,
    )

    sum_integral = _integral_image(
        padded_values
    )

    count_integral = _integral_image(
        padded_counts
    )

    height, width = values.shape

    sums = _window_sums(
        sum_integral,
        height,
        width,
        window,
    )

    sample_counts = _window_sums(
        count_integral,
        height,
        width,
        window,
    )

    output = np.full(
        values.shape,
        np.nan,
        dtype=np.float64,
    )

    usable = (
        sample_counts > 0
    )

    output[
        usable
    ] = (
        sums[usable]
        / sample_counts[usable]
    )

    return output


def _integral_image(
    array: np.ndarray,
) -> np.ndarray:
    """Return an integral image padded by one row and column."""

    integral = np.cumsum(
        np.cumsum(
            array,
            axis=0,
        ),
        axis=1,
    )

    return np.pad(
        integral,
        (
            (1, 0),
            (1, 0),
        ),
        mode="constant",
        constant_values=0.0,
    )


def _window_sums(
    integral: np.ndarray,
    height: int,
    width: int,
    window: int,
) -> np.ndarray:
    """Return box sums from an integral image."""

    return (
        integral[
            window:window + height,
            window:window + width,
        ]
        - integral[
            0:height,
            window:window + width,
        ]
        - integral[
            window:window + height,
            0:width,
        ]
        + integral[
            0:height,
            0:width,
        ]
    )


# =============================================================
# CONNECTED COMPONENTS
# =============================================================


def _connected_components(
    mask: np.ndarray,
) -> list[list[tuple[int, int]]]:
    """Return 8-connected components of a boolean mask."""

    if mask.ndim != 2:
        raise ValueError(
            "candidate mask must be two-dimensional."
        )

    mask = np.asarray(
        mask,
        dtype=bool,
    )

    visited = np.zeros(
        mask.shape,
        dtype=bool,
    )

    components: list[
        list[tuple[int, int]]
    ] = []

    height, width = mask.shape

    neighbours = (
        (-1, -1),
        (-1, 0),
        (-1, 1),
        (0, -1),
        (0, 1),
        (1, -1),
        (1, 0),
        (1, 1),
    )

    for row in range(height):
        for col in range(width):
            if (
                not mask[row, col]
                or visited[row, col]
            ):
                continue

            queue: deque[
                tuple[int, int]
            ] = deque(
                [(row, col)]
            )

            visited[
                row,
                col,
            ] = True

            component: list[
                tuple[int, int]
            ] = []

            while queue:
                (
                    current_row,
                    current_col,
                ) = queue.popleft()

                component.append(
                    (
                        current_row,
                        current_col,
                    )
                )

                for (
                    row_offset,
                    col_offset,
                ) in neighbours:
                    next_row = (
                        current_row
                        + row_offset
                    )

                    next_col = (
                        current_col
                        + col_offset
                    )

                    if not (
                        0
                        <= next_row
                        < height
                        and
                        0
                        <= next_col
                        < width
                    ):
                        continue

                    if visited[
                        next_row,
                        next_col,
                    ]:
                        continue

                    if not mask[
                        next_row,
                        next_col,
                    ]:
                        continue

                    visited[
                        next_row,
                        next_col,
                    ] = True

                    queue.append(
                        (
                            next_row,
                            next_col,
                        )
                    )

            components.append(
                component
            )

    return components


# =============================================================
# STATISTICS
# =============================================================


def _stats(
    values: np.ndarray,
) -> dict[str, float | int | None]:
    """Return compact JSON-safe statistics for finite values."""

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
            "median": None,
            "mean": None,
            "max": None,
        }

    return {
        "count": int(
            finite.size
        ),

        "min": round(
            float(
                np.min(finite)
            ),
            6,
        ),

        "median": round(
            float(
                np.median(finite)
            ),
            6,
        ),

        "mean": round(
            float(
                np.mean(finite)
            ),
            6,
        ),

        "max": round(
            float(
                np.max(finite)
            ),
            6,
        ),
    }


# =============================================================
# VALIDATION
# =============================================================


def _validate_percentile(
    value: Any,
) -> float:
    """Validate adaptive dark-tail percentile."""

    if isinstance(
        value,
        (bool, np.bool_),
    ):
        raise ValueError(
            "dark_percentile must be numeric."
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
            "dark_percentile must be numeric."
        ) from exc

    if not np.isfinite(
        parsed
    ):
        raise ValueError(
            "dark_percentile must be finite."
        )

    if not 0 < parsed < 50:
        raise ValueError(
            "dark_percentile must be between 0 and 50."
        )

    return parsed


def _validate_positive_float(
    value: Any,
    name: str,
) -> float:
    """Validate a finite positive floating-point parameter."""

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

    if (
        not np.isfinite(parsed)
        or parsed <= 0
    ):
        raise ValueError(
            f"{name} must be a finite positive number."
        )

    return parsed


def _validate_positive_int(
    value: Any,
    name: str,
) -> int:
    """Validate a strictly positive integer without silent truncation."""

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
    ):
        raise ValueError(
            f"{name} must be a positive integer."
        )

    parsed = int(
        numeric
    )

    if parsed <= 0:
        raise ValueError(
            f"{name} must be greater than 0."
        )

    return parsed


def _validate_odd_window(
    value: Any,
    name: str,
) -> int:
    """Validate an odd positive moving-window size."""

    parsed = _validate_positive_int(
        value,
        name,
    )

    if parsed % 2 == 0:
        raise ValueError(
            f"{name} must be odd."
        )

    return parsed