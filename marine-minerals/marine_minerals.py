"""
AquaNexus - Marine Minerals Module
Owner: Nethra (feature/marine-minerals)

Public interface for the AI Agent:
    get_mineral_insights(lat, lon, radius_km=50) -> dict

Data sources:
  1. ccz_real_stations.json  - real measured seafloor samples (CCZ only)
     Source: Schoening & Gazis (2019), GEOMAR/PANGAEA, CC-BY-NC-4.0
     DOI: https://doi.org/10.1594/PANGAEA.904967
  2. mineral_deposits.json   - broader region estimates (worldwide, approximate)
"""

import json
import math
from pathlib import Path

DATA_DIR = Path(__file__).parent

with open(DATA_DIR / "ccz_real_stations.json") as f:
    _STATION_DATA = json.load(f)

with open(DATA_DIR / "mineral_deposits.json") as f:
    _REGION_DATA = json.load(f)


def _haversine_km(lat1, lon1, lat2, lon2):
    """Great-circle distance between two lat/lon points, in km."""
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def _nearby_stations(lat, lon, radius_km):
    """Return real PANGAEA stations within radius_km, sorted nearest-first."""
    matches = []
    for s in _STATION_DATA["stations"]:
        d = _haversine_km(lat, lon, s["latitude"], s["longitude"])
        if d <= radius_km:
            matches.append({**s, "distance_km": round(d, 1)})
    return sorted(matches, key=lambda s: s["distance_km"])


def _matching_regions(lat, lon):
    """Return broad region entries whose bounding box contains (lat, lon)."""
    matches = []
    for r in _REGION_DATA:
        bb = r["bounding_box"]
        if bb["lat_min"] <= lat <= bb["lat_max"] and bb["lon_min"] <= lon <= bb["lon_max"]:
            matches.append(r)
    return matches


def _summarize_stations(stations):
    avg_coverage = sum(s["seafloor_coverage_pct"] for s in stations) / len(stations)
    avg_total = sum(s["nodules_total_count"] for s in stations) / len(stations)
    avg_abundance_kg_m2 = (sum(s["total_nodule_mass_kg"] for s in stations) / len(stations)) * 4.0
    nearest = stations[0]
    return (
        f"Verified seafloor data: {len(stations)} nearby sample station(s) from real "
        f"research cruises (SO268/1-2, GEOMAR/PANGAEA) show polymetallic nodules with "
        f"average seafloor coverage of {avg_coverage:.0f}%, roughly {avg_total:.0f} "
        f"nodules per sample, and mean abundance of {avg_abundance_kg_m2:.1f} kg/m2. "
        f"Nearest station is {nearest['distance_km']} km away."
    )


def _summarize_regions(regions):
    parts = []
    for r in regions:
        metals = ", ".join(r["primary_metals"])
        parts.append(
            f"This location falls within the {r['region_name']}, associated with "
            f"{r['mineral_type'].replace('_', ' ')} (estimated density: {r['estimated_density']}). "
            f"Key metals of interest: {metals}. (Estimated region, not a direct measurement.)"
        )
    return " ".join(parts)


def get_mineral_insights(lat, lon, radius_km=50):
    """
    Main entry point for the AI Agent.

    Args:
        lat, lon: query coordinates
        radius_km: search radius for real station matches (default 50km)

    Returns:
        {
          "query": {...},
          "source": "verified_station" | "estimated_region" | "no_data",
          "deposits": [...],
          "summary": str
        }
    """
    stations = _nearby_stations(lat, lon, radius_km)
    if stations:
        return {
            "query": {"lat": lat, "lon": lon, "radius_km": radius_km},
            "source": "verified_station",
            "deposits": stations,
            "summary": _summarize_stations(stations),
        }

    regions = _matching_regions(lat, lon)
    if regions:
        return {
            "query": {"lat": lat, "lon": lon, "radius_km": radius_km},
            "source": "estimated_region",
            "deposits": regions,
            "summary": _summarize_regions(regions),
        }

    return {
        "query": {"lat": lat, "lon": lon, "radius_km": radius_km},
        "source": "no_data",
        "deposits": [],
        "summary": "No known mineral deposit data available for this location.",
    }


if __name__ == "__main__":
    # Quick sanity tests
    test_points = [
        ("Near real CCZ station cluster", 11.93, -117.02),
        ("Inside CCZ region but no real station nearby", 5.0, -140.0),
        ("Central Indian Ocean Basin", -13.0, 76.0),
        ("Middle of nowhere (Arctic)", 80.0, 0.0),
    ]
    for label, lat, lon in test_points:
        print(f"\n--- {label} ({lat}, {lon}) ---")
        result = get_mineral_insights(lat, lon)
        print("source:", result["source"])
        print("summary:", result["summary"])
