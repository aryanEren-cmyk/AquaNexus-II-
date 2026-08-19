from __future__ import annotations

from pathlib import Path

import geopandas as gpd
from shapely.geometry import Point


DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "cables.geojson"


def _validate_inputs(latitude: float, longitude: float, radius_km: float) -> None:
    if not -90 <= latitude <= 90:
        raise ValueError("latitude must be between -90 and 90")
    if not -180 <= longitude <= 180:
        raise ValueError("longitude must be between -180 and 180")
    if radius_km <= 0:
        raise ValueError("radius_km must be greater than 0")


def _get_local_utm_epsg(latitude: float, longitude: float) -> int:
    utm_zone = int((longitude + 180) // 6) + 1
    if latitude >= 0:
        return 32600 + utm_zone
    return 32700 + utm_zone


def find_nearby_cables(latitude: float, longitude: float, radius_km: float):
    """Return submarine cables within a given radius of a location.

    The input point is treated as WGS84 (EPSG:4326). To calculate a metric distance,
    the cable geometries and the query point are projected into a local UTM CRS for the
    search location, where distances are measured in meters and then converted to km.
    """
    _validate_inputs(latitude, longitude, radius_km)

    gdf = gpd.read_file(DATA_PATH)
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")
    if gdf.empty:
        return []

    filtered = gdf[gdf.geometry.notnull()].copy()
    filtered = filtered[filtered.geometry.geom_type.isin({"LineString", "MultiLineString"})].copy()

    if filtered.empty:
        return []

    utm_epsg = _get_local_utm_epsg(latitude, longitude)
    local_gdf = filtered.to_crs(epsg=utm_epsg)
    search_point = Point(longitude, latitude)
    search_point_utm = gpd.GeoSeries([search_point], crs="EPSG:4326").to_crs(epsg=utm_epsg).iloc[0]

    local_gdf["distance_m"] = local_gdf.geometry.distance(search_point_utm)
    nearby = local_gdf[local_gdf["distance_m"] <= radius_km * 1000].copy()

    if nearby.empty:
        return []

    nearby = nearby.sort_values("distance_m").copy()
    nearby["distance_km"] = (nearby["distance_m"] / 1000).round(2)

    results = []
    for _, row in nearby.iterrows():
        results.append(
            {
                "cable_id": row.get("cable_id"),
                "name": row.get("Name"),
                "distance_km": round(float(row["distance_km"]), 2),
                "length": row.get("length"),
                "rfs": row.get("rfs"),
                "owners": row.get("owners"),
                "year": row.get("year"),
            }
        )

    return results
