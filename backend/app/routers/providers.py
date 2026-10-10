from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..db import User
from ..hermes import auth_flows
from ..hermes.pool import pool
from ..hermes.profiles import connected_providers
from ..security import current_user

router = APIRouter(prefix="/api", tags=["providers"])


class ApiKeyIn(BaseModel):
    api_key: str = Field(min_length=8, max_length=500)


@router.get("/providers")
def list_providers(user: User = Depends(current_user)) -> dict:
    return auth_flows.catalog(user.profile_name)


@router.post("/providers/{provider}/login")
def start_login(provider: str, user: User = Depends(current_user)) -> dict:
    try:
        return auth_flows.start_device_login(user.profile_name, provider).public()
    except ValueError:
        raise HTTPException(400, "unsupported_provider")


@router.get("/providers/login/{session_id}")
def poll_login(session_id: str, user: User = Depends(current_user)) -> dict:
    sess = auth_flows.get_login(user.profile_name, session_id)
    if not sess:
        raise HTTPException(404, "login_not_found")
    return sess.public()


class LoginCodeIn(BaseModel):
    code: str = Field(min_length=4, max_length=2000)


@router.post("/providers/login/{session_id}/code")
def submit_login_code(session_id: str, body: LoginCodeIn, user: User = Depends(current_user)) -> dict:
    try:
        return auth_flows.submit_code(user.profile_name, session_id, body.code).public()
    except ValueError as exc:
        raise HTTPException(409, str(exc))


@router.delete("/providers/login/{session_id}")
def cancel_login(session_id: str, user: User = Depends(current_user)) -> dict:
    auth_flows.cancel_login(user.profile_name, session_id)
    return {"ok": True}


@router.post("/providers/{provider}/key")
def add_key(provider: str, body: ApiKeyIn, user: User = Depends(current_user)) -> dict:
    try:
        auth_flows.add_api_key(user.profile_name, provider, body.api_key.strip())
    except ValueError:
        raise HTTPException(400, "unsupported_provider")
    except RuntimeError as exc:
        raise HTTPException(400, str(exc))
    return auth_flows.catalog(user.profile_name)


@router.delete("/providers/{provider}")
def disconnect(provider: str, user: User = Depends(current_user)) -> dict:
    try:
        auth_flows.disconnect(user.profile_name, provider)
    except RuntimeError as exc:
        raise HTTPException(400, str(exc))
    return auth_flows.catalog(user.profile_name)


@router.get("/models")
def list_models(user: User = Depends(current_user)) -> dict:
    connected = connected_providers(user.profile_name)
    if not connected:
        return {"models": [], "current": "", "needs_account": True}
    try:
        state = pool.models(user.profile_name)
    except Exception as exc:  # agent failed to start: surface, do not 500 the page
        raise HTTPException(503, f"agent_unavailable: {exc}")
    models = []
    for m in state.get("availableModels") or []:
        mid = m.get("modelId", "")
        provider = mid.split(":", 1)[0] if ":" in mid else ""
        models.append({"id": mid, "name": m.get("name") or mid, "description": m.get("description", ""),
                       "provider": provider, "connected": provider in connected})
    models.sort(key=lambda m: not m["connected"])
    current = state.get("currentModelId", "")
    if not any(m["id"] == current and m["connected"] for m in models):
        current = next((m["id"] for m in models if m["connected"]), "")
    return {"models": models, "current": current, "needs_account": False}
