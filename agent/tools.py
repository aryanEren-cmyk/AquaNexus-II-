"""LLM tool schemas and deterministic AquaNexus tool execution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from argo.tools import argo_tools
from ocean.conditions import get_ocean_conditions


ToolFunction = Callable[..., dict[str, Any]]


@dataclass(frozen=True)
class ToolDefinition:
    """Registered AquaNexus tool metadata."""

    function: ToolFunction
    schema: dict[str, Any]
    required: tuple[str, ...]


def _integer(description: str) -> dict[str, str]:
    return {"type": "integer", "description": description}


def _number(description: str) -> dict[str, str]:
    return {"type": "number", "description": description}


def _schema(
    name: str,
    description: str,
    properties: dict[str, Any],
    required: tuple[str, ...],
) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": list(required),
                "additionalProperties": False,
            },
        },
    }


TOOL_REGISTRY: dict[str, ToolDefinition] = {
    "get_ocean_conditions": ToolDefinition(
        function=get_ocean_conditions,
        required=("location",),
        schema=_schema(
            "get_ocean_conditions",
            (
                "Get present ocean conditions for a named place, sea, region or "
                "coordinate within AquaNexus coverage. Combines Copernicus "
                "present-state estimates, recent ARGO observations and historical "
                "ARGO context. This is the preferred tool for normal user "
                "location-based ocean questions such as: temperature near Kochi; "
                "ocean conditions in Arabian Sea; salinity near Goa; ocean "
                "conditions at 10N 75E."
            ),
            {
                "location": {
                    "type": "string",
                    "description": (
                        "Named place, region, sea or coordinate such as Kochi, "
                        "Arabian Sea, or 10N 75E"
                    ),
                },
                "depth_m": _number("Requested Copernicus depth in meters. Default 0."),
                "argo_radius_km": _number(
                    "Maximum distance for recent ARGO evidence. Default 300 km."
                ),
            },
            ("location",),
        ),
    ),
    "get_float_profile": ToolDefinition(
        function=argo_tools.get_float_profile,
        required=("platform_number", "cycle_number"),
        schema=_schema(
            "get_float_profile",
            "Use for detailed metadata, statistics, thermocline heuristic, and full pressure-temperature-salinity records for one ARGO float cycle.",
            {
                "platform_number": _integer("ARGO float platform number, for example 1901910."),
                "cycle_number": _integer("ARGO cycle number for that float, for example 243."),
            },
            ("platform_number", "cycle_number"),
        ),
    ),
    "get_value_at_pressure": ToolDefinition(
        function=argo_tools.get_value_at_pressure,
        required=("platform_number", "cycle_number", "pressure"),
        schema=_schema(
            "get_value_at_pressure",
            "Use when the user asks for temperature and/or salinity at a requested pressure in one ARGO profile. Pressure is in dbar.",
            {
                "platform_number": _integer("ARGO float platform number, for example 1901910."),
                "cycle_number": _integer("ARGO cycle number for that float, for example 243."),
                "pressure": _number("Requested pressure in dbar, for example 100."),
            },
            ("platform_number", "cycle_number", "pressure"),
        ),
    ),
    "list_float_cycles": ToolDefinition(
        function=argo_tools.list_float_cycles,
        required=("platform_number",),
        schema=_schema(
            "list_float_cycles",
            "Use when the user asks which cycles are available for a specific ARGO float.",
            {
                "platform_number": _integer("ARGO float platform number, for example 1901910."),
            },
            ("platform_number",),
        ),
    ),
    "get_float_summary": ToolDefinition(
        function=argo_tools.get_float_summary,
        required=("platform_number",),
        schema=_schema(
            "get_float_summary",
            "Use for a concise coverage summary of one ARGO float, including cycle count, observation dates, and coordinate ranges.",
            {
                "platform_number": _integer("ARGO float platform number, for example 1901910."),
            },
            ("platform_number",),
        ),
    ),
    "find_nearest_profiles": ToolDefinition(
        function=argo_tools.find_nearest_profiles,
        required=("latitude", "longitude"),
        schema=_schema(
            "find_nearest_profiles",
            "Use when the user asks for ARGO profiles nearest to a latitude/longitude coordinate.",
            {
                "latitude": _number("Query latitude in decimal degrees. North is positive."),
                "longitude": _number("Query longitude in decimal degrees. East is positive."),
                "limit": _integer("Maximum number of nearest profiles to return. Defaults to 5."),
            },
            ("latitude", "longitude"),
        ),
    ),
    "compare_float_profiles": ToolDefinition(
        function=argo_tools.compare_float_profiles,
        required=("float_a", "cycle_a", "float_b", "cycle_b"),
        schema=_schema(
            "compare_float_profiles",
            "Use when the user asks to compare two ARGO profiles, including two cycles of the same float.",
            {
                "float_a": _integer("First ARGO float platform number."),
                "cycle_a": _integer("First ARGO cycle number."),
                "float_b": _integer("Second ARGO float platform number."),
                "cycle_b": _integer("Second ARGO cycle number."),
            },
            ("float_a", "cycle_a", "float_b", "cycle_b"),
        ),
    ),
    "get_temperature_anomaly": ToolDefinition(
        function=argo_tools.get_temperature_anomaly,
        required=("platform_number", "cycle_number", "pressure"),
        schema=_schema(
            "get_temperature_anomaly",
            "Use when the user asks whether an observed ARGO temperature is unusual or anomalous compared with nearby same-month historical observations. This is a practical baseline, not formal significance testing.",
            {
                "platform_number": _integer("ARGO float platform number, for example 1901910."),
                "cycle_number": _integer("ARGO cycle number for that float, for example 243."),
                "pressure": _number("Requested pressure in dbar, for example 100."),
            },
            ("platform_number", "cycle_number", "pressure"),
        ),
    ),
}


LLM_TOOL_SCHEMAS = [definition.schema for definition in TOOL_REGISTRY.values()]


def execute_tool(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Execute a registered deterministic AquaNexus tool."""
    if tool_name not in TOOL_REGISTRY:
        raise ValueError(f"Unknown AquaNexus tool: {tool_name!r}")
    if not isinstance(arguments, dict):
        raise ValueError(f"Tool arguments must be an object for {tool_name!r}.")

    definition = TOOL_REGISTRY[tool_name]
    missing = [name for name in definition.required if name not in arguments]
    if missing:
        raise ValueError(
            f"Missing required argument(s) for {tool_name!r}: {', '.join(missing)}"
        )

    allowed = set(definition.schema["function"]["parameters"]["properties"])
    unexpected = [name for name in arguments if name not in allowed]
    if unexpected:
        raise ValueError(
            f"Unexpected argument(s) for {tool_name!r}: {', '.join(unexpected)}"
        )

    coerced_arguments = _coerce_arguments(tool_name, arguments, definition.schema)
    return definition.function(**coerced_arguments)


