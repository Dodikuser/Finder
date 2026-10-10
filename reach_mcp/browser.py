"""Real-browser rendering for pages that need JavaScript or reject non-browser clients.

One shared Chrome per server: the Finder backend runs `Engine` and every agent's MCP process asks
it to render over loopback (FINDER_RENDER_URL + FINDER_RENDER_TOKEN). Without those variables
(standalone use) the MCP process runs its own Engine.

Full Chrome/Chromium in the new headless mode (the stripped "headless shell" is recognised by bot
filters). Interstitials that need a human (CAPTCHA) are not solved — they are reported as blocked.
"""

import asyncio
import os
import time

import httpx

from .net import PROXY, Fetched

MODE = os.environ.get("FINDER_BROWSER", "auto")  # auto | off
RENDER_URL = os.environ.get("FINDER_RENDER_URL", "")
RENDER_TOKEN = os.environ.get("FINDER_RENDER_TOKEN", "")

_ARGS = ["--headless=new", "--disable-blink-features=AutomationControlled", "--no-first-run",
         "--no-default-browser-check", "--disable-dev-shm-usage"]
if os.environ.get("FINDER_BROWSER_NO_SANDBOX", "").lower() in ("1", "true", "yes"):
    # Inside an unprivileged container Chrome cannot create its own sandbox; the container is the boundary.
    _ARGS += ["--no-sandbox", "--disable-gpu"]

_VISIBLE_TEXT_JS = """() => {
  // Web components keep their text in Shadow DOM, invisible to innerText (e.g. Hetzner prices):
  // copy each open shadow root's text into the light DOM first.
  const shadowText = (root) => {
    let out = '';
    const walk = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT);
    for (let n = walk.currentNode; n; n = walk.nextNode()) {
      if (n.nodeType === 3) {
        const p = n.parentElement;
        if (!p || !['STYLE', 'SCRIPT', 'TEMPLATE'].includes(p.tagName)) out += n.textContent + ' ';
      } else if (n.shadowRoot) { out += shadowText(n.shadowRoot) + ' '; }
    }
    // join prices split across elements: "€ 1." + "60" -> "€ 1.60"
    return out.replace(/\\s+/g, ' ').replace(/(\\d) ?([.,]) ?(\\d{2})\\b/g, '$1$2$3').trim();
  };
  // Insert next to the host (children of a shadow host are not rendered unless slotted).
  [...document.querySelectorAll('*')].filter(el => el.shadowRoot).forEach(el => {
    const t = shadowText(el.shadowRoot);
    if (t) { const s = document.createElement('span'); s.textContent = ' ' + t + ' '; el.after(s); }
  });
  const junk =['script','style','noscript','svg','iframe','template','nav','footer','[role=navigation]',
    '[role=dialog]','[aria-modal=true]','#CybotCookiebotDialog','#onetrust-consent-sdk','#onetrust-banner-sdk',
    '[id*=cookie i]','[class*=cookie i]','[id*=consent i]','[class*=consent i]','[class*=gdpr i]'];
  for (const sel of junk) { try { document.querySelectorAll(sel).forEach(n => n.remove()); } catch (e) {} }
  const root = document.querySelector('main') || document.body;
  const text = root ? root.innerText : '';
  return text.split('\\n').map(l => l.trim()).filter((l, i, a) => l || (a[i - 1] || '')).join('\\n');
}"""


_HAS_CUSTOM_ELEMENTS_JS = """() => [...document.querySelectorAll('*')].some(e => e.shadowRoot || e.tagName.includes('-'))"""


class BrowserBusy(RuntimeError):
    pass


