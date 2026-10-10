import asyncio
import sys

import pytest
from fastapi.testclient import TestClient

from app.config import PROJECT_ROOT

sys.path.insert(0, str(PROJECT_ROOT))

from reach_mcp import net, server  # noqa: E402
from reach_mcp.extract import tidy_markdown  # noqa: E402


@pytest.mark.parametrize("url", ["http://127.0.0.1:8100/api/health", "http://localhost/", "http://10.0.0.5/x",
                                 "http://169.254.169.254/latest/meta-data", "file:///C:/Windows/win.ini"])
def test_private_addresses_are_refused(url):
    with pytest.raises(net.PrivateAddress):
        asyncio.run(net.assert_public(url))
    f, attempts = asyncio.run(net.fetch_resilient(url))
    assert f is None and "private" in attempts[0] or "unsupported" in attempts[0]


def test_render_endpoint_requires_token(monkeypatch):
    from app import render_service
    from app.main import app

    monkeypatch.setattr(render_service, "_is_loopback", lambda host: True)
    with TestClient(app) as c:
        assert c.post("/internal/render", json={"url": "https://example.com"}).status_code == 403
        assert c.post("/internal/render", json={"url": "https://example.com"},
                      headers={"X-Finder-Render-Token": "wrong"}).status_code == 403
    monkeypatch.setattr(render_service, "_is_loopback", lambda host: False)
    with TestClient(app) as c:  # not loopback, even with the token
        from app.render_service import TOKEN
        assert c.post("/internal/render", json={"url": "https://example.com"},
                      headers={"X-Finder-Render-Token": TOKEN}).status_code == 403


def test_render_endpoint_blocks_internal_targets(monkeypatch):
    from app import render_service
    from app.main import app
    from app.render_service import TOKEN

    monkeypatch.setattr(render_service, "_is_loopback", lambda host: True)
    with TestClient(app) as c:
        r = c.post("/internal/render", json={"url": "http://127.0.0.1:8100/api/health"},
                   headers={"X-Finder-Render-Token": TOKEN})
        assert r.status_code == 422


def test_focus_returns_price_sections_first():
    filler = "\n\n".join(f"About our company paragraph {i}. " * 8 for i in range(40))
    page = filler + "\n\n## StartUp\n\n2.99 €/mo. Renews at 15.99 €/mo.\n\n" + filler
    picked, n, total = server._focus_sections(page, "price renews", 1200)
    assert "2.99 €" in picked and "15.99 €" in picked
    assert len(picked) <= 1500 and n < total


def test_tidy_markdown_drops_menus_and_consent():
    md = ("* [Home](https://a.com)\n* [Pricing](https://a.com/p)\nThis website uses cookies\n- [x]\n"
          "[#IABV2SETTINGS#]\n## Plans\nStartUp costs 2.99 € per month and renews at 15.99 €.")
    out = tidy_markdown(md)
    assert "Home" not in out and "cookies" not in out and "[x]" not in out and "IABV2" not in out
    assert "## Plans" in out and "2.99 €" in out


def test_dashboard_validation_rejects_bad_specs():
    from reach_mcp import artifacts

    good = artifacts.clean_dashboard("T", "s", [{"label": "a", "value": "1"}], [
        {"type": "bar", "title": "c", "unit": "€", "series": [{"name": "n", "points": [{"x": "a", "y": 1}, {"x": "b", "y": 2.5}]}]}])
    assert good["charts"][0]["series"][0]["points"][1] == {"x": "b", "y": 2.5} and good["kpis"][0]["label"] == "a"
    for bad in (
        [],                                                                                    # no charts
        [{"type": "pie", "title": "x", "series": [{"name": "n", "points": [{"x": "a", "y": 1}]}]}],   # unknown type
        [{"type": "bar", "title": "x", "series": [{"name": "n", "points": [{"x": "a", "y": "5 €"}]}]}],  # text value
        [{"type": "bar", "title": "x", "series": [{"name": "n", "points": [{"x": "a", "y": float("nan")}]}]}],
        [{"type": "share", "title": "x", "series": [{"name": "n", "points": [{"x": str(i), "y": 1} for i in range(7)]}]}],
        [{"type": "hbar", "title": "x", "series": [{"name": "a", "points": [{"x": "a", "y": 1}]}] * 2}],
    ):
        with pytest.raises(artifacts.ArtifactError):
            artifacts.clean_dashboard("T", "", [], bad)


def test_document_html_is_sanitised():
    from reach_mcp.artifacts import markdown_to_html

    out = markdown_to_html("## Title\n\n<script>alert(1)</script> <img src=x onerror=alert(2)> [ok](https://a.org) "
                           "[bad](javascript:alert(3))\n\n| a | b |\n|---|---|\n| 1 | 2 |")
    assert "<h2>" in out and "<table>" in out and 'href="https://a.org"' in out
    assert "<script" not in out and "onerror" not in out and "<img" not in out and "javascript:" not in out


def test_artifacts_are_registered_and_served_only_to_their_owner(tmp_path, monkeypatch):
    import json

    from app import artifacts_store
    from app.main import app
    from app.routers import chat as chat_router

    monkeypatch.setattr(artifacts_store, "DATA_DIR", tmp_path)
    with TestClient(app) as owner, TestClient(app) as other:
        owner.post("/api/auth/register", json={"email": "art-owner@example.com", "password": "password123"})
        other.post("/api/auth/register", json={"email": "art-other@example.com", "password": "password123"})
        agent = owner.get("/api/agents").json()[0]
        thread = owner.post("/api/threads", json={"agent_id": agent["id"]}).json()
        folder = artifacts_store.artifact_dir(thread["id"])
        folder.mkdir(parents=True)
        aid = "a" * 24
        (folder / f"{aid}.md").write_text("# hello", encoding="utf-8")
        (folder / f"{aid}.meta.json").write_text(json.dumps({
            "id": aid, "kind": "document", "title": "Report", "mime": "text/markdown; charset=utf-8",
            "file": f"{aid}.md", "filename": "report.md", "size": 7}), encoding="utf-8")
        # A metadata file pointing outside the generated naming scheme must be ignored.
        evil = "b" * 24
        (folder / f"{evil}.meta.json").write_text(json.dumps({
            "id": evil, "kind": "document", "title": "x", "mime": "text/plain", "file": "../../finder.db",
            "filename": "x.txt"}), encoding="utf-8")

        from app.db import session_factory, User
        with session_factory()() as s:
            uid = s.query(User).filter_by(email="art-owner@example.com").one().id
            rows = artifacts_store.ingest(s, uid, thread["id"])
            assert [r.id for r in rows] == [aid]
            assert artifacts_store.ingest(s, uid, thread["id"]) == []  # idempotent

        r = owner.get(f"/api/artifacts/{aid}")
        assert r.status_code == 200 and r.text == "# hello"
        assert "attachment" in r.headers["content-disposition"] and r.headers["x-content-type-options"] == "nosniff"
        assert other.get(f"/api/artifacts/{aid}").status_code == 404
        assert owner.get(f"/api/artifacts/{evil}").status_code == 404
        listed = owner.get(f"/api/threads/{thread['id']}").json()
        assert listed["messages"] == []
        assert chat_router.artifact_dir(thread["id"]) == folder
        owner.delete(f"/api/threads/{thread['id']}")
        assert not folder.exists()
