"""finder-reach: internet-only MCP tools for Finder agents (no filesystem, no shell).

Channels follow the Agent Reach idea — pick the most reliable upstream for each kind of source —
but run as MCP tools, so the agent needs no terminal. FINDER_REACH_TOOLS limits which tools a
given agent sees.
"""

import asyncio
import os
import re
import xml.etree.ElementTree as ET
from datetime import date, datetime
from urllib.parse import parse_qs, quote_plus, urlparse

import feedparser
from mcp.server.fastmcp import FastMCP

from . import artifacts, net
from .extract import clean, links_from, to_text

mcp = FastMCP("finder-reach")
_ENABLED = {t.strip() for t in os.environ.get("FINDER_REACH_TOOLS", "").split(",") if t.strip()}
_REGISTERED: list[str] = []

PAGE_TTL = 6 * 3600
_AD_URL = re.compile(r"duckduckgo\.com/y\.js|bing\.com/aclick|googleadservices|doubleclick\.net")
NCBI = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


def tool(fn):
    """Register only the tools enabled for this agent (all when the list is empty)."""
    _REGISTERED.append(fn.__name__)
    if not _ENABLED or fn.__name__ in _ENABLED:
        return mcp.tool()(fn)
    return fn


def _cut(text: str, limit: int) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[:limit].rstrip() + "…"


# ═══ General web ═════════════════════════════════════════════════════════════

@tool
async def web_search(query: str, max_results: int = 10, kind: str = "web", timelimit: str = "",
                     region: str = "") -> str:
    """Search the web. kind: "web" or "news". timelimit: "" | "d" | "w" | "m" | "y" (past day/week/
    month/year). region like "ua-uk", "de-de", "us-en" (default: worldwide). Returns titles, URLs and
    snippets; open promising results with fetch_page."""
    max_results = max(1, min(max_results, 25))
    key = net.cache_key("search", query, max_results, kind, timelimit, region)
    if (hit := net.cache_get(key, 1800)) is not None:
        return hit  # type: ignore[return-value]
    rows: list[dict] = []
    errors = []
    try:
        rows = await asyncio.to_thread(_ddgs, query, max_results, kind, timelimit, region)
    except Exception as exc:
        errors.append(f"ddgs: {type(exc).__name__}")
    if not rows and kind == "web":
        try:
            rows = await _ddg_html(query, max_results)
        except Exception as exc:
            errors.append(f"duckduckgo-html: {type(exc).__name__}")
    rows = [r for r in rows if r.get("url") and not _AD_URL.search(r["url"])]
    if not rows:
        return f"No results for {query!r}." + (f" ({'; '.join(errors)})" if errors else "")
    lines = [f"Search results for {query!r}:"]
    for i, r in enumerate(rows, 1):
        meta = " · ".join(x for x in (r.get("source", ""), r.get("date", "")) if x)
        lines.append(f"{i}. {r['title']}\n   {r['url']}" + (f"\n   {meta}" if meta else "")
                     + (f"\n   {_cut(r.get('snippet', ''), 300)}" if r.get("snippet") else ""))
    out = "\n".join(lines)
    net.cache_put(key, out)
    return out


def _ddgs(query: str, n: int, kind: str, timelimit: str, region: str) -> list[dict]:
    from ddgs import DDGS
    with DDGS(proxy=net.PROXY, timeout=20) as d:
        kwargs = {"max_results": n, "region": region or "wt-wt", "timelimit": timelimit or None}
        if kind == "news":
            res = d.news(query, **kwargs)
            return [{"title": r.get("title", ""), "url": r.get("url", ""), "snippet": r.get("body", ""),
                     "source": r.get("source", ""), "date": (r.get("date") or "")[:10]} for r in res]
        res = d.text(query, **kwargs)
        return [{"title": r.get("title", ""), "url": r.get("href", ""), "snippet": r.get("body", "")} for r in res]


async def _ddg_html(query: str, n: int) -> list[dict]:
    f = await net.get_impersonated("https://html.duckduckgo.com/html/", params={"q": query})
    rows = []
    for m in re.finditer(r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>.*?class="result__snippet"[^>]*>(.*?)</a>',
                         f.text, re.S):
        href = m.group(1)
        if "uddg=" in href:
            href = parse_qs(urlparse(href).query).get("uddg", [href])[0]
        rows.append({"title": clean(m.group(2)), "url": href, "snippet": clean(m.group(3))})
        if len(rows) >= n:
            break
    return rows


