import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from app.database import engine, Base, get_db
from app.routers import agents, groups, tasks, chat, models, providers, group_chat, files
from app.task_engine import start_scheduler

Base.metadata.create_all(bind=engine)

# SQLite migration: add config column to groups table if missing
with engine.connect() as conn:
    try:
        conn.execute(text("SELECT config FROM groups LIMIT 1"))
    except Exception:
        conn.execute(text("ALTER TABLE groups ADD COLUMN config TEXT DEFAULT '{}'"))
        conn.commit()

# Ensure workspace directory exists
workspace_dir = os.path.join(os.path.dirname(__file__), "workspace")
os.makedirs(workspace_dir, exist_ok=True)

# SQLite migration for tasks table: add result, auto_execute, progress columns
with engine.connect() as conn:
    for col in ["result", "auto_execute", "progress"]:
        try:
            conn.execute(text(f"SELECT {col} FROM tasks LIMIT 1"))
        except Exception:
            if col == "result":
                conn.execute(text("ALTER TABLE tasks ADD COLUMN result TEXT DEFAULT ''"))
            elif col == "auto_execute":
                conn.execute(text("ALTER TABLE tasks ADD COLUMN auto_execute BOOLEAN DEFAULT 0"))
            elif col == "progress":
                conn.execute(text("ALTER TABLE tasks ADD COLUMN progress INTEGER DEFAULT 0"))
            conn.commit()

app = FastAPI(title="Agent Factory API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register files router BEFORE agents/groups to avoid path shadowing
# Files uses /api/agents/{id}/files and /api/groups/{id}/files
app.include_router(files.router, prefix="/api", tags=["files"])
app.include_router(agents.router, prefix="/api/agents", tags=["agents"])
app.include_router(groups.router, prefix="/api/groups", tags=["groups"])
app.include_router(tasks.router, prefix="/api/tasks", tags=["tasks"])
app.include_router(chat.router, prefix="/api/agents", tags=["chat"])
app.include_router(models.router, prefix="/api", tags=["models"])
app.include_router(providers.router, prefix="/api/providers", tags=["providers"])
app.include_router(group_chat.router, prefix="/api/groups", tags=["group_chat"])


@app.get("/api/health")
def health_check():
    return {"status": "ok"}


@app.on_event("startup")
def on_startup():
    db = next(get_db())
    try:
        providers.init_builtin_providers(db)
    finally:
        db.close()
    start_scheduler()
