"""Groq tool-calling AquaNexus Agent v1."""

from __future__ import annotations

import json
from typing import Any

from agent.config import ConfigurationError, load_config
from agent.router import (
    SUPPORTED_MODULES,
    identify_candidate_modules,
    unsupported_module_result,
)
from agent.tools import LLM_TOOL_SCHEMAS, execute_tool


MAX_TOOL_ROUNDS = 6


SYSTEM_PROMPT = """You are an ocean-intelligence assistant.

Use tools for scientific/data claims whenever relevant.

Never invent ARGO measurements.

Clearly distinguish evidence from interpretation.

Pressure is in dbar; do not automatically claim it is exact depth in meters.

For normal place, region, sea, or coordinate ocean questions, prefer
get_ocean_conditions.

Use float-level ARGO tools for explicit float/cycle questions.

Copernicus is a gridded analysis/forecast estimate.
Never describe Copernicus values as direct measurements.

For Copernicus depths, say "model grid depth" or
"nearest model depth", not "measured at".

ARGO is an in-situ observation.

Never treat ARGO pressure in dbar as exact meters.

If latest_argo is unavailable, do not imply failure of the whole query.
Use Copernicus evidence and clearly say no recent ARGO profile was
available within the configured radius.

For area results, temperature/salinity values may contain mean/min/max.
Do not present the mean as if it represents every point in the region.

Mention timestamps when useful.

Copy timestamps exactly from tool evidence.
Never alter dates, years, or time zones.

Do not invent missing evidence.

Thermocline detection currently uses a simplified heuristic.

Historical anomaly analysis is a practical baseline,
not formal climatology or statistical significance.

If data is unavailable, say so.

Never claim ARGO directly detects oil spills, minerals,
or submarine cable damage.

Never convert ARGO pressure in dbar to meters, even approximately.

Do not write statements such as "100 dbar ≈ 100 m".

Report ARGO pressure exactly in dbar unless a separate scientifically
valid depth conversion is provided by a tool.


Marine mineral evidence rules:

For questions about seabed minerals, hydrothermal mineralization,
polymetallic sulphides, polymetallic nodules, phosphorites,
placer deposits, mineral zones, or known marine-mineral sites,
use get_mineral_insights.

Never claim AquaNexus detects marine minerals unless the underlying
tool evidence contains a direct measurement that supports that claim.

Distinguish these evidence categories carefully:

1. station_samples:
   Direct seafloor sample observations from the cited source.

2. cited_sites:
   Individually documented or literature-reported mineral or
   hydrothermal sites. These are not measurements made by AquaNexus.

3. estimated_regions:
   Approximate regional mineral context represented by broad geographic
   bounds. These regions do not prove that a mineral deposit exists at
   every coordinate inside them.

Never relabel a cited_sites result as a direct AquaNexus measurement
or as a station sample.

A literature-reported site can be scientifically documented while still
remaining separate from AquaNexus direct observations.

Never infer absence from an incomplete dataset.

If no record of a particular mineral type is returned, do not say:
"this mineral has not been reported there."

Instead say:
"the current AquaNexus mineral evidence dataset contains no such record
for this query."

Do not convert absence of evidence into evidence of absence.

Never describe ARGO or Copernicus oceanographic values as direct evidence
of a mineral deposit.

If estimated_regions are returned, clearly label them as approximate
regional context, not confirmed deposit boundaries.

Preserve citation, DOI, source URL, provenance, and evidence limitations
provided by the mineral tool whenever they are useful to the answer.

Do not invent citations or source information that the tool did not return.



Oil-spill / SAR evidence rules:

For questions about possible oil spills, oil slicks, petroleum leakage,
slick-like ocean anomalies, or Sentinel-1 slick screening,
use get_oil_slick_insights.

Oil-spill screening uses Sentinel-1 SAR satellite remote sensing.
Do not describe ARGO as detecting oil spills.

A "SAR dark-slick candidate" or "slick-like SAR anomaly" is not a
confirmed oil spill and is not proof of petroleum.

Low backscatter can also be caused by calm water, natural surfactants,
biological films, rain effects, current boundaries, atmospheric effects,
and other look-alike conditions.

If the tool returns no_recent_usable_scene, say that no compatible recent
Sentinel-1 scene was available and that no screening was performed.
Never turn missing satellite coverage into evidence that oil is absent.

If the tool returns no candidates, say that no candidate met the current
heuristic in the analyzed patch. Do not claim that oil is absent.

If an analysis target was shifted from the requested place to a nearby
water-dominated patch, preserve that distinction and mention the shift
when relevant. Do not imply that the named place itself moved.

Never generate or invent an oil-spill confidence percentage.

Preserve Sentinel-1 acquisition times, candidate counts, candidate
coordinates, water coverage, provenance, and scientific caveats from
the tool result when they are useful to the answer.

Prefer concise evidence-based answers.

Return concise prose for the user.
Structured evidence is handled by the application.
"""