@tool
async def fetch_page(url: str, max_chars: int = 12000, offset: int = 0, focus: str = "") -> str:
    """Open a web page or PDF and return its main text as markdown. Handles blocking automatically:
    plain request → Chrome TLS impersonation → real headless browser → Jina Reader → Internet Archive.
    `focus`: words describing what you need (e.g. "price tariff renews", "deadline eligibility") —
    on long pages only the most relevant sections are returned, which saves context.
    Long documents are paginated: call again with offset to continue."""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    max_chars = max(1000, min(max_chars, 40000))
    # PubMed article pages are an app shell; the E-utilities record is cleaner and never blocked.
    if m := re.match(r"https?://pubmed\.ncbi\.nlm\.nih\.gov/(\d+)", url):
        return await pubmed_fetch(m.group(1))
    key = net.cache_key("page", url)
    doc = net.cache_get(key, PAGE_TTL)
    if doc is None:
        f, attempts = await net.fetch_resilient(url)
        if f is None:
            if (doi := _doi_in(url)) and (alt := await _doi_fallback(doi)):
                return f"{url} blocks automated access ({'; '.join(attempts)}). Scholarly record instead:\n\n{alt}"
            return f"Could not read {url}. Attempts: {'; '.join(attempts)}. Try another source for this information."
        try:
            title, text = to_text(f)
        except Exception as exc:
            return f"Fetched {url} via {f.via} but could not extract text ({type(exc).__name__})."
        thin = len(text) < 800 or (len(f.body) > 120_000 and len(text) < 6000)
        if thin and len(f.body) > 30_000 and f.via in ("direct", "impersonated"):
            # Heavy page, little text: content is rendered by JavaScript. Render it for real.
            from . import browser
            renderers = ([browser.render] if browser.available() else []) + [net.get_jina]
            for render in renderers:
                try:
                    rendered = await render(url)
                    if rendered.status >= 400 or net.looks_blocked(rendered):
                        continue
                    r_title, r_text = to_text(rendered)
                    if len(r_text) > len(text) * 1.5:
                        f, title, text = rendered, r_title or title, r_text
                        break
                except Exception:
                    continue
        doc = {"url": f.url, "title": title, "text": text, "via": f.via}
        net.cache_put(key, doc)
    text: str = doc["text"]  # type: ignore[index]
    if focus.strip() and len(text) > max_chars and offset == 0:
        picked, n, total = _focus_sections(text, focus, max_chars)
        head = [f"Source: {doc['url']}", f"Fetched via: {doc['via']}"]  # type: ignore[index]
        if doc.get("title"):  # type: ignore[union-attr]
            head.append(f"Title: {doc['title']}")  # type: ignore[index]
        head.append(f"[Focused on {focus!r}: {n} of {total} sections of a {len(text)}-char page; "
                    f"call without focus to read it in order]")
        return "\n".join(head) + "\n\n" + picked
    chunk = text[offset:offset + max_chars]
    header = [f"Source: {doc['url']}", f"Fetched via: {doc['via']}"]  # type: ignore[index]
    if doc.get("title"):  # type: ignore[union-attr]
        header.append(f"Title: {doc['title']}")  # type: ignore[index]
    if offset + max_chars < len(text):
        header.append(f"[Showing {offset}-{offset + len(chunk)} of {len(text)} chars; "
                      f"call fetch_page with offset={offset + max_chars} for more]")
    return "\n".join(header) + "\n\n" + (chunk or "(no readable text)")


_PRICE = re.compile(r"(?:[$€£₴]\s?\d[\d.,]*|\d[\d.,]*\s?(?:€|\$|£|₴|грн|eur|usd|uah))", re.I)
_PRICE_WORDS = ("price", "pric", "cost", "tariff", "plan", "ціна", "цін", "вартість", "тариф", "цена", "стоим",
                "preis", "kosten", "amount", "budget", "сума", "бюджет", "€", "$")


def _focus_sections(text: str, focus: str, limit: int) -> tuple[str, int, int]:
    """Lightweight retrieval: score markdown sections by focus terms, keep the best ones in page order."""
    terms = [t.lower() for t in re.split(r"[\s,;|]+", focus) if len(t) >= 2]
    want_money = any(w in focus.lower() for w in _PRICE_WORDS)
    blocks = [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()]
    sections: list[str] = []  # glue short blocks to the heading/paragraph before them
    for b in blocks:
        if sections and (len(b) < 120 or b.startswith(("-", "*", "|"))) and len(sections[-1]) < 1500:
            sections[-1] += "\n" + b
        else:
            sections.append(b)
    scored = []
    for i, sec in enumerate(sections):
        low = sec.lower()
        score = sum(low.count(t) for t in terms) + (2 * len(_PRICE.findall(sec)) if want_money else 0)
        if score:
            scored.append((score, i))
    chosen: set[int] = set()
    used = 0
    ranked = [i for _, i in sorted(scored, key=lambda x: (-x[0], x[1]))]
    for i in ranked:  # best sections first
        if used + len(sections[i]) <= limit or not chosen:
            chosen.add(i)
            used += min(len(sections[i]), limit)
    for i in ranked:  # then a short lead-in (heading / plan name) before each, if it still fits
        j = i - 1
        if j >= 0 and j not in chosen and len(sections[j]) < 300 and used + len(sections[j]) <= limit:
            chosen.add(j)
            used += len(sections[j])
    if not chosen:
        return text[:limit], 0, len(sections)
    out, prev = [], -2
    for i in sorted(chosen):
        if i != prev + 1:
            out.append("[…]")
        out.append(sections[i])
        prev = i
    return "\n\n".join(out), len(chosen), len(sections)


