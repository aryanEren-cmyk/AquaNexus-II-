"""Sentinel Hub retrieval for small Sentinel-1 SAR analysis patches.

This module retrieves calibrated Sentinel-1 GRD pixels for a small area of
interest. It performs no oil-spill classification.
"""

from __future__ import annotations

import json
import os
import time
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


TOKEN_URL = (
    "https://identity.dataspace.copernicus.eu/"
    "auth/realms/CDSE/protocol/openid-connect/token"
)

PROCESS_URL = "https://sh.dataspace.copernicus.eu/process/v1"

CLIENT_ID_ENV = "COPERNICUS_SH_CLIENT_ID"
CLIENT_SECRET_ENV = "COPERNICUS_SH_CLIENT_SECRET"

USER_AGENT = "AquaNexus-II/1.0 Sentinel-1 SAR retrieval"

HTTP_TIMEOUT_SECONDS = 60

DEFAULT_HALF_SIZE_DEGREES = 0.05
DEFAULT_WIDTH = 512
DEFAULT_HEIGHT = 512

MAX_HALF_SIZE_DEGREES = 1.0
MAX_IMAGE_DIMENSION = 2048

# In-memory OAuth token cache.
_ACCESS_TOKEN: str | None = None
_ACCESS_TOKEN_EXPIRES_AT: float = 0.0


class SentinelHubError(RuntimeError):
    """Raised when Sentinel Hub authentication or processing fails."""


def fetch_sentinel1_patch(
    latitude: float,
    longitude: float,
    acquisition_time: str,
    half_size_degrees: float = DEFAULT_HALF_SIZE_DEGREES,
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
) -> dict[str, Any]:
    """Retrieve a small calibrated Sentinel-1 VV/VH SAR patch.

    The returned ``content`` value contains GeoTIFF bytes and is intentionally
    not JSON-serializable. This function is an internal raster-retrieval layer.
    A later analysis stage should consume the bytes and return JSON-safe
    scientific evidence.

    This function does not detect or classify oil spills.
    """

    lat = _validate_coordinate(
        latitude,
        "latitude",
        -90.0,
        90.0,
    )
    lon = _validate_coordinate(
        longitude,
        "longitude",
        -180.0,
        180.0,
    )

    half_size = _validate_positive_float(
        half_size_degrees,
        "half_size_degrees",
        maximum=MAX_HALF_SIZE_DEGREES,
    )

    image_width = _validate_positive_int(
        width,
        "width",
        maximum=MAX_IMAGE_DIMENSION,
    )
    image_height = _validate_positive_int(
        height,
        "height",
        maximum=MAX_IMAGE_DIMENSION,
    )

    acquisition = _parse_acquisition_time(
        acquisition_time
    )

    bbox = _build_bbox(
        lat,
        lon,
        half_size,
    )

    time_from = acquisition - timedelta(minutes=2)
    time_to = acquisition + timedelta(minutes=2)

    payload = _build_process_payload(
        bbox=bbox,
        time_from=_format_datetime(time_from),
        time_to=_format_datetime(time_to),
        width=image_width,
        height=image_height,
    )

    access_token = _get_access_token()

    content, content_type = _request_process_api(
        payload,
        access_token,
    )

    return {
        "content": content,
        "content_type": content_type,
        "byte_size": len(content),
        "acquisition_time": _format_datetime(acquisition),
        "bbox": {
            "west": bbox[0],
            "south": bbox[1],
            "east": bbox[2],
            "north": bbox[3],
        },
        "width": image_width,
        "height": image_height,
        "bands": [
            "VV",
            "VH",
            "dataMask",
        ],
        "backscatter_coefficient": "SIGMA0_ELLIPSOID",
        "source": {
            "name": "Copernicus Sentinel Hub",
            "collection": "sentinel-1-grd",
            "api": "Process API",
            "api_url": PROCESS_URL,
        },
        "data_notes": _data_notes(),
    }


