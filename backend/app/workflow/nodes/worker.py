from __future__ import annotations

import logging

from langchain_core.messages import HumanMessage, SystemMessage

from app.services import llm
from app.workflow.prompts import WORKER_SYSTEM
from app.workflow.schemas import EvidenceItem, Plan, Task
from app.workflow.utils import clean_section, evidence_lines, remove_no_source_notes, strip_unverified_links

log = logging.getLogger(__name__)


def worker_node(payload: dict) -> dict:
    task = Task(**payload["task"])
    plan = Plan(**payload["plan"])
    evidence = [EvidenceItem(**e) for e in payload.get("evidence", [])]

    bullets_text = "\n- " + "\n- ".join(task.bullets)

    prompt = (
        f"Blog title: {plan.blog_title}\n"
        f"Audience: {plan.audience}\n"
        f"Tone: {plan.tone}\n"
        f"Blog kind: {plan.blog_kind}\n"
        f"Constraints: {plan.constraints}\n"
        f"Topic: {payload['topic']}\n"
        f"Mode: {payload.get('mode')}\n"
        f"As-of: {payload.get('as_of')} (recency_days={payload.get('recency_days')})\n\n"
        f"Section title: {task.title}\n"
        f"Goal: {task.goal}\n"
        f"Target words: {task.target_words}\n"
        f"Tags: {task.tags}\n"
        f"requires_research: {task.requires_research}\n"
        f"requires_citations: {task.requires_citations}\n"
        f"requires_code: {task.requires_code}\n"
        f"Bullets:{bullets_text}\n\n"
        f"Evidence (ONLY cite these URLs):\n{evidence_lines(evidence, limit=20) or '(none)'}\n"
    )

    try:
        raw = llm.text(
            [SystemMessage(content=WORKER_SYSTEM), HumanMessage(content=prompt)],
            tier="main",
            max_tokens=2000,
        )
        if not raw:
            raise llm.LLMOutputError("empty section")
        section = remove_no_source_notes(
            strip_unverified_links(clean_section(raw, task.title), [e.url for e in evidence])
        )
        return {"sections": [(task.id, section)]}
    except llm.LLMConfigError:
        raise
    except Exception as exc:
        # One failed section should not throw away the other sections.
        log.warning("Section %s failed: %s", task.id, exc)
        placeholder = (
            f"## {task.title}\n\n"
            f"> This section could not be generated ({type(exc).__name__}). "
            f"Write it by hand or generate the post again.\n"
        )
        return {
            "sections": [(task.id, placeholder)],
            "warnings": [f"Section '{task.title}' failed to generate ({type(exc).__name__})."],
        }
