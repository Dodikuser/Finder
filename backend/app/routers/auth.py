import re
import secrets
import threading
import time
from collections import defaultdict, deque

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..agents_logic import seed_agents
from ..config import get_settings
from ..db import User, get_db
from ..hermes.profiles import ensure_profile, profile_name_for
from ..security import clear_session, current_user, hash_password, issue_session, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class RegisterIn(BaseModel):
    email: str = Field(max_length=255)
    password: str = Field(min_length=8, max_length=200)
    display_name: str = Field(default="", max_length=120)
    language: str = "uk"
    invite_code: str = Field(default="", max_length=200)


# Brute-force guard for the two unauthenticated endpoints (in memory: one server process).
_attempts: dict[str, deque] = defaultdict(deque)
_attempts_lock = threading.Lock()


def _throttle(request: Request) -> None:
    limit = get_settings().auth_attempts_per_5min
    key = request.client.host if request.client else "?"
    now = time.monotonic()
    with _attempts_lock:
        q = _attempts[key]
        while q and now - q[0] > 300:
            q.popleft()
        if len(q) >= limit:
            raise HTTPException(429, "too_many_attempts")
        q.append(now)
        if len(_attempts) > 5000:  # forget idle clients
            for k in [k for k, v in _attempts.items() if not v or now - v[-1] > 300]:
                _attempts.pop(k, None)


@router.get("/config")
def auth_config() -> dict:
    s = get_settings()
    return {"registration": s.allow_registration, "invite_required": bool(s.invite_code)}


class LoginIn(BaseModel):
    email: str
    password: str


class MeUpdate(BaseModel):
    display_name: str | None = Field(default=None, max_length=120)
    language: str | None = None


def user_out(u: User) -> dict:
    return {"id": u.id, "email": u.email, "display_name": u.display_name, "language": u.language}


@router.post("/register")
def register(body: RegisterIn, request: Request, response: Response, db: Session = Depends(get_db)) -> dict:
    _throttle(request)
    settings = get_settings()
    if not settings.allow_registration:
        raise HTTPException(403, "registration_closed")
    if settings.invite_code and not secrets.compare_digest(body.invite_code.strip().encode(),
                                                           settings.invite_code.encode()):
        raise HTTPException(403, "invalid_invite")
    email = body.email.strip().lower()
    if not _EMAIL.match(email):
        raise HTTPException(422, "invalid_email")
    if db.query(User).filter_by(email=email).first():
        raise HTTPException(409, "email_taken")
    user = User(email=email, password_hash=hash_password(body.password),
                display_name=body.display_name.strip() or email.split("@")[0],
                language=body.language if body.language in ("uk", "en", "de") else "uk")
    db.add(user)
    db.flush()
    user.profile_name = profile_name_for(user.id)
    seed_agents(db, user)
    db.commit()
    # Prepare the Hermes profile in the background so the first chat starts faster.
    if get_settings().prewarm_profiles:
        threading.Thread(target=ensure_profile, args=(user.profile_name,), daemon=True).start()
    issue_session(response, user)
    return user_out(user)


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)) -> dict:
    _throttle(request)
    user = db.query(User).filter_by(email=body.email.strip().lower()).first()
    if not user or not verify_password(user.password_hash, body.password):
        raise HTTPException(401, "invalid_credentials")
    issue_session(response, user)
    return user_out(user)


@router.post("/logout")
def logout(response: Response) -> dict:
    clear_session(response)
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(current_user)) -> dict:
    return user_out(user)


@router.patch("/me")
def update_me(body: MeUpdate, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    if body.display_name is not None:
        user.display_name = body.display_name.strip()
    if body.language in ("uk", "en", "de"):
        user.language = body.language
    db.add(user)
    db.commit()
    return user_out(user)
