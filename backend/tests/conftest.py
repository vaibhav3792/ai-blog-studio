import re

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app
from app.services import image_gen, llm, runner, search
from app.workflow.schemas import (
    EvidenceItem, GlobalImagePlan, ImageProposal, Plan, RouterDecision, Task,
)


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(tmp_path / 'test.db').as_posix()}")
    monkeypatch.setenv("GROQ_API_KEY", "test-groq")
    monkeypatch.setenv("TAVILY_API_KEY", "test-tavily")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acct123")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "cf-token")
    monkeypatch.setenv("MAX_IMAGES", "2")
    monkeypatch.setenv("CHECK_LINKS", "false")  # tests never touch the network
    get_settings.cache_clear()
    llm.reset_llm_cache()
    runner.reset()
    yield
    get_settings.cache_clear()
    llm.reset_llm_cache()
    runner.reset()


class Fakes:
    """Records calls made to the patched providers."""

    def __init__(self):
        self.router = dict(needs_research=True, mode="hybrid", queries=["q1", "q2", "Q1"])
        self.structured_calls = []
        self.search_calls = []
        self.image_calls = []
        self.fail_section = None
        self.fail_image = False


@pytest.fixture
def fakes(monkeypatch):
    f = Fakes()

    def structured(schema, messages, *, tier="fast", max_tokens=None):
        f.structured_calls.append((schema.__name__, tier))
        if schema is RouterDecision:
            return RouterDecision(reason="test", **f.router)
        if schema is Plan:
            tasks = [
                Task(id=7, title=f"Section {i}", goal="g", bullets=["a", "b", "c", "d", "e", "f", "g"], target_words=9000)
                for i in range(1, 4)
            ]
            return Plan(blog_title="Test Blog", audience="devs", tone="clear", tasks=tasks)
        if schema is GlobalImagePlan:
            return GlobalImagePlan(images=[
                ImageProposal(section_id=2, kind="illustration", filename="Flow Diagram.png", alt="a flow",
                              caption="The flow", prompt="a river splitting into channels"),
                ImageProposal(section_id=3, kind="diagram", alt="pipeline", caption="The pipeline",
                              mermaid='```mermaid\nflowchart LR\n  A["Embed"] --> B["Search"]\n```'),
                ImageProposal(section_id=1, kind="diagram", alt="bad", caption="bad", mermaid="not mermaid at all"),
                ImageProposal(section_id=99, kind="illustration", filename="ghost", alt="x", caption="x", prompt="x"),
            ])
        raise AssertionError(schema)

    def text(messages, *, tier="main", max_tokens=None):
        title = re.search(r"Section title: (.*)", messages[-1].content).group(1)
        if f.fail_section == title:
            raise RuntimeError("boom")
        return f"## {title}\n\nIntro for {title}.\n\nMore detail."

    def search_web(query, *, mode, recency_days, max_results):
        f.search_calls.append(query)
        return [EvidenceItem(title=f"Result {query}", url=f"https://example.com/{query.lower()}", published_at="2026-10-25")]

    def generate_image(prompt):
        f.image_calls.append(prompt)
        if f.fail_image:
            raise image_gen.ImageGenError("HTTP 429")
        return b"\xff\xd8\xffFAKEJPEG", "jpg"

    monkeypatch.setattr(llm, "structured", structured)
    monkeypatch.setattr(llm, "text", text)
    monkeypatch.setattr(search, "search_web", search_web)
    monkeypatch.setattr(image_gen, "generate_image", generate_image)
    return f


@pytest.fixture
def client():
    with TestClient(create_app()) as c:
        yield c
