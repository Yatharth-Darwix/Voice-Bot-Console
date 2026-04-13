"""Webhook configuration helpers (ngrok discovery + assistant webhook sync)."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
from fastapi import HTTPException


def normalize_public_base_url(url: str) -> str:
    return url.strip().rstrip("/")


async def detect_ngrok_public_url(ngrok_local_api_url: str) -> str:
    timeout = httpx.Timeout(5.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            response = await client.get(ngrok_local_api_url)
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPError as exc:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Could not query local ngrok API at {ngrok_local_api_url}. "
                    "Start ngrok or provide public_base_url."
                ),
            ) from exc

    tunnels = payload.get("tunnels")
    if not isinstance(tunnels, list):
        raise HTTPException(
            status_code=400,
            detail="ngrok API did not return tunnel list. Provide public_base_url explicitly.",
        )

    https_tunnel: str | None = None
    http_tunnel: str | None = None
    for tunnel in tunnels:
        if not isinstance(tunnel, dict):
            continue
        public_url = tunnel.get("public_url")
        if not isinstance(public_url, str) or not public_url:
            continue
        if public_url.startswith("https://") and not https_tunnel:
            https_tunnel = public_url
        if public_url.startswith("http://") and not http_tunnel:
            http_tunnel = public_url

    selected = https_tunnel or http_tunnel
    if not selected:
        raise HTTPException(
            status_code=400,
            detail="No ngrok public tunnel found. Start ngrok or provide public_base_url.",
        )

    return normalize_public_base_url(selected)


async def configure_webhook_from_base_url(
    *,
    public_base_url: str,
    assistant_id: str,
    server_messages: list[str],
    update_assistant_webhook: Callable[..., Awaitable[Any]],
) -> str:
    normalized = normalize_public_base_url(public_base_url)
    webhook_url = f"{normalized}/webhook/vapi/server"

    await update_assistant_webhook(
        assistant_id=assistant_id,
        server_url=webhook_url,
        server_messages=server_messages,
    )
    return webhook_url


async def auto_configure_webhook_from_env(
    *,
    env_public_base_url: str | None,
    assistant_id: str | None,
    server_messages: list[str],
    update_assistant_webhook: Callable[..., Awaitable[Any]],
    logger: logging.Logger,
) -> tuple[str | None, str | None]:
    public_base_url = (env_public_base_url or "").strip()
    if not public_base_url:
        return None, None

    resolved_assistant_id = (assistant_id or "").strip()
    if not resolved_assistant_id:
        error = "Missing assistant id. Set VAPI_ASSISTANT_ID."
        logger.error("Auto webhook sync failed: %s", error)
        return None, error

    try:
        webhook_url = await configure_webhook_from_base_url(
            public_base_url=public_base_url,
            assistant_id=resolved_assistant_id,
            server_messages=server_messages,
            update_assistant_webhook=update_assistant_webhook,
        )
        return webhook_url, None
    except RuntimeError as exc:
        logger.error("Auto webhook sync failed: %s", exc)
        return None, str(exc)
