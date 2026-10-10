---
name: data-visualization
description: "Turning research findings into an interactive chart dashboard with the create_dashboard tool: which chart fits which question, how to shape the data, what never to do."
version: 1.0.0
author: Finder
license: MIT
metadata:
  hermes:
    tags: [charts, analytics, dashboard, visualization]
    related_skills: [source-citation, documents]
---

# Data visualization

`create_dashboard` shows charts in the chat. You send **data**, the app draws it — you never write
HTML, SVG or code. Use it when the user asks for charts / analytics / a visual summary, or presses
"Show analytics in charts".

## 1. Find the numbers first

Charts need numbers that are in your sources: prices, counts, years, amounts, percentages,
deadlines-as-days-left, sample sizes. Collect them from what you already found in this chat; search
again only for gaps. **Never invent, estimate or "illustrate" with made-up values.** If the topic
has too few numbers for a chart, say so and offer a table instead.

## 2. Pick the form by the question

| The question | type |
|---|---|
| Compare a few items on one measure | `bar` |
| Rank many items / long names | `hbar` (one series, sort largest first) |
| Compare items on the same measure in 2–4 groups (now vs later, plan A vs B) | `bar` with one series per group |
| Parts adding up to totals across categories | `stacked` |
| Change over time (years, months, dates in order) | `line` |
| Volume over time | `area` |
| Parts of ONE whole, at most 6 | `share` (one series) |
| One striking figure | a `kpis` entry, not a chart |

Rules that keep charts honest:
- **One unit per chart.** Never mix € with % or with counts in one chart — make two charts. Put the
  unit in `unit` ("€", "%", "days", "patients"), not inside the numbers.
- Do not mix currencies: convert, or make one chart per currency and say so in `subtitle`.
- `x` values of all series in a chart use the same labels in the same order.
- Time goes left to right, oldest first. Use sortable labels: `2024`, `2025-03`.
- At most 8 series; merge the tail into "Other". At most 8 charts — 2 to 4 is usually right.
- A chart needs at least 2 points to say anything; one number is a KPI.

## 3. Write it for a reader

- `title` states the finding or the measure: "Renewal price is 5× the promo price", not "Chart 1".
- `subtitle`: scope and date ("EU prices excl. VAT, checked 2026-10-10").
- `source`: where the numbers come from (site names or study ids).
- `kpis`: 2–4 headline figures with a short `hint`.
- `summary`: 1–3 sentences — what the reader should take away.
- Labels in the user's language. Short category names (they sit on the axis).

## 4. Call shape

```json
{
  "title": "Web hosting prices",
  "summary": "Promo prices are similar; renewal prices differ by a factor of two.",
  "kpis": [{"label": "Cheapest start", "value": "€2.99", "hint": "SiteGround StartUp"}],
  "charts": [{
    "type": "bar", "title": "Promo vs renewal price per month", "unit": "€",
    "subtitle": "12-month prepayment, excl. VAT", "source": "siteground.com, hostinger.com",
    "series": [
      {"name": "Now", "points": [{"x": "StartUp", "y": 2.99}, {"x": "GrowBig", "y": 5.49}]},
      {"name": "Renewal", "points": [{"x": "StartUp", "y": 15.99}, {"x": "GrowBig", "y": 27.99}]}
    ]
  }]
}
```

If the tool answers "Dashboard not created: …", fix exactly what it names and call it again.
After it succeeds, add one or two sentences of commentary — do not list the numbers again.
