from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..agents_logic import VERDICTS
from ..db import GrantResult, User, get_db
from ..security import current_user

router = APIRouter(prefix="/api/grants", tags=["grants"])


class VerdictIn(BaseModel):
    verdict: str


def grant_out(g: GrantResult) -> dict:
    return {"id": g.id, "agent_id": g.agent_id, "thread_id": g.thread_id, "title": g.title, "funder": g.funder,
            "amount": g.amount, "deadline": g.deadline, "eligibility": g.eligibility, "verdict": g.verdict,
            "reasoning": g.reasoning, "url": g.url,
            "updated_at": g.updated_at.isoformat() if g.updated_at else None}


def _own(db: Session, user: User, grant_id: int) -> GrantResult:
    g = db.get(GrantResult, grant_id)
    if not g or g.user_id != user.id:
        raise HTTPException(404, "grant_not_found")
    return g


@router.get("")
def list_grants(agent_id: int | None = None, user: User = Depends(current_user),
                db: Session = Depends(get_db)) -> list[dict]:
    q = db.query(GrantResult).filter_by(user_id=user.id)
    if agent_id:
        q = q.filter_by(agent_id=agent_id)
    return [grant_out(g) for g in q.order_by(GrantResult.updated_at.desc()).all()]


@router.patch("/{grant_id}")
def set_verdict(grant_id: int, body: VerdictIn, user: User = Depends(current_user),
                db: Session = Depends(get_db)) -> dict:
    if body.verdict not in VERDICTS:
        raise HTTPException(422, "invalid_verdict")
    g = _own(db, user, grant_id)
    g.verdict = body.verdict
    db.commit()
    return grant_out(g)


@router.delete("/{grant_id}")
def delete_grant(grant_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    db.delete(_own(db, user, grant_id))
    db.commit()
    return {"ok": True}
