"""
Vapi REST API Service
Fires outbound calls with dynamically generated system prompts.
"""

import logging
from typing import Any, TypedDict

import httpx

from config import settings

logger = logging.getLogger(__name__)

VAPI_BASE = "https://api.vapi.ai"
CALL_TIMEOUT = 15.0


class CallResult(TypedDict):
    call_id: str
    status: str
    phone_number: str


def build_assistant_overrides(
    system_prompt: str,
    first_message: str,
    voice_id: str | None = None,
    speaking_speed: float = 1.0,
) -> dict[str, Any]:
    """Build dynamic assistant configuration shared by phone and browser flows."""
    language_enforcement = (
        "Language policy: Always reply in the same language as the customer's last utterance. "
        "Support English, Hindi, and Hinglish naturally. "
        "If the customer switches language, switch immediately on the next turn. "
        "If unsure, ask once whether they prefer English or Hindi, then continue in that language."
    )
    effective_system_prompt = f"{system_prompt.strip()}\n\n{language_enforcement}".strip()

    return {
        "firstMessage": first_message,
        "firstMessageMode": "assistant-speaks-first",
        "interruptionsEnabled": True,
        "stopSpeakingPlan": {
            "numWords": 0,
            "voiceSeconds": 0,
            "backoffSeconds": 0.1,
        },
        "model": {
    "provider": "openai",
    "model": "gpt-5.4-mini", 
    "systemPrompt": effective_system_prompt,
    "maxTokens": 350,        # Keep tokens lower for faster voice response
    "temperature": 0.4,      # Lower temperature ensures higher factual accuracy
},
        "voice": {
            "provider": "11labs",
            "voiceId": voice_id or settings.elevenlabs_voice_id,
            "model": "eleven_turbo_v2_5",
            "stability": 0.5,
            "similarityBoost": 0.75,
            "style": 0.1,
            "useSpeakerBoost": True,
            "optimizeStreamingLatency": 4,
            "speed": round(max(0.7, min(1.3, speaking_speed)), 2),
        },
        "transcriber": {
            "provider": "deepgram",
            "model": "nova-3",
            "language": "multi",
            "confidenceThreshold": 0.4,
        },
        "endCallFunctionEnabled": True,
        "recordingEnabled": True,
        "silenceTimeoutSeconds": 20,
        "maxDurationSeconds": 1800,
    }


def _mask_phone(phone_number: str) -> str:
    """Hide PII in logs while preserving basic traceability."""
    if len(phone_number) <= 4:
        return "***"
    return f"{phone_number[:3]}***{phone_number[-2:]}"


async def create_outbound_call(
    phone_number: str,
    system_prompt: str,
    first_message: str,
    voice_id: str | None = None,
    speaking_speed: float = 1.0,
    metadata: dict[str, Any] | None = None,
) -> CallResult:
    """
    Creates an outbound Vapi call with the GPT-generated system prompt
    injected via assistantOverrides.
    """
    if not settings.vapi_assistant_id:
        raise RuntimeError("Missing VAPI_ASSISTANT_ID. Set it in your .env file.")

    payload = {
        "assistantId": settings.vapi_assistant_id,
        "phoneNumberId": settings.vapi_phone_number_id,
        "customer": {"number": phone_number},
        "assistantOverrides": build_assistant_overrides(
            system_prompt=system_prompt,
            first_message=first_message,
            voice_id=voice_id,
            speaking_speed=speaking_speed,
        ),
    }
    if metadata:
        payload["metadata"] = metadata

    assistant_overrides = payload.get("assistantOverrides", {})
    voice = assistant_overrides.get("voice", {}) if isinstance(assistant_overrides, dict) else {}
    model = assistant_overrides.get("model", {}) if isinstance(assistant_overrides, dict) else {}
    logger.info(
        "Preparing Vapi call payload: voice.provider=%s voice.model=%s model.provider=%s model.model=%s",
        voice.get("provider"),
        voice.get("model"),
        model.get("provider"),
        model.get("model"),
    )

    headers = {
        "Authorization": f"Bearer {settings.vapi_api_key}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=CALL_TIMEOUT) as client:
        try:
            resp = await client.post(
                f"{VAPI_BASE}/call",
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()
            call_id = data.get("id", "unknown")
            logger.info("Vapi call created: %s → %s", call_id, _mask_phone(phone_number))
            return CallResult(call_id=call_id, status="dialing", phone_number=phone_number)

        except httpx.HTTPStatusError as exc:
            logger.error("Vapi API error %s: %s", exc.response.status_code, exc.response.text)
            raise RuntimeError(
                f"Vapi returned {exc.response.status_code}: {exc.response.text}"
            ) from exc

        except httpx.RequestError as exc:
            logger.error("Vapi request failed: %s", exc)
            raise RuntimeError(f"Could not reach Vapi API: {exc}") from exc


async def fetch_call_details(call_id: str) -> dict[str, Any]:
    """Fetches a single Vapi call object including messages/transcript artifacts."""
    headers = {
        "Authorization": f"Bearer {settings.vapi_api_key}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=CALL_TIMEOUT) as client:
        try:
            resp = await client.get(
                f"{VAPI_BASE}/call/{call_id}",
                headers=headers,
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as exc:
            logger.error("Vapi call fetch error %s: %s", exc.response.status_code, exc.response.text)
            raise RuntimeError(
                f"Vapi returned {exc.response.status_code}: {exc.response.text}"
            ) from exc
        except httpx.RequestError as exc:
            logger.error("Vapi call fetch request failed: %s", exc)
            raise RuntimeError(f"Could not reach Vapi API: {exc}") from exc


async def update_assistant_webhook(
    assistant_id: str,
    server_url: str,
    server_messages: list[str],
) -> dict[str, Any]:
    """Updates assistant server webhook URL + allowed server messages."""
    headers = {
        "Authorization": f"Bearer {settings.vapi_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "server": {"url": server_url},
        "serverMessages": server_messages,
    }

    async with httpx.AsyncClient(timeout=CALL_TIMEOUT) as client:
        try:
            resp = await client.patch(
                f"{VAPI_BASE}/assistant/{assistant_id}",
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()
            logger.info("Vapi assistant webhook updated: assistant=%s url=%s", assistant_id, server_url)
            return data
        except httpx.HTTPStatusError as exc:
            logger.error(
                "Vapi assistant update error %s: %s",
                exc.response.status_code,
                exc.response.text,
            )
            raise RuntimeError(
                f"Vapi returned {exc.response.status_code}: {exc.response.text}"
            ) from exc
        except httpx.RequestError as exc:
            logger.error("Vapi assistant update request failed: %s", exc)
            raise RuntimeError(f"Could not reach Vapi API: {exc}") from exc
