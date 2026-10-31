import base64
import json

import groq
import httpx
import pytest
from langchain_groq import ChatGroq

from app.config import get_settings
from app.services import image_gen, llm, search
from app.workflow.schemas import RouterDecision
from app.workflow.utils import insert_after_intro


# ---------- Groq payloads (real SDK + langchain-groq, fake HTTP transport) ----------
def completion(content: str) -> dict:
    return {
        "id": "x", "object": "chat.completion", "created": 1, "model": "m",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }


GOOD = json.dumps({"needs_research": True, "mode": "hybrid", "reason": "r", "queries": ["a"]})


def chat_with(handler, monkeypatch, retries=0):
    http = httpx.Client(transport=httpx.MockTransport(handler))
    chat = ChatGroq(model="openai/gpt-oss-120b", api_key="k", http_client=http, max_retries=retries)
    monkeypatch.setattr(llm, "get_llm", lambda tier="main", max_tokens=None: chat)


def test_json_schema_mode_is_used_first(monkeypatch):
    seen = []

    def handler(req):
        seen.append(json.loads(req.content))
        return httpx.Response(200, json=completion(GOOD))

    chat_with(handler, monkeypatch)
    out = llm.structured(RouterDecision, [llm.SystemMessage(content="s"), llm.HumanMessage(content="h")])
    assert out.mode == "hybrid" and len(seen) == 1
    assert seen[0]["response_format"]["type"] == "json_schema"


def test_falls_back_to_json_mode_on_bad_request(monkeypatch):
    seen = []

    def handler(req):
        body = json.loads(req.content)
        seen.append(body["response_format"]["type"])
        if body["response_format"]["type"] == "json_schema":
            return httpx.Response(400, json={"error": {"message": "schema unsupported", "type": "invalid_request_error"}})
        assert "JSON Schema" in body["messages"][0]["content"]
        return httpx.Response(200, json=completion("```json\n" + GOOD + "\n```"))

    chat_with(handler, monkeypatch)
    out = llm.structured(RouterDecision, [llm.HumanMessage(content="h")])
    assert out.queries == ["a"] and seen == ["json_schema", "json_object"]


def test_json_mode_repairs_invalid_output_once(monkeypatch):
    monkeypatch.setenv("STRUCTURED_METHOD", "json_mode")
    get_settings.cache_clear()
    replies = iter(["not json at all", GOOD])

    def handler(req):
        return httpx.Response(200, json=completion(next(replies)))

    chat_with(handler, monkeypatch)
    assert llm.structured(RouterDecision, [llm.HumanMessage(content="h")]).mode == "hybrid"


def test_json_mode_gives_up_with_clear_error(monkeypatch):
    monkeypatch.setenv("STRUCTURED_METHOD", "json_mode")
    get_settings.cache_clear()
    chat_with(lambda req: httpx.Response(200, json=completion("nope")), monkeypatch)
    with pytest.raises(llm.LLMOutputError):
        llm.structured(RouterDecision, [llm.HumanMessage(content="h")])


def test_rate_limit_is_not_swallowed_by_fallback(monkeypatch):
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(429, json={"error": {"message": "rate limit", "type": "tokens"}})

    chat_with(handler, monkeypatch)
    with pytest.raises(groq.RateLimitError):
        llm.structured(RouterDecision, [llm.HumanMessage(content="h")])
    assert len(calls) == 1
    assert llm.is_retryable(groq.RateLimitError("x", response=httpx.Response(429, request=httpx.Request("POST", "http://x")), body=None))


def test_missing_key_message(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "")
    get_settings.cache_clear()
    llm.reset_llm_cache()
    with pytest.raises(llm.LLMConfigError, match="GROQ_API_KEY"):
        llm.get_llm("main")


def test_reasoning_effort_only_for_gpt_oss():
    assert llm.get_llm("main").reasoning_effort == "low"
    assert llm.get_llm("fast").reasoning_effort == "low"
    assert llm._build("llama-3.3-70b-versatile", None).reasoning_effort is None


# ---------- Cloudflare ----------
def _b64(data=b"\xff\xd8\xffdata"):
    return base64.b64encode(data).decode()