_DOI = re.compile(r"\b(10\.\d{4,9}/[^\s?#]+)", re.I)


def _doi_in(url: str) -> str:
    m = _DOI.search(url)
    return m.group(1).rstrip("/.") if m else ""


async def _doi_fallback(doi: str) -> str:
    """Abstract + open-access copy of a paywalled/protected article via OpenAlex."""
    try:
        w = await net.get_json(f"https://api.openalex.org/works/https://doi.org/{doi}",
                               params={"mailto": net.CONTACT} if net.CONTACT else None)
    except Exception:
        return ""
    oa = (w.get("open_access") or {}).get("oa_url") or ""  # type: ignore[union-attr]
    src = ((w.get("primary_location") or {}).get("source") or {}).get("display_name", "")  # type: ignore[union-attr]
    text = (f"Title: {w.get('display_name', '')}\nJournal: {src} ({w.get('publication_year', '')})\n"  # type: ignore[union-attr]
            f"DOI: https://doi.org/{doi}\nCited by: {w.get('cited_by_count', 0)}\n")  # type: ignore[union-attr]
    if oa:
        text += f"Open-access copy: {oa} (open it with fetch_page)\n"
    abstract = _openalex_abstract(w.get("abstract_inverted_index"))  # type: ignore[union-attr]
    return text + "\nAbstract:\n" + (abstract or "(not available)")


@tool
async def page_links(url: str, contains: str = "", same_site: bool = False, limit: int = 60) -> str:
    """List links on a page (e.g. a listing of grants, news or articles). `contains` filters by text
    in the URL or anchor (case-insensitive, several words separated by |). Use fetch_page to open them."""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    f, attempts = await net.fetch_resilient(url)
    if f is None:
        return f"Could not read {url}. Attempts: {'; '.join(attempts)}."
    host = urlparse(f.url).netloc
    words = [w.strip().lower() for w in contains.split("|") if w.strip()]
    rows = []
    for link, label in links_from(f):
        if same_site and urlparse(link).netloc != host:
            continue
        if words and not any(w in (link + " " + label).lower() for w in words):
            continue
        rows.append(f"- {label or '(no text)'} — {link}")
        if len(rows) >= max(1, min(limit, 200)):
            break
    return f"Links on {f.url} (via {f.via}):\n" + ("\n".join(rows) if rows else "(none matched)")


@tool
async def rss_read(url: str, limit: int = 20) -> str:
    """Read an RSS/Atom feed: newest entries with dates, links and short summaries."""
    f, attempts = await net.fetch_resilient(url)
    if f is None:
        return f"Could not read feed {url}. Attempts: {'; '.join(attempts)}."
    feed = feedparser.parse(f.body)
    if not feed.entries:
        return f"{url} is not a feed or has no entries."
    lines = [f"Feed: {feed.feed.get('title', url)}"]
    for e in feed.entries[:max(1, min(limit, 50))]:
        when = e.get("published") or e.get("updated") or ""
        lines.append(f"- {clean(e.get('title', ''))} ({when})\n  {e.get('link', '')}\n"
                     f"  {_cut(clean(e.get('summary', '')), 280)}")
    return "\n".join(lines)


