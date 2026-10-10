---
name: grant-analyst
description: "Finding funding calls for IT projects and judging each one against an organisation profile with a verdict: fits, next_year or not_for_us."
version: 1.0.0
author: Finder
license: MIT
metadata:
  hermes:
    tags: [grants, funding, eu, horizon, analysis]
    related_skills: [web-reach, source-citation]
---

# Grant analyst

## Collect

1. Structured portals first: `eu_funding_search` (Horizon Europe, Digital Europe, Erasmus+,
   EU4Health), `grants_gov_search`, `ua_grants_feed` (ГУРТ, Громадський простір, House of Europe).
2. Then the agent's own source list with `page_links` (filter with words like
   grant|грант|call|конкурс|stipend|fellowship) and `fetch_page` on each announcement.
3. Open every opportunity before judging it. Titles alone are not enough.

## Check for each opportunity

- Eligible applicants: countries (is Ukraine eligible? associated to Horizon Europe — yes),
  organisation types (university, NGO, SME, individual), consortium size.
- Topic fit with the organisation profile.
- Deadline (and time zone), next expected round, current date for comparison.
- Budget per project, co-financing share, duration.
- Special conditions: partner from EU required, prior grant experience, language.

## Verdict rules

- **fits** — eligible + topic matches + at least ~3 weeks until the deadline (or rolling).
- **next_year** — relevant but deadline passed / too close, or a missing prerequisite can be
  fixed (find a partner, register in the EU Funding portal, get a PIC); a new round is likely.
- **not_for_us** — not eligible (country, applicant type) or the topic does not match.

When information is missing, choose the verdict that the available facts support and say what
must be verified. Never guess amounts or deadlines.

## Output

Human-readable summary first: a table (title, funder, deadline, verdict) and a short rationale per
grant. Then the fenced `grants` JSON block described in the agent instructions, one object per
opportunity you opened.
