from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from app.api.auth import require_auth
from app.config import get_settings

router = APIRouter(tags=["media"], dependencies=[Depends(require_auth)])


@router.get("/media/{blog_id}/{filename}")
def media(blog_id: int, filename: str) -> FileResponse:
    if Path(filename).name != filename:
        raise HTTPException(404)
    path = get_settings().images_dir / str(blog_id) / filename
    if not path.is_file():
        raise HTTPException(404)
    return FileResponse(path, headers={"Cache-Control": "public, max-age=86400"})