@tool
async def youtube_transcript(video: str, languages: str = "uk,en,de,ru") -> str:
    """Transcript of a YouTube video (URL or id) — for talks, lectures, product demos."""
    vid = video
    if "youtu" in video:
        u = urlparse(video)
        vid = parse_qs(u.query).get("v", [u.path.rsplit("/", 1)[-1]])[0]

    def _get() -> tuple[str, str]:
        from youtube_transcript_api import YouTubeTranscriptApi
        api = YouTubeTranscriptApi()
        langs = [x.strip() for x in languages.split(",") if x.strip()]
        try:
            fetched = api.fetch(vid, languages=langs)
        except Exception:
            tl = api.list(vid)
            fetched = next(iter(tl)).fetch()
        return fetched.language_code, " ".join(s.text for s in fetched.snippets)

    try:
        lang, text = await asyncio.to_thread(_get)
    except Exception as exc:
        return f"No transcript available for {vid} ({type(exc).__name__})."
    title = ""
    try:
        meta = await net.get_json("https://www.youtube.com/oembed",
                                  params={"url": f"https://www.youtube.com/watch?v={vid}", "format": "json"})
        title = meta.get("title", "")  # type: ignore[union-attr]
    except Exception:
        pass
    return f"YouTube {vid} {title!r} transcript ({lang}):\n{_cut(text, 30000)}"


@tool
async def github_search(query: str, kind: str = "repositories", limit: int = 10) -> str:
    """Search GitHub. kind: "repositories" (sorted by stars) or "issues"."""
    kind = "issues" if kind == "issues" else "repositories"
    params = {"q": query, "per_page": max(1, min(limit, 30))}
    if kind == "repositories":
        params["sort"] = "stars"
    data = await net.get_json(f"https://api.github.com/search/{kind}", params=params,
                              headers={"Accept": "application/vnd.github+json"})
    items = data.get("items") or []  # type: ignore[union-attr]
    if not items:
        return "No GitHub results."
    if kind == "repositories":
        return "\n".join(f"- {r['full_name']} ★{r.get('stargazers_count', 0)} (updated {r.get('pushed_at', '')[:10]})"
                         f"\n  {r['html_url']}\n  {_cut(r.get('description') or '', 200)}" for r in items)
    return "\n".join(f"- {r['title']} [{r.get('state')}] {r['html_url']} ({r.get('created_at', '')[:10]})" for r in items)


@tool
async def hackernews_search(query: str, limit: int = 15, recent: bool = True) -> str:
    """Search Hacker News stories (good for IT products, launches, developer discussion)."""
    endpoint = "search_by_date" if recent else "search"
    data = await net.get_json(f"https://hn.algolia.com/api/v1/{endpoint}",
                              params={"query": query, "tags": "story", "hitsPerPage": max(1, min(limit, 50))})
    hits = data.get("hits") or []  # type: ignore[union-attr]
    return "\n".join(f"- {h.get('title')} ({h.get('points', 0)} points, {h.get('created_at', '')[:10]})\n"
                     f"  {h.get('url') or ''}\n  https://news.ycombinator.com/item?id={h.get('objectID')}"
                     for h in hits) or "No Hacker News results."


@tool
async def reddit_search(query: str, subreddit: str = "", limit: int = 10, sort: str = "relevance") -> str:
    """Search Reddit posts, optionally inside one subreddit. sort: relevance | new | top."""
    base = f"https://www.reddit.com/r/{subreddit}/search.json" if subreddit else "https://www.reddit.com/search.json"
    params = {"q": query, "limit": max(1, min(limit, 25)), "sort": sort, "restrict_sr": "1" if subreddit else "0"}
    try:
        data = await net.get_json(base, params=params)
    except Exception as exc:
        # Reddit refuses most anonymous API clients; search engines still index it.
        site = f"site:reddit.com/r/{subreddit}" if subreddit else "site:reddit.com"
        found = await web_search(f"{site} {query}", max_results=limit)
        return f"(Reddit API refused: {exc}; results via web search)\n{found}"
    posts = [c["data"] for c in (data.get("data") or {}).get("children", [])]  # type: ignore[union-attr]
    return "\n".join(f"- r/{p.get('subreddit')}: {p.get('title')} ({p.get('score', 0)}↑, "
                     f"{datetime.fromtimestamp(p.get('created_utc', 0)).date()})\n  https://www.reddit.com{p.get('permalink', '')}"
                     for p in posts) or "No Reddit results."


# ═══ Science & medicine ══════════════════════════════════════════════════════

def _ncbi_params(**kw) -> dict:
    p = {"tool": "finder", **kw}
    if net.CONTACT:
        p["email"] = net.CONTACT
    return p


