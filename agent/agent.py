"""Groq tool-calling AquaNexus Agent v1."""

from __future__ import annotations

import json
from typing import Any

from agent.config import ConfigurationError, load_config
from agent.router import SUPPORTED_MODULES, identify_candidate_modules, unsupported_module_result
from agent.tools import LLM_TOOL_SCHEMAS, execute_tool


MAX_TOOL_ROUNDS = 6
SYSTEM_PROMPT = """You are an ocean-intelligence assistant.
Use tools for scientific/data claims whenever relevant.
Never invent ARGO measurements.
Clearly distinguish evidence from interpretation.
Pressure is in dbar; do not automatically claim it is exact depth in meters.
Thermocline detection currently uses a simplified heuristic.
Historical anomaly analysis is a practical baseline, not formal climatology/statistical significance.
If data is unavailable, say so.
Never claim ARGO directly detects oil spills, minerals, or submarine cable damage.
Prefer concise evidence-based answers.
Return concise prose for the user; structured evidence is handled by the application."""


def run_agent(user_message: str) -> dict[str, Any]:
    """Run the AquaNexus Groq tool-calling agent for one user message."""
    candidate_modules = identify_candidate_modules(user_message)
    unsupported_modules = [
        module for module in candidate_modules if module not in SUPPORTED_MODULES
    ]
    if unsupported_modules:
        return unsupported_module_result(candidate_modules)

    try:
        config = load_config()
    except ConfigurationError as exc:
        return _error_response("configuration_error", str(exc), candidate_modules)

    try:
        from groq import Groq
    except ImportError:
        return _error_response(
            "configuration_error",
            "The groq Python package is not installed.",
            candidate_modules,
        )

    client = Groq(api_key=config.groq_api_key)
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
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
            tool_calls = getattr(message, "tool_calls", None)

            messages.append(_assistant_message_to_dict(message))
            if not tool_calls:
                return _success_response(
                    text=message.content or "",
                    modules_used=["argo"] if evidence else [],
                    tools_used=tools_used,
                    evidence=evidence,
                )

            for tool_call in tool_calls:
                tool_name = tool_call.function.name
                arguments = _parse_tool_arguments(tool_call.function.arguments)
                result = execute_tool(tool_name, arguments)
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
                        "content": json.dumps(result),
                    }
                )

        return _error_response(
            "max_tool_rounds_exceeded",
            f"Stopped after {MAX_TOOL_ROUNDS} tool-calling rounds.",
            ["argo"],
            tools_used=tools_used,
            evidence=evidence,
        )
    except ValueError as exc:
        return _error_response(
            "tool_error",
            str(exc),
            ["argo"],
            tools_used=tools_used,
            evidence=evidence,
        )
    except Exception as exc:
        return _error_response(
            "provider_or_runtime_error",
            str(exc),
            ["argo"] if "argo" in candidate_modules else [],
            tools_used=tools_used,
            evidence=evidence,
        )


def _parse_tool_arguments(raw_arguments: str | None) -> dict[str, Any]:
    """Parse JSON tool arguments from the model."""
    if not raw_arguments:
        return {}
    try:
        arguments = json.loads(raw_arguments)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid tool arguments JSON: {raw_arguments!r}") from exc
    if not isinstance(arguments, dict):
        raise ValueError("Tool arguments must decode to an object.")
    return arguments


def _assistant_message_to_dict(message: Any) -> dict[str, Any]:
    """Convert a Groq assistant message into a chat message dictionary."""
    message_dict: dict[str, Any] = {
        "role": "assistant",
        "content": message.content,
    }
    tool_calls = getattr(message, "tool_calls", None)
    if tool_calls:
        message_dict["tool_calls"] = [
            {
                "id": tool_call.id,
                "type": "function",
                "function": {
                    "name": tool_call.function.name,
                    "arguments": tool_call.function.arguments,
                },
            }
            for tool_call in tool_calls
        ]
    return message_dict


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
    """Return structured error information without fabricating an answer."""
    return {
        "text": message,
        "modules_used": [module for module in modules if module in SUPPORTED_MODULES],
        "tools_used": tools_used or [],
        "evidence": evidence or [{"status": error_type, "message": message}],
        "chart_data": None,
        "map_data": None,
    }
