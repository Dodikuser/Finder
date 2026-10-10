"""Things the agent can hand to the user: a chart dashboard, a document (PDF/DOCX/MD/CSV), an image.

The agent still has no filesystem or shell. It passes *content* (numbers, markdown, an image URL)
to these tools; the files are produced by this server code inside one folder that belongs to the
current chat (FINDER_ARTIFACT_DIR). Names are generated here, sizes and types are capped, and the
Finder backend — not the agent — decides who may download what.
"""

import csv
import html
import io
import json
import math
import os
import re
import secrets
import time
from pathlib import Path

import httpx

from . import net

ARTIFACT_DIR = os.environ.get("FINDER_ARTIFACT_DIR", "")
PDF_URL = os.environ.get("FINDER_PDF_URL", "")
RENDER_TOKEN = os.environ.get("FINDER_RENDER_TOKEN", "")

MAX_FILES = 40
MAX_DOC_CHARS = 200_000
MAX_IMAGE_BYTES = 8 * 1024 * 1024
CHART_TYPES = ("bar", "hbar", "stacked", "line", "area", "share")
_IMAGE_MAGIC = ((b"\x89PNG\r\n\x1a\n", "png", "image/png"), (b"\xff\xd8\xff", "jpg", "image/jpeg"),
                (b"GIF87a", "gif", "image/gif"), (b"GIF89a", "gif", "image/gif"))


class ArtifactError(ValueError):
    pass


def _dir() -> Path:
    if not ARTIFACT_DIR:
        raise ArtifactError("File output is not available in this chat.")
    d = Path(ARTIFACT_DIR)
    d.mkdir(parents=True, exist_ok=True)
    if sum(1 for _ in d.glob("*.meta.json")) >= MAX_FILES:
        raise ArtifactError(f"This chat already holds {MAX_FILES} files; no more can be added.")
    return d


def _slug(title: str, fallback: str) -> str:
    s = re.sub(r"[^\w\-]+", "-", title.strip(), flags=re.UNICODE).strip("-_")[:60]
    return s or fallback


def _register(kind: str, title: str, ext: str, mime: str, payload: bytes, *, data: dict | None = None,
              caption: str = "") -> dict:
    d = _dir()
    art_id = secrets.token_hex(12)
    stored = f"{art_id}.{ext}"
    (d / stored).write_bytes(payload)
    meta = {"id": art_id, "kind": kind, "title": title.strip()[:200] or kind, "mime": mime, "file": stored,
            "filename": f"{_slug(title, kind)}.{ext}", "size": len(payload), "caption": caption[:500],
            "created": time.time()}
    if data is not None:
        meta["data"] = data
    # Written last and atomically: the backend picks up an artifact only once its metadata exists.
    tmp = d / f"{art_id}.meta.tmp"
    tmp.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    tmp.replace(d / f"{art_id}.meta.json")
    return meta


# ── dashboard ────────────────────────────────────────────────────────────────

def _num(v, where: str) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        raise ArtifactError(f"{where}: values must be plain numbers (no text, units or null) — got {v!r}")
    return float(v)


def _text(v, limit: int) -> str:
    return str(v if v is not None else "").strip()[:limit]


