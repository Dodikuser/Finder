"""HTTP layer for finder-reach: browser-like requests, TLS impersonation, fallbacks, cache, throttle.

Fetch chain for a page (stops at the first readable result):
  1. httpx, HTTP/2, real browser headers, retries with backoff on 429/5xx
  2. curl_cffi impersonating Chrome's TLS/HTTP2 fingerprint (passes most bot filters)
  3. Jina Reader (r.jina.ai) — renders JavaScript-heavy pages server-side, returns markdown
  4. Internet Archive snapshot of the page
No CAPTCHA solving: a page that demands one is reported as blocked.
"""

import asyncio
import hashlib
import json
import os
import random
import sqlite3
import threading
import time
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx
from curl_cffi.requests import AsyncSession

PROXY = os.environ.get("FINDER_PROXY_URL") or None
CACHE_PATH = os.environ.get("FINDER_REACH_CACHE", "")
LANG = os.environ.get("FINDER_REACH_LANG", "uk")
CONTACT = os.environ.get("FINDER_CONTACT_EMAIL", "")

_ACCEPT_LANG = {"uk": "uk-UA,uk;q=0.9,en-US;q=0.8,en;q=0.7", "de": "de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7",
                "en": "en-US,en;q=0.9"}
BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/131.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": _ACCEPT_LANG.get(LANG, _ACCEPT_LANG["en"]),
    "Sec-Ch-Ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Upgrade-Insecure-Requests": "1",
}
API_HEADERS = {"User-Agent": f"FinderResearchAgent/1.0 (+{CONTACT or 'academic research'})",
               "Accept": "application/json"}

BLOCK_MARKERS = (
    "cf-chl", "just a moment...", "attention required! | cloudflare", "cf-browser-verification",
    "enable javascript and cookies to continue", "px-captcha", "datadome", "access denied",
    "are you a robot", "unusual traffic", "captcha-delivery", "request unsuccessful. incapsula",
    "cookies must be enabled", "please enable cookies", "checking your browser",
)


@dataclass
class Fetched:
    url: str
    status: int
    content_type: str
    body: bytes
    via: str
    html: bytes = b""  # raw DOM when `body` holds extracted text (browser renders)

    @property
    def text(self) -> str:
        return self.body.decode(_charset(self.content_type) or "utf-8", "replace")


def _charset(content_type: str) -> str | None:
    for part in content_type.split(";"):
        part = part.strip().lower()
        if part.startswith("charset="):
            return part[8:].strip("\"'")
    return None


# ── cache ────────────────────────────────────────────────────────────────────
_cache_lock = threading.Lock()
_cache_conn: sqlite3.Connection | None = None


def _db() -> sqlite3.Connection | None:
    global _cache_conn
    if not CACHE_PATH:
        return None
    if _cache_conn is None:
        os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
        _cache_conn = sqlite3.connect(CACHE_PATH, check_same_thread=False, timeout=10)
        _cache_conn.execute("CREATE TABLE IF NOT EXISTS cache (k TEXT PRIMARY KEY, ts REAL, v TEXT)")
    return _cache_conn


def cache_get(key: str, ttl: float) -> object | None:
    with _cache_lock:
        db = _db()
        if db is None:
            return None
        row = db.execute("SELECT ts, v FROM cache WHERE k=?", (key,)).fetchone()
    if row and time.time() - row[0] < ttl:
        return json.loads(row[1])
    return None


def cache_put(key: str, value: object) -> None:
    with _cache_lock:
        db = _db()
        if db is None:
            return
        db.execute("INSERT OR REPLACE INTO cache VALUES (?,?,?)", (key, time.time(), json.dumps(value)))
        db.commit()


def cache_key(*parts: object) -> str:
    return hashlib.sha256(json.dumps(parts, ensure_ascii=False, default=str).encode()).hexdigest()


# ── politeness: at most one request per host per interval ──────────────────
_host_next: dict[str, float] = {}
_host_lock = asyncio.Lock()
HOST_INTERVAL = 1.0


async def _throttle(url: str) -> None:
    host = urlparse(url).netloc.lower()
    async with _host_lock:
        now = time.monotonic()
        wait = _host_next.get(host, 0) - now
        _host_next[host] = max(now, _host_next.get(host, 0)) + HOST_INTERVAL
    if wait > 0:
        await asyncio.sleep(wait)


# ── transports ───────────────────────────────────────────────────────────────
_httpx: httpx.AsyncClient | None = None


def _client() -> httpx.AsyncClient:
    global _httpx
    if _httpx is None:
        _httpx = httpx.AsyncClient(http2=True, follow_redirects=True, timeout=httpx.Timeout(25, connect=10),
                                   proxy=PROXY, headers=BROWSER_HEADERS)
    return _httpx


async def get_direct(url: str, *, headers: dict | None = None, params: dict | None = None,
                     retries: int = 2) -> Fetched:
    last: Exception | None = None
    for attempt in range(retries + 1):
        await _throttle(url)
        try:
            r = await _client().get(url, headers=headers, params=params)
            if r.status_code in (429, 500, 502, 503, 504) and attempt < retries:
                delay = float(r.headers.get("retry-after", 0) or 0) or (1.5 * 2 ** attempt + random.random())
                await asyncio.sleep(min(delay, 20))
                continue
            return Fetched(str(r.url), r.status_code, r.headers.get("content-type", ""), r.content, "direct")
        except httpx.HTTPError as exc:
            last = exc
            await asyncio.sleep(1 + attempt)
    raise last or RuntimeError("request failed")


