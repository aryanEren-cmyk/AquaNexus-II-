import json
from pathlib import Path


DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "cables.geojson"


def load_geojson(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as file_handle:
        return json.load(file_handle)


def collect_geometry_types(features: list[dict]) -> list[str]:
    geometry_types = set()
    for feature in features:
        geometry = feature.get("geometry")
        if isinstance(geometry, dict) and geometry.get("type"):
            geometry_types.add(geometry["type"])
    return sorted(geometry_types)


def collect_property_fields(features: list[dict]) -> list[str]:
    fields = []
    seen = set()
    for feature in features:
        properties = feature.get("properties")
        if not isinstance(properties, dict):
            continue
        for key in properties.keys():
            if key not in seen:
                seen.add(key)
                fields.append(key)
    return fields


def representative_example_value(features: list[dict], field_name: str):
    for feature in features:
        properties = feature.get("properties")
        if not isinstance(properties, dict):
            continue
        value = properties.get(field_name)
        if value is not None:
            return value
    return "N/A"


def main() -> None:
    data = load_geojson(DATA_PATH)
    geojson_type = data.get("type")
    features = data.get("features", [])
    if not isinstance(features, list):
        raise ValueError("GeoJSON file does not contain a valid 'features' array.")

    print(f"GeoJSON top-level type: {geojson_type}")
    print(f"Feature count: {len(features)}")

    geometry_types = collect_geometry_types(features)
    print("Geometry types present: " + (", ".join(geometry_types) if geometry_types else "None"))

    property_fields = collect_property_fields(features)
    print(f"Property/attribute fields ({len(property_fields)}):")
    for field_name in property_fields:
        example_value = representative_example_value(features, field_name)
        if isinstance(example_value, (dict, list)):
            example_value = json.dumps(example_value, ensure_ascii=False)
        print(f"  - {field_name}: {example_value}")


if __name__ == "__main__":
    main()
