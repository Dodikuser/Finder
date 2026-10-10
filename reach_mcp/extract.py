"""Turn fetched bytes into readable text: main-content HTML extraction, PDFs, link lists."""

import html as htmllib
import io
import re
from urllib.parse import urljoin, urlparse

import trafilatura
from pypdf import PdfReader

from .net import Fetched

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"[ \t\r\f\v]+")
_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
_A = re.compile(r"<a\b[^>]*?href\s*=\s*[\"']([^\"'#]+)[\"'][^>]*>(.*?)</a>", re.I | re.S)
_MD_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_MD_LINK =re.compile(r"\[([^\]]{1,200})\]\((https?://[^)\s]+)\)")


def clean(text: str) -> str:
    text = htmllib.unescape(_TAG.sub(" ", text))
    return re.sub(r"\n{3,}", "\n\n", _WS.sub(" ", text)).strip()


def title_of(raw_html: str) -> str:
    m = _TITLE.search(raw_html[:200_000])
    return clean(m.group(1))[:200] if m else ""


_CONSENT = re.compile(r"(?i)\b(cookies?|consent|gdpr|cookiebot|onetrust)\b")
_WIDGET = re.compile(r"\[#[A-Z0-9_]+#\]|^[-*]\s*\[[x ]\]\s*$")
_CONSENT_CTX = re.compile(r"(?i)accept|reject|consent|privacy|preferences|partners|vendors|manage|settings|storage")
_BULLET = re.compile(r"^[\s*\-+|>]+")


def tidy_markdown(text: str) -> str:
    """Drop what a full-page render adds around the content: link-only navigation lines,
    cookie/consent notices, empty table scaffolding. Headings (often article titles) stay."""
    out: list[str] = []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            if out and out[-1] != "":
                out.append("")
            continue
        if s.startswith("#"):
            out.append(line)
            continue
        plain = _BULLET.sub("", _MD_LINK.sub(r"\1", s)).strip()
        if _MD_LINK.search(s) and len(plain.split()) <= 3:
            continue  # menu item / tag / breadcrumb
        if not plain or set(plain) <= set("|-: "):
            continue
        if _WIDGET.search(s) or (_CONSENT.search(s) and (_CONSENT_CTX.search(s) or len(s) < 300)):
            continue  # cookie/consent widget
        out.append(line)
    return "\n".join(out).strip()


def strip_consent(text: str) -> str:
    keep = [l for l in text.splitlines()
            if not (_WIDGET.search(l.strip()) or (_CONSENT.search(l) and (_CONSENT_CTX.search(l) or len(l) < 300)))]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(keep)).strip()


def to_text(f: Fetched) -> tuple[str, str]:
    """(title, readable text) for any fetched document."""
    ctype = f.content_type.lower()
    if "pdf" in ctype or f.body[:5] == b"%PDF-":
        reader = PdfReader(io.BytesIO(f.body))
        meta_title = (reader.metadata.title if reader.metadata else "") or ""
        pages = [p.extract_text() or "" for p in reader.pages[:60]]
        return meta_title, "\n\n".join(pages).strip()
    text = f.text
    if "markdown" in ctype or f.via == "jina-reader":
        first, _, rest = text.partition("\n")
        title = first[6:].strip() if first.lower().startswith("title:") else ""
        if title and f.via == "browser":
            text = rest
        if "Markdown Content:" in text:  # drop Jina's header block
            text = text.split("Markdown Content:", 1)[1]
        text = _MD_IMAGE.sub("", text)  # images are useless to a text agent and cost context
        return title, tidy_markdown(text)
    if "html" in ctype or text.lstrip()[:15].lower().startswith(("<!doctype", "<html")):
        md = trafilatura.extract(text, url=f.url, output_format="markdown", include_links=True,
                                 include_tables=True, favor_recall=True) or ""
        if len(md) < 200:  # extraction found no article body: fall back to all visible text
            body = re.sub(r"<(script|style|noscript|svg)[^>]*>.*?</\1>", " ", text, flags=re.I | re.S)
            md = clean(body)
        return title_of(text), strip_consent(md)
    return "", text


def links_from(f: Fetched) -> list[tuple[str, str]]:
    """(url, anchor text) pairs, absolutised, de-duplicated (longest anchor wins)."""
    found: dict[str, str] = {}
    if f.html:
        pairs = _A.findall(f.html.decode("utf-8", "replace"))
    elif f.via == "jina-reader" or "markdown" in f.content_type:
        pairs = [(u, t) for t, u in _MD_LINK.findall(f.text)]
    else:
        pairs = _A.findall(f.text)
    for href, label in pairs:
        href = htmllib.unescape(href.strip())
        if href.startswith(("javascript:", "mailto:", "tel:")) or "{{" in href:
            continue
        url = urljoin(f.url, href)
        if urlparse(url).scheme not in ("http", "https"):
            continue
        label = clean(label)[:200]
        if len(label) > len(found.get(url, "")):
            found[url] = label
        else:
            found.setdefault(url, label)
    return list(found.items())
