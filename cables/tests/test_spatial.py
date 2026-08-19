import json
from pathlib import Path

import pytest

from app.spatial import find_nearby_cables


def _sample_real_cable_point():
    data_path = Path(__file__).resolve().parents[1] / "data" / "cables.geojson"
    with data_path.open("r", encoding="utf-8") as file_handle:
        data = json.load(file_handle)

    feature = data["features"][0]
    geometry = feature["geometry"]
    if geometry["type"] == "LineString":
        lon, lat = geometry["coordinates"][0]
    else:
        lon, lat = geometry["coordinates"][0][0]
    return lat, lon


@pytest.mark.parametrize("latitude", [-91, 91])
def test_invalid_latitude_rejected(latitude):
    with pytest.raises(ValueError, match="latitude"):
        find_nearby_cables(latitude, 0.0, 50.0)


@pytest.mark.parametrize("longitude", [-181, 181])
def test_invalid_longitude_rejected(longitude):
    with pytest.raises(ValueError, match="longitude"):
        find_nearby_cables(0.0, longitude, 50.0)


@pytest.mark.parametrize("radius", [0, -1])
def test_non_positive_radius_rejected(radius):
    with pytest.raises(ValueError, match="radius_km"):
        find_nearby_cables(0.0, 0.0, radius)


def test_valid_nearby_cable_query_returns_list():
    latitude, longitude = _sample_real_cable_point()
    results = find_nearby_cables(latitude, longitude, 50.0)
    assert isinstance(results, list)
    assert len(results) > 0


def test_results_are_sorted_by_distance():
    latitude, longitude = _sample_real_cable_point()
    results = find_nearby_cables(latitude, longitude, 50.0)
    distances = [item["distance_km"] for item in results]
    assert distances == sorted(distances)