def clean_dashboard(title: str, summary: str, kpis: list, charts: list) -> dict:
    """Validate and normalise what the model sent; raise ArtifactError with a fixable message."""
    if not isinstance(charts, list) or not charts:
        raise ArtifactError("Give at least one chart.")
    if len(charts) > 8:
        raise ArtifactError("At most 8 charts per dashboard: keep the ones that answer the question.")
    out_charts = []
    for ci, c in enumerate(charts, 1):
        if not isinstance(c, dict):
            raise ArtifactError(f"chart {ci}: must be an object")
        ctype = _text(c.get("type"), 20).lower()
        if ctype not in CHART_TYPES:
            raise ArtifactError(f"chart {ci}: type must be one of {', '.join(CHART_TYPES)}")
        series_in = c.get("series")
        if not isinstance(series_in, list) or not series_in:
            raise ArtifactError(f"chart {ci}: needs a non-empty 'series' list")
        if len(series_in) > 8:
            raise ArtifactError(f"chart {ci}: at most 8 series — merge the smallest into 'Other' or split the chart")
        if ctype in ("share", "hbar") and len(series_in) != 1:
            raise ArtifactError(f"chart {ci}: '{ctype}' takes exactly one series (one value per category)")
        series = []
        for si, s in enumerate(series_in, 1):
            pts_in = s.get("points") if isinstance(s, dict) else None
            if not isinstance(pts_in, list) or not pts_in:
                raise ArtifactError(f"chart {ci}, series {si}: needs 'points': [{{\"x\": ..., \"y\": number}}]")
            if len(pts_in) > 200:
                raise ArtifactError(f"chart {ci}, series {si}: at most 200 points")
            pts = []
            for p in pts_in:
                if not isinstance(p, dict) or "x" not in p or "y" not in p:
                    raise ArtifactError(f"chart {ci}, series {si}: every point needs x and y")
                pts.append({"x": _text(p["x"], 60), "y": _num(p["y"], f"chart {ci}, series {si}")})
            series.append({"name": _text(s.get("name"), 60) or f"Series {si}", "points": pts})
        if ctype == "share":
            if len(series[0]["points"]) > 6:
                raise ArtifactError(f"chart {ci}: 'share' shows at most 6 parts — merge small ones into 'Other' or use 'hbar'")
            if any(p["y"] < 0 for p in series[0]["points"]):
                raise ArtifactError(f"chart {ci}: 'share' cannot show negative values")
        out_charts.append({"type": ctype, "title": _text(c.get("title"), 140) or f"Chart {ci}",
                           "subtitle": _text(c.get("subtitle"), 240), "unit": _text(c.get("unit"), 16),
                           "x_label": _text(c.get("x_label"), 60), "y_label": _text(c.get("y_label"), 60),
                           "source": _text(c.get("source"), 300), "series": series})
    out_kpis = []
    for k in (kpis or [])[:6]:
        if isinstance(k, dict) and _text(k.get("label"), 60) and _text(k.get("value"), 40):
            out_kpis.append({"label": _text(k.get("label"), 60), "value": _text(k.get("value"), 40),
                             "hint": _text(k.get("hint"), 120)})
    return {"title": _text(title, 160) or "Analytics", "summary": _text(summary, 2000), "kpis": out_kpis,
            "charts": out_charts}


def save_dashboard(title: str, summary: str, kpis: list, charts: list) -> dict:
    data = clean_dashboard(title, summary, kpis, charts)
    payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
    return _register("dashboard", data["title"], "json", "application/json", payload, data=data)


# ── documents ────────────────────────────────────────────────────────────────

_DOC_CSS = """
@page { size: A4; margin: 18mm 16mm 20mm 16mm; }
* { box-sizing: border-box; }
body { font-family: "DejaVu Sans", "Segoe UI", "Noto Sans", Arial, sans-serif; font-size: 10.5pt; line-height: 1.55; color: #14211d; }
h1 { font-size: 20pt; margin: 0 0 4pt; line-height: 1.2; }
h2 { font-size: 14pt; margin: 18pt 0 6pt; padding-bottom: 3pt; border-bottom: 1.5pt solid #cfe9dd; }
h3 { font-size: 11.5pt; margin: 14pt 0 4pt; }
p { margin: 0 0 7pt; }
ul, ol { margin: 0 0 7pt; padding-left: 16pt; }
li { margin-bottom: 2.5pt; }
a { color: #0b6e55; text-decoration: none; word-break: break-all; }
table { border-collapse: collapse; width: 100%; margin: 6pt 0 10pt; font-size: 9.2pt; page-break-inside: auto; }
th, td { border: 0.6pt solid #b9d6c9; padding: 4pt 6pt; text-align: left; vertical-align: top; }
th { background: #e8f7f0; font-weight: 700; }
tr { page-break-inside: avoid; }
code { font-family: "DejaVu Sans Mono", Consolas, monospace; font-size: 9pt; background: #eef6f2; padding: 0 2pt; }
pre { background: #eef6f2; padding: 7pt; font-size: 8.8pt; white-space: pre-wrap; word-break: break-word; }
blockquote { margin: 6pt 0; padding-left: 9pt; border-left: 2.5pt solid #9fd9c2; color: #3f5a52; }
.doc-meta { color: #5a736b; font-size: 9pt; margin-bottom: 14pt; }
"""
_ALLOWED_TAGS = {"h1", "h2", "h3", "h4", "p", "ul", "ol", "li", "strong", "em", "b", "i", "a", "table", "thead",
                 "tbody", "tr", "th", "td", "code", "pre", "blockquote", "br", "hr", "sup", "sub", "del"}


def markdown_to_html(md: str) -> str:
    """Markdown → sanitised HTML fragment (no scripts, styles, images or raw HTML pass through)."""
    import markdown
    import nh3

    raw = markdown.markdown(md, extensions=["tables", "fenced_code", "sane_lists"], output_format="html")
    return nh3.clean(raw, tags=_ALLOWED_TAGS, attributes={"a": {"href"}, "td": {"align"}, "th": {"align"}},
                     url_schemes={"http", "https", "mailto"}, link_rel=None)


