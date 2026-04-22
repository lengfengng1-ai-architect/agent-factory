"""File summary management API."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from app.database import get_db
from app import models

router = APIRouter()


@router.get("/summaries")
def list_summaries(
    agent_id: Optional[int] = Query(None),
    group_id: Optional[int] = Query(None),
    search: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """List file summaries with optional filtering.
    
    - agent_id: filter by agent
    - group_id: filter by group  
    - search: fuzzy search on file_name
    """
    query = db.query(models.FileSummary)
    
    if agent_id is not None:
        query = query.filter(models.FileSummary.agent_id == agent_id)
    if group_id is not None:
        query = query.filter(models.FileSummary.group_id == group_id)
    if search:
        query = query.filter(models.FileSummary.file_name.contains(search))
    
    total = query.count()
    items = query.order_by(models.FileSummary.created_at.desc()).offset(offset).limit(limit).all()
    
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [
            {
                "id": s.id,
                "content_hash": s.content_hash,
                "file_name": s.file_name,
                "file_ext": s.file_ext,
                "file_size": s.file_size,
                "char_count": s.char_count,
                "summary": s.summary,
                "summary_char_count": s.summary_char_count,
                "agent_id": s.agent_id,
                "group_id": s.group_id,
                "model_id": s.model_id,
                "created_at": s.created_at.isoformat() if s.created_at else None,
                "updated_at": s.updated_at.isoformat() if s.updated_at else None,
            }
            for s in items
        ],
    }


@router.get("/summaries/{summary_id}")
def get_summary(summary_id: int, db: Session = Depends(get_db)):
    """Get a single summary by ID."""
    s = db.query(models.FileSummary).filter(models.FileSummary.id == summary_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Summary not found")
    return {
        "id": s.id,
        "content_hash": s.content_hash,
        "file_name": s.file_name,
        "file_ext": s.file_ext,
        "file_size": s.file_size,
        "char_count": s.char_count,
        "summary": s.summary,
        "summary_char_count": s.summary_char_count,
        "agent_id": s.agent_id,
        "group_id": s.group_id,
        "model_id": s.model_id,
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "updated_at": s.updated_at.isoformat() if s.updated_at else None,
    }


@router.delete("/summaries/{summary_id}")
def delete_summary(summary_id: int, db: Session = Depends(get_db)):
    """Delete a summary by ID."""
    s = db.query(models.FileSummary).filter(models.FileSummary.id == summary_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Summary not found")
    db.delete(s)
    db.commit()
    
    # Also clear from Redis cache if exists
    from app.redis_client import r
    r.delete(f"chat_file_summary:{s.content_hash}")
    
    return {"message": "Summary deleted", "id": summary_id}
