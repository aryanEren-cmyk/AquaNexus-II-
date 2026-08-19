"""Pydantic request schemas for the AquaNexus API."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class ChatRequest(BaseModel):
    """Request payload for the LLM-backed chat endpoint."""

    message: str = Field(..., max_length=4000)

    @field_validator("message")
    @classmethod
    def validate_message(cls, value: str) -> str:
        message = value.strip()
        if not message:
            raise ValueError("message cannot be empty")
        return message


class OceanConditionsRequest(BaseModel):
    """Request payload for deterministic location-based ocean conditions."""

    location: str
    depth_m: float = 0
    argo_radius_km: float = 300

    @field_validator("location")
    @classmethod
    def validate_location(cls, value: str) -> str:
        location = value.strip()
        if not location:
            raise ValueError("location cannot be empty")
        return location

    @field_validator("depth_m")
    @classmethod
    def validate_depth_m(cls, value: float) -> float:
        if value < 0:
            raise ValueError("depth_m must be greater than or equal to 0")
        return value

    @field_validator("argo_radius_km")
    @classmethod
    def validate_argo_radius_km(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("argo_radius_km must be greater than 0")
        return value
