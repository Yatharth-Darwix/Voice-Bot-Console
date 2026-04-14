"""Request and response models for call/session/webhook routes."""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field, field_validator

PHONE_PATTERN = re.compile(r"^\+[1-9]\d{7,14}$")


class PromptGenerationRequest(BaseModel):
    industry: str = Field(..., min_length=2, max_length=100, description="Industry sector")
    company: str = Field(..., min_length=2, max_length=100, description="Company name")
    use_case: str = Field(..., min_length=2, max_length=100, description="Purpose of the call")
    persona: str = Field(..., min_length=5, max_length=300, description="Agent personality and tone")
    guardrails: str = Field(..., min_length=5, description="Rules the agent must follow")
    call_flow: str = Field(default="", description="Optional full call script / instructions")
    query_handling: str = Field(default="", description="Rules for handling specific customer queries")
    speaking_speed: float = Field(
        default=1.0,
        ge=0.7,
        le=1.3,
        description="ElevenLabs TTS speed (0.7 slow – 1.3 brisk)",
    )
    agent_name: str = Field(default="Aisha", min_length=1, max_length=50, description="Name of the AI agent")
    voice_gender: str = Field(default="female", description="Gender of the voice agent (male/female)")
    start_language: str = Field(
        default="english",
        description="Language for the very first greeting only (english/hindi)",
    )
    customer_name: str = Field(default="Customer", min_length=1, max_length=50, description="Name of the customer")
    customer_gender: str = Field(default="male", description="Gender of the customer (male/female)")

    @field_validator("industry", "company", "use_case", "persona", "guardrails", "call_flow", "query_handling")
    @classmethod
    def sanitise_input(cls, value: str) -> str:
        return value.replace("```", "").replace("{{", "").replace("}}", "").strip()

    @field_validator("start_language")
    @classmethod
    def validate_start_language(cls, value: str) -> str:
        cleaned = value.strip().lower()
        if cleaned not in {"english", "hindi"}:
            raise ValueError("start_language must be english or hindi")
        return cleaned


class InitiateCallRequest(PromptGenerationRequest):
    phone_number: str = Field(..., description="E.164 format phone number, e.g. +919876543210")

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, value: str) -> str:
        cleaned = value.replace(" ", "").replace("-", "")
        if not PHONE_PATTERN.match(cleaned):
            raise ValueError("Phone number must be in E.164 format, e.g. +919876543210")
        return cleaned


class PrepareBrowserBotRequest(PromptGenerationRequest):
    """Request to generate a browser-session bot config."""


class PrepareBrowserBotResponse(BaseModel):
    session_id: str
    system_prompt: str
    first_message: str
    assistant_id: str
    assistant_overrides: dict[str, Any]


class BindCallRequest(BaseModel):
    call_id: str = Field(..., min_length=2, max_length=120)


class AppendSessionEventRequest(BaseModel):
    role: str = Field(..., min_length=2, max_length=40)
    text: str = Field(..., min_length=1, max_length=4000)
    source: str = Field(default="frontend_browser", min_length=2, max_length=60)
    event_type: str = Field(default="message", min_length=2, max_length=60)
    metadata: dict[str, Any] | None = None


class ConfigureWebhookRequest(BaseModel):
    public_base_url: str | None = Field(
        default=None,
        description="Optional public base URL (e.g. https://xxxx.ngrok-free.app).",
    )
    assistant_id: str | None = Field(
        default=None,
        description="Optional assistant id. Falls back to VAPI_ASSISTANT_ID.",
    )
    server_messages: list[str] | None = Field(
        default=None,
        description="Optional override for assistant serverMessages.",
    )


class ConfigureWebhookResponse(BaseModel):
    assistant_id: str
    webhook_url: str
    server_messages: list[str]


class SessionSummaryResponse(BaseModel):
    session_id: str
    mode: str
    status: str
    call_id: str | None
    industry: str
    company: str
    use_case: str
    created_at: str
    updated_at: str


class SessionListResponse(BaseModel):
    sessions: list[SessionSummaryResponse]


class SessionMessage(BaseModel):
    at: str
    role: str
    text: str
    source: str
    event_type: str
    metadata: dict[str, Any] | None = None


class SessionDetailResponse(SessionSummaryResponse):
    persona: str
    guardrails: str
    system_prompt: str
    first_message: str
    messages: list[SessionMessage]
    vapi_fetch_error: str | None = None
