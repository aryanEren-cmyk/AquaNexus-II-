"""Copernicus land/water masking for Sentinel-1 analysis."""

from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import numpy as np
from rasterio.io import MemoryFile

from oil_spill.sentinelhub import (
    PROCESS_URL,
    HTTP_TIMEOUT_SECONDS,
    USER_AGENT,
    SentinelHubError,
    _get_access_token,
)


LAND_COVER_COLLECTION = (
    "byoc-828f6b20-8ffd-48f8-a1da-fefd271456db"
)

PERMANENT_WATER_CLASS = 100


class WaterMaskError(RuntimeError):
    """Raised when the Copernicus water mask cannot be retrieved."""


def fetch_water_mask(
    bbox: dict[str, float],
    width: int,
    height: int,
) -> dict[str, Any]:
    """Return a boolean permanent-water mask matching a SAR raster."""

    payload = {
        "input": {
            "bounds": {
                "bbox": [
                    bbox["west"],
                    bbox["south"],
                    bbox["east"],
                    bbox["north"],
                ],
                "properties": {
                    "crs": (
                        "http://www.opengis.net/"
                        "def/crs/OGC/1.3/CRS84"
                    )
                },
            },
            "data": [
                {
                    "type": LAND_COVER_COLLECTION,
                    "dataFilter": {
                        "timeRange": {
                            "from": "2020-01-01T00:00:00Z",
                            "to": "2020-12-31T23:59:59Z",
                        },
                        "mosaickingOrder": "mostRecent",
                    },
                }
            ],
        },
        "output": {
            "width": int(width),
            "height": int(height),
            "responses": [
                {
                    "identifier": "default",
                    "format": {
                        "type": "image/tiff"
                    },
                }
            ],
        },
        "evalscript": """
//VERSION=3
function setup() {
    return {
        input: [{
            bands: ["LCM10"]
        }],
        output: {
            bands: 1,
            sampleType: "UINT8"
        }
    };
}

function evaluatePixel(sample) {
    return [sample.LCM10];
}
""".strip(),
    }

    token = _get_access_token()

    request = Request(
        PROCESS_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
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

    except HTTPError as exc:
        raise WaterMaskError(
            "Copernicus land-cover request failed "
            f"with HTTP {exc.code}."
        ) from exc

    except (TimeoutError, URLError, OSError) as exc:
        raise WaterMaskError(
            "Unable to retrieve Copernicus land-cover data."
        ) from exc

    if not content:
        raise WaterMaskError(
            "Copernicus returned an empty land-cover raster."
        )

    try:
        with MemoryFile(content) as memory_file:
            with memory_file.open() as dataset:
                classes = dataset.read(1)

    except Exception as exc:
        raise WaterMaskError(
            "Unable to decode Copernicus land-cover raster."
        ) from exc

    water_mask = classes == PERMANENT_WATER_CLASS

    return {
        "water_mask": water_mask,
        "water_pixel_count": int(
            np.count_nonzero(water_mask)
        ),
        "total_pixels": int(water_mask.size),
        "water_fraction": round(
            float(np.count_nonzero(water_mask))
            / water_mask.size,
            6,
        ),
        "source": {
            "name": (
                "Copernicus Global Dynamic "
                "Land Cover 10 m"
            ),
            "collection": LAND_COVER_COLLECTION,
            "class_used": PERMANENT_WATER_CLASS,
            "class_label": "Permanent water bodies",
            "reference_year": 2020,
        },
        "data_notes": [
            (
                "The mask uses Copernicus land-cover "
                "class 100: Permanent water bodies."
            ),
            (
                "The land-cover layer is auxiliary "
                "context, not oil-spill evidence."
            ),
            (
                "Coastlines and land cover can change "
                "relative to the reference-year map."
            ),
        ],
    }