class Engine:
    """Lazily started Chrome with a hard cap on concurrently open pages and an idle shutdown."""

    def __init__(self, max_pages: int = 3, idle_seconds: int = 120, queue_timeout: float = 90):
        self.max_pages, self.idle_seconds, self.queue_timeout = max_pages, idle_seconds, queue_timeout
        self._sem = asyncio.Semaphore(max_pages)
        self._lock = asyncio.Lock()
        self._pw = self._browser = self._ctx = None
        self._used = 0.0
        self._active = 0
        self._waiting = 0
        self.failed = False
        self.renders = 0

    def stats(self) -> dict:
        return {"running": self._browser is not None, "active_pages": self._active, "waiting": self._waiting,
                "max_pages": self.max_pages, "renders": self.renders, "failed": self.failed}

    async def _launch(self) -> None:
        from playwright.async_api import async_playwright

        pw = await async_playwright().start()
        browser = None
        for extra in (dict(channel="chrome"), dict(channel="msedge"), dict()):  # system browser, then bundled
            try:
                browser = await pw.chromium.launch(headless=False, args=_ARGS,
                                                   proxy={"server": PROXY} if PROXY else None, **extra)
                break
            except Exception:
                continue
        if browser is None:
            await pw.stop()
            raise RuntimeError("no Chromium/Chrome available")
        self._pw, self._browser = pw, browser
        asyncio.get_running_loop().create_task(self._reaper())

    async def _new_context(self):
        # A fresh context per page: no cookies or storage leak between users' requests.
        ctx = await self._browser.new_context(locale="en-US", viewport={"width": 1366, "height": 900})
        await ctx.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        await ctx.route("**/*", lambda route: route.abort()
                        if route.request.resource_type in ("image", "media", "font") else route.continue_())
        return ctx

    async def _reaper(self) -> None:
        while self._browser is not None:
            await asyncio.sleep(15)
            if self._active == 0 and self._waiting == 0 and time.monotonic() - self._used > self.idle_seconds:
                async with self._lock:
                    if self._active == 0:
                        await self.close()
                return

    async def close(self) -> None:
        browser, pw = self._browser, self._pw
        self._browser = self._pw = None
        for closer in (browser.close if browser else None, pw.stop if pw else None):
            if closer:
                try:
                    await closer()
                except Exception:
                    pass

    async def pdf(self, document_html: str) -> bytes:
        """Print our own HTML to an A4 PDF. The page runs with JavaScript off and every network
        request refused, so document content cannot execute or fetch anything."""
        if self.failed:
            raise RuntimeError("browser unavailable")
        self._waiting += 1
        try:
            await asyncio.wait_for(self._sem.acquire(), timeout=self.queue_timeout)
        except asyncio.TimeoutError:
            raise BrowserBusy("browser queue is full, try again later") from None
        finally:
            self._waiting -= 1
        self._active += 1
        try:
            async with self._lock:
                if self._browser is None:
                    try:
                        await self._launch()
                    except Exception:
                        self.failed = True
                        raise
            self._used = time.monotonic()
            ctx = await self._browser.new_context(java_script_enabled=False, offline=True)
            try:
                await ctx.route("**/*", lambda route: route.abort())
                page = await ctx.new_page()
                await page.set_content(document_html, wait_until="domcontentloaded")
                return await page.pdf(format="A4", print_background=True)
            finally:
                await ctx.close()
        finally:
            self._active -= 1
            self._used = time.monotonic()
            self._sem.release()

    async def render(self, url: str, timeout: float = 40) -> dict:
        if self.failed:
            raise RuntimeError("browser unavailable")
        self._waiting += 1
        try:
            await asyncio.wait_for(self._sem.acquire(), timeout=self.queue_timeout)
        except asyncio.TimeoutError:
            raise BrowserBusy("browser queue is full, try again later") from None
        finally:
            self._waiting -= 1
        self._active += 1
        try:
            async with self._lock:
                if self._browser is None:
                    try:
                        await self._launch()
                    except Exception:
                        self.failed = True
                        raise
            self._used = time.monotonic()
            ctx = await self._new_context()
            try:
                page = await ctx.new_page()
                resp = await page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
                title = ""
                for _ in range(3):  # let client-side rendering and JS challenges settle
                    try:
                        await page.wait_for_load_state("networkidle", timeout=6000)
                    except Exception:
                        pass
                    title = await page.title()
                    if not any(m in title.lower() for m in ("just a moment", "403", "checking", "attention required")):
                        break
                    await page.wait_for_timeout(2500)
                if await page.evaluate(_HAS_CUSTOM_ELEMENTS_JS):
                    # Web components often fetch their data (prices!) after the network looked idle.
                    await page.wait_for_timeout(2500)
                    try:
                        await page.wait_for_load_state("networkidle", timeout=5000)
                    except Exception:
                        pass
                html = await page.content()
                text = await page.evaluate(_VISIBLE_TEXT_JS)
                status = resp.status if resp else 200
                if status in (403, 503) and "403" not in title:
                    status = 200  # challenge passed after the first response
                self.renders += 1
                return {"url": page.url, "status": status, "title": title, "text": text, "html": html}
            finally:
                await ctx.close()
        finally:
            self._active -= 1
            self._used = time.monotonic()
            self._sem.release()


_local: Engine | None = None
_remote_dead = False


def available() -> bool:
    return MODE != "off" and not (_local is not None and _local.failed)


def _to_fetched(d: dict) -> Fetched:
    body = f"Title: {d.get('title', '')}\n\n{d.get('text', '')}".encode("utf-8")
    return Fetched(d["url"], int(d["status"]), "text/markdown; charset=utf-8", body, "browser",
                   html=(d.get("html") or "").encode("utf-8"))


async def render(url: str) -> Fetched:
    global _local, _remote_dead
    if MODE == "off":
        raise RuntimeError("browser disabled")
    if RENDER_URL and not _remote_dead:
        try:
            async with httpx.AsyncClient(timeout=180) as c:
                r = await c.post(RENDER_URL, json={"url": url}, headers={"X-Finder-Render-Token": RENDER_TOKEN})
        except httpx.ConnectError:
            _remote_dead = True  # backend gone: fall back to a local browser
        else:
            if r.status_code != 200:
                raise RuntimeError(f"render service: {r.status_code} {r.text[:200]}")
            return _to_fetched(r.json())
    if _local is None:
        _local = Engine(max_pages=2, idle_seconds=90)
    return _to_fetched(await _local.render(url))
