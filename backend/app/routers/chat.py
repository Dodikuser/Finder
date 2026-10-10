import asyncio
import json
import logging
import threading
from typing import Any, AsyncIterator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..agents_logic import build_prompt, extract_grants, reply_language, strip_grants_block, upsert_grants
from ..artifacts_store import artifact_dir, artifact_out, ingest, remove_thread_files
from ..config import get_settings
from ..db import Agent, Artifact, Message, Thread, User, get_db, session_factory, utcnow
from ..hermes.acp import AcpError
from ..hermes.pool import pool
from ..hermes.profiles import connected_providers
from ..hermes.runtime import mcp_server_spec
from ..security import current_user

router = APIRouter(prefix="/api/threads", tags=["chat"])
log = logging.getLogger("finder.chat")

_busy: set[int] = set()
_busy_lock = threading.Lock()


class ThreadIn(BaseModel):
    agent_id: int


class MessageIn(BaseModel):
    text: str = Field(min_length=1, max_length=20000)
    model_id: str = Field(default="", max_length=160)
    language: str = "uk"
    # Shown in the chat instead of `text` (buttons send a long instruction but display a short label).
    display: str = Field(default="", max_length=300)


def thread_out(t: Thread) -> dict:
    return {"id": t.id, "agent_id": t.agent_id, "title": t.title, "model_id": t.model_id,
            "updated_at": t.updated_at.isoformat() if t.updated_at else None, "busy": t.id in _busy}


def message_out(m: Message) -> dict:
    return {"id": m.id, "role": m.role, "content": m.content, "steps": m.steps, "status": m.status,
            "created_at": m.created_at.isoformat() if m.created_at else None}


def _own_thread(db: Session, user: User, thread_id: int) -> Thread:
    t = db.get(Thread, thread_id)
    if not t or t.user_id != user.id:
        raise HTTPException(404, "thread_not_found")
    return t


@router.get("")
def list_threads(agent_id: int | None = None, user: User = Depends(current_user),
                 db: Session = Depends(get_db)) -> list[dict]:
    q = db.query(Thread).filter_by(user_id=user.id)
    if agent_id:
        q = q.filter_by(agent_id=agent_id)
    return [thread_out(t) for t in q.order_by(Thread.updated_at.desc()).limit(200)]


