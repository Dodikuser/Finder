"""Provider sign-in for a user's profile, driven through the providers' own CLIs.

Three flows, none of which ever shows Finder a password:
- device: ``hermes auth add <id> --no-browser`` prints a verification URL and a one-time code
  (ChatGPT/Codex, Nous, xAI, MiniMax); we relay both and wait for the process to finish.
- code:   the CLI prints an authorization URL and waits for a code on stdin; the user signs in on
  the provider's page and pastes the code into Finder (Claude Pro/Max; Gemini via Antigravity).
"""

import logging
import os
import re
import secrets
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass, field
from typing import Iterator

from . import antigravity
from .pool import pool
from .profiles import (connected_providers, ensure_default_provider, ensure_profile, home_dir, profile_dir,
                       run_hermes)
from .runtime import CREATE_NO_WINDOW, hermes_command, hermes_env

log = logging.getLogger("finder.auth")

OAUTH_PROVIDERS = [
    {"id": "nous", "name": "Nous Portal", "flow": "device", "recommended": True},
    {"id": "openai-codex", "name": "ChatGPT / Codex", "flow": "device"},
    {"id": "anthropic", "name": "Claude Pro / Max", "flow": "code"},
    {"id": antigravity.PROVIDER_ID, "name": "Google Gemini (Antigravity)", "flow": "code"},
    {"id": "xai-oauth", "name": "xAI Grok (SuperGrok / Premium+)", "flow": "device"},
    {"id": "minimax-oauth", "name": "MiniMax", "flow": "device"},
]
API_KEY_PROVIDERS = [
    {"id": "openrouter", "name": "OpenRouter"},
    {"id": "anthropic", "name": "Anthropic API"},
    {"id": "openai-api", "name": "OpenAI API"},
    {"id": "gemini", "name": "Google AI Studio (Gemini)"},
    {"id": "deepseek", "name": "DeepSeek"},
    {"id": "xai", "name": "xAI API"},
    {"id": "minimax", "name": "MiniMax API"},
    {"id": "huggingface", "name": "Hugging Face"},
]
_KEY_IDS = {p["id"] for p in API_KEY_PROVIDERS}

_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|\x1b\][^\x07]*\x07")
_URL = re.compile(r"https?://[^\s\]\)\"'<>]+")
_CODE = re.compile(r"\b[A-Z0-9]{3,10}(?:-[A-Z0-9]{3,10})+\b")
LOGIN_TIMEOUT = 900
_ACTIVE = ("starting", "waiting", "verifying")


def offered_oauth() -> list[dict]:
    """Subscription sign-ins this server can actually perform."""
    return [p for p in OAUTH_PROVIDERS if p["id"] != antigravity.PROVIDER_ID or antigravity.available()]