@tool
async def pubmed_search(query: str, max_results: int = 10, sort: str = "relevance", from_year: int = 0,
                        to_year: int = 0) -> str:
    """Search PubMed (biomedical literature). Supports PubMed syntax, e.g. '"large language model"[tiab]
    AND radiology'. sort: relevance | date. Returns PMIDs with title, journal, date, DOI; use
    pubmed_fetch for abstracts."""
    params = _ncbi_params(db="pubmed", term=query, retmode="json", retmax=max(1, min(max_results, 50)),
                          sort="pub_date" if sort == "date" else "relevance")
    if from_year or to_year:
        params.update(datetype="pdat", mindate=str(from_year or 1900), maxdate=str(to_year or date.today().year))
    ids = (await net.get_json(f"{NCBI}/esearch.fcgi", params=params))["esearchresult"]  # type: ignore[index]
    pmids = ids.get("idlist", [])
    if not pmids:
        return f"PubMed: no results for {query!r}."
    summ = (await net.get_json(f"{NCBI}/esummary.fcgi",
                               params=_ncbi_params(db="pubmed", id=",".join(pmids), retmode="json")))["result"]  # type: ignore[index]
    lines = [f"PubMed: {ids.get('count')} total, showing {len(pmids)} for {query!r}"]
    for pid in pmids:
        r = summ.get(pid) or {}
        doi = next((a["value"] for a in r.get("articleids", []) if a.get("idtype") == "doi"), "")
        authors = ", ".join(a["name"] for a in r.get("authors", [])[:3]) + (" et al." if len(r.get("authors", [])) > 3 else "")
        types = ", ".join(r.get("pubtype", [])[:2])
        lines.append(f"- PMID {pid}: {r.get('title', '')}\n  {authors} — {r.get('fulljournalname', '')}, "
                     f"{r.get('pubdate', '')}{f' [{types}]' if types else ''}\n  https://pubmed.ncbi.nlm.nih.gov/{pid}/"
                     + (f"  doi:{doi}" if doi else ""))
    return "\n".join(lines)


@tool
async def pubmed_fetch(pmids: str) -> str:
    """Abstracts and metadata (publication type, MeSH terms, DOI) for comma-separated PMIDs (max 20)."""
    ids = [p.strip() for p in re.split(r"[,\s]+", pmids) if p.strip().isdigit()][:20]
    if not ids:
        return "Give one or more numeric PMIDs."
    key = net.cache_key("efetch", ids)
    if (hit := net.cache_get(key, 7 * 86400)) is not None:
        return hit  # type: ignore[return-value]
    f = await net.get_direct(f"{NCBI}/efetch.fcgi", params=_ncbi_params(db="pubmed", id=",".join(ids),
                                                                        rettype="abstract", retmode="xml"),
                             headers=net.API_HEADERS)
    root = ET.fromstring(f.body)
    out = []
    for art in root.iter("PubmedArticle"):
        pmid = art.findtext(".//PMID", "")
        title = "".join(art.find(".//ArticleTitle").itertext()) if art.find(".//ArticleTitle") is not None else ""
        abstract = "\n".join(
            (f"{a.get('Label')}: " if a.get("Label") else "") + "".join(a.itertext())
            for a in art.iterfind(".//Abstract/AbstractText"))
        journal = art.findtext(".//Journal/Title", "")
        year = art.findtext(".//PubDate/Year", "") or art.findtext(".//PubDate/MedlineDate", "")
        ptypes = [p.text or "" for p in art.iterfind(".//PublicationType")]
        mesh = [m.findtext("DescriptorName", "") for m in art.iterfind(".//MeshHeading")][:12]
        doi = next((i.text for i in art.iterfind(".//ArticleId") if i.get("IdType") == "doi"), "")
        out.append(f"## PMID {pmid}: {title}\n{journal} ({year}); types: {', '.join(ptypes)}"
                   + (f"; doi:{doi}" if doi else "") + (f"\nMeSH: {', '.join(mesh)}" if mesh else "")
                   + f"\n\n{abstract or '(no abstract)'}")
    result = "\n\n".join(out) or "No records."
    net.cache_put(key, result)
    return result


@tool
async def europepmc_search(query: str, limit: int = 10, open_access_only: bool = False, from_year: int = 0) -> str:
    """Search Europe PMC (PubMed + preprints + full-text open access). Returns abstracts excerpts."""
    q = query + (" AND OPEN_ACCESS:y" if open_access_only else "") + (f" AND PUB_YEAR:[{from_year} TO 3000]" if from_year else "")
    data = await net.get_json("https://www.ebi.ac.uk/europepmc/webservices/rest/search",
                              params={"query": q, "format": "json", "pageSize": max(1, min(limit, 25)),
                                      "resultType": "core", "sort": "P_PDATE_D desc" if from_year else ""})
    rows = (data.get("resultList") or {}).get("result", [])  # type: ignore[union-attr]
    if not rows:
        return f"Europe PMC: no results for {query!r}."
    lines = [f"Europe PMC: {data.get('hitCount')} hits for {query!r}"]  # type: ignore[union-attr]
    for r in rows:
        src_id = r.get("pmid") or r.get("id")
        link = f"https://europepmc.org/article/{r.get('source')}/{src_id}"
        journal = ((r.get("journalInfo") or {}).get("journal") or {}).get("title", "") or r.get("bookOrReportDetails", {}).get("publisher", "")
        lines.append(f"- {r.get('title', '')} ({r.get('pubYear', '')}) — {journal}"
                     f"{' [open access]' if r.get('isOpenAccess') == 'Y' else ''}\n  {link}"
                     + (f"  doi:{r['doi']}" if r.get("doi") else "")
                     + f"\n  {_cut(clean(r.get('abstractText', '')), 500)}")
    return "\n".join(lines)


