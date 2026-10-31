"""Optional shared access code for public deployments (cookie based, so SSE and <img> work)."""
from __future__ import annotations

import hashlib
import hmac

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from app.config import get_settings

COOKIE = "studio_auth"
router = APIRouter(prefix="/api", tags=["auth"])


def _token(code: str) -> str:
    return hmac.new(code.encode(), b"ai-blog-studio", hashlib.sha256).hexdigest()


def is_authed(request: Request) -> bool:
    code = get_settings().access_code
    if not code:
        return True
    return hmac.compare_digest(request.cookies.get(COOKIE, ""), _token(code))


async def require_auth(request: Request) -> None:
    if not is_authed(request):
        raise HTTPException(401, "Access code required")


class LoginBody(BaseModel):
    code: str


@router.post("/auth")
def login(body: LoginBody, request: Request, response: Response) -> dict:
    code = get_settings().access_code
    if not code:
        return {"ok": True}
    if not hmac.compare_digest(body.code.strip(), code):
        raise HTTPException(401, "That access code is not correct.")
    response.set_cookie(
        COOKIE, _token(code), max_age=60 * 60 * 24 * 30, httponly=True, samesite="lax",
        secure=request.url.scheme == "https",
    )
    return {"ok": True}
