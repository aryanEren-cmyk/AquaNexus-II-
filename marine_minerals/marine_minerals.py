"""Deterministic marine-mineral evidence tools for AquaNexus."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any


DATA_DIR = Path(__file__).resolve().parent

with open(DATA_DIR / "ccz_real_stations.json", encoding="utf-8") as file:
    _STATION_DATA = json.load(file)

with open(DATA_DIR / "real_cited_sites.json", encoding="utf-8") as file:
    _CITED_SITES_DATA = json.load(file)

with open(DATA_DIR / "mineral_deposits.json", encoding="utf-8") as file:
    _REGION_DATA = json.load(file)


DATA_NOTES = [
    (
        "Verified station samples are direct seafloor observations from the "
        "cited PANGAEA dataset."
    ),
    (
        "Individually cited mineral sites are literature-reported discoveries "
        "and are not AquaNexus measurements."
    ),
    (
        "Estimated mineral regions are approximate bounding-box context and "
        "do not prove that a mineral deposit exists at every coordinate inside them."
    ),
    (
        "Marine-mineral evidence is kept separate from ARGO observations and "
        "Copernicus ocean-model estimates."
    ),
]


def get_mineral_insights(
    latitude: float,
    longitude: float,
    radius_km: float = 50,
) -> dict[str, Any]:
    """
    Return marine-mineral evidence near one coordinate.

    Evidence priority:
    1. Direct PANGAEA seafloor sample stations.
    2. Individually cited literature sites.
    3. Approximate contextual mineral regions.
    """

    latitude = _validate_latitude(latitude)
    longitude = _validate_longitude(longitude)
    radius_km = _validate_radius(radius_km)

    stations = _nearby_stations(
        latitude,
        longitude,
        radius_km,
    )

    cited_sites = _nearby_cited_sites(
        latitude,
        longitude,
        radius_km,
    )

    estimated_regions = _matching_regions(
        latitude,
        longitude,
    )

    return _build_result(
        query={
            "type": "point",
            "latitude": latitude,
            "longitude": longitude,
            "radius_km": radius_km,
        },
        stations=stations,
        cited_sites=cited_sites,
        estimated_regions=estimated_regions,
    )


def get_mineral_insights_for_area(
    bounding_box: dict[str, float],
) -> dict[str, Any]:
    """
    Return marine-mineral evidence intersecting one geographic area.
    """

    south = _validate_latitude(
        bounding_box["south"]
    )

    north = _validate_latitude(
        bounding_box["north"]
    )

    west = _validate_longitude(
        bounding_box["west"]
    )

    east = _validate_longitude(
        bounding_box["east"]
    )

    if south > north:
        raise ValueError(
            "Area south latitude cannot exceed north latitude."
        )

    if west > east:
        raise ValueError(
            "Dateline-crossing mineral areas are not currently supported."
        )

    normalized_box = {
        "south": south,
        "north": north,
        "west": west,
        "east": east,
    }

    stations = [
        dict(station)
        for station in _STATION_DATA["stations"]
        if _point_in_box(
            station["latitude"],
            station["longitude"],
            normalized_box,
        )
    ]

    cited_sites = [
        dict(site)
        for site in _CITED_SITES_DATA["sites"]
        if _point_in_box(
            site["latitude"],
            site["longitude"],
            normalized_box,
        )
    ]

    estimated_regions = [
        dict(region)
        for region in _REGION_DATA
        if _region_overlaps_box(
            region["bounding_box"],
            normalized_box,
        )
    ]

    return _build_result(
        query={
            "type": "area",
            "bounding_box": normalized_box,
        },
        stations=stations,
        cited_sites=cited_sites,
        estimated_regions=estimated_regions,
    )


def _nearby_stations(
    latitude: float,
    longitude: float,
    radius_km: float,
) -> list[dict[str, Any]]:
    """Return PANGAEA stations within the requested radius."""

    matches = []

    for station in _STATION_DATA["stations"]:
        distance_km = _haversine_km(
            latitude,
            longitude,
            station["latitude"],
            station["longitude"],
        )

        if distance_km <= radius_km:
            matches.append(
                {
                    **station,
                    "distance_km": round(
                        distance_km,
                        3,
                    ),
                }
            )

    return sorted(
        matches,
        key=lambda item: item["distance_km"],
    )


def _nearby_cited_sites(
    latitude: float,
    longitude: float,
    radius_km: float,
) -> list[dict[str, Any]]:
    """Return individually cited mineral sites within radius."""

    matches = []

    for site in _CITED_SITES_DATA["sites"]:
        distance_km = _haversine_km(
            latitude,
            longitude,
            site["latitude"],
            site["longitude"],
        )

        if distance_km <= radius_km:
            matches.append(
                {
                    **site,
                    "distance_km": round(
                        distance_km,
                        3,
                    ),
                }
            )

    return sorted(
        matches,
        key=lambda item: item["distance_km"],
    )


def _matching_regions(
    latitude: float,
    longitude: float,
) -> list[dict[str, Any]]:
    """
    Return approximate mineral regions whose bounding box
    contains the requested coordinate.
    """

    matches = []

    for region in _REGION_DATA:
        box = region["bounding_box"]

        if (
            box["lat_min"]
            <= latitude
            <= box["lat_max"]
            and box["lon_min"]
            <= longitude
            <= box["lon_max"]
        ):
            matches.append(
                dict(region)
            )

    return matches


def _build_result(
    *,
    query: dict[str, Any],
    stations: list[dict[str, Any]],
    cited_sites: list[dict[str, Any]],
    estimated_regions: list[dict[str, Any]],
) -> dict[str, Any]:
    """Create the consistent AquaNexus mineral response."""

    has_verified_evidence = bool(
        stations or cited_sites
    )

    if stations:
        strongest_evidence = (
            "measured_seafloor_sample"
        )

    elif cited_sites:
        strongest_evidence = (
            "peer_reviewed_reported_site"
        )

    elif estimated_regions:
        strongest_evidence = (
            "approximate_region_context"
        )

    else:
        strongest_evidence = "none"

    return {
        "query": query,
        "has_verified_evidence": has_verified_evidence,
        "strongest_evidence": strongest_evidence,
        "station_samples": stations,
        "cited_sites": cited_sites,
        "estimated_regions": estimated_regions,
        "counts": {
            "station_samples": len(stations),
            "cited_sites": len(cited_sites),
            "estimated_regions": len(
                estimated_regions
            ),
        },
        "provenance": _build_provenance(
            stations,
            cited_sites,
        ),
        "summary": _build_summary(
            stations,
            cited_sites,
            estimated_regions,
        ),
        "data_notes": DATA_NOTES,
    }


def _build_provenance(
    stations: list[dict[str, Any]],
    cited_sites: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return structured citation/provenance metadata."""

    provenance = []

    if stations:
        provenance.append(
            {
                "evidence_type":
                    "measured_seafloor_samples",
                "source":
                    _STATION_DATA.get("source"),
                "doi":
                    _STATION_DATA.get("doi"),
                "license":
                    _STATION_DATA.get("license"),
                "region":
                    _STATION_DATA.get("region"),
            }
        )

    for site in cited_sites:
        provenance.append(
            {
                "evidence_type":
                    "literature_reported_site",
                "site_id":
                    site.get("id"),
                "site_name":
                    site.get("name"),
                "citation":
                    site.get("citation"),
                "source_url":
                    site.get("source_url"),
            }
        )

    return provenance