class _Proc:
    """A CLI we talk to line by line. ``tty=True`` gives it a pseudo-terminal (POSIX): interactive
    sign-in tools such as agy only prompt for the pasted code when they see a terminal."""

    def __init__(self, cmd: list[str], env: dict[str, str], *, interactive: bool, tty: bool = False,
                 cwd: str | None = None):
        self._master: int | None = None
        if tty and os.name != "nt":
            import pty

            self._master, slave = pty.openpty()
            self.proc = subprocess.Popen(cmd, env=env, cwd=cwd, stdin=slave, stdout=slave, stderr=slave,
                                         start_new_session=True, close_fds=True)
            os.close(slave)
        else:
            self.proc = subprocess.Popen(cmd, env=env, cwd=cwd,
                                         stdin=subprocess.PIPE if interactive else subprocess.DEVNULL,
                                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                         creationflags=CREATE_NO_WINDOW)

    def lines(self) -> Iterator[str]:
        if self._master is None:
            assert self.proc.stdout
            for raw in self.proc.stdout:
                yield raw.decode("utf-8", "replace")
            return
        import select

        fd = self._master  # kill() may clear self._master from another thread while we wait
        buf = b""
        while True:
            try:
                ready, _, _ = select.select([fd], [], [], 0.7)
                if not ready:
                    # Output paused: a prompt that never gets its newline is complete as it stands.
                    if buf:
                        yield buf.decode("utf-8", "replace")
                        buf = b""
                    if self.proc.poll() is not None:
                        break
                    continue
                chunk = os.read(fd, 4096)
            except (OSError, ValueError):  # EIO / closed fd: the child exited or the login was cancelled
                break
            if not chunk:
                break
            buf += chunk
            *done, buf = re.split(rb"[\r\n]+", buf)
            for part in done:
                yield part.decode("utf-8", "replace")
        if buf:
            yield buf.decode("utf-8", "replace")

    def send(self, text: str) -> None:
        data = text.encode("utf-8") + b"\n"
        if self._master is not None:
            os.write(self._master, data)
            return
        assert self.proc.stdin
        self.proc.stdin.write(data)
        self.proc.stdin.flush()
        self.proc.stdin.close()

    def wait(self) -> int:
        return self.proc.wait()

    def kill(self) -> None:
        if self.proc.poll() is None:
            self.proc.kill()
        if self._master is not None:
            try:
                os.close(self._master)
            except OSError:
                pass
            self._master = None


@dataclass
class LoginSession:
    id: str
    profile: str
    provider: str
    flow: str = "device"  # device | code
    status: str = "starting"  # starting | waiting | verifying | approved | error | cancelled
    url: str = ""
    code: str = ""
    message: str = ""
    lines: list[str] = field(default_factory=list)
    started: float = field(default_factory=time.time)
    proc: _Proc | None = None
    workdir: tempfile.TemporaryDirectory | None = None

    def public(self) -> dict:
        return {"session_id": self.id, "provider": self.provider, "flow": self.flow, "status": self.status,
                "verification_url": self.url, "user_code": self.code, "message": self.message,
                "expires_at": self.started + LOGIN_TIMEOUT}


_sessions: dict[str, LoginSession] = {}
_lock = threading.Lock()


def start_device_login(profile: str, provider: str) -> LoginSession:
    spec = next((p for p in offered_oauth() if p["id"] == provider), None)
    if spec is None:
        raise ValueError("unsupported provider")
    flow = spec["flow"]
    ensure_profile(profile)
    with _lock:  # one login per profile+provider at a time
        for s in _sessions.values():
            if s.profile == profile and s.provider == provider and s.status in _ACTIVE:
                _kill(s)
    sess = LoginSession(secrets.token_urlsafe(12), profile, provider, flow=flow)
    env = hermes_env(profile_dir(profile), home_dir=home_dir(profile))
    if provider == antigravity.PROVIDER_ID:
        # agy owns Google's sign-in. Private cwd so it does not adopt a workspace; HOME is the
        # user's profile home, which is where agy leaves the session.
        sess.workdir = tempfile.TemporaryDirectory(prefix="finder-agy-login-")
        sess.proc = _Proc(antigravity.login_command(), env, interactive=True, tty=True, cwd=sess.workdir.name)
    elif flow == "code":
        sess.proc = _Proc(hermes_command("auth", "add", provider, "--type", "oauth", "--no-browser"), env,
                          interactive=True)
    else:
        sess.proc = _Proc(hermes_command("auth", "add", provider, "--no-browser", "--timeout", str(LOGIN_TIMEOUT)),
                          env, interactive=False)
    with _lock:
        _sessions[sess.id] = sess
    threading.Thread(target=_watch, args=(sess,), daemon=True).start()
    # A login nobody finishes (tab closed, code never pasted) must not leave a process behind.
    timer = threading.Timer(LOGIN_TIMEOUT, lambda: _kill(sess) if sess.status in _ACTIVE else None)
    timer.daemon = True
    timer.start()
    # Give the CLI a moment to print the URL (and code) so the first response already has them.
    deadline = time.time() + 25
    while time.time() < deadline and sess.status == "starting" and not (sess.url and (sess.code or flow == "code")):
        time.sleep(0.2)
    return sess


