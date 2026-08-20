"""Location-aware Sentinel-1 SAR slick-candidate screening service.

This module connects:

location resolution
    -> Sentinel-1 scene discovery
    -> Sentinel Hub SAR patch retrieval
    -> Copernicus water masking
    -> adaptive dark-slick candidate screening

The service returns JSON-safe scientific evidence.

It does NOT confirm oil spills.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from location.resolver import (
    LocationResolverError,
    resolve_location,
)

from oil_spill.detector import (
    SlickDetectionError,
    detect_dark_slick_candidates,
)

from oil_spill.targeting import (
    OceanTargetingError,
    choose_ocean_analysis_target,
)

from oil_spill.sentinel import (
    SentinelSearchError,
    search_sentinel1_scenes,
)

from oil_spill.sentinelhub import (
    SentinelHubError,
    fetch_sentinel1_patch,
)

from oil_spill.watermask import (
    fetch_water_mask,
)


DEFAULT_SCENE_DAYS = 30
DEFAULT_SCENE_LIMIT = 10

DEFAULT_HALF_SIZE_DEGREES = 0.03
DEFAULT_RASTER_WIDTH = 256
DEFAULT_RASTER_HEIGHT = 256

MIN_WATER_PIXELS_FOR_ANALYSIS = 100


class OilSpillServiceError(RuntimeError):
    """Raised when Oil Spill screening cannot be completed safely."""


def get_oil_slick_insights(
    location: str,
    *,
    scene_days: int = DEFAULT_SCENE_DAYS,
    half_size_degrees: float = DEFAULT_HALF_SIZE_DEGREES,
    width: int = DEFAULT_RASTER_WIDTH,
    height: int = DEFAULT_RASTER_HEIGHT,
) -> dict[str, Any]:
    """Return evidence-backed Sentinel-1 SAR slick-candidate context.

    This is the main deterministic service function for AquaNexus Oil Spill
    analysis.

    The returned result is JSON-safe.

    Important:
        A SAR dark-slick candidate is NOT confirmation of petroleum or an
        oil spill.
    """

    started_at = datetime.now(UTC)

    resolved = _resolve_query_location(
        location
    )

    latitude = _required_float(
        resolved.get("latitude"),
        "resolved latitude",
    )

    longitude = _required_float(
        resolved.get("longitude"),
        "resolved longitude",
    )

    # ---------------------------------------------------------
    # SELECT SCIENTIFIC ANALYSIS TARGET
    # ---------------------------------------------------------

    try:
        analysis_target = choose_ocean_analysis_target(
            latitude,
            longitude,
            patch_half_size_degrees=half_size_degrees,
        )

    except (
        OceanTargetingError,
        ValueError,
    ) as exc:
        raise OilSpillServiceError(
            "Nearby-ocean analysis targeting failed."
        ) from exc

    analysis_latitude = _required_float(
        analysis_target.get("latitude"),
        "analysis target latitude",
    )

    analysis_longitude = _required_float(
        analysis_target.get("longitude"),
        "analysis target longitude",
    )

    # ---------------------------------------------------------
    # 1. DISCOVER REAL SENTINEL-1 SCENES
    # ---------------------------------------------------------

    try:
        scene_search = search_sentinel1_scenes(
            analysis_latitude,
            analysis_longitude,
            days=scene_days,
            limit=DEFAULT_SCENE_LIMIT,
        )

    except (
        SentinelSearchError,
        ValueError,
    ) as exc:
        raise OilSpillServiceError(
            "Sentinel-1 scene discovery failed."
        ) from exc

    scenes = scene_search.get(
        "scenes",
        [],
    )

    if not isinstance(
        scenes,
        list,
    ):
        raise OilSpillServiceError(
            "Sentinel-1 scene discovery returned "
            "an invalid scene list."
        )

    selected_scene = _select_usable_scene(
        scenes
    )

    # No compatible scene is not a system failure.
    if selected_scene is None:
        return _no_scene_result(
            location=resolved,
            analysis_target=analysis_target,
            scene_search=scene_search,
            scene_days=scene_days,
            started_at=started_at,
        )

    acquisition_time = selected_scene.get(
        "acquisition_time"
    )

    if not isinstance(
        acquisition_time,
        str,
    ) or not acquisition_time.strip():
        raise OilSpillServiceError(
            "Selected Sentinel-1 scene has no "
            "usable acquisition timestamp."
        )

    # ---------------------------------------------------------
    # 2. FETCH SMALL REAL SAR PATCH
    # ---------------------------------------------------------

    try:
        patch = fetch_sentinel1_patch(
            analysis_latitude,
            analysis_longitude,
            acquisition_time,
            half_size_degrees=half_size_degrees,
            width=width,
            height=height,
        )

    except (
        SentinelHubError,
        ValueError,
    ) as exc:
        raise OilSpillServiceError(
            "Sentinel-1 SAR patch retrieval failed."
        ) from exc

    patch_bbox = patch.get(
        "bbox"
    )

    if not isinstance(
        patch_bbox,
        dict,
    ):
        raise OilSpillServiceError(
            "Sentinel-1 SAR patch did not contain "
            "a valid bounding box."
        )

    # ---------------------------------------------------------
    # 3. FETCH REAL WATER MASK
    # ---------------------------------------------------------

    try:
        water = fetch_water_mask(
            patch_bbox,
            width,
            height,
        )

    except Exception as exc:
        # The water mask is scientifically essential before arbitrary
        # coastal/location screening. We do not silently continue without it.
        raise OilSpillServiceError(
            "Copernicus water-mask retrieval failed."
        ) from exc

    water_mask = water.get(
        "water_mask"
    )

    water_pixels = _optional_int(
        water.get(
            "water_pixel_count"
        )
    )

    total_pixels = _optional_int(
        water.get(
            "total_pixels"
        )
    )

    water_fraction = _optional_float(
        water.get(
            "water_fraction"
        )
    )

    # ---------------------------------------------------------
    # 4. HANDLE PATCHES WITH TOO LITTLE WATER
    # ---------------------------------------------------------

    if (
        water_pixels is not None
        and water_pixels
        < MIN_WATER_PIXELS_FOR_ANALYSIS
    ):
        return {
            "status": (
                "insufficient_water_coverage"
            ),

            "screening_performed": False,

            "location": _location_payload(
                resolved
            ),

            "analysis_target": (
                _analysis_target_payload(
                    analysis_target
                )
            ),

            "satellite_observation": (
                _scene_payload(
                    selected_scene
                )
            ),

            "scene_search": (
                _scene_search_payload(
                    scene_search
                )
            ),

            "analysis_patch": {
                "center": {
                    "latitude": analysis_latitude,
                    "longitude": analysis_longitude,
                },
                "bbox": patch_bbox,
                "width": width,
                "height": height,
                "half_size_degrees": (
                    half_size_degrees
                ),
            },

            "water_context": (
                _water_payload(
                    water
                )
            ),

            "screening": None,

            "summary": (
                "A recent Sentinel-1 SAR scene was available, "
                "but the selected analysis patch contained too few "
                "mapped water pixels for responsible slick-"
                "candidate screening."
            ),

            "data_notes": (
                _service_notes()
                + _safe_string_list(
                    analysis_target.get(
                        "data_notes"
                    )
                )
                + [
                    (
                        "No slick-candidate classification was "
                        "performed because mapped water coverage "
                        "was insufficient."
                    )
                ]
            ),

            "runtime_seconds": (
                _runtime_seconds(
                    started_at
                )
            ),
        }

    # ---------------------------------------------------------
    # 5. RUN OCEAN-ONLY DARK-SLICK DETECTOR
    # ---------------------------------------------------------

    try:
        screening = (
            detect_dark_slick_candidates(
                patch,
                water_mask=water_mask,
            )
        )

    except SlickDetectionError as exc:
        # This is usually a scientific insufficiency rather than an
        # infrastructure failure.
        return {
            "status": (
                "insufficient_analysis_data"
            ),

            "screening_performed": False,

            "location": _location_payload(
                resolved
            ),

            "analysis_target": (
                _analysis_target_payload(
                    analysis_target
                )
            ),

            "satellite_observation": (
                _scene_payload(
                    selected_scene
                )
            ),

            "scene_search": (
                _scene_search_payload(
                    scene_search
                )
            ),

            "analysis_patch": {
                "center": {
                    "latitude": analysis_latitude,
                    "longitude": analysis_longitude,
                },
                "bbox": patch_bbox,
                "width": width,
                "height": height,
                "half_size_degrees": (
                    half_size_degrees
                ),
            },

            "water_context": (
                _water_payload(
                    water
                )
            ),

            "screening": None,

            "summary": (
                "Sentinel-1 data were available, but the "
                "patch did not contain enough valid ocean SAR "
                "pixels for reliable candidate screening."
            ),

            "analysis_message": str(
                exc
            ),

            "data_notes": (
                _service_notes()
                + _safe_string_list(
                    analysis_target.get(
                        "data_notes"
                    )
                )
                + [
                    (
                        "No oil interpretation should be made "
                        "when the detector reports insufficient "
                        "analysis data."
                    )
                ]
            ),

            "runtime_seconds": (
                _runtime_seconds(
                    started_at
                )
            ),
        }

    except ValueError as exc:
        raise OilSpillServiceError(
            "Oil-slick screening received "
            "invalid analysis data."
        ) from exc

    # ---------------------------------------------------------
    # 6. INTERPRET SCREENING RESULT CONSERVATIVELY
    # ---------------------------------------------------------

    candidate_count = int(
        screening.get(
            "candidate_count",
            0,
        )
        or 0
    )

    analysis_context = screening.get(
        "analysis_context"
    )

    land_dominated = False

    if isinstance(
        analysis_context,
        dict,
    ):
        land_dominated = bool(
            analysis_context.get(
                "land_dominated",
                False,
            )
        )

    if candidate_count > 0:
        if land_dominated:
            status = (
                "candidates_found_limited_context"
            )

            summary = (
                f"{candidate_count} SAR dark-slick "
                "candidate region(s) were identified "
                "within mapped water pixels. The patch "
                "is land-dominated, so the result has "
                "limited coastal context. These are not "
                "confirmed oil spills."
            )

        else:
            status = "candidates_found"

            summary = (
                f"{candidate_count} SAR dark-slick "
                "candidate region(s) were identified "
                "within the analyzed mapped-water pixels. "
                "These are not confirmed oil spills."
            )

    else:
        if land_dominated:
            status = (
                "no_candidates_limited_context"
            )

            summary = (
                "No SAR dark-slick candidate region met "
                "the current screening heuristic in the "
                "mapped-water pixels. The patch is "
                "land-dominated, so this is a limited "
                "coastal observation and does not prove "
                "the absence of oil."
            )

        else:
            status = "no_candidates_found"

            summary = (
                "No SAR dark-slick candidate region met "
                "the current screening heuristic in this "
                "Sentinel-1 patch. This does not prove "
                "the absence of oil."
            )

    # ---------------------------------------------------------
    # 7. JSON-SAFE FINAL EVIDENCE RESULT
    # ---------------------------------------------------------

    return {
        "status": status,

        "screening_performed": True,

        "location": (
            _location_payload(
                resolved
            )
        ),

        "analysis_target": (
            _analysis_target_payload(
                analysis_target
            )
        ),

        "satellite_observation": (
            _scene_payload(
                selected_scene
            )
        ),

        "scene_search": (
            _scene_search_payload(
                scene_search
            )
        ),

        "analysis_patch": {
            "center": {
                "latitude": analysis_latitude,
                "longitude": analysis_longitude,
            },
            "bbox": patch_bbox,
            "width": width,
            "height": height,
            "half_size_degrees": (
                half_size_degrees
            ),
            "content_type": patch.get(
                "content_type"
            ),
            "downloaded_byte_size": patch.get(
                "byte_size"
            ),
            "bands": patch.get(
                "bands"
            ),
            "backscatter_coefficient": (
                patch.get(
                    "backscatter_coefficient"
                )
            ),
        },

        "water_context": (
            _water_payload(
                water
            )
        ),

        # detect_dark_slick_candidates is already JSON-safe.
        "screening": screening,

        "candidate_count": (
            candidate_count
        ),

        "candidate_locations": [
            {
                "candidate_id": (
                    candidate.get(
                        "candidate_id"
                    )
                ),
                "centroid": (
                    candidate.get(
                        "centroid"
                    )
                ),
                "geographic_bounds": (
                    candidate.get(
                        "geographic_bounds"
                    )
                ),
                "pixel_count": (
                    candidate.get(
                        "pixel_count"
                    )
                ),
            }
            for candidate in screening.get(
                "candidates",
                [],
            )
            if isinstance(
                candidate,
                dict,
            )
        ],

        "summary": summary,

        "interpretation": {
            "evidence_type": (
                "sentinel_1_sar_dark_slick_candidate"
            ),

            "oil_confirmation": False,

            "confidence_score": None,

            "meaning": (
                "A candidate indicates a spatially coherent "
                "low-backscatter SAR anomaly that may warrant "
                "further investigation."
            ),

            "not_equivalent_to": [
                "confirmed oil spill",
                "confirmed petroleum leakage",
                "verified pollution event",
            ],
        },

        "provenance": [
            {
                "evidence_type": (
                    "analysis_targeting"
                ),
                "source": (
                    analysis_target.get(
                        "source"
                    )
                ),
                "shifted": bool(
                    analysis_target.get(
                        "shifted",
                        False,
                    )
                ),
                "shift_distance_km": (
                    analysis_target.get(
                        "shift_distance_km"
                    )
                ),
            },
            {
                "evidence_type": (
                    "satellite_scene_metadata"
                ),
                "source": (
                    "Copernicus Data Space "
                    "Sentinel-1 GRD STAC"
                ),
                "scene_id": (
                    selected_scene.get(
                        "id"
                    )
                ),
                "acquisition_time": (
                    acquisition_time
                ),
            },
            {
                "evidence_type": (
                    "sar_backscatter"
                ),
                "source": (
                    "Copernicus Sentinel Hub "
                    "Process API"
                ),
                "bands": [
                    "VV",
                    "VH",
                ],
                "backscatter_coefficient": (
                    patch.get(
                        "backscatter_coefficient"
                    )
                ),
            },
            {
                "evidence_type": (
                    "land_water_context"
                ),
                "source": (
                    water.get(
                        "source"
                    )
                ),
            },
        ],

        "data_notes": (
            _service_notes()
            + _safe_string_list(
                analysis_target.get(
                    "data_notes"
                )
            )
            + _safe_string_list(
                screening.get(
                    "data_notes"
                )
            )
        ),

        "runtime_seconds": (
            _runtime_seconds(
                started_at
            )
        ),
    }


# =============================================================
# SCENE SELECTION
# =============================================================


def _select_usable_scene(
    scenes: list[Any],
) -> dict[str, Any] | None:
    """Return newest usable dual-polarization IW scene."""

    for scene in scenes:
        if not isinstance(
            scene,
            dict,
        ):
            continue

        acquisition_time = (
            scene.get(
                "acquisition_time"
            )
        )

        if not isinstance(
            acquisition_time,
            str,
        ) or not acquisition_time.strip():
            continue

        mode = str(
            scene.get(
                "instrument_mode"
            )
            or ""
        ).upper()

        if mode and mode != "IW":
            continue

        polarizations = (
            scene.get(
                "polarizations"
            )
        )

        if not isinstance(
            polarizations,
            list,
        ):
            continue

        normalized_polarizations = {
            str(value).upper()
            for value in polarizations
        }

        if not {
            "VV",
            "VH",
        }.issubset(
            normalized_polarizations
        ):
            continue

        return scene

    return None


# =============================================================
# LOCATION
# =============================================================


def _resolve_query_location(
    location: str,
) -> dict[str, Any]:
    try:
        resolved = resolve_location(
            location
        )

    except LocationResolverError as exc:
        raise OilSpillServiceError(
            str(exc)
        ) from exc

    if not isinstance(
        resolved,
        dict,
    ):
        raise OilSpillServiceError(
            "Location resolver returned "
            "an invalid result."
        )

    return resolved


def _location_payload(
    resolved: dict[str, Any],
) -> dict[str, Any]:
    """Return only JSON-safe public location metadata."""

    location_type = resolved.get(
        "type"
    )

    payload = {
        "query": resolved.get(
            "query"
        ),
        "display_name": resolved.get(
            "display_name"
        ),
        "type": location_type,
        "latitude": resolved.get(
            "latitude"
        ),
        "longitude": resolved.get(
            "longitude"
        ),
        "bounding_box": resolved.get(
            "bounding_box"
        ),
        "source": resolved.get(
            "source"
        ),
        "inside_aquanexus_coverage": (
            resolved.get(
                "inside_aquanexus_coverage"
            )
        ),
    }

    if location_type == "area":
        payload["analysis_scope_note"] = (
            "This Oil Spill screening analyzes a small "
            "Sentinel-1 patch around a representative "
            "analysis target associated with the resolved "
            "region. It is not a complete scan of the "
            "entire named region."
        )

    return payload


def _analysis_target_payload(
    target: dict[str, Any],
) -> dict[str, Any]:
    """Return JSON-safe metadata describing the SAR analysis center."""

    return {
        "latitude": _optional_float(
            target.get(
                "latitude"
            )
        ),
        "longitude": _optional_float(
            target.get(
                "longitude"
            )
        ),
        "shifted_from_requested_location": bool(
            target.get(
                "shifted",
                False,
            )
        ),
        "shift_distance_km": _optional_float(
            target.get(
                "shift_distance_km"
            )
        ),
        "selection_status": target.get(
            "selection_status"
        ),
        "estimated_water_fraction": _optional_float(
            target.get(
                "estimated_water_fraction"
            )
        ),
        "minimum_water_fraction": _optional_float(
            target.get(
                "minimum_water_fraction"
            )
        ),
        "search_bbox": target.get(
            "search_bbox"
        ),
        "source": target.get(
            "source"
        ),
        "data_notes": _safe_string_list(
            target.get(
                "data_notes"
            )
        ),
    }


# =============================================================
# SCENE / WATER PAYLOADS
# =============================================================


def _scene_payload(
    scene: dict[str, Any],
) -> dict[str, Any]:
    acquisition_time = scene.get(
        "acquisition_time"
    )

    return {
        "scene_id": scene.get(
            "id"
        ),
        "acquisition_time": (
            acquisition_time
        ),
        "acquisition_age_hours": (
            _age_hours(
                acquisition_time
            )
        ),
        "platform": scene.get(
            "platform"
        ),
        "constellation": scene.get(
            "constellation"
        ),
        "instrument_mode": scene.get(
            "instrument_mode"
        ),
        "polarizations": scene.get(
            "polarizations"
        ),
        "product_type": scene.get(
            "product_type"
        ),
        "bbox": scene.get(
            "bbox"
        ),
    }


def _scene_search_payload(
    search: dict[str, Any],
) -> dict[str, Any]:
    return {
        "source": search.get(
            "source"
        ),
        "query": search.get(
            "query"
        ),
        "scene_count": search.get(
            "scene_count"
        ),
    }


def _water_payload(
    water: dict[str, Any],
) -> dict[str, Any]:
    """Remove the NumPy water_mask from the public response."""

    return {
        "water_pixel_count": (
            _optional_int(
                water.get(
                    "water_pixel_count"
                )
            )
        ),
        "total_pixels": (
            _optional_int(
                water.get(
                    "total_pixels"
                )
            )
        ),
        "water_fraction": (
            _optional_float(
                water.get(
                    "water_fraction"
                )
            )
        ),
        "source": water.get(
            "source"
        ),
        "data_notes": (
            _safe_string_list(
                water.get(
                    "data_notes"
                )
            )
        ),
    }


# =============================================================
# NO-SCENE RESULT
# =============================================================


def _no_scene_result(
    *,
    location: dict[str, Any],
    analysis_target: dict[str, Any],
    scene_search: dict[str, Any],
    scene_days: int,
    started_at: datetime,
) -> dict[str, Any]:
    return {
        "status": "no_recent_usable_scene",

        "screening_performed": False,

        "location": (
            _location_payload(
                location
            )
        ),

        "analysis_target": (
            _analysis_target_payload(
                analysis_target
            )
        ),

        "satellite_observation": None,

        "scene_search": (
            _scene_search_payload(
                scene_search
            )
        ),

        "analysis_patch": None,

        "water_context": None,

        "screening": None,

        "candidate_count": None,

        "candidate_locations": [],

        "summary": (
            "No compatible Sentinel-1 IW VV/VH scene "
            f"was found for this location within the "
            f"recent {scene_days}-day search window. "
            "No slick screening was performed."
        ),

        "interpretation": {
            "oil_confirmation": False,
            "confidence_score": None,
            "meaning": (
                "Absence of a recent usable satellite "
                "scene is not evidence that an oil spill "
                "is absent."
            ),
        },

        "data_notes": (
            _service_notes()
            + _safe_string_list(
                analysis_target.get(
                    "data_notes"
                )
            )
            + [
                (
                    "Satellite-scene availability and "
                    "oil-spill evidence are separate concepts."
                )
            ]
        ),

        "runtime_seconds": (
            _runtime_seconds(
                started_at
            )
        ),
    }


# =============================================================
# GENERIC HELPERS
# =============================================================


def _required_float(
    value: Any,
    name: str,
) -> float:
    try:
        parsed = float(
            value
        )

    except (
        TypeError,
        ValueError,
    ) as exc:
        raise OilSpillServiceError(
            f"{name} is missing or invalid."
        ) from exc

    return parsed


def _optional_float(
    value: Any,
) -> float | None:
    if value is None:
        return None

    try:
        return float(
            value
        )

    except (
        TypeError,
        ValueError,
    ):
        return None


def _optional_int(
    value: Any,
) -> int | None:
    if value is None:
        return None

    try:
        return int(
            value
        )

    except (
        TypeError,
        ValueError,
    ):
        return None


def _safe_string_list(
    value: Any,
) -> list[str]:
    if not isinstance(
        value,
        list,
    ):
        return []

    return [
        str(item)
        for item in value
        if str(item).strip()
    ]


def _age_hours(
    timestamp: Any,
) -> float | None:
    if not isinstance(
        timestamp,
        str,
    ):
        return None

    text = timestamp.strip()

    if not text:
        return None

    try:
        parsed = datetime.fromisoformat(
            text.replace(
                "Z",
                "+00:00",
            )
        )

    except ValueError:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(
            tzinfo=UTC
        )

    delta = (
        datetime.now(UTC)
        - parsed.astimezone(UTC)
    )

    return round(
        delta.total_seconds()
        / 3600.0,
        3,
    )


def _runtime_seconds(
    started_at: datetime,
) -> float:
    return round(
        (
            datetime.now(UTC)
            - started_at
        ).total_seconds(),
        3,
    )


def _service_notes() -> list[str]:
    return [
        (
            "Sentinel-1 SAR is satellite remote sensing "
            "and is separate from ARGO in-situ observations."
        ),
        (
            "A SAR dark-slick candidate is a low-backscatter "
            "anomaly and is not confirmation of petroleum."
        ),
        (
            "Calm water, natural surfactants, biological "
            "films, rain effects, current boundaries and "
            "other conditions can create similar SAR signatures."
        ),
        (
            "VV is the primary screening signal; VH is "
            "supporting evidence when usable."
        ),
        (
            "The water mask restricts screening to mapped "
            "water pixels but may not represent recent "
            "shoreline or reclamation changes."
        ),
        (
            "No arbitrary oil-spill confidence percentage "
            "is generated."
        ),
    ]