def run_agent(user_message: str) -> dict[str, Any]:
    """Run the AquaNexus Groq tool-calling agent for one user message."""

    candidate_modules = identify_candidate_modules(user_message)

    unsupported_modules = [
        module
        for module in candidate_modules
        if module not in SUPPORTED_MODULES
    ]

    if unsupported_modules:
        return unsupported_module_result(candidate_modules)

    try:
        config = load_config()

    except ConfigurationError as exc:
        return _error_response(
            "configuration_error",
            str(exc),
            _supported_candidate_modules(candidate_modules),
        )

    try:
        from groq import Groq

    except ImportError:
        return _error_response(
            "configuration_error",
            "The groq Python package is not installed.",
            _supported_candidate_modules(candidate_modules),
        )

    client = Groq(api_key=config.groq_api_key)

    messages: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT,
        },
        {
            "role": "user",
            "content": user_message,
        },
    ]

    tools_used: list[str] = []
    evidence: list[dict[str, Any]] = []

    try:
        for _ in range(MAX_TOOL_ROUNDS):

            response = client.chat.completions.create(
                model=config.groq_model,
                messages=messages,
                tools=LLM_TOOL_SCHEMAS,
                tool_choice="auto",
            )

            message = response.choices[0].message

            tool_calls = getattr(
                message,
                "tool_calls",
                None,
            )

            messages.append(
                _assistant_message_to_dict(message)
            )

            # ------------------------------------------------
            # MODEL HAS FINISHED TOOL CALLING
            # ------------------------------------------------

            if not tool_calls:
                return _success_response(
                    text=message.content or "",
                    modules_used=_modules_from_tools(
                        tools_used
                    ),
                    tools_used=tools_used,
                    evidence=evidence,
                )

            # ------------------------------------------------
            # EXECUTE REQUESTED TOOLS
            # ------------------------------------------------

            for tool_call in tool_calls:

                tool_name = tool_call.function.name

                arguments = _parse_tool_arguments(
                    tool_call.function.arguments
                )

                result = execute_tool(
                    tool_name,
                    arguments,
                )

                tools_used.append(tool_name)

                evidence.append(
                    {
                        "tool": tool_name,
                        "arguments": arguments,
                        "result": result,
                    }
                )

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": tool_name,
                        "content": json.dumps(
                            _tool_result_for_llm(
                                tool_name,
                                result,
                            )
                        ),
                    }
                )

        # ----------------------------------------------------
        # TOO MANY TOOL-CALLING ROUNDS
        # ----------------------------------------------------

        return _error_response(
            "max_tool_rounds_exceeded",
            (
                f"Stopped after {MAX_TOOL_ROUNDS} "
                "tool-calling rounds."
            ),
            _modules_for_error(
                candidate_modules,
                tools_used,
            ),
            tools_used=tools_used,
            evidence=evidence,
        )

    except ValueError as exc:

        return _error_response(
            "tool_error",
            str(exc),
            _modules_for_error(
                candidate_modules,
                tools_used,
            ),
            tools_used=tools_used,
            evidence=evidence,
        )

    except Exception as exc:

        return _error_response(
            "provider_or_runtime_error",
            str(exc),
            _modules_for_error(
                candidate_modules,
                tools_used,
            ),
            tools_used=tools_used,
            evidence=evidence,
        )



