"""Evidence-backed operational advisories for AquaNexus ocean queries.

This module intentionally does NOT generate hazard warnings from arbitrary
temperature/current thresholds. It only reports data-availability and
observation-coverage conditions that are directly supported by deterministic
AquaNexus evidence.

Future scientific modules (oil spill, cables, minerals) can append their own
domain-specific alerts through this same contract once their deterministic
detectors are integrated.
"""

from __future__ import annotations

from typing import Any

from ocean.conditions import get_ocean_conditions


SEVERITY_ORDER = {
    "info": 0,
    "advisory": 1,
    "warning": 2,
}


def scan_ocean_alerts(
    location: str,
    *,
    depth_m: float = 0,
    argo_radius_km: float = 300,
) -> dict[str, Any]:
    """Return deterministic, evidence-backed operational advisories.

    Current alert scope:
    - Copernicus present-state data availability.
    - Recent/live ARGO observation coverage.
    - Historical ARGO context availability for point queries.

    This function does not infer storms, oil spills, tsunamis, ecological
    hazards, or other environmental danger from arbitrary thresholds.
    """
    conditions = get_ocean_conditions(
        location,
        depth_m=depth_m,
        argo_radius_km=argo_radius_km,
    )

    alerts: list[dict[str, Any]] = []

    resolved_location = conditions.get("location") or {}
    location_type = resolved_location.get("type")

    present_state = conditions.get("present_state")
    latest_argo = conditions.get("latest_argo")
    historical_context = conditions.get("historical_context")

    _append_present_state_alert(
        alerts,
        present_state,
    )

    _append_live_argo_alert(
        alerts,
        latest_argo,
        location_type=location_type,
        argo_radius_km=argo_radius_km,
    )

    if location_type == "point":
        _append_historical_context_alert(
            alerts,
            historical_context,
        )

    severity_counts = {
        "warning": sum(
            alert["severity"] == "warning"
            for alert in alerts
        ),
        "advisory": sum(
            alert["severity"] == "advisory"
            for alert in alerts
        ),
        "info": sum(
            alert["severity"] == "info"
            for alert in alerts
        ),
    }

    return {
        "status": _overall_status(alerts),
        "alert_count": len(alerts),
        "severity_counts": severity_counts,
        "location": resolved_location,
        "requested_depth_m": conditions.get("requested_depth_m"),
        "argo_radius_km": float(argo_radius_km),
        "alerts": alerts,
        "evidence_summary": {
            "copernicus_present_state_available": _source_available(
                present_state
            ),
            "live_argo_available": _source_available(
                latest_argo
            ),
            "historical_context_available": (
                _source_available(historical_context)
                if location_type == "point"
                else None
            ),
            "data_notes": conditions.get("data_notes") or [],
            "source_runtime_seconds": conditions.get("runtime_seconds"),
        },
        "terminology": {
            "copernicus": "gridded analysis/forecast estimate",
            "argo": "in-situ observation",
            "argo_vertical_coordinate": "pressure in dbar",
        },
    }


def _append_present_state_alert(
    alerts: list[dict[str, Any]],
    present_state: Any,
) -> None:
    if present_state is None:
        alerts.append(
            _alert(
                code="COPERNICUS_PRESENT_STATE_MISSING",
                severity="warning",
                category="data_availability",
                source="COPERNICUS_MARINE",
                title="Copernicus present-state data unavailable",
                message=(
                    "No Copernicus present-state result was returned for "
                    "the resolved query."
                ),
                evidence={
                    "available": False,
                },
            )
        )
        return

    if (
        isinstance(present_state, dict)
        and present_state.get("available") is False
    ):
        alerts.append(
            _alert(
                code="COPERNICUS_PRESENT_STATE_UNAVAILABLE",
                severity="warning",
                category="data_availability",
                source="COPERNICUS_MARINE",
                title="Copernicus present-state data unavailable",
                message=(
                    "The deterministic Copernicus present-state lookup "
                    "could not produce a valid result."
                ),
                evidence={
                    "available": False,
                    "reason": present_state.get("reason"),
                },
            )
        )


