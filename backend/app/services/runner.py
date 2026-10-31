"""Runs the LangGraph workflow in the background and streams progress to SSE clients."""
from __future__ import annotations

import asyncio
import logging
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional

import groq

from app.config import get_settings
from app.db import session as db
from app.db.models import Blog
from app.services.llm import LLMConfigError
from app.workflow.graph import build_graph

log = logging.getLogger(__name__)

MAX_JOBS_KEPT = 50


@dataclass
class Job:
    blog_id: int
    events: List[dict] = field(default_factory=list)
    cond: asyncio.Condition = field(default_factory=asyncio.Condition)
    finished: bool = False
    task: Optional[asyncio.Task] = None

    async def publish(self, event: dict) -> None:
        async with self.cond:
            self.events.append(event)
            if event["type"] in ("done", "error"):
                self.finished = True
            self.cond.notify_all()


_jobs: "OrderedDict[int, Job]" = OrderedDict()
_graph = None


def get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph


def reset() -> None:
    """Test helper."""
    global _graph
    _jobs.clear()
    _graph = None


def get_job(blog_id: int) -> Optional[Job]:
    return _jobs.get(blog_id)


def is_running(blog_id: int) -> bool:
    job = _jobs.get(blog_id)
    return bool(job and not job.finished)


def mark_interrupted() -> None:
    """On startup: runs that were in flight when the server stopped cannot be resumed."""
    with db.session_scope() as session:
        for blog in session.query(Blog).filter(Blog.status.in_(["queued", "running"])):
            blog.status = "failed"
            blog.error = "The server restarted while this post was being generated. Generate it again."


def start(blog_id: int, topic: str) -> Job:
    job = Job(blog_id=blog_id)
    _jobs[blog_id] = job
    while len(_jobs) > MAX_JOBS_KEPT:
        _jobs.popitem(last=False)
    job.task = asyncio.create_task(_run(job, topic))
    return job


def friendly_error(exc: BaseException) -> str:
    if isinstance(exc, LLMConfigError):
        return str(exc)
    if isinstance(exc, groq.RateLimitError):
        return (
            "Groq's free-tier rate limit was hit. Wait a minute and generate again, "
            "or lower MAX_CONCURRENCY in backend/.env."
        )
    if isinstance(exc, groq.AuthenticationError):
        return "Groq rejected the API key. Check GROQ_API_KEY in backend/.env."
    if isinstance(exc, groq.APIConnectionError):
        return "Could not reach Groq. Check your internet connection and try again."
    return f"{type(exc).__name__}: {exc}"


def _event_for(node: str, delta: Dict[str, Any], progress: Dict[str, int]) -> Optional[dict]:
    if node == "router":
        mode = delta.get("mode")
        if delta.get("needs_research"):
            msg = f"Mode {mode}. {len(delta.get('queries') or [])} search queries planned."
        else:
            msg = "Mode closed_book. No web research needed."
        return {"type": "node", "node": node, "message": msg,
                "data": {"mode": mode, "needs_research": delta.get("needs_research"), "queries": delta.get("queries", [])}}
    if node == "research":
        n = len(delta.get("evidence") or [])
        return {"type": "node", "node": node, "message": f"Collected {n} sources.", "data": {"sources": n}}
    if node == "orchestrator":
        plan = delta["plan"]
        progress["total"] = len(plan.tasks)
        return {"type": "node", "node": node, "message": f"Outline ready: {len(plan.tasks)} sections.",
                "data": {"title": plan.blog_title,
                         "sections": [{"id": t.id, "title": t.title} for t in plan.tasks]}}
    if node == "worker":
        progress["done"] += 1
        task_id = delta["sections"][0][0]
        return {"type": "node", "node": node,
                "message": f"Wrote section {progress['done']} of {progress['total']}.",
                "data": {"task_id": task_id, "done": progress["done"], "total": progress["total"]}}
    if node == "merge_content":
        return {"type": "node", "node": node, "message": "Sections merged.", "data": {}}
    if node == "decide_images":
        n = len(delta.get("image_specs") or [])
        return {"type": "node", "node": node, "message": f"{n} visuals planned.", "data": {"images": n}}
    if node == "generate_and_place_images":
        n = int(delta.get("visuals") or 0)
        return {"type": "node", "node": node, "message": f"{n} visuals added.", "data": {"visuals": n}}
    return None


async def _run(job: Job, topic: str) -> None:
    s = get_settings()
    blog_id = job.blog_id
    progress = {"done": 0, "total": 0}
    final_state: Dict[str, Any] = {}

    with db.session_scope() as session:
        blog = session.get(Blog, blog_id)
        blog.status = "running"

    await job.publish({"type": "started", "message": "Started."})

    inputs = {
        "topic": topic,
        "run_id": str(blog_id),
        "as_of": date.today().isoformat(),
        "sections": [],
        "warnings": [],
    }
    config = {"max_concurrency": s.max_concurrency, "recursion_limit": 60}

    try:
        async for mode, chunk in get_graph().astream(inputs, config=config, stream_mode=["updates", "values"]):
            if mode == "values":
                final_state = chunk
                continue
            for node, delta in chunk.items():
                if node.startswith("__"):
                    continue
                event = _event_for(node, delta or {}, progress)
                if event:
                    await job.publish(event)
                for w in (delta or {}).get("warnings", []) or []:
                    await job.publish({"type": "warning", "message": w})

        plan = final_state.get("plan")
        with db.session_scope() as session:
            blog = session.get(Blog, blog_id)
            blog.status = "complete"
            blog.title = plan.blog_title if plan else topic
            blog.markdown = final_state.get("final", "")
            blog.mode = final_state.get("mode")
            blog.plan = plan.model_dump() if plan else None
            blog.evidence = [e.model_dump() for e in final_state.get("evidence", [])]
            blog.warnings = list(final_state.get("warnings", []))
            blog.images = list(final_state.get("images", []))
            blog.error = None
        await job.publish({"type": "done", "blog_id": blog_id})
    except Exception as exc:  # noqa: BLE001 - everything must end in a terminal event
        log.exception("Run %s failed", blog_id)
        message = friendly_error(exc)
        with db.session_scope() as session:
            blog = session.get(Blog, blog_id)
            if blog:
                blog.status = "failed"
                blog.error = message
        await job.publish({"type": "error", "message": message})
