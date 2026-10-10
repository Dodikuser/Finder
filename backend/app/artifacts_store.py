"""Files and dashboards an agent produced for a chat.

Each chat has one folder (DATA_DIR/artifacts/t<thread id>) that only the finder-reach tools write
to. The backend registers what appears there in the database and serves it to the chat's owner.
"""

import json
import logging
import re
import shutil
from pathlib import Path

from sqlalchemy.orm import Session

from .config import DATA_DIR
from .db import Artifact

log = logging.getLogger("finder.artifacts")

KINDS = ("dashboard", "document", "image")
_ID = re.compile(r"^[0-9a-f]{24}$")
_STORED = re.compile(r"^[0-9a-f]{24}\.[a-z0-9]{1,5}$")
MAX_BYTES = 25 * 1024 * 1024


def artifact_dir(thread_id: int) -> Path:
    return DATA_DIR / "artifacts" / f"t{thread_id}"


def remove_thread_files(thread_id: int) -> None:
    shutil.rmtree(artifact_dir(thread_id), ignore_errors=True)


def ingest(db: Session, user_id: int, thread_id: int) -> list[Artifact]:
    """Register artifacts whose metadata file appeared since the last call. Returns the new rows."""
    folder = artifact_dir(thread_id)
    if not folder.is_dir():
        return []
    known = {row[0] for row in db.query(Artifact.id).filter_by(thread_id=thread_id)}
    fresh: list[Artifact] = []
    for meta_path in sorted(folder.glob("*.meta.json"), key=lambda p: p.stat().st_mtime):
        art_id = meta_path.name.split(".", 1)[0]
        if art_id in known or not _ID.match(art_id):
            continue
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            stored = str(meta.get("file", ""))
            path = folder / stored
            # The tools generate these names; anything else in the folder is not ours to serve.
            if meta.get("id") != art_id or meta.get("kind") not in KINDS or not _STORED.match(stored) \
                    or not stored.startswith(art_id) or not path.is_file() or path.stat().st_size > MAX_BYTES:
                log.warning("ignoring malformed artifact %s in thread %s", art_id, thread_id)
                continue
            row = Artifact(id=art_id, user_id=user_id, thread_id=thread_id, kind=meta["kind"],
                           title=str(meta.get("title", ""))[:200], filename=str(meta.get("filename", stored))[:120],
                           mime=str(meta.get("mime", "application/octet-stream"))[:120], size=path.stat().st_size,
                           file=stored, caption=str(meta.get("caption", ""))[:500],
                           data=meta.get("data") if isinstance(meta.get("data"), dict) else {})
        except (OSError, ValueError, KeyError) as exc:
            log.warning("unreadable artifact metadata %s: %s", meta_path, exc)
            continue
        db.add(row)
        fresh.append(row)
    if fresh:
        db.commit()
    return fresh


def artifact_out(a: Artifact) -> dict:
    out = {"id": a.id, "kind": a.kind, "title": a.title, "filename": a.filename, "mime": a.mime, "size": a.size,
           "caption": a.caption, "url": f"/api/artifacts/{a.id}"}
    if a.kind == "dashboard":
        out["data"] = a.data
    elif a.kind == "image":
        out["source_url"] = (a.data or {}).get("source_url", "")
    return out