def _build_summary(
    stations: list[dict[str, Any]],
    cited_sites: list[dict[str, Any]],
    estimated_regions: list[dict[str, Any]],
) -> str:
    """Build an evidence-aware human-readable summary."""

    parts = []

    if stations:
        average_coverage = (
            sum(
                station[
                    "seafloor_coverage_pct"
                ]
                for station in stations
            )
            / len(stations)
        )

        average_mass = (
            sum(
                station[
                    "total_nodule_mass_kg"
                ]
                for station in stations
            )
            / len(stations)
        )

        # The PANGAEA samples were collected
        # with a 0.25 m² box corer.
        # Multiplying kg/sample by 4 produces kg/m².
        average_abundance = (
            average_mass * 4.0
        )

        parts.append(
            (
                f"{len(stations)} direct PANGAEA "
                f"seafloor sample station(s) were found. "
                f"Mean observed nodule seafloor coverage "
                f"across the returned samples is "
                f"{average_coverage:.1f}%, and mean "
                f"sample-derived abundance is "
                f"{average_abundance:.1f} kg/m²."
            )
        )

    if cited_sites:
        names = ", ".join(
            site["name"]
            for site in cited_sites
        )

        parts.append(
            (
                f"{len(cited_sites)} individually cited "
                f"mineral or hydrothermal site(s) were "
                f"found: {names}."
            )
        )

    if estimated_regions:
        names = ", ".join(
            region["region_name"]
            for region in estimated_regions
        )

        parts.append(
            (
                "The query also intersects approximate "
                "documented mineral region context: "
                f"{names}. These region matches are not "
                "direct measurements at the query "
                "coordinate."
            )
        )

    if not parts:
        return (
            "No marine-mineral evidence is stored for "
            "this query in the current AquaNexus "
            "mineral datasets."
        )

    return " ".join(parts)


