"""Location-aware Marine Minerals service."""

from __future__ import annotations

from typing import Any

from location.resolver import resolve_location
from marine_minerals.marine_minerals import (
    get_mineral_insights,
    get_mineral_insights_for_area,
)


def get_mineral_insights_for_location(
    location: str,
    radius_km: float = 50,
) -> dict[str, Any]:
    """Resolve a location and return deterministic marine-mineral evidence."""

    resolved = resolve_location(location)

    if resolved["type"] == "point":
        result = get_mineral_insights(
            resolved["latitude"],
            resolved["longitude"],
            radius_km=radius_km,
        )

    elif resolved["type"] == "area":
        result = get_mineral_insights_for_area(
            resolved["bounding_box"]
        )

    else:
        raise ValueError(
            f"Unsupported resolved location type: {resolved['type']!r}"
        )

    return {
        "location": resolved,
        **result,
    }