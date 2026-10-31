"""Tavily web search -> EvidenceItem list (no LLM involved, so nothing can be hallucinated)."""
from __future__ import annotations

from datetime import date
from email.utils import parsedate_to_datetime
from typing import TYPE_CHECKING, List, Optional
from urllib.parse import urlparse

from app.config import get_settings
from app.workflow.schemas import EvidenceItem

if TYPE_CHECKING:
    import httpx


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


def drop_dead_links(
    items: List[EvidenceItem], *, client: "httpx.Client | None" = None, timeout: float = 6.0, workers: int = 8
) -> List[EvidenceItem]:
    """Remove sources whose page is gone (404/410) or whose host does not exist.

    Search engines sometimes return URLs that have since been deleted. Anything uncertain
    (timeouts, 403 bot blocks, server errors) is kept, so only clearly dead pages are dropped.
    """
    import httpx
    from concurrent.futures import ThreadPoolExecutor

    http = client or httpx.Client(
        timeout=timeout,
        follow_redirects=True,
        headers={"User-Agent": "Mozilla/5.0 (compatible; AIBlogStudio/1.1)"},
    )

    def alive(url: str) -> bool:
        try:
            status = http.head(url).status_code
            if status >= 400:  # some servers mishandle HEAD, so confirm with a GET
                with http.stream("GET", url) as resp:
                    status = resp.status_code
            return status not in (404, 410)
        except httpx.ConnectError:
            return False
        except httpx.HTTPError:
            return True

    try:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            flags = list(pool.map(alive, [e.url for e in items]))
    finally:
        if client is None:
            http.close()
    return [e for e, ok in zip(items, flags) if ok]
