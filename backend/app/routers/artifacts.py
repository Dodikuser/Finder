from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..artifacts_store import artifact_dir
from ..db import Artifact, User, get_db
from ..security import current_user

router = APIRouter(prefix="/api/artifacts", tags=["artifacts"])

# Shown in the browser tab; everything else is always a download.
_INLINE = {"image/png", "image/jpeg", "image/gif", "image/webp", "application/pdf"}


@router.get("/{artifact_id}")
def get_artifact(artifact_id: str, download: bool = False, user: User = Depends(current_user),
                 db: Session = Depends(get_db)) -> FileResponse:
    a = db.get(Artifact, artifact_id)
    if not a or a.user_id != user.id:
        raise HTTPException(404, "artifact_not_found")
    folder = artifact_dir(a.thread_id).resolve()
    path = (folder / a.file).resolve()
    if folder not in path.parents or not path.is_file():
        raise HTTPException(404, "artifact_not_found")
    base_mime = a.mime.split(";")[0]
    inline = base_mime in _INLINE and not download
    disposition = f"{'inline' if inline else 'attachment'}; filename*=UTF-8''{quote(a.filename)}"
    headers = {"Content-Disposition": disposition, "X-Content-Type-Options": "nosniff",
               "Cache-Control": "private, max-age=3600"}
    if base_mime != "application/pdf":  # the browser's PDF viewer does not start inside a CSP sandbox
        # Agent-produced files never run script or load anything in the site's origin.
        headers["Content-Security-Policy"] = "default-src 'none'; img-src 'self' data:; style-src 'unsafe-inline'; sandbox"
    return FileResponse(path, media_type=a.mime, headers=headers)
