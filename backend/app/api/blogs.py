from __future__ import annotations

import asyncio
import io
import json
import shutil
import zipfile
from datetime import datetime, timezone
from typing import AsyncIterator, List

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.auth import require_auth
from app.config import get_settings
from app.db.models import Blog
from app.db.session import get_db
from app.schemas.blog import BlogDetail, BlogSummary, BlogUpdate, GenerateRequest
from app.services import runner
from app.workflow.utils import safe_slug

router = APIRouter(prefix="/api/blogs", tags=["blogs"], dependencies=[Depends(require_auth)])


def _words(md: str) -> int:
    return len(md.split())


def _utc(dt: datetime) -> datetime:
    # SQLite returns naive datetimes; they are stored as UTC, so say so (browsers parse the "Z").
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _summary(b: Blog) -> BlogSummary:
    return BlogSummary(
        id=b.id, topic=b.topic, title=b.title or b.topic, status=b.status, mode=b.mode,
        word_count=_words(b.markdown or ""), created_at=_utc(b.created_at), updated_at=_utc(b.updated_at),
    )


def _detail(b: Blog) -> BlogDetail:
    return BlogDetail(
        **_summary(b).model_dump(),
        markdown=b.markdown or "", error=b.error, plan=b.plan,
        evidence=b.evidence or [], warnings=b.warnings or [], images=b.images or [],
    )


def _get_or_404(db: Session, blog_id: int) -> Blog:
    blog = db.get(Blog, blog_id)
    if not blog:
        raise HTTPException(404, "Blog not found")
    return blog


@router.post("/generate", response_model=BlogSummary, status_code=202)
async def generate(body: GenerateRequest, db: Session = Depends(get_db)) -> BlogSummary:
    settings = get_settings()
    if not settings.groq_ready:
        raise HTTPException(400, "GROQ_API_KEY is not set. Add it to backend/.env and restart the server.")
    if settings.daily_generation_limit:
        day_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
        today = db.scalar(select(func.count()).select_from(Blog).where(Blog.created_at >= day_start)) or 0
        if today >= settings.daily_generation_limit:
            raise HTTPException(429, f"Daily limit of {settings.daily_generation_limit} posts reached. Try again tomorrow (UTC).")
    blog = Blog(topic=body.topic.strip(), status="queued", created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc))
    db.add(blog)
    db.commit()
    db.refresh(blog)
    runner.start(blog.id, blog.topic)
    return _summary(blog)


@router.get("", response_model=List[BlogSummary])
def list_blogs(db: Session = Depends(get_db)) -> List[BlogSummary]:
    rows = db.scalars(select(Blog).order_by(Blog.created_at.desc())).all()
    return [_summary(b) for b in rows]


@router.get("/{blog_id}", response_model=BlogDetail)
def get_blog(blog_id: int, db: Session = Depends(get_db)) -> BlogDetail:
    return _detail(_get_or_404(db, blog_id))


@router.patch("/{blog_id}", response_model=BlogDetail)
def update_blog(blog_id: int, body: BlogUpdate, db: Session = Depends(get_db)) -> BlogDetail:
    blog = _get_or_404(db, blog_id)
    if runner.is_running(blog_id):
        raise HTTPException(409, "This post is still being generated.")
    if body.title is not None:
        blog.title = body.title.strip()
    if body.markdown is not None:
        blog.markdown = body.markdown
    blog.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(blog)
    return _detail(blog)


@router.delete("/{blog_id}", status_code=204)
def delete_blog(blog_id: int, db: Session = Depends(get_db)) -> Response:
    blog = _get_or_404(db, blog_id)
    if runner.is_running(blog_id):
        raise HTTPException(409, "This post is still being generated.")
    db.delete(blog)
    db.commit()
    shutil.rmtree(get_settings().images_dir / str(blog_id), ignore_errors=True)
    return Response(status_code=204)


@router.get("/{blog_id}/events")
async def events(blog_id: int, db: Session = Depends(get_db)) -> StreamingResponse:
    blog = _get_or_404(db, blog_id)
    job = runner.get_job(blog_id)

    async def stream() -> AsyncIterator[str]:
        if job is None:
            # Not in memory (finished earlier or server restarted): answer from the database.
            if blog.status == "complete":
                event = {"type": "done", "blog_id": blog_id}
            else:
                event = {"type": "error", "message": blog.error or "This post is not being generated."}
            yield f"data: {json.dumps(event)}\n\n"
            return
        index = 0
        while True:
            async with job.cond:
                try:
                    await asyncio.wait_for(job.cond.wait_for(lambda: index < len(job.events)), timeout=15)
                except asyncio.TimeoutError:
                    pass
            if index >= len(job.events):
                yield ": keepalive\n\n"
                continue
            while index < len(job.events):
                event = job.events[index]
                index += 1
                yield f"data: {json.dumps(event)}\n\n"
                if event["type"] in ("done", "error"):
                    return

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/{blog_id}/export")
def export_blog(blog_id: int, format: str = Query("md", pattern="^(md|zip)$"), db: Session = Depends(get_db)) -> Response:
    blog = _get_or_404(db, blog_id)
    slug = safe_slug(blog.title or blog.topic)
    if format == "md":
        return Response(
            blog.markdown or "", media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{slug}.md"'},
        )
    buf = io.BytesIO()
    img_dir = get_settings().images_dir / str(blog_id)
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(f"{slug}/{slug}.md", blog.markdown or "")
        for name in blog.images or []:
            path = img_dir / name
            if path.is_file():
                z.write(path, f"{slug}/images/{name}")
    return Response(
        buf.getvalue(), media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{slug}.zip"'},
    )
