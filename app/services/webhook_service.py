"""Webhook orchestration service functions."""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import HTTPException

from web_search_service import WebSearchError, run_web_search


def extract_tool_calls(message: dict[str, Any]) -> list[dict[str, Any]]:
    raw = message.get("toolCallList")
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]

    fallback = message.get("toolCalls")
    if isinstance(fallback, list):
        return [item for item in fallback if isinstance(item, dict)]

    return []


async def handle_tool_calls(message: dict[str, Any]) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    tool_calls = extract_tool_calls(message)

    if not tool_calls:
        return {
            "results": [],
            "error": "No toolCallList found in tool-calls message",
        }

    for call in tool_calls:
        tool_call_id = str(call.get("id") or "")
        function_block = call.get("function")
        if not isinstance(function_block, dict):
            results.append(
                {
                    "toolCallId": tool_call_id,
                    "name": "unknown",
                    "error": "Missing function payload",
                }
            )
            continue

        function_name = str(function_block.get("name") or "unknown")
        raw_arguments = function_block.get("arguments")
        parsed_args: dict[str, Any] = {}

        if isinstance(raw_arguments, str) and raw_arguments.strip():
            try:
                maybe_args = json.loads(raw_arguments)
                if isinstance(maybe_args, dict):
                    parsed_args = maybe_args
            except json.JSONDecodeError:
                parsed_args = {}
        elif isinstance(raw_arguments, dict):
            parsed_args = raw_arguments

        if function_name != "web_search":
            results.append(
                {
                    "toolCallId": tool_call_id,
                    "name": function_name,
                    "error": f"Unsupported tool '{function_name}'",
                }
            )
            continue

        query = str(parsed_args.get("query") or parsed_args.get("q") or "").strip()
        max_results = parsed_args.get("max_results", 3)

        try:
            max_results_int = int(max_results)
        except (TypeError, ValueError):
            max_results_int = 3

        if not query:
            results.append(
                {
                    "toolCallId": tool_call_id,
                    "name": function_name,
                    "error": "Missing 'query' argument",
                }
            )
            continue

        try:
            result_text = await run_web_search(query=query, max_results=max_results_int)
            results.append(
                {
                    "toolCallId": tool_call_id,
                    "name": function_name,
                    "result": result_text.replace("\n", " ").strip(),
                }
            )
        except WebSearchError as exc:
            results.append(
                {
                    "toolCallId": tool_call_id,
                    "name": function_name,
                    "error": str(exc),
                }
            )

    return {"results": results}


async def process_vapi_server_message(
    *,
    payload: dict[str, Any],
    source: str,
    logger: logging.Logger,
    session_store: Any,
    extract_call_id: Callable[[dict[str, Any], dict[str, Any] | None], str | None],
    resolve_session_id: Callable[[dict[str, Any], dict[str, Any] | None, str | None], str | None],
    persist_server_message: Callable[[str, str, dict[str, Any], str], None],
    clear_model_output_state: Callable[[str], None],
    tool_call_handler: Callable[[dict[str, Any]], Awaitable[dict[str, Any]]] = handle_tool_calls,
) -> dict[str, Any]:
    message = payload.get("message")
    if not isinstance(message, dict):
        direct_type = payload.get("type")
        if isinstance(direct_type, str) and direct_type:
            message = payload

    if not isinstance(message, dict):
        raise HTTPException(status_code=400, detail="Invalid payload: missing message object")

    event_type = str(message.get("type") or "unknown")
    call_id = extract_call_id(message, payload)
    session_id = resolve_session_id(message, payload, call_id)

    logger.info("Vapi server message: type=%s call_id=%s session_id=%s", event_type, call_id, session_id)

    if event_type == "tool-calls":
        tool_response = await tool_call_handler(message)
        if session_id:
            session_store.append_transcript_event(
                session_id=session_id,
                role="event",
                text="Tool call processed",
                source=source,
                event_type="tool-calls",
                metadata=message,
            )
        return tool_response

    if session_id:
        if event_type in {"status-update", "call-started"}:
            status = str(message.get("status") or "").lower()
            if status in {"in-progress", "in_progress"} or event_type == "call-started":
                session_store.set_status(session_id, "in_progress")
            elif status == "ended":
                session_store.set_status(session_id, "ended")
                clear_model_output_state(session_id)
            else:
                session_store.set_status(session_id, status or "in_progress")

        if event_type in {"call-ended", "hang"}:
            session_store.set_status(session_id, "ended")
            clear_model_output_state(session_id)

        persist_server_message(session_id=session_id, event_type=event_type, message=message, source=source)

    return {"received": True, "event_type": event_type, "session_id": session_id, "call_id": call_id}
