"""Runtime settings, read from environment / backend/.env."""

import os
import secrets
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = PROJECT_ROOT / "backend"
DATA_DIR = Path(os.environ.get("FINDER_DATA_DIR") or PROJECT_ROOT / "data")


def _default_hermes_root() -> Path:
    local = os.environ.get("LOCALAPPDATA")
    return Path(local) / "hermes" if local else Path.home() / ".hermes"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_ROOT / ".env", env_prefix="FINDER_", extra="ignore")

    secret_key: str = ""
    database_url: str = f"sqlite:///{(DATA_DIR / 'finder.db').as_posix()}"
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    cookie_secure: bool = False
    token_ttl_hours: int = 24 * 7
    allow_registration: bool = True
    invite_code: str = ""  # when set, registration requires this code
    auth_attempts_per_5min: int = 20  # per client address, for login + register

    # Hermes
    hermes_root: Path = _default_hermes_root()
    hermes_bin: str = "hermes"
    profile_prefix: str = "finder"
    prewarm_profiles: bool = True  # create the Hermes profile right after registration
    acp_idle_seconds: int = 900
    prompt_timeout_seconds: int = 900

    # finder-reach MCP
    mcp_python: str = ""  # defaults to the backend interpreter
    proxy_url: str = ""  # optional outbound proxy for the search tools
    browser: str = "auto"  # auto | off — shared headless Chrome for blocked / JavaScript pages
    browser_max_pages: int = 3  # pages rendered at once across ALL users; the rest wait in a queue
    browser_idle_seconds: int = 120
    self_url: str = f"http://127.0.0.1:{os.environ.get('PORT', '8100')}"  # how agents reach this server
    contact_email: str = ""  # sent to NCBI / OpenAlex polite pools when set

    # Google Gemini subscription via the Antigravity CLI. auto = offered where every user gets a
    # private session (Linux); force = also on Windows, where the session is machine-wide.
    antigravity: str = "auto"  # auto | off | force
    agy_command: str = "agy"
    antigravity_plugin_dir: Path = PROJECT_ROOT / "hermes-plugins" / "antigravity-oauth"


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not s.secret_key:
        key_file = DATA_DIR / ".secret_key"
        if not key_file.exists():
            key_file.write_text(secrets.token_urlsafe(48), encoding="utf-8")
        s.secret_key = key_file.read_text(encoding="utf-8").strip()
    return s