@tool
async def clinicaltrials_search(query: str, status: str = "", limit: int = 10) -> str:
    """Search ClinicalTrials.gov. status (optional): RECRUITING, NOT_YET_RECRUITING, ACTIVE_NOT_RECRUITING,
    COMPLETED. Returns NCT id, title, phase, conditions, sponsor, dates."""
    params = {"query.term": query, "pageSize": max(1, min(limit, 30)), "format": "json"}
    if status:
        params["filter.overallStatus"] = status.upper()
    data = await net.get_json("https://clinicaltrials.gov/api/v2/studies", params=params)
    studies = data.get("studies") or []  # type: ignore[union-attr]
    if not studies:
        return f"ClinicalTrials.gov: no studies for {query!r}."
    lines = []
    for s in studies:
        p = s.get("protocolSection", {})
        ident, st = p.get("identificationModule", {}), p.get("statusModule", {})
        phases = ", ".join(p.get("designModule", {}).get("phases", []) or [])
        conds = ", ".join(p.get("conditionsModule", {}).get("conditions", [])[:4])
        sponsor = p.get("sponsorCollaboratorsModule", {}).get("leadSponsor", {}).get("name", "")
        nct = ident.get("nctId", "")
        lines.append(f"- {nct}: {ident.get('briefTitle', '')}\n  status {st.get('overallStatus', '')}"
                     f"{f', {phases}' if phases else ''}; start {st.get('startDateStruct', {}).get('date', '')}; "
                     f"sponsor {sponsor}\n  conditions: {conds}\n  https://clinicaltrials.gov/study/{nct}\n"
                     f"  {_cut(p.get('descriptionModule', {}).get('briefSummary', ''), 300)}")
    return "\n".join(lines)


def _openalex_abstract(inv: dict | None) -> str:
    if not inv:
        return ""
    words = sorted((pos, w) for w, positions in inv.items() for pos in positions)
    return " ".join(w for _, w in words)


@tool
async def openalex_search(query: str, limit: int = 10, from_year: int = 0, sort: str = "relevance") -> str:
    """Search OpenAlex (all scholarly fields incl. computer science). sort: relevance | cited | date."""
    filters = ["type:article|preprint|review"]
    if from_year:
        filters.append(f"from_publication_date:{from_year}-01-01")
    params = {"search": query, "per-page": max(1, min(limit, 25)), "filter": ",".join(filters)}
    if sort == "cited":
        params["sort"] = "cited_by_count:desc"
    elif sort == "date":
        params["sort"] = "publication_date:desc"
    if net.CONTACT:
        params["mailto"] = net.CONTACT
    data = await net.get_json("https://api.openalex.org/works", params=params)
    rows = data.get("results") or []  # type: ignore[union-attr]
    if not rows:
        return f"OpenAlex: no works for {query!r}."
    lines = [f"OpenAlex: {data.get('meta', {}).get('count')} works for {query!r}"]  # type: ignore[union-attr]
    for w in rows:
        src = ((w.get("primary_location") or {}).get("source") or {}).get("display_name", "")
        oa = (w.get("open_access") or {}).get("oa_url") or ""
        lines.append(f"- {w.get('display_name', '')} ({w.get('publication_year', '')}) — {src}; "
                     f"cited {w.get('cited_by_count', 0)}\n  {w.get('doi') or w.get('id')}"
                     + (f"\n  open access: {oa}" if oa else "")
                     + f"\n  {_cut(_openalex_abstract(w.get('abstract_inverted_index')), 400)}")
    return "\n".join(lines)