def _get_access_token() -> str:
    """Return a cached or newly requested Sentinel Hub OAuth token."""

    global _ACCESS_TOKEN
    global _ACCESS_TOKEN_EXPIRES_AT

    now = time.monotonic()

    if (
        _ACCESS_TOKEN is not None
        and now < _ACCESS_TOKEN_EXPIRES_AT
    ):
        return _ACCESS_TOKEN

    _load_dotenv_if_available()

    client_id = os.getenv(CLIENT_ID_ENV)
    client_secret = os.getenv(CLIENT_SECRET_ENV)

    if not client_id or not client_secret:
        raise SentinelHubError(
            "Copernicus Sentinel Hub credentials are not configured."
        )

    encoded_body = urlencode(
        {
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        }
    ).encode("utf-8")

    request = Request(
        TOKEN_URL,
        data=encoded_body,
        headers={
            "Content-Type": (
                "application/x-www-form-urlencoded"
            ),
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        },
        method="POST",
    )

    try:
        with urlopen(
            request,
            timeout=HTTP_TIMEOUT_SECONDS,
        ) as response:
            body = response.read()

    except HTTPError as exc:
        raise SentinelHubError(
            "Copernicus authentication failed "
            f"with HTTP {exc.code}."
        ) from exc

    except (
        TimeoutError,
        URLError,
        OSError,
    ) as exc:
        raise SentinelHubError(
            "Unable to reach Copernicus authentication service."
        ) from exc

    try:
        payload = json.loads(
            body.decode("utf-8")
        )

    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as exc:
        raise SentinelHubError(
            "Copernicus authentication returned "
            "an invalid response."
        ) from exc

    if not isinstance(payload, dict):
        raise SentinelHubError(
            "Copernicus authentication returned "
            "an unexpected response."
        )

    token = payload.get("access_token")

    if not isinstance(token, str) or not token:
        raise SentinelHubError(
            "Copernicus authentication response "
            "did not contain an access token."
        )

    expires_in = payload.get("expires_in", 300)

    try:
        expires_seconds = float(expires_in)
    except (TypeError, ValueError):
        expires_seconds = 300.0

    # Refresh at least one minute before nominal expiry.
    usable_seconds = max(
        30.0,
        expires_seconds - 60.0,
    )

    _ACCESS_TOKEN = token
    _ACCESS_TOKEN_EXPIRES_AT = (
        time.monotonic() + usable_seconds
    )

    return token


def _request_process_api(
    payload: dict[str, Any],
    access_token: str,
) -> tuple[bytes, str]:
    """Execute one Sentinel Hub Process API request."""

    body = json.dumps(payload).encode("utf-8")

    request = Request(
        PROCESS_URL,
        data=body,
        headers={
            "Authorization": (
                f"Bearer {access_token}"
            ),
            "Content-Type": "application/json",
            "Accept": "image/tiff",
            "User-Agent": USER_AGENT,
        },
        method="POST",
    )

    try:
        with urlopen(
            request,
            timeout=HTTP_TIMEOUT_SECONDS,
        ) as response:
            content = response.read()
            content_type = (
                response.headers.get(
                    "Content-Type",
                    "",
                )
                or ""
            )

    except HTTPError as exc:
        raise SentinelHubError(
            "Sentinel Hub Process API request failed "
            f"with HTTP {exc.code}."
        ) from exc

    except (
        TimeoutError,
        URLError,
        OSError,
    ) as exc:
        raise SentinelHubError(
            "Unable to reach Sentinel Hub Process API."
        ) from exc

    if not content:
        raise SentinelHubError(
            "Sentinel Hub returned an empty raster response."
        )

    normalized_type = content_type.lower()

    if (
        "tiff" not in normalized_type
        and "geotiff" not in normalized_type
    ):
        raise SentinelHubError(
            "Sentinel Hub returned an unexpected "
            f"content type: {content_type or 'unknown'}."
        )

    return content, content_type


def _build_process_payload(
    bbox: list[float],
    time_from: str,
    time_to: str,
    width: int,
    height: int,
) -> dict[str, Any]:
    """Build a Sentinel Hub Sentinel-1 Process API request."""

    return {
        "input": {
            "bounds": {
                "bbox": bbox,
                "properties": {
                    "crs": (
                        "http://www.opengis.net/"
                        "def/crs/OGC/1.3/CRS84"
                    )
                },
            },
            "data": [
                {
                    "type": "sentinel-1-grd",
                    "dataFilter": {
                        "timeRange": {
                            "from": time_from,
                            "to": time_to,
                        },
                        "mosaickingOrder": "mostRecent",
                        "acquisitionMode": "IW",
                        "polarization": "DV",
                    },
                    "processing": {
                        "backCoeff": "SIGMA0_ELLIPSOID",
                        "orthorectify": "false",
                    },
                }
            ],
        },
        "output": {
            "width": width,
            "height": height,
            "responses": [
                {
                    "identifier": "default",
                    "format": {
                        "type": "image/tiff"
                    },
                }
            ],
        },
        "evalscript": _evalscript(),
    }


