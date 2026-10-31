"""Cloudflare Workers AI image generation over the REST API.

Different models take different request shapes, so the request is built per model family:
  - flux-1-schnell : JSON {prompt, steps}
  - flux-2-*       : multipart/form-data {prompt, width, height[, steps for flux-2-dev]}
  - others         : JSON {prompt, width, height}  (lucid-origin, phoenix, SDXL ...)
Responses are either JSON {"result": {"image": "<base64>"}} or raw image bytes.
"""
from __future__ import annotations

import base64
import time
from typing import Tuple

import httpx

from app.config import get_settings

API_ROOT = "https://api.cloudflare.com/client/v4/accounts"


class ImageGenError(RuntimeError):
    pass


def _extension(data: bytes) -> str:
    if data.startswith(b"\x89PNG"):
        return "png"
    if data.startswith(b"\xff\xd8"):
        return "jpg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return "jpg"


def _request_kwargs(model: str, prompt: str) -> dict:
    s = get_settings()
    prompt = prompt[:2048]
    m = model.lower()
    if "flux-1-schnell" in m:
        return {"json": {"prompt": prompt, "steps": 8}}
    if "flux-2" in m:
        fields = {"prompt": prompt, "width": str(s.image_width), "height": str(s.image_height)}
        if "flux-2-dev" in m:
            fields["steps"] = "25"
        # (None, value) tuples make httpx send multipart/form-data fields without any file.
        return {"files": {k: (None, v) for k, v in fields.items()}}
    return {"json": {"prompt": prompt, "width": s.image_width, "height": s.image_height}}


def _decode(resp: httpx.Response) -> bytes:
    if resp.headers.get("content-type", "").startswith("image/"):
        return resp.content
    try:
        result = resp.json().get("result")
    except ValueError:
        result = None
    b64 = result.get("image") if isinstance(result, dict) else result if isinstance(result, str) else None
    if not b64:
        raise ImageGenError("Cloudflare response contained no image")
    return base64.b64decode(b64)


def generate_image(prompt: str, *, client: httpx.Client | None = None) -> Tuple[bytes, str]:
    """Return (image_bytes, extension). Raises ImageGenError on any failure."""
    s = get_settings()
    if not (s.cloudflare_account_id and s.cloudflare_api_token):
        raise ImageGenError("Cloudflare credentials are not set")

    url = f"{API_ROOT}/{s.cloudflare_account_id}/ai/run/{s.cloudflare_image_model}"
    headers = {"Authorization": f"Bearer {s.cloudflare_api_token}"}
    kwargs = _request_kwargs(s.cloudflare_image_model, prompt)

    own_client = client is None
    http = client or httpx.Client(timeout=120.0)
    try:
        last = "unknown error"
        for attempt in range(3):
            try:
                resp = http.post(url, headers=headers, **kwargs)
            except httpx.HTTPError as exc:
                last = f"network error: {type(exc).__name__}"
            else:
                if resp.status_code == 200:
                    data = _decode(resp)
                    return data, _extension(data)
                last = f"HTTP {resp.status_code}: {resp.text[:200]}"
                if resp.status_code not in (429, 500, 502, 503, 504):
                    break
            if attempt < 2:
                time.sleep(2 * (attempt + 1))
        raise ImageGenError(last)
    finally:
        if own_client:
            http.close()
