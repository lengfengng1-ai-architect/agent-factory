"""File upload and management for chat attachments."""

import os
import uuid
import shutil
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from fastapi.responses import JSONResponse, FileResponse
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db, workspace_dir
from app import models
from app import redis_client
from datetime import datetime, timezone

router = APIRouter()

MAX_FILE_SIZE = 100 * 1024 * 1024  # 100 MB
MAX_FILES_PER_UPLOAD = 5


def _get_chat_files_dir(entity_type: str, entity_id: int) -> str:
    """Get the storage directory for chat files."""
    base = os.path.join(workspace_dir, "chat_files")
    path = os.path.join(base, f"{entity_type}_{entity_id}")
    os.makedirs(path, exist_ok=True)
    return path


def _save_uploaded_file(upload_file: UploadFile, entity_type: str, entity_id: int) -> dict:
    """Save an uploaded file and return metadata."""
    file_size = 0
    # Read content to check size
    content = upload_file.file.read()
    file_size = len(content)

    if file_size > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail=f"File '{upload_file.filename}' exceeds 10MB limit")

    file_id = str(uuid.uuid4())[:8]
    safe_name = os.path.basename(upload_file.filename or "unnamed")
    stored_name = f"{file_id}_{safe_name}"
    dest_dir = _get_chat_files_dir(entity_type, entity_id)
    dest_path = os.path.join(dest_dir, stored_name)

    with open(dest_path, "wb") as f:
        f.write(content)

    return {
        "id": file_id,
        "name": safe_name,
        "size": file_size,
        "type": upload_file.content_type or "application/octet-stream",
        "path": dest_path,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/agents/{agent_id}/files/upload")
def upload_agent_files(
    agent_id: int,
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
):
    """Upload files for an agent chat session."""
    agent = db.query(models.Agent).filter(models.Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    if len(files) > MAX_FILES_PER_UPLOAD:
        raise HTTPException(status_code=400, detail=f"Max {MAX_FILES_PER_UPLOAD} files per upload")

    results = []
    for upload_file in files:
        meta = _save_uploaded_file(upload_file, "agent", agent_id)
        redis_client.add_chat_file(agent_id, meta)
        results.append({
            "id": meta["id"],
            "name": meta["name"],
            "size": meta["size"],
            "type": meta["type"],
            "timestamp": meta["timestamp"],
        })

    return {"files": results}


@router.post("/groups/{group_id}/files/upload")
def upload_group_files(
    group_id: int,
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
):
    """Upload files for a group chat session."""
    group = db.query(models.Group).filter(models.Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    if len(files) > MAX_FILES_PER_UPLOAD:
        raise HTTPException(status_code=400, detail=f"Max {MAX_FILES_PER_UPLOAD} files per upload")

    results = []
    for upload_file in files:
        meta = _save_uploaded_file(upload_file, "group", group_id)
        redis_client.add_group_chat_file(group_id, meta)
        results.append({
            "id": meta["id"],
            "name": meta["name"],
            "size": meta["size"],
            "type": meta["type"],
            "timestamp": meta["timestamp"],
        })

    return {"files": results}


@router.get("/agents/{agent_id}/files")
def list_agent_files(agent_id: int, db: Session = Depends(get_db)):
    """List uploaded files for an agent."""
    agent = db.query(models.Agent).filter(models.Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    files = redis_client.get_chat_files(agent_id)
    return {"files": files}


@router.get("/groups/{group_id}/files")
def list_group_files(group_id: int, db: Session = Depends(get_db)):
    """List uploaded files for a group."""
    group = db.query(models.Group).filter(models.Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    files = redis_client.get_group_chat_files(group_id)
    return {"files": files}


@router.delete("/files/{file_id}")
def delete_file_global(file_id: str, db: Session = Depends(get_db)):
    """Delete a file by ID. Searches across all agent and group file lists."""
    # Search in agent files
    # This is inefficient but fine for small scale.
    # We scan all agent and group file lists.
    # For a better approach we'd need an index, but this is acceptable.

    # Try agents first
    # We need to find which agent has this file - scan is needed since we don't
    # maintain a global index. In practice, the frontend can pass entity info.
    # For now, return a hint that the frontend should use a more specific endpoint.
    raise HTTPException(
        status_code=501,
        detail="Use DELETE /api/agents/{agent_id}/files/{file_id} or DELETE /api/groups/{group_id}/files/{file_id} instead",
    )


@router.delete("/agents/{agent_id}/files/{file_id}")
def delete_agent_file(agent_id: int, file_id: str, db: Session = Depends(get_db)):
    """Delete a file from an agent's chat files."""
    agent = db.query(models.Agent).filter(models.Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    files = redis_client.get_chat_files(agent_id)
    target = None
    for f in files:
        if f.get("id") == file_id:
            target = f
            break

    if not target:
        raise HTTPException(status_code=404, detail="File not found")

    # Remove from disk
    path = target.get("path", "")
    if path and os.path.exists(path):
        os.remove(path)

    # Remove from Redis
    redis_client.remove_chat_file(agent_id, file_id)

    return {"message": "File deleted", "file_id": file_id}


@router.get("/tasks/{task_id}/artifacts")
def list_task_artifacts(task_id: int):
    """List artifact files for a workflow task."""
    import os
    task_dir = os.path.join(workspace_dir, "tasks", str(task_id))
    if not os.path.exists(task_dir):
        return {"artifacts": []}
    
    artifacts = []
    try:
        for fname in sorted(os.listdir(task_dir)):
            fpath = os.path.join(task_dir, fname)
            if os.path.isfile(fpath):
                artifacts.append({
                    "name": fname,
                    "path": os.path.abspath(fpath),
                    "size": os.path.getsize(fpath),
                })
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to list artifacts: {str(e)}")
    return {"artifacts": artifacts}


@router.get("/artifacts/read")
def read_artifact(path: str):
    """Read content of an artifact file."""
    import os
    # Security: ensure path is within workspace
    abs_path = os.path.abspath(path)
    workspace_root = os.path.abspath(workspace_dir)
    if not abs_path.startswith(workspace_root):
        raise HTTPException(status_code=403, detail="Access denied")
    if not os.path.exists(abs_path) or not os.path.isfile(abs_path):
        raise HTTPException(status_code=404, detail="File not found")
    
    try:
        with open(abs_path, "r", encoding="utf-8") as f:
            content = f.read()
        return {"content": content, "path": abs_path}
    except UnicodeDecodeError:
        return {"content": "[Binary file]", "path": abs_path}


@router.get("/agents/{agent_id}/files/{file_id}")
def serve_chat_file(agent_id: int, file_id: str, db: Session = Depends(get_db)):
    """Serve an uploaded chat file for preview/download."""
    agent = db.query(models.Agent).filter(models.Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    files = redis_client.get_chat_files(agent_id)
    target = None
    for f in files:
        if f.get("id") == file_id:
            target = f
            break

    if not target:
        raise HTTPException(status_code=404, detail="File not found")

    path = target.get("path", "")
    if not path or not os.path.exists(path):
        raise HTTPException(status_code=404, detail="File not found on disk")

    content_type = target.get("type") or "application/octet-stream"
    return FileResponse(path, media_type=content_type, filename=target.get("name"))


@router.delete("/groups/{group_id}/files/{file_id}")
def delete_group_file(group_id: int, file_id: str, db: Session = Depends(get_db)):
    """Delete a file from a group's chat files."""
    group = db.query(models.Group).filter(models.Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    files = redis_client.get_group_chat_files(group_id)
    target = None
    for f in files:
        if f.get("id") == file_id:
            target = f
            break

    if not target:
        raise HTTPException(status_code=404, detail="File not found")

    path = target.get("path", "")
    if path and os.path.exists(path):
        os.remove(path)

    redis_client.remove_group_chat_file(group_id, file_id)

    return {"message": "File deleted", "file_id": file_id}
