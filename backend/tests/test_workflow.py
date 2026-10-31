from app.config import get_settings
from app.workflow.graph import build_graph


def run(topic="KV cache", run_id="1"):
    inputs = {"topic": topic, "run_id": run_id, "as_of": "2026-10-30", "sections": [], "warnings": []}
    return build_graph().invoke(inputs, config={"max_concurrency": 2})


def test_full_pipeline_with_research_and_images(fakes):
    out = run()
    md = out["final"]

    assert md.startswith("# Test Blog")
    assert md.index("## Section 1") < md.index("## Section 2") < md.index("## Section 3")
    assert [t.id for t in out["plan"].tasks] == [1, 2, 3]          # ids renumbered
    assert all(len(t.bullets) <= 6 and t.target_words == 550 for t in out["plan"].tasks)

    assert sorted(fakes.search_calls) == ["q1", "q2"]               # duplicate query removed
    assert len(out["evidence"]) == 2

    assert out["images"] == ["1_flow_diagram.jpg"]                  # unknown section_id=99 dropped
    assert "![a flow](images/1_flow_diagram.jpg)\n*The flow*" in md
    assert md.index("Intro for Section 2") < md.index("![a flow]") < md.index("## Section 3")
    # diagram: fences stripped by the cleaner, placed after section 3's intro, no image file needed
    assert '```mermaid\nflowchart LR\n  A["Embed"] --> B["Search"]\n```\n\n*The pipeline*' in md
    assert md.index("Intro for Section 3") < md.index("```mermaid")
    assert "not mermaid" not in md and out["visuals"] == 2
    assert any("unusable Mermaid" in w for w in out["warnings"])
    assert len(fakes.image_calls) == 1
    assert fakes.image_calls[0].startswith("a river splitting into channels clean editorial illustration")
    assert "[[IMAGE" not in md
    assert (get_settings().images_dir / "1" / "1_flow_diagram.jpg").read_bytes().startswith(b"\xff\xd8")
    assert ("RouterDecision", "fast") in fakes.structured_calls
    assert ("Plan", "main") in fakes.structured_calls


def test_closed_book_skips_research(fakes, monkeypatch):
    fakes.router = dict(needs_research=False, mode="open_book", queries=["ignored"])
    out = run()
    assert out["mode"] == "closed_book"
    assert fakes.search_calls == []
    assert not out.get("evidence")


def test_image_failure_keeps_post_usable(fakes):
    fakes.fail_image = True
    out = run()
    assert out["images"] == []
    assert "<!-- image skipped" in out["final"]
    assert "[[IMAGE" not in out["final"]
    assert any("failed" in w for w in out["warnings"])


def test_one_failed_section_does_not_sink_the_run(fakes):
    fakes.fail_section = "Section 2"
    out = run()
    assert "could not be generated" in out["final"]
    assert "Intro for Section 1" in out["final"] and "Intro for Section 3" in out["final"]
    assert any("Section 2" in w for w in out["warnings"])


def test_missing_keys_degrade_gracefully(fakes, monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "")
    get_settings.cache_clear()
    out = run()
    assert fakes.search_calls == [] and fakes.image_calls == []
    assert any("TAVILY_API_KEY" in w for w in out["warnings"])
    assert any("Cloudflare" in w for w in out["warnings"])
    assert out["final"].startswith("# Test Blog")
    assert "```mermaid" in out["final"]          # diagrams do not need any key


def test_diagram_only_when_illustrations_disabled(fakes, monkeypatch):
    monkeypatch.setenv("IMAGES_ENABLED", "false")
    get_settings.cache_clear()
    out = run()
    assert fakes.image_calls == [] and out["images"] == []
    assert "```mermaid" in out["final"] and out["visuals"] == 1


def test_no_visual_llm_call_when_everything_is_off(fakes, monkeypatch):
    monkeypatch.setenv("IMAGES_ENABLED", "false")
    monkeypatch.setenv("MAX_DIAGRAMS", "0")
    get_settings.cache_clear()
    out = run()
    assert ("GlobalImagePlan", "fast") not in fakes.structured_calls
    assert "```mermaid" not in out["final"] and out["visuals"] == 0


def test_strip_unverified_links_keeps_only_evidence_urls():
    from app.workflow.utils import strip_unverified_links

    md = (
        "See [the docs](https://made.up/docs) and [real](https://example.com/a/) here.\n"
        "Also [rel](/docs/x) and [bare](example.com/x).\n"
        "![fig](images/a.png) and [top](#intro).\n"
        "```\n[code](https://made.up/x)\n```\n"
    )
    out = strip_unverified_links(md, ["https://example.com/a"])
    assert "[the docs]" not in out and "the docs and" in out
    assert "[rel]" not in out and "[bare]" not in out
    assert "[real](https://example.com/a/)" in out
    assert "![fig](images/a.png)" in out and "[top](#intro)" in out
    assert "[code](https://made.up/x)" in out


def test_remove_no_source_notes():
    from app.workflow.utils import remove_no_source_notes

    md = "## Title\n\nGood text.\n\nSource: Not found in provided sources.\n\n- point (Not found in provided sources.)\n"
    out = remove_no_source_notes(md)
    assert "provided sources" not in out.lower()
    assert "Good text." in out and "- point" in out


def test_drop_dead_links_removes_only_404_and_unreachable():
    import httpx
    from app.services.search import drop_dead_links
    from app.workflow.schemas import EvidenceItem

    def handler(request: httpx.Request) -> httpx.Response:
        host = request.url.host
        if host == "gone.test":
            return httpx.Response(404)
        if host == "blocked.test":
            return httpx.Response(403)
        if host == "down.test":
            raise httpx.ConnectError("no host")
        return httpx.Response(200)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    items = [EvidenceItem(title=h, url=f"https://{h}/p") for h in ("ok.test", "gone.test", "blocked.test", "down.test")]
    kept = [e.title for e in drop_dead_links(items, client=client)]
    assert kept == ["ok.test", "blocked.test"]


def test_name_generic_links_uses_site_name():
    from app.workflow.utils import name_generic_links

    md = "Big news. ([Source](https://www.reuters.com/a)) And [Google announced](https://blog.google/x) it.\n```\n[Source](https://x.y/z)\n```\n"
    out = name_generic_links(md)
    assert "[reuters.com](https://www.reuters.com/a)" in out
    assert "[Google announced](https://blog.google/x)" in out
    assert "[Source](https://x.y/z)" in out
