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
