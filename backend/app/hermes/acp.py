"""Minimal Agent Client Protocol client for one ``hermes acp`` process (JSON-RPC over stdio).

Threads, not asyncio subprocesses: works under any event loop policy on Windows.
"""

import itertools
import json
import logging
import subprocess
import threading
import time
from concurrent.futures import Future
from pathlib import Path
from typing import Any, Callable

from .runtime import CREATE_NO_WINDOW

log = logging.getLogger("finder.acp")

UpdateHandler = Callable[[dict], None]


class AcpError(RuntimeError):
    def __init__(self, message: str, code: int | None = None, data: Any = None):
        super().__init__(message)
        self.code = code
        self.data = data


class AcpProcess:
    def __init__(self, cmd: list[str], env: dict[str, str], cwd: Path, log_path: Path):
        self.cmd, self.env, self.cwd, self.log_path = cmd, env, cwd, log_path
        self.proc: subprocess.Popen | None = None
        self._ids = itertools.count(1)
        self._pending: dict[int, Future] = {}
        self._handlers: dict[str, UpdateHandler] = {}
        self._write_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self.last_used = time.monotonic()
        self.init_result: dict = {}

    # ── lifecycle ────────────────────────────────────────────────────────────
    def start(self) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.proc = subprocess.Popen(self.cmd, env=self.env, cwd=str(self.cwd), stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                     creationflags=CREATE_NO_WINDOW)
        threading.Thread(target=self._read_stdout, name="acp-stdout", daemon=True).start()
        threading.Thread(target=self._read_stderr, name="acp-stderr", daemon=True).start()
        self.init_result = self.request("initialize", {
            "protocolVersion": 1,
            # No filesystem and no terminal capability: the agent cannot reach the client's disk.
            "clientCapabilities": {"fs": {"readTextFile": False, "writeTextFile": False}, "terminal": False},
            "clientInfo": {"name": "finder", "version": "1.0"},
        }, timeout=120)

    @property
    def alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def close(self) -> None:
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.stdin.close()  # type: ignore[union-attr]
                self.proc.wait(timeout=5)
            except Exception:
                self.proc.kill()
        self._fail_pending(AcpError("agent process stopped"))

    # ── messaging ────────────────────────────────────────────────────────────
    def _send(self, payload: dict) -> None:
        if not self.alive:
            raise AcpError("agent process is not running")
        line = (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")
        with self._write_lock:
            self.proc.stdin.write(line)  # type: ignore[union-attr]
            self.proc.stdin.flush()  # type: ignore[union-attr]

    def request_future(self, method: str, params: dict) -> Future:
        msg_id = next(self._ids)
        fut: Future = Future()
        with self._state_lock:
            self._pending[msg_id] = fut
        self.last_used = time.monotonic()
        self._send({"jsonrpc": "2.0", "id": msg_id, "method": method, "params": params})
        return fut

    def request(self, method: str, params: dict, timeout: float = 120) -> Any:
        return self.request_future(method, params).result(timeout=timeout)

    def notify(self, method: str, params: dict) -> None:
        self._send({"jsonrpc": "2.0", "method": method, "params": params})

    def subscribe(self, session_id: str, handler: UpdateHandler) -> None:
        self._handlers[session_id] = handler

    def unsubscribe(self, session_id: str) -> None:
        self._handlers.pop(session_id, None)

    # ── reader threads ───────────────────────────────────────────────────────
    def _read_stdout(self) -> None:
        assert self.proc and self.proc.stdout
        for raw in self.proc.stdout:
            try:
                msg = json.loads(raw.decode("utf-8", "replace"))
            except ValueError:
                continue
            try:
                self._dispatch(msg)
            except Exception:
                log.exception("ACP dispatch failed")
        self._fail_pending(AcpError("agent process exited"))

    def _read_stderr(self) -> None:
        assert self.proc and self.proc.stderr
        with open(self.log_path, "ab") as fh:
            for raw in self.proc.stderr:
                fh.write(raw)
                fh.flush()

    def _dispatch(self, msg: dict) -> None:
        if "method" not in msg:  # response to one of our requests
            with self._state_lock:
                fut = self._pending.pop(msg.get("id"), None)
            if fut is None:
                return
            if "error" in msg:
                err = msg["error"] or {}
                fut.set_exception(AcpError(err.get("message", "ACP error"), err.get("code"), err.get("data")))
            else:
                fut.set_result(msg.get("result"))
            return
        method, params = msg["method"], msg.get("params") or {}
        if method == "session/update":
            handler = self._handlers.get(params.get("sessionId", ""))
            if handler:
                handler(params.get("update") or {})
            return
        if "id" in msg:  # a request from the agent to us
            self._answer_agent_request(msg["id"], method, params)

    def _answer_agent_request(self, msg_id: Any, method: str, params: dict) -> None:
        if method == "session/request_permission":
            # Finder agents have nothing that needs approval; anything that asks is refused.
            options = params.get("options") or []
            reject = next((o for o in options if str(o.get("kind", "")).startswith("reject")), None)
            outcome = ({"outcome": "selected", "optionId": reject["optionId"]} if reject
                       else {"outcome": "cancelled"})
            handler = self._handlers.get(params.get("sessionId", ""))
            if handler:
                handler({"sessionUpdate": "finder_permission_denied",
                         "toolCall": params.get("toolCall") or {}})
            self._send({"jsonrpc": "2.0", "id": msg_id, "result": {"outcome": outcome}})
            return
        self._send({"jsonrpc": "2.0", "id": msg_id,
                    "error": {"code": -32601, "message": f"{method} is not available in Finder"}})

    def _fail_pending(self, exc: Exception) -> None:
        with self._state_lock:
            pending, self._pending = self._pending, {}
        for fut in pending.values():
            if not fut.done():
                fut.set_exception(exc)
