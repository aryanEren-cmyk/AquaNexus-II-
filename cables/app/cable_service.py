import json
from pathlib import Path


DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "cables.geojson"


def _load_cables():
    with DATA_PATH.open("r", encoding="utf-8") as file_handle:
        data = json.load(file_handle)
    return data.get("features", [])


def _serialize_cable(feature):
    properties = feature.get("properties", {})
    return {
        "cable_id": properties.get("cable_id"),
        "name": properties.get("Name"),
        "length": properties.get("length"),
        "rfs": properties.get("rfs"),
        "owners": properties.get("owners"),
        "year": properties.get("year"),
        "url": properties.get("url"),
    }


def get_cable(cable_id):
    """Return a single cable dictionary for the matching cable_id, or None."""
    target = cable_id
    if isinstance(target, str):
        try:
            target = int(target)
        except ValueError:
            return None

    for feature in _load_cables():
        properties = feature.get("properties", {})
        if properties.get("cable_id") == target:
            return _serialize_cable(feature)
    return None


def search_cables(query):
    """Return all cable dictionaries whose names contain the query string, case-insensitive."""
    if query is None:
        return []

    search_term = str(query).strip().lower()
    if not search_term:
        return []

    matches = []
    for feature in _load_cables():
        properties = feature.get("properties", {})
        name = properties.get("Name")
        if isinstance(name, str) and search_term in name.lower():
            matches.append(_serialize_cable(feature))
    return matches


def get_cable_geojson(cable_id):
    """Return the matching cable as a GeoJSON Feature, or None."""
    target = cable_id
    if isinstance(target, str):
        try:
            target = int(target)
        except ValueError:
            return None

    for feature in _load_cables():
        properties = feature.get("properties", {})
        if properties.get("cable_id") == target:
            return feature
    return None


def search_cables_geojson(query):
    """Return a GeoJSON FeatureCollection containing all matching cable features."""
    if query is None:
        return {"type": "FeatureCollection", "features": []}

    search_term = str(query).strip().lower()
    if not search_term:
        return {"type": "FeatureCollection", "features": []}

    matches = []
    for feature in _load_cables():
        properties = feature.get("properties", {})
        name = properties.get("Name")
        if isinstance(name, str) and search_term in name.lower():
            matches.append(feature)

    return {"type": "FeatureCollection", "features": matches}
