"""How to start a Hermes process for a profile: interpreter, entry script, sanitized env."""

import json
import logging
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from ..config import BACKEND_ROOT, DATA_DIR, PROJECT_ROOT, get_settings

log = logging.getLogger("finder.hermes")

ENTRY_SCRIPT = BACKEND_ROOT / "hermes_entry" / "finder_hermes.py"

# Environment passed through to Hermes. Everything else (API keys exported in the server's
# shell, tokens, proxies of the operator) stays out of user agents.
_ENV_PASSTHROUGH = (
    "SYSTEMROOT", "WINDIR", "SYSTEMDRIVE", "COMSPEC", "PATH", "PATHEXT", "TEMP", "TMP",
    "LOCALAPPDATA", "APPDATA", "PROGRAMDATA", "PROGRAMFILES", "PROGRAMFILES(X86)", "COMMONPROGRAMFILES",
    "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE", "OS", "LANG", "LC_ALL", "TZ", "TMPDIR",
    "XDG_RUNTIME_DIR", "SSL_CERT_FILE", "REQUESTS_CA_BUNDLE",
)


@dataclass(frozen=True)
class HermesRuntime:
    python: str
    agent_dir: str


@lru_cache
def resolve_runtime() -> HermesRuntime:
    """Hermes' interpreter + checkout. Env overrides first (Docker), else ask the launcher."""
    py = os.environ.get("FINDER_HERMES_PYTHON", "")
    agent_dir = os.environ.get("FINDER_HERMES_AGENT_DIR", "")
    if py and agent_dir:
        return HermesRuntime(py, agent_dir)
    hermes = shutil.which(get_settings().hermes_bin)
    if not hermes:
        raise RuntimeError("Hermes is not installed (no `hermes` on PATH); set FINDER_HERMES_PYTHON "
                           "and FINDER_HERMES_AGENT_DIR")
    out = subprocess.check_output([hermes, "--print-runtime-command", "acp"], text=True, timeout=60,
                                  stdin=subprocess.DEVNULL)
    cmd = json.loads(out.strip().splitlines()[-1])
    match = re.search(r"sys\.path\.insert\(0, '([^']+)'\)", " ".join(cmd))
    if not match:
        raise RuntimeError(f"cannot parse Hermes runtime command: {cmd!r}")
    agent_dir = match.group(1).replace("\\\\", "\\")
    log.info("Hermes runtime: python=%s agent_dir=%s", cmd[0], agent_dir)
    return HermesRuntime(cmd[0], agent_dir)


def hermes_command(*args: str) -> list[str]:
    rt = resolve_runtime()
    return [rt.python, "-I", str(ENTRY_SCRIPT), *args]


def hermes_env(hermes_home: Path, *, home_dir: Path | None = None) -> dict[str, str]:
    env = {k: v for k in _ENV_PASSTHROUGH if (v := os.environ.get(k)) is not None}
    rt = resolve_runtime()
    env.update(
        HERMES_HOME=str(hermes_home),
        FINDER_HERMES_AGENT_DIR=rt.agent_dir,
        PYTHONIOENCODING="utf-8",
        PYTHONUTF8="1",
        PYTHONUNBUFFERED="1",
        NO_COLOR="1",
        HERMES_ACCEPT_HOOKS="0",
    )
    if os.name != "nt":
        env["BROWSER"] = "true"  # sign-in tools (agy) must print the URL, not open a browser on the server
    if home_dir is not None:
        # Per-user HOME: tools that look in ~ (.codex, .claude, .config) see the profile, not the operator.
        home_dir.mkdir(parents=True, exist_ok=True)
        env["HOME"] = env["USERPROFILE"] = str(home_dir)
    else:  # operator-level commands (profile create): the server's own home
        env.update({k: v for k in ("HOME", "USERPROFILE", "HOMEDRIVE", "HOMEPATH") if (v := os.environ.get(k))})
    proxy = get_settings().proxy_url
    if proxy:
        env["HTTP_PROXY"] = env["HTTPS_PROXY"] = proxy
    return env


def mcp_server_spec(tools: list[str], language: str, artifact_dir: Path | None = None) -> dict:
    """ACP stdio MCP server entry for the finder-reach search tools."""
    s = get_settings()
    python = s.mcp_python or sys.executable
    env = {k: v for k in ("SYSTEMROOT", "WINDIR", "PATH", "TEMP", "TMP", "LOCALAPPDATA", "APPDATA",
                          "LANG", "TZ", "SSL_CERT_FILE") if (v := os.environ.get(k))}
    env.update(PYTHONPATH=str(PROJECT_ROOT), PYTHONIOENCODING="utf-8", PYTHONUTF8="1",
               FINDER_REACH_TOOLS=",".join(tools), FINDER_REACH_LANG=language,
               FINDER_REACH_CACHE=str(DATA_DIR / "reach_cache.sqlite"))
    if s.proxy_url:
        env["FINDER_PROXY_URL"] = s.proxy_url
    from ..render_service import TOKEN
    env.update(FINDER_BROWSER=s.browser, FINDER_RENDER_URL=f"{s.self_url}/internal/render",
               FINDER_PDF_URL=f"{s.self_url}/internal/pdf", FINDER_RENDER_TOKEN=TOKEN)
    if artifact_dir is not None:
        env["FINDER_ARTIFACT_DIR"] = str(artifact_dir)  # the only place the tools may write files
    if s.contact_email:
        env["FINDER_CONTACT_EMAIL"] = s.contact_email
    return {"name": "finder-reach", "command": python, "args": ["-m", "reach_mcp"],
            "env": [{"name": k, "value": v} for k, v in env.items()]}


CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
