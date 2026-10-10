import os
import tempfile
from pathlib import Path

_tmp = tempfile.mkdtemp(prefix="finder-test-")
os.environ["FINDER_DATA_DIR"] = _tmp
os.environ["FINDER_HERMES_ROOT"] = str(Path(_tmp) / "hermes")
os.environ["FINDER_SECRET_KEY"] = "test-secret"
os.environ["FINDER_PREWARM_PROFILES"] = "false"

import yaml  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import agents_logic  # noqa: E402
from app.db import Agent  # noqa: E402
from app.hermes import auth_flows, profiles  # noqa: E402
from app.main import app  # noqa: E402


def test_extract_grants_parses_and_validates():
    text = """Summary table...
```grants
[{"title": "Horizon call", "funder": "EU", "verdict": "fits", "url": "https://x", "deadline": "2026-12-01"},
 {"title": "Bad verdict", "verdict": "maybe"},
 {"title": "", "verdict": "fits"},
 {"title": "Later", "verdict": "next-year"}]
```"""
    items = agents_logic.extract_grants(text)
    assert [i["title"] for i in items] == ["Horizon call", "Later"]
    assert items[1]["verdict"] == "next_year"
    assert agents_logic.strip_grants_block(text) == "Summary table..."


def test_instruction_block_contains_config_and_language():
    agent = Agent(name={"uk": "Тест", "en": "Test"}, instructions="Do research.", sources=["https://a.org"],
                  org_profile="Uni", skills=["web-reach"], kind="grants", tools=[], description={})
    block = agents_logic.instruction_block(agent, "de")
    assert 'agent "Test"' in block  # no German name: falls back to English
    assert "https://a.org" in block and "Uni" in block and "```grants" in block
    assert "Always answer in German" in block
    assert agents_logic.build_prompt(agent, "uk", "hi", fresh=False).endswith("[Answer in Ukrainian.]")


def test_presets_load_and_only_known_tools():
    presets = agents_logic.presets()
    assert {p["slug"] for p in presets} == {"medical-ai", "topic-researcher", "it-grants"}
    for p in presets:
        assert set(p["tools"]) <= set(agents_logic.ALL_TOOLS), p["slug"]
        assert set(p["skills"]) <= set(agents_logic.ALL_SKILLS), p["slug"]


def test_profile_config_disables_disk_and_shell(tmp_path, monkeypatch):
    pdir = tmp_path / "profiles" / "finderu9"
    pdir.mkdir(parents=True)
    (pdir / "config.yaml").write_text("model:\n  provider: openai-codex\n", encoding="utf-8")
    monkeypatch.setattr(profiles, "profile_dir", lambda name: pdir)
    profiles.ensure_profile("finderu9")
    cfg = yaml.safe_load((pdir / "config.yaml").read_text(encoding="utf-8"))
    for forbidden in ("terminal", "file", "code_execution", "browser", "delegation", "web"):
        assert forbidden not in cfg["platform_toolsets"]["acp"]
        assert forbidden in cfg["agent"]["disabled_toolsets"]
    assert cfg["model"]["provider"] == "openai-codex"  # untouched
    assert (pdir / "skills" / "finder" / "web-reach" / "SKILL.md").exists()


def test_connected_providers_reads_auth_store_without_secrets(tmp_path, monkeypatch):
    monkeypatch.setattr(profiles, "profile_dir", lambda name: tmp_path)
    (tmp_path / "auth.json").write_text(
        '{"providers": {"openai-codex": {"tokens": {"access_token": "SECRET"}}},'
        ' "credential_pool": {"openrouter": [{"auth_type": "api_key", "access_token": "SECRET2"}], "nous": []}}',
        encoding="utf-8")
    got = profiles.connected_providers("x")
    assert set(got) == {"openai-codex", "openrouter"}
    assert "SECRET" not in str(got)


def test_device_code_patterns():
    line = "Enter this code:     MYSF-5KU8Q"
    assert auth_flows._CODE.search(line).group(0) == "MYSF-5KU8Q"
    assert auth_flows._URL.search("  1. Open https://auth.openai.com/codex/device now").group(0) == \
        "https://auth.openai.com/codex/device"


def test_auth_flow_and_agent_isolation():
    with TestClient(app) as c:
        r = c.post("/api/auth/register", json={"email": "a@example.com", "password": "password123"})
        assert r.status_code == 200
        agents = c.get("/api/agents").json()
        assert len(agents) == 3
        assert c.post("/api/auth/register", json={"email": "a@example.com", "password": "password123"}).status_code == 409
        c.post("/api/auth/logout")
        assert c.get("/api/agents").status_code == 401
        assert c.post("/api/auth/login", json={"email": "a@example.com", "password": "nope"}).status_code == 401

    with TestClient(app) as other:
        other.post("/api/auth/register", json={"email": "b@example.com", "password": "password123"})
        assert other.patch(f"/api/agents/{agents[0]['id']}", json={"instructions": "x"}).status_code == 404
        # Chat refuses to start without a connected provider account.
        own = other.get("/api/agents").json()[0]
        th = other.post("/api/threads", json={"agent_id": own["id"]}).json()
        r = other.post(f"/api/threads/{th['id']}/messages", json={"text": "hi"})
        assert r.status_code == 412 and r.json()["detail"] == "needs_account"


def test_invite_code_gates_registration(monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "invite_code", "let-me-in")
    with TestClient(app) as c:
        assert c.get("/api/auth/config").json() == {"registration": True, "invite_required": True}
        body = {"email": "invited@example.com", "password": "password123"}
        assert c.post("/api/auth/register", json=body).json()["detail"] == "invalid_invite"
        assert c.post("/api/auth/register", json={**body, "invite_code": "wrong"}).status_code == 403
        assert c.post("/api/auth/register", json={**body, "invite_code": "let-me-in"}).status_code == 200


def test_auth_attempts_are_throttled(monkeypatch):
    from app.config import get_settings
    from app.routers import auth as auth_router

    monkeypatch.setattr(get_settings(), "auth_attempts_per_5min", 3)
    auth_router._attempts.clear()
    with TestClient(app) as c:
        codes = [c.post("/api/auth/login", json={"email": "x@example.com", "password": "nope"}).status_code
                 for _ in range(5)]
    auth_router._attempts.clear()
    assert codes == [401, 401, 401, 429, 429]


def test_gemini_subscription_hidden_where_sessions_are_shared(monkeypatch):
    """Antigravity keeps one machine-wide session on Windows: never offer it there by default."""
    import os

    from app.hermes import antigravity, auth_flows

    monkeypatch.setattr(antigravity, "agy_path", lambda: "/usr/local/bin/agy")
    monkeypatch.setattr(antigravity, "plugin_source", lambda: Path("."))
    ids = [p["id"] for p in auth_flows.offered_oauth()]
    assert ("antigravity-oauth" in ids) == (os.name != "nt")
    assert "qwen-oauth" not in ids and "copilot-acp" not in ids and "anthropic" in ids
