"""Tavily web search -> EvidenceItem list (no LLM involved, so nothing can be hallucinated)."""
from __future__ import annotations

from datetime import date
from email.utils import parsedate_to_datetime
from typing import List, Optional
from urllib.parse import urlparse

from app.config import get_settings
from app.workflow.schemas import EvidenceItem


class SearchUnavailable(RuntimeError):
    pass


def normalize_date(value: Optional[str]) -> Optional[str]:
    """Return YYYY-MM-DD or None. Never guesses."""
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10]).isoformat()
    except ValueError:
        pass
    try:
        return parsedate_to_datetime(value).date().isoformat()
    except (TypeError, ValueError):
        return None


def search_web(query: str, *, mode: str, recency_days: int, max_results: int) -> List[EvidenceItem]:
    s = get_settings()
    if not s.tavily_api_key:
        raise SearchUnavailable("TAVILY_API_KEY is not set")

    from tavily import TavilyClient

    client = TavilyClient(api_key=s.tavily_api_key)
    params: dict = {"query": query, "max_results": max_results, "search_depth": "basic"}
    if mode == "open_book":
        params.update(topic="news", days=recency_days)
    else:
        params.update(topic="general", time_range="year")

    response = client.search(**params)

    out: List[EvidenceItem] = []
    for r in response.get("results", []) or []:
        url = (r.get("url") or "").strip()
        if not url:
            continue
        out.append(
            EvidenceItem(
                title=(r.get("title") or url).strip(),
                url=url,
                published_at=normalize_date(r.get("published_date")),
                snippet=(r.get("content") or "").strip()[:300] or None,
                source=urlparse(url).netloc or None,
            )
        )
    return out
