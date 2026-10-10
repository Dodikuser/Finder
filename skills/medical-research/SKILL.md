---
name: medical-research
description: "Searching and appraising medical and digital-health evidence: PubMed queries, study types, evidence levels, regulation sources."
version: 1.0.0
author: Finder
license: MIT
metadata:
  hermes:
    tags: [medicine, healthtech, pubmed, evidence, research]
    related_skills: [web-reach, source-citation]
---

# Medical research

## Search strategy

1. Translate the question to English terms and MeSH-like keywords, e.g.
   `("large language model"[tiab] OR LLM[tiab]) AND (radiology[tiab] OR "radiology report"[tiab])`.
2. `pubmed_search` with `sort="date"` and `from_year` for "latest" questions; relevance otherwise.
3. `pubmed_fetch` the 3–8 best PMIDs to read abstracts and publication types.
4. Add `europepmc_search` (preprints, open access) and `clinicaltrials_search` for ongoing trials.
5. For products, companies, regulation and news use `web_search` + `fetch_page`.

## Appraise every study

Report for each: design (RCT, prospective/retrospective cohort, diagnostic accuracy study,
systematic review/meta-analysis, preprint), population and size when given, main result with the
metric (AUC, sensitivity/specificity, accuracy vs clinicians), and limitations.

Evidence hierarchy (strongest first): systematic reviews/meta-analyses of RCTs → RCTs →
prospective cohorts → retrospective studies → case series → expert opinion / news.
Flag preprints as not peer-reviewed.

## Regulation & safety sources

- EU: AI Act (high-risk medical AI), MDR/IVDR, EMA, health.ec.europa.eu
- US: FDA "AI-enabled medical devices" list and SaMD guidance
- WHO guidance on AI for health; Ukraine: МОЗ України, eHealth (Helsi, eHealth system)

## Safety

You provide research summaries, not medical advice. If the user asks about a personal health
situation, give general information with sources and recommend consulting a clinician.