def _tool_result_for_llm(
    tool_name: str,
    result: dict[str, Any],
) -> dict[str, Any]:
    """
    Return a compact tool result for the LLM while preserving the full
    deterministic result separately in the API evidence payload.

    Large scientific payloads can exceed provider token-per-minute limits
    when echoed back into the model. The model only needs the evidence
    required to write a faithful user-facing explanation.
    """

    if tool_name != "get_oil_slick_insights":
        return result

    if not isinstance(result, dict):
        return {"status": "invalid_tool_result"}

    analysis_target = result.get("analysis_target") or {}
    satellite = result.get("satellite_observation") or {}
    water = result.get("water_context") or {}
    screening = result.get("screening") or {}
    interpretation = result.get("interpretation") or {}
    location = result.get("location") or {}

    candidate_locations = result.get("candidate_locations") or []

    # A few representative candidate positions are enough for the LLM
    # explanation. The complete candidate set remains available in
    # response["evidence"] for the frontend/map.
    representative_candidates = candidate_locations[:5]

    compact: dict[str, Any] = {
        "status": result.get("status"),
        "screening_performed": result.get("screening_performed"),
        "location": {
            "display_name": location.get("display_name"),
            "latitude": location.get("latitude"),
            "longitude": location.get("longitude"),
        },
        "analysis_target": {
            "latitude": analysis_target.get("latitude"),
            "longitude": analysis_target.get("longitude"),
            "shifted_from_requested_location": analysis_target.get(
                "shifted_from_requested_location"
            ),
            "shift_distance_km": analysis_target.get("shift_distance_km"),
            "selection_status": analysis_target.get("selection_status"),
            "estimated_water_fraction": analysis_target.get(
                "estimated_water_fraction"
            ),
        },
        "satellite_observation": {
            "scene_id": satellite.get("scene_id"),
            "acquisition_time": satellite.get("acquisition_time"),
            "platform": satellite.get("platform"),
            "instrument_mode": satellite.get("instrument_mode"),
            "polarizations": satellite.get("polarizations"),
        },
        "water_context": {
            "water_fraction": water.get("water_fraction"),
            "reference_year": (
                (water.get("source") or {}).get("reference_year")
                if isinstance(water.get("source"), dict)
                else None
            ),
        },
        "screening": {
            "classification": screening.get("classification"),
            "analysis_context": screening.get("analysis_context"),
            "statistics": screening.get("statistics"),
            "thresholds": screening.get("thresholds"),
        },
        "candidate_count": result.get("candidate_count"),
        "representative_candidate_locations": representative_candidates,
        "representative_candidate_count": len(representative_candidates),
        "candidate_locations_truncated_for_llm": (
            len(candidate_locations) > len(representative_candidates)
        ),
        "summary": result.get("summary"),
        "interpretation": {
            "evidence_type": interpretation.get("evidence_type"),
            "oil_confirmation": interpretation.get("oil_confirmation"),
            "confidence_score": interpretation.get("confidence_score"),
            "meaning": interpretation.get("meaning"),
            "not_equivalent_to": interpretation.get("not_equivalent_to"),
        },
        "provenance": result.get("provenance"),
        "data_notes": (result.get("data_notes") or [])[:8],
        "runtime_seconds": result.get("runtime_seconds"),
    }

    return compact


