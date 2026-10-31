from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.types import Send

from app.services import llm
from app.workflow.prompts import ORCH_SYSTEM
from app.workflow.schemas import Plan
from app.workflow.state import State
from app.workflow.utils import evidence_lines


def orchestrator_node(state: State) -> dict:
    mode = state.get("mode", "closed_book")
    forced_kind = "news_roundup" if mode == "open_book" else None
    evidence = state.get("evidence", [])

    plan = llm.structured(
        Plan,
        [
            SystemMessage(content=ORCH_SYSTEM),
            HumanMessage(
                content=(
                    f"Topic: {state['topic']}\n"
                    f"Mode: {mode}\n"
                    f"As-of: {state['as_of']} (recency_days={state['recency_days']})\n"
                    f"{'Force blog_kind=news_roundup' if forced_kind else ''}\n\n"
                    f"Evidence (title | url | date | snippet):\n"
                    f"{evidence_lines(evidence, snippet_chars=160, limit=16) or '(none)'}"
                )
            ),
        ],
        tier="main",
        max_tokens=3000,
    )

    if forced_kind:
        plan.blog_kind = "news_roundup"

    plan.tasks = plan.tasks[:9]
    if not plan.tasks:
        raise llm.LLMOutputError("The planner returned no sections.")
    for i, task in enumerate(plan.tasks, start=1):  # ids must be unique and ordered
        task.id = i

    return {"plan": plan}


def fanout(state: State):
    assert state["plan"] is not None
    return [
        Send(
            "worker",
            {
                "task": task.model_dump(),
                "topic": state["topic"],
                "mode": state["mode"],
                "as_of": state["as_of"],
                "recency_days": state["recency_days"],
                "plan": state["plan"].model_dump(),
                "evidence": [e.model_dump() for e in state.get("evidence", [])],
            },
        )
        for task in state["plan"].tasks
    ]
