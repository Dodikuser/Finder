"""Agent presets, the per-session instruction block, and parsing of grant verdicts."""

import hashlib
import json
import re
from functools import lru_cache

import yaml
from sqlalchemy.orm import Session

from .config import PROJECT_ROOT
from .db import Agent, GrantResult, User

PRESETS_DIR = PROJECT_ROOT / "agents" / "presets"
LANG_NAMES = {"uk": "Ukrainian", "en": "English", "de": "German"}
VERDICTS = ("fits", "next_year", "not_for_us")

ALL_TOOLS = [
    "web_search", "fetch_page", "page_links", "rss_read", "youtube_transcript", "github_search",
    "hackernews_search", "reddit_search",
    "pubmed_search", "pubmed_fetch", "europepmc_search", "clinicaltrials_search", "openalex_search",
    "arxiv_search",
    "eu_funding_search", "grants_gov_search", "ua_grants_feed",
]
ALL_SKILLS = ["web-reach", "medical-research", "grant-analyst", "source-citation", "data-visualization",
              "documents"]


@lru_cache
def presets() -> list[dict]:
    items = []
    for path in sorted(PRESETS_DIR.glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        items.append(data)
    return items


def preset(slug: str) -> dict | None:
    return next((p for p in presets() if p["slug"] == slug), None)


def apply_preset(agent: Agent, p: dict) -> None:
    agent.preset = p["slug"]
    agent.kind = p.get("kind", "research")
    agent.name = dict(p.get("name") or {})
    agent.description = dict(p.get("description") or {})
    agent.instructions = (p.get("instructions") or "").strip()
    agent.tools = list(p.get("tools") or [])
    agent.skills = list(p.get("skills") or [])
    agent.sources = list(p.get("sources") or [])
    agent.org_profile = (p.get("org_profile") or "").strip()


def seed_agents(db: Session, user: User) -> None:
    for i, p in enumerate(presets()):
        agent = Agent(owner_id=user.id, position=i)
        apply_preset(agent, p)
        db.add(agent)


def reply_language(agent: Agent, ui_language: str) -> str:
    lang = agent.answer_language if agent.answer_language in LANG_NAMES else ui_language
    return lang if lang in LANG_NAMES else "uk"


DELIVERABLES = """
You can hand the user more than text (finder-reach tools; load the skills data-visualization and
documents first): create_dashboard shows interactive charts in the chat, create_document attaches a
PDF / DOCX / MD / CSV file, send_image shows an image from the web. Use them when the user asks for
charts, analytics, a report, a file or a picture — not on every answer.
"""

GRANTS_FORMAT = """
At the end of every answer that evaluates opportunities, add one fenced block exactly like this
(a JSON array, one object per opportunity you evaluated; strings in the reply language except
the verdict values):
```grants
[{"title": "...", "funder": "...", "amount": "...", "deadline": "YYYY-MM-DD or text",
  "eligibility": "who may apply, briefly", "verdict": "fits|next_year|not_for_us",
  "reasoning": "one or two sentences", "url": "https://..."}]
```
Only include opportunities you actually opened and read. Unknown fields are empty strings.
"""


def instruction_block(agent: Agent, lang: str) -> str:
    name = agent.name.get(lang) or agent.name.get("en") or next(iter(agent.name.values()), "Agent")
    parts = [f"You are acting as the Finder agent \"{name}\"."]
    if agent.instructions:
        parts.append(agent.instructions)
    if agent.sources:
        parts.append("Priority sources (start here, then broaden):\n" + "\n".join(f"- {s}" for s in agent.sources))
    if agent.org_profile:
        parts.append("Organisation profile used for every judgement:\n" + agent.org_profile)
    if agent.skills:
        parts.append("Relevant skills you have installed: " + ", ".join(agent.skills) + ". Load them when useful.")
    parts.append(DELIVERABLES.strip())
    if agent.kind == "grants":
        parts.append(GRANTS_FORMAT.strip())
    parts.append(f"Always answer in {LANG_NAMES[lang]}. Cite sources as markdown links.")
    return "<finder-agent-config>\n" + "\n\n".join(parts) + "\n</finder-agent-config>"


def build_prompt(agent: Agent, lang: str, text: str, *, fresh: bool) -> str:
    if fresh:
        return instruction_block(agent, lang) + "\n\n" + text
    return f"{text}\n\n[Answer in {LANG_NAMES[lang]}.]"


_GRANTS_BLOCK = re.compile(r"```grants\s*(\[.*?\])\s*```", re.S)


def extract_grants(text: str) -> list[dict]:
    items: list[dict] = []
    for m in _GRANTS_BLOCK.finditer(text):
        try:
            data = json.loads(m.group(1))
        except ValueError:
            continue
        for row in data if isinstance(data, list) else []:
            if not isinstance(row, dict) or not str(row.get("title", "")).strip():
                continue
            verdict = str(row.get("verdict", "")).strip().lower().replace("-", "_").replace(" ", "_")
            if verdict not in VERDICTS:
                continue
            items.append({k: str(row.get(k, "") or "").strip() for k in
                          ("title", "funder", "amount", "deadline", "eligibility", "reasoning", "url")}
                         | {"verdict": verdict})
    return items


def strip_grants_block(text: str) -> str:
    return _GRANTS_BLOCK.sub("", text).rstrip()


def upsert_grants(db: Session, user_id: int, agent_id: int, thread_id: int, items: list[dict]) -> list[GrantResult]:
    saved = []
    for it in items:
        key = hashlib.sha256((it["url"] or it["title"]).lower().encode()).hexdigest()[:32]
        row = db.query(GrantResult).filter_by(user_id=user_id, agent_id=agent_id, key=key).one_or_none()
        if row is None:
            row = GrantResult(user_id=user_id, agent_id=agent_id, key=key, title=it["title"], verdict=it["verdict"])
            db.add(row)
        row.thread_id = thread_id
        for field in ("title", "funder", "amount", "deadline", "eligibility", "verdict", "reasoning", "url"):
            setattr(row, field, it[field][:1000] if field != "title" else it[field][:400])
        saved.append(row)
    return saved