def _point_in_box(
    latitude: float,
    longitude: float,
    box: dict[str, float],
) -> bool:
    """Check whether a coordinate lies inside a box."""

    return (
        box["south"]
        <= latitude
        <= box["north"]
        and box["west"]
        <= longitude
        <= box["east"]
    )


def _region_overlaps_box(
    region_box: dict[str, float],
    query_box: dict[str, float],
) -> bool:
    """Check whether two non-dateline bounding boxes overlap."""

    return not (
        region_box["lat_max"]
        < query_box["south"]
        or region_box["lat_min"]
        > query_box["north"]
        or region_box["lon_max"]
        < query_box["west"]
        or region_box["lon_min"]
        > query_box["east"]
    )


def _haversine_km(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> float:
    """Return great-circle distance in kilometers."""

    earth_radius_km = 6371.0088

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)

    delta_phi = math.radians(
        lat2 - lat1
    )

    delta_lambda = math.radians(
        lon2 - lon1
    )

    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1)
        * math.cos(phi2)
        * math.sin(delta_lambda / 2) ** 2
    )

    return (
        2
        * earth_radius_km
        * math.asin(
            math.sqrt(a)
        )
    )


def _validate_latitude(
    value: Any,
) -> float:
    """Validate latitude."""

    try:
        latitude = float(value)

    except (
        TypeError,
        ValueError,
    ) as exc:
        raise ValueError(
            "latitude must be numeric."
        ) from exc

    if not -90 <= latitude <= 90:
        raise ValueError(
            "latitude must be between "
            "-90 and 90 degrees."
        )

    return latitude


def _validate_longitude(
    value: Any,
) -> float:
    """Validate longitude."""

    try:
        longitude = float(value)

    except (
        TypeError,
        ValueError,
    ) as exc:
        raise ValueError(
            "longitude must be numeric."
        ) from exc

    if not -180 <= longitude <= 180:
        raise ValueError(
            "longitude must be between "
            "-180 and 180 degrees."
        )

    return longitude


def _validate_radius(
    value: Any,
) -> float:
    """Validate radius in kilometers."""

    try:
        radius = float(value)

    except (
        TypeError,
        ValueError,
    ) as exc:
        raise ValueError(
            "radius_km must be numeric."
        ) from exc

    if radius <= 0:
        raise ValueError(
            "radius_km must be greater than 0."
        )

    return radius