def _coerce_arguments(
    tool_name: str, arguments: dict[str, Any], schema: dict[str, Any]
) -> dict[str, Any]:
    """Coerce LLM JSON values to declared tool argument types."""
    properties = schema["function"]["parameters"]["properties"]
    coerced: dict[str, Any] = {}
    for name, value in arguments.items():
        expected_type = properties[name]["type"]
        if expected_type == "integer":
            coerced[name] = _coerce_integer(tool_name, name, value)
        elif expected_type == "number":
            coerced[name] = _coerce_number(tool_name, name, value)
        else:
            coerced[name] = value
    return coerced


def _coerce_integer(tool_name: str, argument_name: str, value: Any) -> int:
    """Coerce one integer argument or raise a clear error."""
    if isinstance(value, bool):
        raise ValueError(f"Invalid integer for {tool_name}.{argument_name}: {value!r}")
    try:
        integer_value = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid integer for {tool_name}.{argument_name}: {value!r}") from exc
    if float(value) != integer_value:
        raise ValueError(f"Invalid integer for {tool_name}.{argument_name}: {value!r}")
    return integer_value


def _coerce_number(tool_name: str, argument_name: str, value: Any) -> float:
    """Coerce one numeric argument or raise a clear error."""
    if isinstance(value, bool):
        raise ValueError(f"Invalid number for {tool_name}.{argument_name}: {value!r}")
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid number for {tool_name}.{argument_name}: {value!r}") from exc