def submit_code(profile: str, session_id: str, code: str) -> LoginSession:
    """Hand the code the user copied from the provider's page to the waiting CLI."""
    sess = get_login(profile, session_id)
    if not sess or sess.flow != "code" or sess.status != "waiting" or not sess.proc:
        raise ValueError("login is not waiting for a code")
    sess.status = "verifying"
    try:
        sess.proc.send(code.strip())
    except OSError:
        sess.status = "error"
        sess.message = "sign-in process ended before the code was sent"
    return sess


def _watch(sess: LoginSession) -> None:
    assert sess.proc
    for raw in sess.proc.lines():
        line = _ANSI.sub("", raw).strip()
        if not line:
            continue
        sess.lines = (sess.lines + [line])[-40:]
        if not sess.url and (m := _URL.search(line)):
            sess.url = m.group(0).rstrip(".,")
        if sess.flow == "device" and not sess.code and (m := _CODE.search(line)) and "http" not in line:
            sess.code = m.group(0)
        if sess.url and sess.status == "starting":
            sess.status = "waiting"
    code = sess.proc.wait()
    if sess.workdir:
        sess.workdir.cleanup()
    if sess.status == "cancelled":
        return
    # Code flows can exit 0 without a credential (wrong code): trust the credential store instead.
    ok = sess.provider in connected_providers(sess.profile) if sess.flow == "code" else code == 0
    if ok:
        ensure_default_provider(sess.profile)
        sess.status = "approved"
        pool.restart(sess.profile)
    else:
        sess.status = "error"
        sess.message = _last_meaningful(sess.lines)


def _last_meaningful(lines: list[str]) -> str:
    for line in reversed(lines):
        if not line.startswith(("Traceback", "  File")):
            return line.removeprefix("Authorization code:").strip()[:300]
    return "sign-in failed"


def _kill(sess: LoginSession) -> None:
    sess.status = "cancelled"
    if sess.proc:
        sess.proc.kill()


def get_login(profile: str, session_id: str) -> LoginSession | None:
    sess = _sessions.get(session_id)
    return sess if sess and sess.profile == profile else None


def cancel_login(profile: str, session_id: str) -> None:
    sess = get_login(profile, session_id)
    if sess and sess.status in _ACTIVE:
        _kill(sess)


def add_api_key(profile: str, provider: str, api_key: str) -> None:
    if provider not in _KEY_IDS:
        raise ValueError("unsupported provider")
    ensure_profile(profile)
    r = run_hermes(profile, "auth", "add", provider, "--type", "api-key", "--api-key", api_key,
                   "--label", "finder", timeout=90)
    if r.returncode != 0:
        raise RuntimeError(_last_meaningful((_ANSI.sub("", r.stdout + r.stderr)).splitlines()) or "failed")
    ensure_default_provider(profile)
    pool.restart(profile)


def disconnect(profile: str, provider: str) -> None:
    if provider == antigravity.PROVIDER_ID:
        antigravity.sign_out(home_dir(profile))  # the session is a file in this user's own home
    else:
        r = run_hermes(profile, "auth", "logout", provider, timeout=90)
        if r.returncode != 0 and provider in connected_providers(profile):
            raise RuntimeError(_last_meaningful((_ANSI.sub("", r.stdout + r.stderr)).splitlines()))
    ensure_default_provider(profile)
    pool.restart(profile)


def catalog(profile: str) -> dict:
    connected = connected_providers(profile)
    oauth = [{**p, "connected": p["id"] in connected} for p in offered_oauth()]
    keys = [{**p, "connected": p["id"] in connected} for p in API_KEY_PROVIDERS]
    return {"oauth": oauth, "api_key": keys, "connected": sorted(connected)}