def _parse_tool_arguments(
    raw_arguments: str | None,
) -> dict[str, Any]:
    """Parse JSON tool arguments from the model."""

    if not raw_arguments:
        return {}

    try:
        arguments = json.loads(
            raw_arguments
        )

    except json.JSONDecodeError as exc:
        raise ValueError(
            (
                "Invalid tool arguments JSON: "
                f"{raw_arguments!r}"
            )
        ) from exc

    if not isinstance(arguments, dict):
        raise ValueError(
            "Tool arguments must decode to an object."
        )

    return arguments


def _assistant_message_to_dict(
    message: Any,
) -> dict[str, Any]:
    """
    Convert a Groq assistant message into
    a chat message dictionary.
    """

    message_dict: dict[str, Any] = {
        "role": "assistant",
        "content": message.content,
    }

    tool_calls = getattr(
        message,
        "tool_calls",
        None,
    )

    if tool_calls:

        message_dict["tool_calls"] = [
            {
                "id": tool_call.id,
                "type": "function",
                "function": {
                    "name":
                        tool_call.function.name,
                    "arguments":
                        tool_call.function.arguments,
                },
            }
            for tool_call in tool_calls
        ]

    return message_dict


def _modules_from_tools(
    tools_used: list[str],
) -> list[str]:
    """
    Infer AquaNexus modules from tools that
    were actually executed.
    """

    tool_module_map = {
        # --------------------------------
        # Ocean / ARGO module
        # --------------------------------
        "get_ocean_conditions": "argo",
        "get_float_profile": "argo",
        "get_value_at_pressure": "argo",
        "list_float_cycles": "argo",
        "get_float_summary": "argo",
        "find_nearest_profiles": "argo",
        "compare_float_profiles": "argo",
        "get_temperature_anomaly": "argo",

        # --------------------------------
        # Marine Minerals module
        # --------------------------------
        "get_mineral_insights": "minerals",

        # --------------------------------
        # Oil Spill / Sentinel-1 SAR module
        # --------------------------------
        "get_oil_slick_insights": "oil_spill",
    }

    modules: list[str] = []

    for tool_name in tools_used:

        module = tool_module_map.get(
            tool_name
        )

        if (
            module is not None
            and module in SUPPORTED_MODULES
            and module not in modules
        ):
            modules.append(module)

    return modules


def _supported_candidate_modules(
    candidate_modules: list[str],
) -> list[str]:
    """
    Return candidate modules that are actually
    implemented by AquaNexus.
    """

    return [
        module
        for module in candidate_modules
        if module in SUPPORTED_MODULES
    ]


def _modules_for_error(
    candidate_modules: list[str],
    tools_used: list[str],
) -> list[str]:
    """
    Determine module metadata for an error response.

    Prefer modules whose tools actually ran.
    If no tool executed yet, fall back to supported
    modules inferred from the user's request.
    """

    executed_modules = _modules_from_tools(
        tools_used
    )

    if executed_modules:
        return executed_modules

    return _supported_candidate_modules(
        candidate_modules
    )


def _success_response(
    text: str,
    modules_used: list[str],
    tools_used: list[str],
    evidence: list[dict[str, Any]],
) -> dict[str, Any]:
    """Return the final structured agent response."""

    return {
        "text": text,
        "modules_used": modules_used,
        "tools_used": tools_used,
        "evidence": evidence,
        "chart_data": None,
        "map_data": None,
    }


def _error_response(
    error_type: str,
    message: str,
    modules: list[str],
    *,
    tools_used: list[str] | None = None,
    evidence: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Return structured error information
    without fabricating an answer.
    """

    return {
        "text": message,
        "modules_used": [
            module
            for module in modules
            if module in SUPPORTED_MODULES
        ],
        "tools_used": tools_used or [],
        "evidence": (
            evidence
            or [
                {
                    "status": error_type,
                    "message": message,
                }
            ]
        ),
        "chart_data": None,
        "map_data": None,
    }