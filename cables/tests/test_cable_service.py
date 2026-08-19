import pytest

from app.cable_service import (
    get_cable,
    get_cable_geojson,
    search_cables,
    search_cables_geojson,
)


def test_get_cable_returns_known_cable():
    cable = get_cable(1007)
    assert cable is not None
    assert cable["cable_id"] == 1007
    assert cable["name"] == "Pacific Crossing-1 (PC-1)"


def test_get_cable_returns_none_for_missing_id():
    assert get_cable(999999) is None


def test_search_cables_is_case_insensitive():
    results = search_cables("seamEwe")
    assert isinstance(results, list)
    assert len(results) > 0
    assert all("seamewe" in result["name"].lower() for result in results)


def test_search_cables_supports_partial_name_match():
    results = search_cables("Pacific")
    assert isinstance(results, list)
    assert len(results) > 0
    assert any(result["name"] == "Pacific Crossing-1 (PC-1)" for result in results)


def test_search_cables_returns_list():
    assert isinstance(search_cables("SeaMeWe"), list)


def test_search_cables_empty_for_no_match():
    assert search_cables("definitely-not-a-real-cable") == []


def test_get_cable_geojson_returns_feature_for_known_cable():
    feature = get_cable_geojson(1007)
    assert feature is not None
    assert feature["type"] == "Feature"
    assert "geometry" in feature
    assert feature["properties"]["Name"] == "Pacific Crossing-1 (PC-1)"
    assert feature["properties"]["cable_id"] == 1007


def test_get_cable_geojson_returns_none_for_missing_id():
    assert get_cable_geojson(999999) is None


def test_search_cables_geojson_returns_featurecollection():
    fc = search_cables_geojson("SeaMeWe")
    assert fc["type"] == "FeatureCollection"
    assert isinstance(fc["features"], list)
    assert len(fc["features"]) > 1
    assert all(feature["type"] == "Feature" for feature in fc["features"])


def test_search_cables_geojson_no_match_returns_empty_featurecollection():
    fc = search_cables_geojson("definitely-not-a-real-cable")
    assert fc["type"] == "FeatureCollection"
    assert fc["features"] == []