@tool
async def arxiv_search(query: str, limit: int = 10, newest_first: bool = True) -> str:
    """Search arXiv preprints (AI/ML, CS, quantitative biology)."""
    params = {"search_query": f"all:{query}", "max_results": max(1, min(limit, 30)),
              "sortBy": "submittedDate" if newest_first else "relevance", "sortOrder": "descending"}
    f = await net.get_direct("https://export.arxiv.org/api/query", params=params, headers=net.API_HEADERS)
    if f.status != 200:
        f = await net.get_impersonated("https://export.arxiv.org/api/query", params=params)
    if f.status != 200:
        return f"arXiv is rate-limiting right now (HTTP {f.status}); use openalex_search for preprints instead."
    feed = feedparser.parse(f.body)
    if not feed.entries:
        return f"arXiv: no results for {query!r}."
    return "\n".join(
        f"- {clean(e.title)} ({e.get('published', '')[:10]})\n  {', '.join(a.name for a in e.get('authors', [])[:3])}\n"
        f"  {e.link}\n  {_cut(clean(e.get('summary', '')), 350)}" for e in feed.entries)


# ═══ Grants ══════════════════════════════════════════════════════════════════

_EU_STATUS = {"forthcoming": ["31094501"], "open": ["31094502"], "all": ["31094501", "31094502"]}


@tool
async def eu_funding_search(query: str, status: str = "all", limit: int = 15) -> str:
    """Search the EU Funding & Tenders portal (Horizon Europe, Digital Europe, Erasmus+, EU4Health ...)
    for open or forthcoming calls. status: open | forthcoming | all. Expired deadlines are dropped."""
    q = {"bool": {"must": [{"terms": {"type": ["1", "2", "8"]}},
                           {"terms": {"status": _EU_STATUS.get(status, _EU_STATUS["all"])}}]}}
    import json as _json
    files = {"query": ("blob", _json.dumps(q), "application/json"),
             "languages": ("blob", '["en"]', "application/json"),
             "sort": ("blob", '{"field":"sortStatus","order":"ASC"}', "application/json")}
    data = await net.post_json("https://api.tech.ec.europa.eu/search-api/prod/rest/search",
                               params={"apiKey": "SEDIA", "text": query, "pageSize": 50, "pageNumber": 1},
                               files=files, ttl=3 * 3600)
    today = date.today().isoformat()
    rows = []
    for res in data.get("results") or []:  # type: ignore[union-attr]
        md = res.get("metadata") or {}
        first = lambda k: (md.get(k) or [""])[0]  # noqa: E731
        deadlines = sorted(d[:10] for d in (md.get("deadlineDate") or []) if d)
        upcoming = [d for d in deadlines if d >= today]
        if deadlines and not upcoming:
            continue
        ident = first("identifier") or first("callIdentifier")
        title = first("title") or res.get("title") or res.get("summary") or ident
        url = (f"https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/opportunities/topic-details/{ident}"
               if ident else res.get("url", ""))
        rows.append((upcoming[0] if upcoming else "9999", f"- {clean(title)} [{ident}]\n  deadline: "
                     f"{', '.join(upcoming) or 'n/a'}; opens {first('startDate')[:10]}; status "
                     f"{'forthcoming' if first('status') == '31094501' else 'open'}\n  {url}"))
    rows.sort()
    if not rows:
        return f"EU portal: no open/forthcoming calls for {query!r}."
    return (f"EU Funding & Tenders — {len(rows)} upcoming for {query!r} (sorted by deadline):\n"
            + "\n".join(r for _, r in rows[:max(1, min(limit, 40))]))


@tool
async def grants_gov_search(keyword: str, status: str = "posted|forecasted", limit: int = 15) -> str:
    """Search Grants.gov (US federal opportunities; many accept international applicants — check
    eligibility). status: posted | forecasted | posted|forecasted."""
    data = await net.post_json("https://api.grants.gov/v1/api/search2",
                               json_body={"keyword": keyword, "oppStatuses": status, "rows": max(1, min(limit, 50))},
                               ttl=3 * 3600)
    hits = ((data or {}).get("data") or {}).get("oppHits") or []  # type: ignore[union-attr]
    if not hits:
        return f"Grants.gov: no opportunities for {keyword!r}."
    return "\n".join(f"- {h.get('title')} [{h.get('number')}] — {h.get('agency')}\n  status {h.get('oppStatus')}; "
                     f"open {h.get('openDate')}; close {h.get('closeDate') or 'n/a'}\n"
                     f"  https://www.grants.gov/search-results-detail/{h.get('id')}" for h in hits)


_UA_SOURCES = {
    "gurt": ("https://gurt.org.ua/news/grants/", re.compile(r"/news/grants/\d+")),
    "prostir": ("https://www.prostir.ua/category/grants/", re.compile(r"[?&]grants=")),
    "houseofeurope": ("https://houseofeurope.org.ua/opportunities", re.compile(r"/opportunity/\d+")),
}


