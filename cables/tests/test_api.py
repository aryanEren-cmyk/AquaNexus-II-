from fastapi.testclient import TestClient

from app.api import app


client = TestClient(app)


def test_post_nearby_valid_location_returns_results():
    response = client.post(
        "/cables/nearby",
        json={"latitude": 19.0760, "longitude": 72.8777, "radius_km": 500},
    )
    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload["results"], list)
    assert len(payload["results"]) > 0


def test_post_nearby_invalid_latitude_rejected():
    response = client.post(
        "/cables/nearby",
        json={"latitude": 91, "longitude": 72.8777, "radius_km": 500},
    )
    assert response.status_code in {400, 422}


def test_post_nearby_invalid_longitude_rejected():
    response = client.post(
        "/cables/nearby",
        json={"latitude": 19.0760, "longitude": 181, "radius_km": 500},
    )
    assert response.status_code in {400, 422}


def test_post_nearby_invalid_radius_rejected():
    response = client.post(
        "/cables/nearby",
        json={"latitude": 19.0760, "longitude": 72.8777, "radius_km": 0},
    )
    assert response.status_code in {400, 422}


def test_get_cable_by_id_returns_ok():
    response = client.get("/cables/1035")
    assert response.status_code == 200
    payload = response.json()
    assert payload["cable_id"] == 1035


def test_get_cable_by_id_missing_returns_404():
    response = client.get("/cables/999999")
    assert response.status_code == 404


def test_search_cables_returns_results():
    response = client.get("/cables/search?q=SeaMeWe")
    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload["results"], list)
    assert len(payload["results"]) > 1


def test_get_cable_geojson_returns_feature():
    response = client.get("/cables/1035/geojson")
    assert response.status_code == 200
    payload = response.json()
    assert payload["type"] == "Feature"
    assert payload["properties"]["cable_id"] == 1035
    assert "geometry" in payload
