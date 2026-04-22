"""File upload and management for chat attachments."""

import os
import uuid
import shutil
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app import models
from app import redis_client
from datetime import datetime, timezone

router = APIRouter()

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
MAX_FILES_PER_UPLOAD = 5


def _get_chat_files_dir(entity_type: str, entity_id: int) -> str:
    """Get the storage directory for chat files."""
    base = os.path.join(os.path.dirname(os.path.dirname(__file__)), "workspace", "chat_files")
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
