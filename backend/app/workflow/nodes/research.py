from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from typing import Dict, List, Optional

from app.config import get_settings
from app.services import search
from app.workflow.schemas import EvidenceItem
from app.workflow.state import State


def _iso_to_date(s: Optional[str]) -> Optional[date]:
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def research_node(state: State) -> dict:
    s = get_settings()
    if not s.tavily_ready:
        return {
            "evidence": [],
            "warnings": ["Web research skipped: TAVILY_API_KEY is not set, so this draft uses model knowledge only."],
        }

    queries = (state.get("queries") or [])[: s.max_research_queries]
    mode = state.get("mode", "hybrid")
    recency_days = int(state["recency_days"])
    warnings: List[str] = []

    def run(q: str) -> List[EvidenceItem]:
        return search.search_web(q, mode=mode, recency_days=recency_days, max_results=s.results_per_query)

    by_url: Dict[str, EvidenceItem] = {}
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [(q, pool.submit(run, q)) for q in queries]
        for q, fut in futures:
            try:
                for item in fut.result():
                    by_url.setdefault(item.url, item)
            except Exception as exc:  # one bad query must not sink the run
                warnings.append(f"Search failed for '{q}' ({type(exc).__name__}).")

    evidence = list(by_url.values())

    if mode == "open_book":
        cutoff = date.fromisoformat(state["as_of"]) - timedelta(days=recency_days)
        evidence = [e for e in evidence if (d := _iso_to_date(e.published_at)) and d >= cutoff]

    evidence = evidence[: s.max_evidence]
    if not evidence:
        warnings.append("No usable sources were found, so the draft avoids claims that need citations.")

    return {"evidence": evidence, "warnings": warnings}
