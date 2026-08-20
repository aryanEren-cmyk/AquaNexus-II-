"""Lightweight module routing for AquaNexus Agent v1."""

from __future__ import annotations

from typing import Any


SUPPORTED_MODULES = {"argo", "minerals"}
FUTURE_MODULES = {"oil_spill", "minerals", "cables"}

ARGO_KEYWORDS = {
    "argo",
    "float",
    "cycle",
    "profile",
    "profiles",
    "conditions",
    "condition",
    "ocean",
    "sea",
    "near",
    " at ",
    " in ",
    "temperature",
    "salinity",
    "pressure",
    "dbar",
    "thermocline",
    "anomaly",
}
UNSUPPORTED_KEYWORDS = {
    "oil_spill": {"oil spill", "slick", "hydrocarbon", "pollution"},
    "minerals": {"mineral", "minerals", "nodules", "seafloor mining", "manganese"},
    "cables": {"cable", "cables", "submarine cable", "fiber optic", "damage"},
}


def identify_candidate_modules(user_query: str) -> list[str]:
    """Identify AquaNexus modules that may be relevant to a user query."""
    text = user_query.lower()
    modules: list[str] = []

    if any(keyword in text for keyword in ARGO_KEYWORDS):
        modules.append("argo")

    for module_name, keywords in UNSUPPORTED_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            modules.append(module_name)

    return modules or ["argo"]


def unsupported_module_result(modules: list[str]) -> dict[str, Any]:
    """Return a structured result for clearly requested unimplemented modules."""
    unsupported = [module for module in modules if module not in SUPPORTED_MODULES]
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
                "supported_modules": sorted(SUPPORTED_MODULES),
            }
        ],
        "chart_data": None,
        "map_data": None,
    }