@tool
async def ua_grants_feed(source: str = "all", query: str = "") -> str:
    """Latest grant announcements from Ukrainian aggregators: gurt (ГУРТ), prostir (Громадський простір),
    houseofeurope. source: all | gurt | prostir | houseofeurope. query filters titles (words separated by |)."""
    names = list(_UA_SOURCES) if source == "all" else [source]
    words = [w.strip().lower() for w in query.split("|") if w.strip()]
    out = []
    for name in names:
        if name not in _UA_SOURCES:
            continue
        url, pattern = _UA_SOURCES[name]
        f, attempts = await net.fetch_resilient(url)
        if f is None:
            out.append(f"## {name}: unavailable ({'; '.join(attempts)})")
            continue
        items = [(link, label) for link, label in links_from(f)
                 if pattern.search(link) and len(label) > 12 and label.lower() not in ("детально", "читати далі")]
        if words:
            items = [(l, t) for l, t in items if any(w in t.lower() for w in words)]
        out.append(f"## {name} ({url})\n" + ("\n".join(f"- {t} — {l}" for l, t in items[:40]) or "(nothing matched)"))
    return "\n\n".join(out) + "\n\nOpen individual announcements with fetch_page to check eligibility and deadlines."


# ═══ Deliverables: charts, documents, images ═════════════════════════════════
# Always available (not part of the per-agent search-tool selection). The agent supplies content;
# files are produced server-side inside the current chat's own folder — see artifacts.py.

def _kb(n: int) -> str:
    return f"{n / 1024:.0f} KB" if n < 1024 * 1024 else f"{n / 1024 / 1024:.1f} MB"


@mcp.tool()
async def create_dashboard(title: str, charts: list[dict], summary: str = "", kpis: list[dict] | None = None) -> str:
    """Show the user an interactive analytics dashboard (charts + headline numbers) in the chat.

    charts: 1-8 objects {"type", "title", "series", "subtitle"?, "unit"?, "x_label"?, "y_label"?, "source"?}
      type: "bar" (compare categories) | "hbar" (ranking, long labels; ONE series) | "stacked" (parts of
            totals across categories) | "line" (change over time) | "area" (volume over time) |
            "share" (parts of one whole, max 6 parts; ONE series)
      series: [{"name": "...", "points": [{"x": "label or date", "y": 12.5}, ...]}], max 8 series.
              y must be a plain number in ONE unit per chart (put the unit in "unit", e.g. "€", "%").
    kpis: up to 6 headline figures [{"label": "...", "value": "€2.99", "hint": "..."}].
    summary: 1-3 sentences on what the charts show.
    Use only numbers you found in sources or computed from them — never invented data."""
    try:
        meta = artifacts.save_dashboard(title, summary, kpis or [], charts)
    except artifacts.ArtifactError as exc:
        return f"Dashboard not created: {exc}"
    n = len(meta["data"]["charts"])
    return (f"Dashboard \"{meta['title']}\" with {n} chart(s) is now shown to the user in the chat. "
            "Do not repeat its numbers as a long list; add a short comment at most.")


@mcp.tool()
async def create_document(title: str, content_markdown: str, format: str = "pdf") -> str:
    """Create a file the user can download from the chat. format: "pdf" | "docx" | "md" | "csv".
    Write the whole document as markdown (headings, lists, tables, links) — for csv pass one markdown
    table. Images and raw HTML are not supported. Keep source links in the text."""
    try:
        meta = await artifacts.save_document(title, content_markdown, format)
    except artifacts.ArtifactError as exc:
        return f"Document not created: {exc}"
    except Exception as exc:
        return f"Document not created ({type(exc).__name__}: {str(exc)[:200]}). Try format=\"md\"."
    return (f"Document \"{meta['filename']}\" ({_kb(meta['size'])}) is attached to the chat as a download. "
            "Tell the user briefly what it contains; do not paste its full text again.")


@mcp.tool()
async def send_image(url: str, caption: str = "") -> str:
    """Show an image from the web in the chat (PNG, JPEG, GIF or WebP, up to 8 MB), e.g. a chart from a
    paper, a product screenshot or a logo. Give the direct image URL and a caption with its source."""
    try:
        meta = await artifacts.save_image(url, caption)
    except (artifacts.ArtifactError, net.PrivateAddress) as exc:
        return f"Image not sent: {exc}"
    except Exception as exc:
        return f"Image not sent ({type(exc).__name__}). Check that the URL points directly at an image file."
    return f"Image ({_kb(meta['size'])}) is now shown to the user in the chat."


def main() -> None:
    import logging
    import warnings

    logging.getLogger("httpx").setLevel(logging.WARNING)
    warnings.filterwarnings("ignore", category=RuntimeWarning, module=r"curl_cffi.*")  # Windows Proactor loop
    mcp.run()