def test_cloudflare_flux2_klein_uses_multipart():
    seen = {}

    def handler(req):
        seen["url"], seen["auth"] = str(req.url), req.headers["authorization"]
        seen["ctype"], seen["body"] = req.headers["content-type"], req.content.decode()
        return httpx.Response(200, json={"success": True, "result": {"image": _b64()}})

    data, ext = image_gen.generate_image("a" * 3000, client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert data == b"\xff\xd8\xffdata" and ext == "jpg"
    assert seen["url"] == "https://api.cloudflare.com/client/v4/accounts/acct123/ai/run/@cf/black-forest-labs/flux-2-klein-4b"
    assert seen["auth"] == "Bearer cf-token" and seen["ctype"].startswith("multipart/form-data")
    assert 'name="prompt"' in seen["body"] and 'name="width"' in seen["body"] and "1024" in seen["body"]
    assert 'name="height"' in seen["body"] and "576" in seen["body"]
    assert "a" * 2048 in seen["body"] and "a" * 2049 not in seen["body"] and 'name="steps"' not in seen["body"]


def test_cloudflare_schnell_uses_json_with_steps(monkeypatch):
    monkeypatch.setenv("CLOUDFLARE_IMAGE_MODEL", "@cf/black-forest-labs/flux-1-schnell")
    get_settings.cache_clear()
    seen = {}

    def handler(req):
        seen["ctype"], seen["body"] = req.headers["content-type"], json.loads(req.content)
        return httpx.Response(200, json={"result": {"image": _b64()}})

    image_gen.generate_image("p", client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert seen["ctype"] == "application/json" and seen["body"] == {"prompt": "p", "steps": 8}


def test_cloudflare_generic_model_and_binary_response(monkeypatch):
    monkeypatch.setenv("CLOUDFLARE_IMAGE_MODEL", "@cf/bytedance/stable-diffusion-xl-lightning")
    get_settings.cache_clear()
    seen = {}

    def handler(req):
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, content=b"\x89PNGrawbytes", headers={"content-type": "image/png"})

    data, ext = image_gen.generate_image("p", client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert seen["body"] == {"prompt": "p", "width": 1024, "height": 576}
    assert data == b"\x89PNGrawbytes" and ext == "png"


def test_cloudflare_errors(monkeypatch):
    monkeypatch.setattr(image_gen.time, "sleep", lambda s: None)
    c = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(401, text="bad token")))
    with pytest.raises(image_gen.ImageGenError, match="401"):
        image_gen.generate_image("p", client=c)
    c = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"result": {}})))
    with pytest.raises(image_gen.ImageGenError, match="no image"):
        image_gen.generate_image("p", client=c)
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "")
    get_settings.cache_clear()
    with pytest.raises(image_gen.ImageGenError, match="credentials"):
        image_gen.generate_image("p")


# ---------- Tavily ----------
def test_search_builds_evidence_without_llm(monkeypatch):
    captured = {}

    class FakeClient:
        def __init__(self, api_key): pass

        def search(self, **kw):
            captured.update(kw)
            return {"results": [
                {"title": "A", "url": "https://x.com/a", "content": "c" * 500, "published_date": "Mon, 27 Oct 2026 10:00:00 GMT"},
                {"title": "B", "url": "", "content": "skip me"},
                {"title": "C", "url": "https://y.org/c", "content": "ok", "published_date": "not a date"},
            ]}

    import tavily
    monkeypatch.setattr(tavily, "TavilyClient", FakeClient)
    items = search.search_web("q", mode="open_book", recency_days=7, max_results=5)
    assert captured["topic"] == "news" and captured["days"] == 7
    assert [i.url for i in items] == ["https://x.com/a", "https://y.org/c"]
    assert items[0].published_at == "2026-10-27" and len(items[0].snippet) == 300
    assert items[1].published_at is None and items[0].source == "x.com"
    search.search_web("q", mode="hybrid", recency_days=45, max_results=5)
    assert captured["topic"] == "general" and captured["time_range"] == "year"


# ---------- markdown helpers ----------
def test_image_placeholder_never_lands_inside_code_fence():
    md = "## T\n\n```python\nx = 1\n\ny = 2\n```\n\nPlain paragraph.\n\n- list"
    out = insert_after_intro(md, "[[IMAGE_1]]")
    assert out.index("```python") < out.index("y = 2") < out.index("Plain paragraph.") < out.index("[[IMAGE_1]]") < out.index("- list")


def test_clean_mermaid():
    from app.workflow.utils import clean_mermaid
    good = 'flowchart LR\n  A["One"] --> B["Two"]'
    assert clean_mermaid(f"```mermaid\n{good}\n```") == good
    assert clean_mermaid("pie title x") == ""                      # unsupported type
    assert clean_mermaid('flowchart LR\n  A["One --> B') == ""      # unbalanced brackets
    assert clean_mermaid('flowchart LR\n  A["<b>x</b>"] --> B["y"]') == ""   # html
    assert clean_mermaid("") == ""
