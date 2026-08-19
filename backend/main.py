"""FastAPI application for AquaNexus-II."""

from __future__ import annotations

from contextlib import asynccontextmanager
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from agent.agent import run_agent
from argo.live.live_argo import LIVE_DATA_PATH
from argo.tools.argo_tools import PROFILE_INDEX_PATH
from backend.schemas import ChatRequest, OceanConditionsRequest
from copernicus.present_state import PRESENT_DATA_PATH
from location.resolver import LocationResolverError
from ocean.conditions import OceanConditionsError, get_ocean_conditions


DEFAULT_CORS_ORIGINS = (
    "http://localhost:3000",
    "http://localhost:5173",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Perform lightweight startup checks without loading large datasets."""
    app.state.cache_status = _cache_status()
    _warm_small_profile_index()
    yield


app = FastAPI(
    title="AquaNexus API",
    version="1.0.0",
    lifespan=lifespan,
)


@app.exception_handler(LocationResolverError)
async def location_resolver_error_handler(_: Any, exc: LocationResolverError) -> JSONResponse:
    return _safe_error_response(400, str(exc))


@app.exception_handler(OceanConditionsError)
async def ocean_conditions_error_handler(_: Any, exc: OceanConditionsError) -> JSONResponse:
    return _safe_error_response(400, str(exc))


@app.exception_handler(ValueError)
async def value_error_handler(_: Any, exc: ValueError) -> JSONResponse:
    return _safe_error_response(400, str(exc))


@app.exception_handler(ValidationError)
async def validation_error_handler(_: Any, exc: ValidationError) -> JSONResponse:
    return _safe_error_response(400, str(exc))


@app.exception_handler(RequestValidationError)
async def request_validation_error_handler(_: Any, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={
            "detail": {
                "error": "bad_request",
                "message": _validation_message(exc),
            }
        },
    )


@app.get("/api/health")
def health() -> dict[str, Any]:
    """Return service health and cache file existence."""
    return {
        "status": "ok",
        "service": "AquaNexus API",
        "caches": _cache_status(),
    }


@app.post("/api/chat")
def chat(request: ChatRequest) -> dict[str, Any]:
    """Run the AquaNexus agent and return its structured contract unchanged."""
    try:
        return run_agent(request.message)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_error",
                "message": "An unexpected internal error occurred.",
            },
        ) from exc


@app.post("/api/ocean/conditions")
def ocean_conditions(request: OceanConditionsRequest) -> dict[str, Any]:
    """Return deterministic location-based ocean conditions without the LLM."""
    try:
        return get_ocean_conditions(
            request.location,
            depth_m=request.depth_m,
            argo_radius_km=request.argo_radius_km,
        )
    except (LocationResolverError, OceanConditionsError, ValueError) as exc:
        raise HTTPException(
            status_code=400,
            detail={"error": "bad_request", "message": _safe_message(exc)},
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_error",
                "message": "An unexpected internal error occurred.",
            },
        ) from exc


def _cache_status() -> dict[str, bool]:
    return {
        "copernicus_present_state": PRESENT_DATA_PATH.exists(),
        "live_argo": LIVE_DATA_PATH.exists(),
        "historical_argo_profile_index": PROFILE_INDEX_PATH.exists(),
    }


def _warm_small_profile_index() -> None:
    if not PROFILE_INDEX_PATH.exists():
        return
    try:
        import numpy as np

        with np.load(PROFILE_INDEX_PATH, allow_pickle=False) as profile_index:
            _ = profile_index.files
    except Exception:
        return


def _cors_origins() -> list[str]:
    origins = list(DEFAULT_CORS_ORIGINS)
    extra = os.getenv("AQUANEXUS_CORS_ORIGINS", "")
    origins.extend(origin.strip() for origin in extra.split(",") if origin.strip())
    return sorted(set(origins))


def _safe_error_response(status_code: int, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"detail": {"error": "bad_request", "message": _safe_message(message)}},
    )


def _validation_message(exc: RequestValidationError) -> str:
    errors = exc.errors()
    if not errors:
        return "Invalid request."
    messages = []
    for error in errors:
        location = ".".join(str(part) for part in error.get("loc", []) if part != "body")
        message = str(error.get("msg", "Invalid value."))
        messages.append(f"{location}: {message}" if location else message)
    return "; ".join(messages)


def _safe_message(error: Any) -> str:
    text = str(error)
    for secret_name in (
        "GROQ_API_KEY",
        "COPERNICUSMARINE_USERNAME",
        "COPERNICUSMARINE_PASSWORD",
        "COPERNICUSMARINE_SERVICE_USERNAME",
        "COPERNICUSMARINE_SERVICE_PASSWORD",
    ):
        secret_value = os.getenv(secret_name)
        if secret_value:
            text = text.replace(secret_value, "[redacted]")
    return text


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=[
        "Content-Type",
        "Authorization",
    ],
)
