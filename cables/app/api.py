from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from app.cable_service import get_cable, get_cable_geojson, search_cables
from app.spatial import find_nearby_cables


app = FastAPI(title="AquaNexus Cable API", version="0.1.0")


class NearbyRequest(BaseModel):
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    radius_km: float = Field(..., gt=0)


@app.post("/cables/nearby")
def nearby_cables(payload: NearbyRequest):
    try:
        results = find_nearby_cables(payload.latitude, payload.longitude, payload.radius_km)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return {"results": results}


@app.get("/cables/search")
def search_cables_endpoint(q: str = Query(default="", min_length=0)):
    results = search_cables(q)
    return {"results": results}


@app.get("/cables/{cable_id}")
def get_cable_by_id(cable_id: int):
    cable = get_cable(cable_id)
    if cable is None:
        raise HTTPException(status_code=404, detail=f"Cable {cable_id} not found")
    return cable


@app.get("/cables/{cable_id}/geojson")
def get_cable_geojson_endpoint(cable_id: int):
    feature = get_cable_geojson(cable_id)
    if feature is None:
        raise HTTPException(status_code=404, detail=f"Cable {cable_id} not found")
    return feature
