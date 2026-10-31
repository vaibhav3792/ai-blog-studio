import io
import json
import time
import zipfile

from app.config import get_settings


def wait_done(client, blog_id, timeout=15):
    end = time.time() + timeout
    while time.time() < end:
        data = client.get(f"/api/blogs/{blog_id}").json()
        if data["status"] in ("complete", "failed"):
            return data
        time.sleep(0.05)
    raise AssertionError("run did not finish")


def test_health_reports_provider_status(client):
    body = client.get("/api/health").json()
    assert body["providers"] == {"groq": True, "tavily": True, "cloudflare_images": True}
    assert "api_key" not in json.dumps(body).lower()


def test_generate_requires_groq_key(client, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "")
    get_settings.cache_clear()
    r = client.post("/api/blogs/generate", json={"topic": "anything"})
    assert r.status_code == 400 and "GROQ_API_KEY" in r.json()["detail"]


def test_generate_validates_topic(client):
    assert client.post("/api/blogs/generate", json={"topic": "x"}).status_code == 422


def test_full_lifecycle(client, fakes):
    r = client.post("/api/blogs/generate", json={"topic": "How KV caching works"})
    assert r.status_code == 202
    blog_id = r.json()["id"]

    blog = wait_done(client, blog_id)
    assert blog["status"] == "complete", blog["error"]
    assert blog["title"] == "Test Blog"
    assert blog["images"] == ["1_flow_diagram.jpg"]
    assert blog["word_count"] > 5 and len(blog["evidence"]) == 2

    # event replay after completion
    with client.stream("GET", f"/api/blogs/{blog_id}/events") as resp:
        events = [json.loads(l[6:]) for l in resp.iter_lines() if l.startswith("data:")]
    kinds = [e["type"] for e in events]
    assert kinds[0] == "started" and kinds[-1] == "done"
    nodes = [e["node"] for e in events if e["type"] == "node"]
    assert nodes[0] == "router" and nodes.count("worker") == 3 and nodes[-1] == "generate_and_place_images"
    assert [e["data"]["done"] for e in events if e.get("node") == "worker"] == [1, 2, 3]

    # edit
    r = client.patch(f"/api/blogs/{blog_id}", json={"title": "Edited", "markdown": "# Edited\n\nbody"})
    assert r.status_code == 200 and r.json()["title"] == "Edited"

    # export
    md = client.get(f"/api/blogs/{blog_id}/export?format=md")
    assert md.text == "# Edited\n\nbody" and "edited.md" in md.headers["content-disposition"]
    z = zipfile.ZipFile(io.BytesIO(client.get(f"/api/blogs/{blog_id}/export?format=zip").content))
    assert sorted(z.namelist()) == ["edited/edited.md", "edited/images/1_flow_diagram.jpg"]

    # images are served
    assert client.get(f"/media/{blog_id}/1_flow_diagram.jpg").status_code == 200
    assert client.get(f"/media/{blog_id}/missing.jpg").status_code == 404
    assert client.get(f"/media/{blog_id}/..%2F..%2Ftest.db").status_code == 404

    assert [b["id"] for b in client.get("/api/blogs").json()] == [blog_id]

    assert client.delete(f"/api/blogs/{blog_id}").status_code == 204
    assert client.get(f"/api/blogs/{blog_id}").status_code == 404
    assert not (get_settings().images_dir / str(blog_id)).exists()


def test_failed_run_reports_friendly_error(client, fakes, monkeypatch):
    from app.services import llm

    def boom(*a, **k):
        raise llm.LLMConfigError("GROQ_API_KEY is not set.")

    monkeypatch.setattr(llm, "structured", boom)
    blog_id = client.post("/api/blogs/generate", json={"topic": "will fail"}).json()["id"]
    blog = wait_done(client, blog_id)
    assert blog["status"] == "failed" and "GROQ_API_KEY" in blog["error"]
    with client.stream("GET", f"/api/blogs/{blog_id}/events") as resp:
        last = [json.loads(l[6:]) for l in resp.iter_lines() if l.startswith("data:")][-1]
    assert last["type"] == "error"


def test_access_code_protects_api_media_and_sse(client, fakes, monkeypatch):
    monkeypatch.setenv("ACCESS_CODE", "s3cret")
    get_settings.cache_clear()

    assert client.get("/api/health").json()["auth"] == {"required": True, "ok": False}
    assert client.get("/api/blogs").status_code == 401
    assert client.post("/api/blogs/generate", json={"topic": "no access"}).status_code == 401
    assert client.get("/media/1/x.jpg").status_code == 401
    assert client.post("/api/auth", json={"code": "wrong"}).status_code == 401

    r = client.post("/api/auth", json={"code": "s3cret"})
    assert r.status_code == 200 and "httponly" in r.headers["set-cookie"].lower()
    assert client.get("/api/health").json()["auth"]["ok"] is True
    assert client.get("/api/blogs").status_code == 200

    blog_id = client.post("/api/blogs/generate", json={"topic": "with access"}).json()["id"]
    assert wait_done(client, blog_id)["status"] == "complete"
    assert client.get(f"/media/{blog_id}/1_flow_diagram.jpg").status_code == 200
    client.cookies.clear()
    assert client.get(f"/api/blogs/{blog_id}/events").status_code == 401


def test_daily_generation_limit(client, fakes, monkeypatch):
    monkeypatch.setenv("DAILY_GENERATION_LIMIT", "1")
    get_settings.cache_clear()
    first = client.post("/api/blogs/generate", json={"topic": "first post"})
    assert first.status_code == 202
    wait_done(client, first.json()["id"])
    second = client.post("/api/blogs/generate", json={"topic": "second post"})
    assert second.status_code == 429 and "Daily limit" in second.json()["detail"]


def test_serves_built_frontend_with_spa_fallback(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import create_app

    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>app</html>")
    (dist / "assets" / "app.js").write_text("console.log(1)")
    (dist / "favicon.txt").write_text("fav")
    monkeypatch.setenv("FRONTEND_DIST", str(dist))
    get_settings.cache_clear()
    with TestClient(create_app()) as c:
        assert c.get("/").text == "<html>app</html>"
        assert c.get("/library").text == "<html>app</html>"          # client-side route
        assert c.get("/blogs/3").text == "<html>app</html>"
        assert c.get("/assets/app.js").text == "console.log(1)"
        assert c.get("/favicon.txt").text == "fav"
        assert c.get("/..%2F..%2Fetc%2Fpasswd").text == "<html>app</html>"
        assert c.get("/api/nope").status_code == 404
        assert c.get("/api/health").json()["status"] == "ok"