@router.post("")
def create_thread(body: ThreadIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    agent = db.get(Agent, body.agent_id)
    if not agent or agent.owner_id != user.id:
        raise HTTPException(404, "agent_not_found")
    t = Thread(user_id=user.id, agent_id=agent.id, model_id=agent.default_model)
    db.add(t)
    db.commit()
    return thread_out(t)


@router.get("/{thread_id}")
def get_thread(thread_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    t = _own_thread(db, user, thread_id)
    by_message: dict[int | None, list[dict]] = {}
    for a in db.query(Artifact).filter_by(thread_id=t.id).order_by(Artifact.created_at, Artifact.id):
        by_message.setdefault(a.message_id, []).append(artifact_out(a))
    return {**thread_out(t),
            "messages": [{**message_out(m), "artifacts": by_message.get(m.id, [])} for m in t.messages]}


@router.delete("/{thread_id}")
def delete_thread(thread_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    t = _own_thread(db, user, thread_id)
    db.delete(t)
    db.commit()
    remove_thread_files(thread_id)
    return {"ok": True}


@router.post("/{thread_id}/cancel")
def cancel(thread_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    t = _own_thread(db, user, thread_id)
    if t.acp_session_id:
        pool.cancel(user.profile_name, t.acp_session_id)
    return {"ok": True}


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


def _text_of(content: Any) -> str:
    if isinstance(content, dict):
        return content.get("text", "") if content.get("type") == "text" else ""
    if isinstance(content, list):
        return "".join(_text_of(c) for c in content)
    return ""


def _preview(value: Any, limit: int = 240) -> str:
    if value in (None, "", {}, []):
        return ""
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return text if len(text) <= limit else text[:limit] + "…"


def _tool_output(update: dict) -> str:
    parts = []
    for c in update.get("content") or []:
        if isinstance(c, dict) and c.get("type") == "content":
            parts.append(_text_of(c.get("content")))
    return _preview("".join(parts) or update.get("rawOutput"), 400)


@router.post("/{thread_id}/messages")
async def post_message(thread_id: int, body: MessageIn, user: User = Depends(current_user),
                       db: Session = Depends(get_db)) -> StreamingResponse:
    thread = _own_thread(db, user, thread_id)
    agent = db.get(Agent, thread.agent_id)
    if agent is None:
        raise HTTPException(404, "agent_not_found")
    if not connected_providers(user.profile_name):
        raise HTTPException(412, "needs_account")
    with _busy_lock:
        if thread.id in _busy:
            raise HTTPException(409, "thread_busy")
        _busy.add(thread.id)

    shown = body.display.strip() or body.text
    db.add(Message(thread_id=thread.id, role="user", content=shown))
    if not thread.title:
        thread.title = shown.strip().splitlines()[0][:80]
    thread.updated_at = utcnow()
    db.commit()

    lang = reply_language(agent, body.language if body.language in ("uk", "en", "de") else user.language)
    profile = user.profile_name
    model_id = body.model_id or thread.model_id or agent.default_model
    mcp = [mcp_server_spec(agent.tools, lang, artifact_dir(thread.id))]
    snapshot = {"thread_id": thread.id, "session_id": thread.acp_session_id, "model_id": thread.model_id,
                "agent_id": agent.id, "kind": agent.kind}
    agent_state = {c.key: getattr(agent, c.key) for c in Agent.__table__.columns}

    async def stream() -> AsyncIterator[str]:
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()
        answer: list[str] = []
        steps: dict[str, dict] = {}
        produced: list[str] = []  # ids of artifacts created during this turn
        status = "done"

        def new_artifacts() -> list[dict]:
            with session_factory()() as s:
                rows = ingest(s, user.id, snapshot["thread_id"])
                produced.extend(r.id for r in rows)
                return [artifact_out(r) for r in rows]

        def on_update(update: dict) -> None:
            loop.call_soon_threadsafe(queue.put_nowait, update)

        def start_turn():
            handle = pool.open_session(profile, snapshot["session_id"], mcp)
            if model_id and (handle.fresh or model_id != snapshot["model_id"]):
                pool.set_model(profile, handle.session_id, model_id)
            prompt_agent = Agent(**agent_state)
            text = build_prompt(prompt_agent, lang, body.text, fresh=handle.fresh)
            return handle, pool.prompt(profile, handle.session_id, text, on_update)

        try:
            yield _sse({"type": "status", "state": "starting"})
            handle, fut = await asyncio.to_thread(start_turn)
            with session_factory()() as s:
                t = s.get(Thread, snapshot["thread_id"])
                t.acp_session_id, t.model_id = handle.session_id, model_id or t.model_id
                s.commit()
            yield _sse({"type": "status", "state": "running", "model_id": model_id})
            done = asyncio.ensure_future(asyncio.wrap_future(fut))
            timeout = get_settings().prompt_timeout_seconds
            started = loop.time()
            while True:
                getter = asyncio.ensure_future(queue.get())
                finished, _ = await asyncio.wait({getter, done}, timeout=15,
                                                 return_when=asyncio.FIRST_COMPLETED)
                if getter in finished:
                    for ev in _translate(getter.result(), answer, steps):
                        yield _sse(ev)
                        if ev["type"] == "step" and ev["step"]["status"] in ("completed", "failed"):
                            # A tool just finished: show what it produced (dashboard, file, image) right away.
                            for art in await asyncio.to_thread(new_artifacts):
                                yield _sse({"type": "artifact", "artifact": art})
                else:
                    getter.cancel()
                if done in finished and queue.empty():
                    break
                if not finished:
                    yield ": keep-alive\n\n"
                    if loop.time() - started > timeout:
                        pool.cancel(profile, handle.session_id)
                        raise TimeoutError("agent took too long")
            result = done.result() or {}
            stop = result.get("stopReason", "end_turn")
            if stop == "cancelled":
                status = "cancelled"
            yield _sse({"type": "done", "stop_reason": stop})
        except (AcpError, RuntimeError, TimeoutError) as exc:
            status = "error"
            log.warning("turn failed for thread %s: %s", snapshot["thread_id"], exc)
            yield _sse({"type": "error", "message": str(exc)})
        except asyncio.CancelledError:  # client went away: let the agent finish in the background
            status = "cancelled"
            raise
        finally:
            full = "".join(answer)
            grants = extract_grants(full) if snapshot["kind"] == "grants" else []
            with session_factory()() as s:
                ingest(s, user.id, snapshot["thread_id"])
                message = Message(thread_id=snapshot["thread_id"], role="assistant",
                                  content=strip_grants_block(full) if grants else full,
                                  steps=list(steps.values()), status=status)
                s.add(message)
                s.flush()
                # Everything the tools left in this chat's folder during the turn belongs to this answer.
                s.query(Artifact).filter(Artifact.thread_id == snapshot["thread_id"],
                                         Artifact.message_id.is_(None)).update({"message_id": message.id})
                saved = upsert_grants(s, user.id, snapshot["agent_id"], snapshot["thread_id"], grants)
                s.commit()
                saved_out = [{"id": g.id, "title": g.title, "verdict": g.verdict} for g in saved]
            with _busy_lock:
                _busy.discard(snapshot["thread_id"])
        if grants:
            yield _sse({"type": "grants", "items": saved_out})

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


def _translate(update: dict, answer: list[str], steps: dict[str, dict]) -> list[dict]:
    kind = update.get("sessionUpdate")
    if kind == "agent_message_chunk":
        text = _text_of(update.get("content"))
        if text:
            answer.append(text)
            return [{"type": "text", "delta": text}]
    elif kind == "agent_thought_chunk":
        text = _text_of(update.get("content"))
        return [{"type": "thought", "delta": text}] if text else []
    elif kind in ("tool_call", "tool_call_update"):
        sid = update.get("toolCallId", "")
        step = steps.setdefault(sid, {"id": sid, "title": "", "kind": "", "status": "pending", "input": "",
                                      "output": ""})
        if update.get("title"):
            step["title"] = update["title"]
        if update.get("kind"):
            step["kind"] = update["kind"]
        if update.get("status"):
            step["status"] = update["status"]
        if update.get("rawInput") is not None:
            step["input"] = _preview(update.get("rawInput"))
        out = _tool_output(update)
        if out:
            step["output"] = out
        return [{"type": "step", "step": dict(step)}]
    elif kind == "plan":
        return [{"type": "plan", "entries": update.get("entries") or []}]
    elif kind == "finder_permission_denied":
        tc = update.get("toolCall") or {}
        return [{"type": "notice", "message": f"blocked: {tc.get('title', 'action')}"}]
    return []
