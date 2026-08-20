"""Lightweight module routing for AquaNexus Agent v1."""

from __future__ import annotations

import re
from typing import Any


# Modules that are fully implemented and safe for the agent to use.
SUPPORTED_MODULES = {
    "argo",
    "minerals",
    "oil_spill",
}

# Modules that may be recognized by the router but are not yet available.
FUTURE_MODULES = {
    "cables",
}


ARGO_KEYWORDS = {
    "argo",
    "float",
    "floats",
    "cycle",
    "cycles",
    "profile",
    "profiles",
    "ocean conditions",
    "temperature",
    "salinity",
    "pressure",
    "dbar",
    "thermocline",
    "anomaly",
    "anomalies",
}


MODULE_KEYWORDS = {
    "oil_spill": {
        "oil spill",
        "oil spills",
        "oil slick",
        "oil slicks",
        "slick",
        "slicks",
        "dark slick",
        "dark slicks",
        "slick-like",
        "hydrocarbon",
        "hydrocarbons",
        "petroleum leak",
        "petroleum leakage",
        "oil leakage",
        "oil pollution",
        "sentinel-1",
        "sentinel 1",
        "sar slick",
        "sar anomaly",
    },
    "minerals": {
        "mineral",
        "minerals",
        "marine mineral",
        "marine minerals",
        "seabed mineral",
        "seabed minerals",
        "seafloor mineral",
        "seafloor minerals",
        "hydrothermal",
        "hydrothermal field",
        "hydrothermal vent",
        "polymetallic nodule",
        "polymetallic nodules",
        "polymetallic sulphide",
        "polymetallic sulphides",
        "polymetallic sulfide",
        "polymetallic sulfides",
        "phosphorite",
        "phosphorites",
        "placer deposit",
        "placer deposits",
        "seafloor mining",
        "manganese",
    },
    "cables": {
        "cable",
        "cables",
        "submarine cable",
        "submarine cables",
        "undersea cable",
        "undersea cables",
        "fiber optic",
        "fibre optic",
        "cable route",
        "cable routes",
        "cable damage",
    },
}


GENERIC_OCEAN_KEYWORDS = {
    "ocean",
    "sea",
    "marine",
    "water",
}


def identify_candidate_modules(
    user_query: str,
) -> list[str]:
    """Identify AquaNexus modules that may be relevant to a user query.

    Specialized modules are detected first. ARGO is added when the query
    explicitly asks for oceanographic/ARGO evidence, or as the default module
    when no specialized module is identified.
    """

    text = _normalize_text(user_query)
    modules: list[str] = []

    # ---------------------------------------------------------
    # 1. Specialized domain modules
    # ---------------------------------------------------------

    for module_name, keywords in MODULE_KEYWORDS.items():
        if _contains_any(text, keywords):
            modules.append(module_name)

    # ---------------------------------------------------------
    # 2. ARGO / oceanographic module
    # ---------------------------------------------------------

    argo_requested = _contains_any(
        text,
        ARGO_KEYWORDS,
    )

    if argo_requested:
        modules.append("argo")

    # A generic ocean/location question with no specialized module
    # defaults to the normal AquaNexus ocean/ARGO workflow.
    if not modules and (
        _contains_any(text, GENERIC_OCEAN_KEYWORDS)
        or text
    ):
        modules.append("argo")

    return _deduplicate(modules)


def unsupported_module_result(
    modules: list[str],
) -> dict[str, Any]:
    """Return a structured result for clearly requested unimplemented modules."""

    unsupported = [
        module
        for module in modules
        if module not in SUPPORTED_MODULES
    ]

    return {
        "text": (
            "That request needs an AquaNexus module that is not implemented yet: "
            f"{', '.join(unsupported)}. I cannot fabricate results for it."
        ),
        "modules_used": [],
        "tools_used": [],
        "evidence": [
            {
                "status": "unsupported_module",
                "unsupported_modules": unsupported,
                "supported_modules": sorted(
                    SUPPORTED_MODULES
                ),
            }
        ],
        "chart_data": None,
        "map_data": None,
    }


def _normalize_text(
    value: str,
) -> str:
    if value is None:
        return ""

    return " ".join(
        str(value).lower().split()
    )


def _contains_any(
    text: str,
    keywords: set[str],
) -> bool:
    return any(
        _contains_keyword(
            text,
            keyword,
        )
        for keyword in keywords
    )


def _contains_keyword(
    text: str,
    keyword: str,
) -> bool:
    """Match complete words/phrases instead of arbitrary substrings."""

    pattern = (
        r"(?<![a-z0-9])"
        + re.escape(keyword.lower())
        + r"(?![a-z0-9])"
    )

    return re.search(
        pattern,
        text,
    ) is not None


def _deduplicate(
    values: list[str],
) -> list[str]:
    result: list[str] = []

    for value in values:
        if value not in result:
            result.append(value)

    return result