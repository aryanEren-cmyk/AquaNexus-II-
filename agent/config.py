"""Configuration loading for AquaNexus Agent v1."""

from __future__ import annotations

import os
from dataclasses import dataclass


DEFAULT_GROQ_MODEL = "openai/gpt-oss-120b"


class ConfigurationError(RuntimeError):
    """Raised when required agent configuration is unavailable."""


@dataclass(frozen=True)
class AgentConfig:
    """Runtime configuration for the Groq-backed agent."""

    groq_api_key: str
    groq_model: str = DEFAULT_GROQ_MODEL


def load_config() -> AgentConfig:
    """Load agent configuration from environment variables."""
    _load_dotenv_if_available()

    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ConfigurationError(
            "Missing GROQ_API_KEY. Set it in the environment or in a local .env file."
        )

    return AgentConfig(
        groq_api_key=api_key,
        groq_model=os.getenv("GROQ_MODEL", DEFAULT_GROQ_MODEL),
    )


def _load_dotenv_if_available() -> None:
    """Load a local .env file when python-dotenv is installed."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return

    load_dotenv()