async def get_impersonated(url: str, *, headers: dict | None = None, params: dict | None = None) -> Fetched:
    await _throttle(url)
    async with AsyncSession(impersonate="chrome", proxy=PROXY, timeout=30) as s:
        r = await s.get(url, headers=headers, params=params, allow_redirects=True)
        return Fetched(str(r.url), r.status_code, r.headers.get("content-type", ""), r.content, "impersonated")


async def get_jina(url: str) -> Fetched:
    target = "https://r.jina.ai/" + url
    await _throttle(target)
    r = await _client().get(target, headers={"Accept": "text/plain", "X-Return-Format": "markdown",
                                             "User-Agent": API_HEADERS["User-Agent"]}, timeout=60)
    return Fetched(url, r.status_code, "text/markdown; charset=utf-8", r.content, "jina-reader")


async def get_wayback(url: str) -> Fetched | None:
    r = await _client().get("https://archive.org/wayback/available", params={"url": url},
                            headers=API_HEADERS, timeout=20)
    if r.status_code != 200:
        raise RuntimeError(f"archive.org HTTP {r.status_code}")
    snap = (r.json().get("archived_snapshots") or {}).get("closest") or {}
    if not snap.get("available"):
        return None
    f = await get_direct(snap["url"], retries=1)
    f.via = f"wayback ({snap.get('timestamp', '')[:8]})"
    return f


def looks_blocked(f: Fetched) -> bool:
    if f.status in (401, 403, 407, 429, 451, 503):
        return True
    if f.status >= 400:
        return False
    if "html" in f.content_type and len(f.body) < 400_000:
        head = f.body[:60_000].decode("utf-8", "replace").lower()
        return any(m in head for m in BLOCK_MARKERS)
    return False


class PrivateAddress(ValueError):
    pass


async def assert_public(url: str) -> None:
    """Agents browse the public internet only: no localhost, LAN, link-local or metadata addresses."""
    import ipaddress
    import socket

    parts = urlparse(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise PrivateAddress(f"unsupported URL: {url}")
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(parts.hostname, parts.port or 443,
                                                             type=socket.SOCK_STREAM)
    except socket.gaierror:
        return  # unresolvable: the request itself will fail normally
    for info in infos:
        ip = ipaddress.ip_address(info[4][0].split("%")[0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast \
                or ip.is_unspecified:
            raise PrivateAddress(f"{parts.hostname} is a private/internal address; only public sites are allowed")


async def fetch_resilient(url: str) -> tuple[Fetched | None, list[str]]:
    """Run the fallback chain; returns the first good response and a log of attempts."""
    try:
        await assert_public(url)
    except PrivateAddress as exc:
        return None, [str(exc)]
    attempts: list[str] = []
    for name, fn in (("direct", get_direct), ("impersonated", get_impersonated)):
        try:
            f = await fn(url)
        except Exception as exc:  # network errors, TLS, timeouts
            attempts.append(f"{name}: {type(exc).__name__}")
            continue
        if f.status < 400 and not looks_blocked(f):
            attempts.append(f"{name}: {f.status}")
            return f, attempts
        attempts.append(f"{name}: {f.status}{' blocked' if looks_blocked(f) else ''}")
        if f.status in (404, 410):
            return None, attempts
    from . import browser
    if browser.available():
        try:
            f = await browser.render(url)
            if f.status < 400 and not looks_blocked(f):
                attempts.append("browser: ok")
                return f, attempts
            attempts.append(f"browser: {f.status}{' blocked' if looks_blocked(f) else ''}")
        except Exception as exc:
            attempts.append(f"browser: {type(exc).__name__}")
    try:
        f = await get_jina(url)
        head = f.body[:3000].decode("utf-8", "replace").lower()
        jina_blocked = "requiring captcha" in head or "title: just a moment" in head
        if f.status < 400 and len(f.body) > 200 and not jina_blocked:
            attempts.append("jina-reader: ok")
            return f, attempts
        attempts.append(f"jina-reader: {'captcha' if jina_blocked else f.status}")
    except Exception as exc:
        attempts.append(f"jina-reader: {type(exc).__name__}")
    try:
        f = await get_wayback(url)
        if f and f.status < 400:
            attempts.append("wayback: ok")
            return f, attempts
        attempts.append("wayback: no snapshot")
    except Exception as exc:
        attempts.append(f"wayback: {exc if isinstance(exc, RuntimeError) else type(exc).__name__}")
    return None, attempts


async def get_json(url: str, *, params: dict | None = None, headers: dict | None = None,
                   ttl: float = 3600) -> object:
    """GET a JSON API, falling back to TLS impersonation when the plain client is refused."""
    key = cache_key("json", url, params)
    if (hit := cache_get(key, ttl)) is not None:
        return hit
    hdrs = {**API_HEADERS, **(headers or {})}
    f = await get_direct(url, params=params, headers=hdrs)
    if f.status >= 400 or looks_blocked(f):
        f = await get_impersonated(url, params=params, headers={"Accept": "application/json"})
    if f.status >= 400:
        raise RuntimeError(f"{urlparse(url).netloc} answered HTTP {f.status}")
    data = json.loads(f.body)
    cache_put(key, data)
    return data


async def post_json(url: str, *, json_body: object = None, params: dict | None = None,
                    files: dict | None = None, ttl: float = 3600) -> object:
    key = cache_key("post", url, params, json_body, {k: v[1] for k, v in (files or {}).items()})
    if (hit := cache_get(key, ttl)) is not None:
        return hit
    await _throttle(url)
    r = await _client().post(url, json=json_body, params=params, files=files, headers=API_HEADERS)
    if r.status_code >= 400:
        raise RuntimeError(f"{urlparse(url).netloc} answered HTTP {r.status_code}")
    data = r.json()
    cache_put(key, data)
    return data