def _append_live_argo_alert(
    alerts: list[dict[str, Any]],
    latest_argo: Any,
    *,
    location_type: str | None,
    argo_radius_km: float,
) -> None:
    if latest_argo is None:
        alerts.append(
            _alert(
                code="LIVE_ARGO_CONTEXT_MISSING",
                severity="warning",
                category="data_availability",
                source="ARGO",
                title="Live ARGO context unavailable",
                message=(
                    "No live ARGO context was returned for the resolved query."
                ),
                evidence={
                    "available": False,
                },
            )
        )
        return

    if not isinstance(latest_argo, dict):
        alerts.append(
            _alert(
                code="LIVE_ARGO_CONTEXT_INVALID",
                severity="warning",
                category="data_availability",
                source="ARGO",
                title="Live ARGO context unavailable",
                message=(
                    "The live ARGO result could not be interpreted."
                ),
                evidence={
                    "available": False,
                },
            )
        )
        return

    if latest_argo.get("available") is not False:
        return

    reason = latest_argo.get("reason")

    if location_type == "point":
        nearest_distance_km = _number_or_none(
            latest_argo.get("nearest_distance_km")
        )

        if nearest_distance_km is not None:
            alerts.append(
                _alert(
                    code="NO_RECENT_ARGO_WITHIN_RADIUS",
                    severity="advisory",
                    category="observation_coverage",
                    source="ARGO",
                    title="No recent ARGO observation within search radius",
                    message=(
                        "The nearest cached live ARGO profile lies outside "
                        "the requested observation radius. Copernicus model "
                        "estimates may still be available, but no qualifying "
                        "nearby live in-situ ARGO observation supports this point."
                    ),
                    evidence={
                        "requested_radius_km": float(argo_radius_km),
                        "nearest_distance_km": nearest_distance_km,
                        "reason": reason,
                    },
                )
            )
            return

        alerts.append(
            _alert(
                code="LIVE_ARGO_UNAVAILABLE",
                severity="warning",
                category="data_availability",
                source="ARGO",
                title="Live ARGO data unavailable",
                message=(
                    "A nearby live ARGO observation could not be evaluated "
                    "for the requested point."
                ),
                evidence={
                    "requested_radius_km": float(argo_radius_km),
                    "reason": reason,
                },
            )
        )
        return

    if location_type == "area":
        profile_count = _integer_or_none(
            latest_argo.get("profile_count")
        )

        if profile_count == 0:
            alerts.append(
                _alert(
                    code="NO_LIVE_ARGO_IN_AREA",
                    severity="advisory",
                    category="observation_coverage",
                    source="ARGO",
                    title="No live ARGO profiles inside resolved area",
                    message=(
                        "The resolved area contains no cached live ARGO "
                        "profiles. Regional Copernicus model statistics may "
                        "still be available."
                    ),
                    evidence={
                        "profile_count": 0,
                        "unique_floats": _integer_or_none(
                            latest_argo.get("unique_floats")
                        ),
                        "reason": reason,
                    },
                )
            )
            return

        alerts.append(
            _alert(
                code="LIVE_ARGO_AREA_UNAVAILABLE",
                severity="warning",
                category="data_availability",
                source="ARGO",
                title="Live ARGO area context unavailable",
                message=(
                    "Live ARGO coverage could not be evaluated for the "
                    "resolved area."
                ),
                evidence={
                    "reason": reason,
                },
            )
        )


def _append_historical_context_alert(
    alerts: list[dict[str, Any]],
    historical_context: Any,
) -> None:
    if historical_context is None:
        alerts.append(
            _alert(
                code="HISTORICAL_ARGO_CONTEXT_MISSING",
                severity="info",
                category="historical_context",
                source="ARGO",
                title="Historical ARGO context unavailable",
                message=(
                    "No historical ARGO comparison context was returned "
                    "for this point."
                ),
                evidence={
                    "available": False,
                },
            )
        )
        return

    if (
        isinstance(historical_context, dict)
        and historical_context.get("available") is False
    ):
        alerts.append(
            _alert(
                code="HISTORICAL_ARGO_CONTEXT_UNAVAILABLE",
                severity="info",
                category="historical_context",
                source="ARGO",
                title="Historical ARGO context unavailable",
                message=(
                    "Historical ARGO comparison context could not be "
                    "retrieved for this point."
                ),
                evidence={
                    "available": False,
                    "reason": historical_context.get("reason"),
                },
            )
        )


def _alert(
    *,
    code: str,
    severity: str,
    category: str,
    source: str,
    title: str,
    message: str,
    evidence: dict[str, Any],
) -> dict[str, Any]:
    if severity not in SEVERITY_ORDER:
        raise ValueError(
            f"Unsupported alert severity: {severity}"
        )

    return {
        "code": code,
        "severity": severity,
        "category": category,
        "source": source,
        "title": title,
        "message": message,
        "evidence": _clean_mapping(evidence),
        "scope": "operational_scientific_advisory",
        "is_hazard_warning": False,
    }


def _overall_status(
    alerts: list[dict[str, Any]],
) -> str:
    if not alerts:
        return "normal"

    highest = max(
        alerts,
        key=lambda alert: SEVERITY_ORDER[
            alert["severity"]
        ],
    )["severity"]

    return {
        "warning": "attention",
        "advisory": "advisory",
        "info": "information",
    }[highest]


def _source_available(
    value: Any,
) -> bool:
    if value is None:
        return False

    if isinstance(value, dict):
        return value.get("available") is not False

    return True


def _clean_mapping(
    value: dict[str, Any],
) -> dict[str, Any]:
    return {
        key: item
        for key, item in value.items()
        if item is not None
    }


def _number_or_none(
    value: Any,
) -> float | None:
    if isinstance(value, bool):
        return None

    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None

    return parsed


def _integer_or_none(
    value: Any,
) -> int | None:
    if isinstance(value, bool):
        return None

    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None

    return parsed