---
name: web-reach
description: "Reliable internet research with the finder-reach tools: which tool for which source, and what to do when a site blocks access."
version: 1.0.0
author: Finder
license: MIT
metadata:
  hermes:
    tags: [research, web, search, scraping]
    related_skills: [source-citation, medical-research, grant-analyst]
---

# Web reach

All internet access goes through the **finder-reach** MCP tools. You have no shell, no files and
no local browser — do not try to use them.

## Pick the right channel

| Need | Tool |
|---|---|
| General discovery, news | `web_search` (kind="news" + timelimit for recent items) |
| Read an article, PDF, report | `fetch_page` (paginate with `offset`) |
| One fact from a long page (price, deadline, eligibility) | `fetch_page` with `focus="price plan renews"` — returns only matching sections |
| A listing page (grants, news, catalogues) | `page_links` with `contains` filter, then `fetch_page` |
| Biomedical papers | `pubmed_search` → `pubmed_fetch` for abstracts |
| Papers incl. preprints / open access | `europepmc_search`, `openalex_search`, `arxiv_search` |
| Clinical trials | `clinicaltrials_search` |
| Feeds | `rss_read` |
| Talks, lectures, demos | `youtube_transcript` |
| Code, products, dev discussion | `github_search`, `hackernews_search`, `reddit_search` |
| Funding | `eu_funding_search`, `grants_gov_search`, `ua_grants_feed` |

Prefer structured APIs (PubMed, OpenAlex, EU portal) over scraping search results: they are
faster, never blocked and return exact dates and identifiers.

## When a site blocks you

`fetch_page` already tries: plain request → Chrome TLS impersonation → a real headless browser
(JavaScript, bot checks) → Jina Reader → Internet Archive, and for DOI links falls back to the scholarly record (abstract +
open-access copy). If it still reports "Could not read":

1. Search for the same document elsewhere: the title in quotes with `web_search`, the DOI in
   `openalex_search` / `europepmc_search`, a press release, a PDF mirror, the publisher's
   open-access copy.
2. For listing pages, try the site's RSS feed (`/feed`, `/rss`) or `page_links` on a category page.
3. Never claim you read a page you could not open. Say which sources were unreachable.

## Efficiency

- Pricing, plans and conditions are often deep in long pages: pass `focus` instead of paging
  through the whole document. If a value is still missing, the page may not contain it — look for
  a dedicated pricing/tariff page with `page_links` before saying it is unavailable.

- Search broadly once, then open only the 3–6 most promising results.
- Do not re-fetch the same URL; results are cached anyway.
- Stop when the question is answered; report gaps instead of looping.
