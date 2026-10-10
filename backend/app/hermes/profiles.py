"""One Hermes profile per Finder user: creation, sandboxing config, skills, credential status."""

import json
import logging
import shutil
import subprocess
import threading
from pathlib import Path

import yaml

from ..config import PROJECT_ROOT, get_settings
from . import antigravity
from .runtime import CREATE_NO_WINDOW, hermes_command, hermes_env

log = logging.getLogger("finder.profiles")

CONFIG_VERSION = 8
SKILLS_SRC = PROJECT_ROOT / "skills"

# Only internet-facing toolsets. The disk, shell, code execution, sub-agents, scheduled jobs and
# desktop control are not reachable from a Finder agent.
# Hermes' own "web" toolset is off too: all browsing goes through finder-reach (fallback chain,
# shared browser, focus, private-address guard) so behaviour is the same whatever the model.
ACP_TOOLSETS = ["skills", "clarify", "todo", "memory", "session_search", "vision"]
DISABLED_TOOLSETS = ["terminal", "file", "code_execution", "delegation", "cronjob", "computer_use",
                     "connections", "image_gen", "video_gen", "tts", "stt", "kanban", "spotify",
                     "browser", "web", "x_search"]

SOUL = """# Finder research agent

You are a research agent inside the Finder web app. You search the internet and report what you
find, always with links to the sources.

- You have no access to files, a terminal or code execution, and you never ask for them.
- Use the finder-reach tools (web_search, fetch_page, pubmed_search, eu_funding_search, ...)
  for everything on the internet. When a site blocks one method, fetch_page already falls back
  to others; try a different source rather than giving up.
- Separate facts found in sources from your own conclusions. Never invent references, numbers,
  deadlines or amounts.
- Answer in the language the user asks for.
"""

_create_lock = threading.Lock()


def profile_name_for(user_id: int) -> str:
    return f"{get_settings().profile_prefix}u{user_id}"


def profile_dir(name: str) -> Path:
    return get_settings().hermes_root / "profiles" / name


def home_dir(name: str) -> Path:
    return profile_dir(name) / "home"


def run_hermes(name: str | None, *args: str, timeout: float = 120) -> subprocess.CompletedProcess:
    """Run a one-shot Hermes CLI command in a profile (``None`` = the data root)."""
    s = get_settings()
    home = profile_dir(name) if name else s.hermes_root
    env = hermes_env(home, home_dir=home_dir(name) if name else None)
    return subprocess.run(hermes_command(*args), env=env, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout, stdin=subprocess.DEVNULL,
                          creationflags=CREATE_NO_WINDOW)


def ensure_profile(name: str) -> Path:
    """Create (once) and configure the profile; idempotent and cheap when up to date."""
    pdir = profile_dir(name)
    with _create_lock:
        if not (pdir / "config.yaml").exists():
            log.info("creating Hermes profile %s", name)
            r = run_hermes(None, "profile", "create", name, "--no-alias", "--no-skills",
                           "--description", "Finder web user", timeout=180)
            if r.returncode != 0 and not (pdir / "config.yaml").exists():
                raise RuntimeError(f"hermes profile create failed: {(r.stderr or r.stdout)[-800:]}")
        marker = pdir / ".finder-config-version"
        if marker.exists() and marker.read_text().strip() == str(CONFIG_VERSION):
            return pdir
        _write_config(pdir)
        _sync_skills(pdir)
        (pdir / "SOUL.md").write_text(SOUL, encoding="utf-8")
        for sub in ("home", "workspace"):
            (pdir / sub).mkdir(exist_ok=True)
        marker.write_text(str(CONFIG_VERSION))
    return pdir


def _write_config(pdir: Path) -> None:
    path = pdir / "config.yaml"
    cfg = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}
    cfg = cfg or {}
    cfg.setdefault("platform_toolsets", {})["acp"] = ACP_TOOLSETS
    agent = cfg.setdefault("agent", {})
    agent["disabled_toolsets"] = DISABLED_TOOLSETS
    # The profile template pins the default provider's endpoint (base_url / api_mode). With those
    # pinned, switching a chat to another provider's model keeps calling the old endpoint (404);
    # Hermes resolves the right endpoint itself from provider + model.
    if isinstance(cfg.get("model"), dict):
        cfg["model"] = {k: v for k, v in cfg["model"].items() if k in ("default", "provider")}
    antigravity.install_plugin(pdir, cfg)
    path.write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False), encoding="utf-8")


def _sync_skills(pdir: Path) -> None:
    dest = pdir / "skills" / "finder"
    if dest.exists():
        shutil.rmtree(dest)
    if SKILLS_SRC.exists():
        shutil.copytree(SKILLS_SRC, dest)


def set_default_model(name: str, provider: str, model: str) -> None:
    path = profile_dir(name) / "config.yaml"
    cfg = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    cfg["model"] = {"default": model, "provider": provider} if model else {"provider": provider}
    path.write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False), encoding="utf-8")


_PREFERRED = ["nous", "openai-codex", "anthropic", antigravity.PROVIDER_ID, "openrouter", "xai-oauth", "gemini",
              "openai-api",
              "deepseek", "minimax-oauth", "xai", "minimax", "huggingface"]


def ensure_default_provider(name: str) -> None:
    """Point the profile's default model at a provider the user actually connected.

    A fresh profile inherits the template default (often openai-codex); Hermes cannot even open a
    session when that provider has no credentials.
    """
    connected = connected_providers(name)
    if not connected:
        return
    path = profile_dir(name) / "config.yaml"
    cfg = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    current = (cfg.get("model") or {}).get("provider", "")
    if current in connected:
        return
    provider = next((p for p in _PREFERRED if p in connected), sorted(connected)[0])
    if provider == antigravity.PROVIDER_ID:
        model = antigravity.default_model(hermes_env(profile_dir(name), home_dir=home_dir(name)))
    else:
        r = run_hermes(name, "--finder-default-model", provider, timeout=60)
        model = (r.stdout or "").strip().splitlines()[-1] if r.returncode == 0 and r.stdout.strip() else ""
    log.info("profile %s: default provider %s -> %s (%s)", name, current, provider, model or "auto")
    set_default_model(name, provider, model)


def connected_providers(name: str) -> dict[str, dict]:
    """Providers with stored credentials in this profile (never returns secrets)."""
    result: dict[str, dict] = {}
    # Gemini via Antigravity keeps its session with agy, in this user's home, not in auth.json.
    if antigravity.available() and antigravity.signed_in(home_dir(name)):
        result[antigravity.PROVIDER_ID] = {"auth_type": "external"}
    path = profile_dir(name) / "auth.json"
    if not path.exists():
        return result
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return result
    for pid in (data.get("providers") or {}):
        result[pid] = {"auth_type": "oauth"}
    for pid, rows in (data.get("credential_pool") or {}).items():
        if rows:
            result.setdefault(pid, {"auth_type": rows[0].get("auth_type", "")})
            result[pid]["count"] = len(rows)
    return result
