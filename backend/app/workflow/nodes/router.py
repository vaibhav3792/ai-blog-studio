from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage

from app.config import get_settings
from app.services import llm
from app.workflow.prompts import ROUTER_SYSTEM
from app.workflow.schemas import RouterDecision
from app.workflow.state import State


def router_node(state: State) -> dict:
    decision = llm.structured(
        RouterDecision,
        [
            SystemMessage(content=ROUTER_SYSTEM),
            HumanMessage(content=f"Topic: {state['topic']}\nAs-of date: {state['as_of']}"),
        ],
        tier="fast",
        max_tokens=800,
    )

    # Keep mode and needs_research consistent even if the model contradicts itself.
    mode = decision.mode
    needs_research = decision.needs_research
    if needs_research and mode == "closed_book":
        mode = "hybrid"
    if not needs_research:
        mode = "closed_book"

    recency_days = {"open_book": 7, "hybrid": 45}.get(mode, 3650)

    seen: set[str] = set()
    queries = []
    for q in decision.queries:
        q = q.strip()
        if q and q.lower() not in seen:
            seen.add(q.lower())
            queries.append(q)
    queries = queries[: get_settings().max_research_queries]

    if needs_research and not queries:
        queries = [state["topic"]]

    return {
        "needs_research": needs_research,
        "mode": mode,
        "queries": queries,
        "recency_days": recency_days,
    }


def route_next(state: State) -> str:
    return "research" if state["needs_research"] else "orchestrator"
