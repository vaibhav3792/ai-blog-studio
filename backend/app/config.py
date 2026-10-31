from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    # Groq
    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-120b"
    groq_fast_model: str = "openai/gpt-oss-20b"
    groq_reasoning_effort: str = "low"
    groq_max_retries: int = 5
    groq_timeout_s: float = 90.0
    llm_temperature: float = 0.3
    structured_method: Literal["json_schema", "json_mode"] = "json_schema"
    max_concurrency: int = 2

    # Tavily
    tavily_api_key: str = ""
    max_research_queries: int = 6
    results_per_query: int = 5
    max_evidence: int = 20
    check_links: bool = True  # drop sources whose page no longer exists (404/410)

    # Cloudflare Workers AI
    cloudflare_account_id: str = ""
    cloudflare_api_token: str = ""
    cloudflare_image_model: str = "@cf/black-forest-labs/flux-2-klein-4b"
    image_width: int = 1024
    image_height: int = 576
    image_style: str = (
        "clean editorial illustration, soft natural lighting, muted colour palette, "
        "uncluttered composition, no text or lettering"
    )
    images_enabled: bool = True
    max_images: int = 2      # AI illustrations (Cloudflare)
    max_diagrams: int = 2    # Mermaid diagrams (free, drawn by the browser)

    # App
    database_url: str = ""
    data_dir: Path = BACKEND_DIR / "data"
    cors_origins: str = "http://localhost:5173"
    access_code: str = ""            # set this on any public deployment
    daily_generation_limit: int = 0  # 0 = unlimited
    frontend_dist: str = ""          # folder with the built frontend (set in Docker)

    @property
    def images_dir(self) -> Path:
        return self.data_dir / "images"

    @property
    def effective_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        return f"sqlite:///{(self.data_dir / 'blog_studio.db').as_posix()}"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def groq_ready(self) -> bool:
        return bool(self.groq_api_key)

    @property
    def tavily_ready(self) -> bool:
        return bool(self.tavily_api_key)

    @property
    def images_ready(self) -> bool:
        return bool(
            self.images_enabled and self.cloudflare_account_id and self.cloudflare_api_token
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
