from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import auth, blogs, health, media
from app.config import get_settings
from app.db import session as db
from app.db.models import Base
from app.services import runner


def create_app() -> FastAPI:
    s = get_settings()
    s.data_dir.mkdir(parents=True, exist_ok=True)
    s.images_dir.mkdir(parents=True, exist_ok=True)
    db.configure(s.effective_database_url)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        Base.metadata.create_all(db.engine)
        runner.mark_interrupted()
        yield

    app = FastAPI(title="AI Blog Studio", version="1.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=s.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(blogs.router)
    app.include_router(media.router)

    # In Docker the built frontend is served by this same process (one URL, no CORS).
    dist = Path(s.frontend_dist) if s.frontend_dist else None
    if dist and (dist / "index.html").is_file():
        root = dist.resolve()
        if (dist / "assets").is_dir():
            app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        def spa(full_path: str) -> FileResponse:
            if full_path.startswith(("api/", "media/")):
                raise HTTPException(404)
            candidate = (root / full_path).resolve()
            if full_path and candidate.is_file() and root in candidate.parents:
                return FileResponse(candidate)
            return FileResponse(root / "index.html")

    return app
