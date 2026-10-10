from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..agents_logic import ALL_SKILLS, ALL_TOOLS, apply_preset, preset, presets
from ..db import Agent, User, get_db
from ..security import current_user

router = APIRouter(prefix="/api/agents", tags=["agents"])


class AgentIn(BaseModel):
    name: dict[str, str] | None = None
    description: dict[str, str] | None = None
    instructions: str | None = Field(default=None, max_length=20000)
    tools: list[str] | None = None
    skills: list[str] | None = None
    sources: list[str] | None = None
    org_profile: str | None = Field(default=None, max_length=10000)
    default_model: str | None = Field(default=None, max_length=160)
    answer_language: str | None = None
    kind: str | None = None


class AgentCreate(AgentIn):
    preset: str | None = None
    copy_of: int | None = None


def agent_out(a: Agent) -> dict:
    return {"id": a.id, "preset": a.preset, "kind": a.kind, "name": a.name, "description": a.description,
            "instructions": a.instructions, "tools": a.tools, "skills": a.skills, "sources": a.sources,
            "org_profile": a.org_profile, "default_model": a.default_model,
            "answer_language": a.answer_language, "position": a.position,
            "updated_at": a.updated_at.isoformat() if a.updated_at else None}


def _own(db: Session, user: User, agent_id: int) -> Agent:
    agent = db.get(Agent, agent_id)
    if not agent or agent.owner_id != user.id:
        raise HTTPException(404, "agent_not_found")
    return agent


def _apply(agent: Agent, body: AgentIn) -> None:
    if body.name is not None:
        agent.name = {k: v.strip()[:120] for k, v in body.name.items() if k in ("uk", "en", "de")}
    if body.description is not None:
        agent.description = {k: v.strip()[:300] for k, v in body.description.items() if k in ("uk", "en", "de")}
    if body.instructions is not None:
        agent.instructions = body.instructions.strip()
    if body.tools is not None:
        agent.tools = [t for t in body.tools if t in ALL_TOOLS]
    if body.skills is not None:
        agent.skills = [s for s in body.skills if s in ALL_SKILLS]
    if body.sources is not None:
        agent.sources = [s.strip() for s in body.sources if s.strip()][:50]
    if body.org_profile is not None:
        agent.org_profile = body.org_profile.strip()
    if body.default_model is not None:
        agent.default_model = body.default_model
    if body.answer_language in ("ui", "uk", "en", "de"):
        agent.answer_language = body.answer_language
    if body.kind in ("research", "grants"):
        agent.kind = body.kind


@router.get("")
def list_agents(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[dict]:
    rows = db.query(Agent).filter_by(owner_id=user.id).order_by(Agent.position, Agent.id).all()
    return [agent_out(a) for a in rows]


@router.get("/catalog")
def catalog(user: User = Depends(current_user)) -> dict:
    return {"tools": ALL_TOOLS, "skills": ALL_SKILLS,
            "presets": [{"slug": p["slug"], "kind": p.get("kind"), "name": p.get("name"),
                         "description": p.get("description")} for p in presets()]}


@router.post("")
def create_agent(body: AgentCreate, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    count = db.query(Agent).filter_by(owner_id=user.id).count()
    if count >= 50:
        raise HTTPException(400, "too_many_agents")
    agent = Agent(owner_id=user.id, position=count)
    if body.copy_of:
        src = _own(db, user, body.copy_of)
        for field in ("preset", "kind", "name", "description", "instructions", "tools", "skills", "sources",
                      "org_profile", "default_model", "answer_language"):
            value = getattr(src, field)
            setattr(agent, field, dict(value) if isinstance(value, dict) else list(value)
                    if isinstance(value, list) else value)
        agent.name = {k: f"{v} (2)" for k, v in agent.name.items()}
    elif body.preset:
        p = preset(body.preset)
        if not p:
            raise HTTPException(404, "preset_not_found")
        apply_preset(agent, p)
    else:
        agent.name = {"uk": "Новий агент", "en": "New agent", "de": "Neuer Agent"}
        agent.tools = ["web_search", "fetch_page", "page_links"]
        agent.skills = ["web-reach", "source-citation"]
    _apply(agent, body)
    db.add(agent)
    db.commit()
    return agent_out(agent)


@router.patch("/{agent_id}")
def update_agent(agent_id: int, body: AgentIn, user: User = Depends(current_user),
                 db: Session = Depends(get_db)) -> dict:
    agent = _own(db, user, agent_id)
    _apply(agent, body)
    db.commit()
    return agent_out(agent)


@router.post("/{agent_id}/reset")
def reset_agent(agent_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    agent = _own(db, user, agent_id)
    p = preset(agent.preset)
    if not p:
        raise HTTPException(400, "no_preset")
    apply_preset(agent, p)
    db.commit()
    return agent_out(agent)


@router.delete("/{agent_id}")
def delete_agent(agent_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    agent = _own(db, user, agent_id)
    db.delete(agent)
    db.commit()
    return {"ok": True}
