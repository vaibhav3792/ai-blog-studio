from fastapi import APIRouter, Request

from app.api.auth import is_authed
from app.config import get_settings

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
def health(request: Request) -> dict:
    s = get_settings()
    return {
        "status": "ok",
        "providers": {
            "groq": s.groq_ready,
            "tavily": s.tavily_ready,
            "cloudflare_images": s.images_ready,
        },
        "models": {"main": s.groq_model, "fast": s.groq_fast_model, "image": s.cloudflare_image_model},
        "auth": {"required": bool(s.access_code), "ok": is_authed(request)},
    }
