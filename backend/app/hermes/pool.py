"""Per-user ``hermes acp`` processes: started on demand, reused across chats, stopped when idle."""

import logging
import threading
import time
from concurrent.futures import Future
from dataclasses import dataclass, field

from ..config import get_settings
from .acp import AcpError, AcpProcess, UpdateHandler
from .profiles import ensure_profile, home_dir, profile_dir
from .runtime import hermes_command, hermes_env

log = logging.getLogger("finder.pool")


@dataclass
class _Slot:
    proc: AcpProcess
    loaded: set[str] = field(default_factory=set)
    models: dict = field(default_factory=dict)
    active: int = 0


@dataclass
class SessionHandle:
    session_id: str
    fresh: bool  # True when the agent has no history for it (first turn, or history lost)
    models: dict


class AgentPool:
    def __init__(self) -> None:
        self._slots: dict[str, _Slot] = {}
        self._locks: dict[str, threading.Lock] = {}
        self._guard = threading.Lock()
        self._stop = threading.Event()
        threading.Thread(target=self._reaper, name="acp-reaper", daemon=True).start()

    def _lock(self, profile: str) -> threading.Lock:
        with self._guard:
            return self._locks.setdefault(profile, threading.Lock())

    def _slot(self, profile: str) -> _Slot:
        with self._lock(profile):
            slot = self._slots.get(profile)
            if slot and slot.proc.alive:
                return slot
            pdir = ensure_profile(profile)
            proc = AcpProcess(hermes_command("acp"), hermes_env(pdir, home_dir=home_dir(profile)),
                              cwd=pdir / "workspace", log_path=pdir / "logs" / "finder-acp.log")
            log.info("starting hermes acp for %s", profile)
            proc.start()
            slot = _Slot(proc)
            self._slots[profile] = slot
            return slot

    # ── sessions ─────────────────────────────────────────────────────────────
    def open_session(self, profile: str, session_id: str, mcp_servers: list[dict]) -> SessionHandle:
        slot = self._slot(profile)
        cwd = str(profile_dir(profile) / "workspace")
        if session_id and session_id in slot.loaded:
            return SessionHandle(session_id, False, slot.models)
        if session_id:
            try:
                res = slot.proc.request("session/load", {"sessionId": session_id, "cwd": cwd,
                                                         "mcpServers": mcp_servers}, timeout=180) or {}
                slot.loaded.add(session_id)
                if res.get("models"):
                    slot.models = res["models"]
                return SessionHandle(session_id, False, slot.models)
            except AcpError as exc:
                log.warning("session/load %s failed (%s); starting a new session", session_id, exc)
        res = slot.proc.request("session/new", {"cwd": cwd, "mcpServers": mcp_servers}, timeout=180)
        sid = res["sessionId"]
        slot.loaded.add(sid)
        if res.get("models"):
            slot.models = res["models"]
        return SessionHandle(sid, True, slot.models)

    def set_model(self, profile: str, session_id: str, model_id: str) -> None:
        self._slot(profile).proc.request("session/set_model", {"sessionId": session_id, "modelId": model_id},
                                         timeout=60)

    def prompt(self, profile: str, session_id: str, text: str, on_update: UpdateHandler) -> Future:
        slot = self._slot(profile)
        slot.proc.subscribe(session_id, on_update)
        slot.active += 1
        fut = slot.proc.request_future("session/prompt", {"sessionId": session_id,
                                                          "prompt": [{"type": "text", "text": text}]})

        def _done(_f: Future) -> None:
            slot.active -= 1
            slot.proc.unsubscribe(session_id)
            slot.proc.last_used = time.monotonic()

        fut.add_done_callback(_done)
        return fut

    def cancel(self, profile: str, session_id: str) -> None:
        slot = self._slots.get(profile)
        if slot and slot.proc.alive:
            slot.proc.notify("session/cancel", {"sessionId": session_id})

    def models(self, profile: str) -> dict:
        slot = self._slot(profile)
        if not slot.models:
            self.open_session(profile, "", [])
        return slot.models

    def restart(self, profile: str) -> None:
        """Drop the process (e.g. after credentials changed) so the next use reloads them."""
        with self._lock(profile):
            slot = self._slots.pop(profile, None)
        if slot:
            slot.proc.close()

    def shutdown(self) -> None:
        self._stop.set()
        for profile in list(self._slots):
            self.restart(profile)

    def _reaper(self) -> None:
        idle = get_settings().acp_idle_seconds
        while not self._stop.wait(30):
            now = time.monotonic()
            for profile, slot in list(self._slots.items()):
                if slot.active == 0 and now - slot.proc.last_used > idle:
                    log.info("stopping idle hermes acp for %s", profile)
                    self.restart(profile)


pool = AgentPool()
