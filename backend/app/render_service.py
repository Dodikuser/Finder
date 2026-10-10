"""Shared headless browser for all agents of this server.

Every agent's finder-reach MCP process asks this endpoint to render pages, so the server runs at
most ONE Chrome with at most `browser_max_pages` pages open at a time (the rest wait in a queue),
instead of one browser per chat. The engine lives in its own thread and event loop, independent of
the web server's loop policy (Playwright needs subprocess support).
"""

import asyncio
import ipaddress
import secrets
import sys
import threading
from concurrent.futures import Future

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from .config import PROJECT_ROOT, get_settings

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from reach_mcp.browser import BrowserBusy, Engine  # noqa: E402
from reach_mcp.net import PrivateAddress, assert_public  # noqa: E402

TOKEN = secrets.token_urlsafe(32)
router = APIRouter(include_in_schema=False)


class _Service:
    def __init__(self) -> None:
        self.loop: asyncio.AbstractEventLoop | None = None
        self.engine: Engine | None = None
        self._ready = threading.Event()
        self._lock = threading.Lock()

    def _run(self) -> None:
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        s = get_settings()
        self.engine = Engine(max_pages=s.browser_max_pages, idle_seconds=s.browser_idle_seconds)
        self._ready.set()
        self.loop.run_forever()

    def start(self) -> None:
        with self._lock:
            if self.loop is None:
                threading.Thread(target=self._run, name="render-service", daemon=True).start()
        self._ready.wait(10)

    def submit(self, url: str) -> Future:
        self.start()
        return asyncio.run_coroutine_threadsafe(self.engine.render(url), self.loop)  # type: ignore[union-attr]

    def submit_pdf(self, document_html: str) -> Future:
        self.start()
        return asyncio.run_coroutine_threadsafe(self.engine.pdf(document_html), self.loop)  # type: ignore[union-attr]

    def stats(self) -> dict:
        return self.engine.stats() if self.engine else {"running": False}

    def stop(self) -> None:
        if self.loop and self.engine:
            asyncio.run_coroutine_threadsafe(self.engine.close(), self.loop).result(timeout=15)
            self.loop.call_soon_threadsafe(self.loop.stop)


service = _Service()


class RenderIn(BaseModel):
    url: str = Field(max_length=4000)


def _is_loopback(host: str | None) -> bool:
    try:
        return host is not None and ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host == "localhost"


def _authorize(request: Request) -> None:
    if not _is_loopback(request.client.host if request.client else None) or \
            not secrets.compare_digest(request.headers.get("X-Finder-Render-Token", ""), TOKEN):
        raise HTTPException(403, "forbidden")


class PdfIn(BaseModel):
    html: str = Field(max_length=3_000_000)


@router.post("/internal/pdf")
async def pdf(body: PdfIn, request: Request) -> Response:
    """HTML (built by the document tool from sanitised markdown) → A4 PDF."""
    _authorize(request)
    try:
        data = await asyncio.wrap_future(service.submit_pdf(body.html))
    except BrowserBusy as exc:
        raise HTTPException(429, str(exc))
    except Exception as exc:
        raise HTTPException(502, f"{type(exc).__name__}: {exc}")
    return Response(content=data, media_type="application/pdf")


@router.post("/internal/render")
async def render(body: RenderIn, request: Request) -> dict:
    _authorize(request)
    try:
        await assert_public(body.url)
    except PrivateAddress as exc:
        raise HTTPException(422, str(exc))
    try:
        return await asyncio.wrap_future(service.submit(body.url))
    except BrowserBusy as exc:
        raise HTTPException(429, str(exc))
    except Exception as exc:
        raise HTTPException(502, f"{type(exc).__name__}: {exc}")