def _doc_html(title: str, body_html: str) -> str:
    stamp = time.strftime("%Y-%m-%d")
    return (f"<!doctype html><html><head><meta charset='utf-8'><title>{html.escape(title)}</title>"
            f"<style>{_DOC_CSS}</style></head><body><h1>{html.escape(title)}</h1>"
            f"<div class='doc-meta'>Finder · {stamp}</div>{body_html}</body></html>")


async def _html_to_pdf(doc_html: str) -> bytes:
    if PDF_URL:
        async with httpx.AsyncClient(timeout=120) as c:
            r = await c.post(PDF_URL, json={"html": doc_html}, headers={"X-Finder-Render-Token": RENDER_TOKEN})
        if r.status_code != 200:
            raise ArtifactError(f"PDF service error {r.status_code}: {r.text[:200]}")
        return r.content
    from .browser import Engine  # standalone use: a private browser just for this conversion

    eng = Engine(max_pages=1, idle_seconds=5)
    try:
        return await eng.pdf(doc_html)
    finally:
        await eng.close()


def _html_to_docx(title: str, body_html: str) -> bytes:
    from docx import Document
    from htmldocx import HtmlToDocx

    doc = Document()
    doc.add_heading(title, level=0)
    HtmlToDocx().add_html_to_document(body_html, doc)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


async def save_document(title: str, content_markdown: str, fmt: str) -> dict:
    fmt = (fmt or "pdf").lower().strip(".")
    if fmt not in ("pdf", "docx", "md", "csv"):
        raise ArtifactError("format must be one of: pdf, docx, md, csv")
    if not content_markdown or not content_markdown.strip():
        raise ArtifactError("The document is empty.")
    if len(content_markdown) > MAX_DOC_CHARS:
        raise ArtifactError(f"The document is too long ({len(content_markdown)} chars; limit {MAX_DOC_CHARS}).")
    title = title.strip() or "Document"
    if fmt == "md":
        return _register("document", title, "md", "text/markdown; charset=utf-8",
                         f"# {title}\n\n{content_markdown}".encode("utf-8"))
    if fmt == "csv":
        rows = _markdown_table_rows(content_markdown)
        if not rows:
            raise ArtifactError("For csv, pass one markdown table (| a | b | rows) as the content.")
        buf = io.StringIO()
        csv.writer(buf).writerows(rows)
        return _register("document", title, "csv", "text/csv; charset=utf-8", ("﻿" + buf.getvalue()).encode("utf-8"))
    body = markdown_to_html(content_markdown)
    if fmt == "docx":
        return _register("document", title, "docx",
                         "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                         _html_to_docx(title, body))
    return _register("document", title, "pdf", "application/pdf", await _html_to_pdf(_doc_html(title, body)))


def _markdown_table_rows(md: str) -> list[list[str]]:
    rows = []
    for line in md.splitlines():
        line = line.strip()
        if not (line.startswith("|") and line.endswith("|")):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if all(re.fullmatch(r":?-{2,}:?", c) for c in cells):
            continue  # the header separator
        rows.append([re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 (\2)", re.sub(r"[*_`]", "", c)) for c in cells])
    return rows


# ── images ───────────────────────────────────────────────────────────────────

async def save_image(url: str, caption: str) -> dict:
    await net.assert_public(url)
    f = await net.get_direct(url, headers={"Accept": "image/avif,image/webp,image/png,image/jpeg,*/*;q=0.5"}, retries=1)
    if f.status >= 400 or net.looks_blocked(f):
        f = await net.get_impersonated(url)
    if f.status >= 400:
        raise ArtifactError(f"Could not download the image (HTTP {f.status}).")
    body = f.body
    if len(body) > MAX_IMAGE_BYTES:
        raise ArtifactError("The image is larger than 8 MB.")
    kind = next(((ext, mime) for magic, ext, mime in _IMAGE_MAGIC if body.startswith(magic)), None)
    if kind is None and body[:4] == b"RIFF" and body[8:12] == b"WEBP":
        kind = ("webp", "image/webp")
    if kind is None:
        raise ArtifactError("That URL is not a PNG, JPEG, GIF or WebP image (SVG and other formats are not accepted).")
    title = caption.strip() or url.rsplit("/", 1)[-1][:80] or "image"
    return _register("image", title, kind[0], kind[1], body, caption=caption, data={"source_url": url[:1000]})