def _evalscript() -> str:
    """Return Evalscript V3 for numerical VV/VH backscatter."""

    return """
//VERSION=3
function setup() {
    return {
        input: [{
            bands: ["VV", "VH", "dataMask"]
        }],
        output: {
            id: "default",
            bands: 3,
            sampleType: "FLOAT32"
        }
    };
}

function evaluatePixel(sample) {
    return [
        sample.VV,
        sample.VH,
        sample.dataMask
    ];
}
""".strip()


def _parse_acquisition_time(
    value: Any,
) -> datetime:
    if not isinstance(value, str):
        raise ValueError(
            "acquisition_time must be an ISO-8601 string."
        )

    text = value.strip()

    if not text:
        raise ValueError(
            "acquisition_time cannot be empty."
        )

    normalized = text.replace(
        "Z",
        "+00:00",
    )

    try:
        parsed = datetime.fromisoformat(
            normalized
        )
    except ValueError as exc:
        raise ValueError(
            "acquisition_time must be a valid "
            "ISO-8601 timestamp."
        ) from exc

    if parsed.tzinfo is None:
        parsed = parsed.replace(
            tzinfo=UTC
        )

    return parsed.astimezone(UTC)


def _build_bbox(
    latitude: float,
    longitude: float,
    half_size: float,
) -> list[float]:
    west = max(
        -180.0,
        longitude - half_size,
    )
    east = min(
        180.0,
        longitude + half_size,
    )
    south = max(
        -90.0,
        latitude - half_size,
    )
    north = min(
        90.0,
        latitude + half_size,
    )

    if west >= east or south >= north:
        raise ValueError(
            "Requested raster bounding box is invalid."
        )

    return [
        west,
        south,
        east,
        north,
    ]


def _validate_coordinate(
    value: Any,
    name: str,
    minimum: float,
    maximum: float,
) -> float:
    if isinstance(value, bool):
        raise ValueError(
            f"{name} must be numeric."
        )

    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"{name} must be numeric."
        ) from exc

    if not minimum <= parsed <= maximum:
        raise ValueError(
            f"{name} must be between "
            f"{minimum:g} and {maximum:g}."
        )

    return parsed


def _validate_positive_float(
    value: Any,
    name: str,
    maximum: float,
) -> float:
    if isinstance(value, bool):
        raise ValueError(
            f"{name} must be numeric."
        )

    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"{name} must be numeric."
        ) from exc

    if parsed <= 0:
        raise ValueError(
            f"{name} must be greater than 0."
        )

    if parsed > maximum:
        raise ValueError(
            f"{name} must be less than or equal "
            f"to {maximum}."
        )

    return parsed


def _validate_positive_int(
    value: Any,
    name: str,
    maximum: int,
) -> int:
    if isinstance(value, bool):
        raise ValueError(
            f"{name} must be a positive integer."
        )

    if isinstance(value, float) and not value.is_integer():
        raise ValueError(
            f"{name} must be a positive integer."
        )

    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"{name} must be a positive integer."
        ) from exc

    if parsed <= 0:
        raise ValueError(
            f"{name} must be greater than 0."
        )

    if parsed > maximum:
        raise ValueError(
            f"{name} must be less than or equal "
            f"to {maximum}."
        )

    return parsed


def _format_datetime(
    value: datetime,
) -> str:
    return (
        value.astimezone(UTC)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def _load_dotenv_if_available() -> None:
    """Load project .env using the repository's optional dotenv pattern."""

    try:
        from dotenv import load_dotenv
    except ImportError:
        return

    load_dotenv()


def _data_notes() -> list[str]:
    return [
        (
            "VV and VH are calibrated Sentinel-1 "
            "SAR backscatter channels."
        ),
        (
            "Backscatter values use SIGMA0_ELLIPSOID "
            "and are returned as linear power."
        ),
        (
            "The raster corresponds to a discrete "
            "Sentinel-1 satellite acquisition."
        ),
        (
            "Low SAR backscatter does not by itself "
            "prove petroleum or an oil spill."
        ),
        (
            "Calm water, natural surfactants, rain "
            "effects and other phenomena can also "
            "produce dark SAR signatures."
        ),
        (
            "This retrieval function performs no "
            "oil-spill classification."
        ),
    ]