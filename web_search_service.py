"""Server-side web search helper for Vapi tool calls."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from config import settings

logger = logging.getLogger(__name__)


class WebSearchError(RuntimeError):
    """Raised when web search provider request fails."""


async def run_web_search(query: str, max_results: int = 3) -> str:
    """Execute web search and return a short single-line summary."""
    provider = settings.web_search_provider.strip().lower()

    if provider == "tavily":
        return await _tavily_search(query=query, max_results=max_results)

    raise WebSearchError(
        f"Unsupported WEB_SEARCH_PROVIDER='{settings.web_search_provider}'. Supported: tavily."
    )


async def _tavily_search(query: str, max_results: int) -> str:
    api_key = settings.web_search_api_key
    if not api_key:
        raise WebSearchError("Missing WEB_SEARCH_API_KEY for Tavily web search.")

    payload = {
        "api_key": api_key,
        "query": query,
        "max_results": max(1, min(max_results, 5)),
        "search_depth": "advanced",
        "include_answer": True,
        "include_raw_content": False,
    }

    timeout = httpx.Timeout(settings.web_search_timeout_seconds)
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            response = await client.post("https://api.tavily.com/search", json=payload)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.error("Tavily HTTP error %s: %s", exc.response.status_code, exc.response.text)
            raise WebSearchError(
                f"Tavily returned {exc.response.status_code}: {exc.response.text}"
            ) from exc
        except httpx.RequestError as exc:
            logger.error("Tavily request error: %s", exc)
            raise WebSearchError(f"Could not reach Tavily: {exc}") from exc

    data = response.json()
    return _format_tavily_result(data=data)


def _format_tavily_result(data: dict[str, Any]) -> str:
    answer = str(data.get("answer") or "").strip()
    results = data.get("results")
    if not isinstance(results, list):
        results = []

    top_sources: list[str] = []
    for item in results[:3]:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        url = str(item.get("url") or "").strip()
        if not title and not url:
            continue
        if title and url:
            top_sources.append(f"{title} ({url})")
        elif url:
            top_sources.append(url)
        else:
            top_sources.append(title)

    if answer and top_sources:
        return f"{answer} Sources: {'; '.join(top_sources)}"
    if answer:
        return answer
    if top_sources:
        return f"Top sources: {'; '.join(top_sources)}"

    return "No relevant web results found."
