import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

LAYER_URL = (
    "https://services.arcgis.com/6DIQcwlPy8knb6sg/arcgis/rest/services/"
    "SubmarineCables/FeatureServer/2/query"
)


def build_query_url() -> str:
    params = {
        "where": "1=1",
        "outFields": "*",
        "f": "geojson",
    }
    return f"{LAYER_URL}?{urlencode(params)}"


def download_cable_geojson() -> dict:
    request_url = build_query_url()
    request = Request(
        request_url,
        headers={
            "User-Agent": "AquaNexus Cable Downloader",
            "Accept": "application/json",
        },
    )

    try:
        with urlopen(request, timeout=30) as response:
            payload = response.read()
            return json.loads(payload.decode("utf-8"))
    except HTTPError as exc:
        raise RuntimeError(
            f"HTTP error {exc.code} while downloading cable data from {request_url}: {exc.reason}"
        ) from exc
    except URLError as exc:
        raise RuntimeError(
            f"Network error while downloading cable data from {request_url}: {exc.reason}"
        ) from exc


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    data_dir = project_root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    output_path = data_dir / "cables.geojson"

    geojson = download_cable_geojson()

    if not isinstance(geojson, dict):
        raise ValueError("Unexpected response format from ArcGIS service: expected a GeoJSON object.")

    features = geojson.get("features", [])
    if not isinstance(features, list):
        raise ValueError("GeoJSON response is missing a valid 'features' array.")

    with output_path.open("w", encoding="utf-8") as file_handle:
        json.dump(geojson, file_handle, ensure_ascii=False)

    print(f"Downloaded {len(features)} cable features to {output_path}")


if __name__ == "__main__":
    main()
