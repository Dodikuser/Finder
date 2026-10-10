"""Google Gemini subscription through the Antigravity CLI (`agy`) and its Hermes plugin.

Google's sign-in belongs to `agy`: it keeps the session wherever the OS user's home points.
Finder runs every agent with HOME = that user's profile home, so on Linux each site user gets a
private session file. On Windows `agy` stores the session in the machine-wide credential store,
which every profile would share — there the provider stays hidden unless explicitly forced
(FINDER_ANTIGRAVITY=force, single-operator installs only).
"""

import os
import shutil
import subprocess
from pathlib import Path

from ..config import get_settings

PROVIDER_ID = "antigravity-oauth"
PLUGIN_NAME = "antigravity-oauth"
_TOKEN_NAMES = ("jetski-standalone-oauth-token", "antigravity-oauth-token")
LOGIN_PROMPT = "Reply with exactly: OK"


def agy_path() -> str | None:
    cmd = get_settings().agy_command
    return cmd if os.path.isabs(cmd) and os.path.isfile(cmd) else shutil.which(cmd)


def plugin_source() -> Path | None:
    src = get_settings().antigravity_plugin_dir
    return src if src and (src / "plugin.yaml").exists() else None


def available() -> bool:
    mode = get_settings().antigravity
    if mode == "off" or not agy_path() or not plugin_source():
        return False
    return mode == "force" or os.name != "nt"


def token_dir(home: Path) -> Path:
    return home / ".gemini" / "antigravity-cli"


def signed_in(home: Path) -> bool:
    """A session file in THIS user's home (presence only; the token is never read)."""
    for name in _TOKEN_NAMES:
        f = token_dir(home) / name
        try:
            if f.is_file() and f.stat().st_size > 10:
                return True
        except OSError:
            pass
    if os.name == "nt" and get_settings().antigravity == "force":
        return _shared_session_alive()
    return False


def _shared_session_alive() -> bool:
    agy = agy_path()
    if not agy:
        return False
    try:
        r = subprocess.run([agy, "models"], capture_output=True, text=True, timeout=45, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return r.returncode == 0 and any(l.strip() and "fetching" not in l.lower() for l in r.stdout.splitlines())


def sign_out(home: Path) -> None:
    for name in _TOKEN_NAMES:
        (token_dir(home) / name).unlink(missing_ok=True)


def login_command() -> list[str]:
    agy = agy_path()
    if not agy:
        raise RuntimeError("Antigravity CLI (agy) is not installed on the server")
    return [agy, "-p", LOGIN_PROMPT, "--print-timeout", "5m"]


def default_model(env: dict[str, str]) -> str:
    """First model the signed-in account can use, without the effort suffix Hermes adds itself."""
    agy = agy_path()
    if not agy:
        return ""
    try:
        r = subprocess.run([agy, "models"], capture_output=True, text=True, timeout=60, env=env,
                           stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    ids = [l.split()[0] for l in r.stdout.splitlines() if l.strip() and "fetching" not in l.lower()]
    if not ids:
        return ""
    model = ids[0]
    for suffix in ("-high", "-medium", "-low"):
        if model.startswith("gemini-") and model.endswith(suffix):
            return model[: -len(suffix)]
    return model


def install_plugin(profile_dir: Path, cfg: dict) -> None:
    """Copy the plugin into the profile and enable it (plugins are per Hermes home) — or remove
    both when this server cannot offer the provider, so the profile never lists a dead plugin."""
    src = plugin_source()
    dest = profile_dir / "plugins" / PLUGIN_NAME
    if dest.exists():
        shutil.rmtree(dest)
    plugins = cfg.get("plugins") if isinstance(cfg.get("plugins"), dict) else {}
    enabled = [p for p in (plugins.get("enabled") or []) if p != PLUGIN_NAME]
    if src and available():
        shutil.copytree(src, dest, ignore=shutil.ignore_patterns("__pycache__", "tests", "node_modules", ".git"))
        enabled.append(PLUGIN_NAME)
    if enabled or "enabled" in plugins:
        plugins["enabled"] = enabled
        cfg["plugins"] = plugins
