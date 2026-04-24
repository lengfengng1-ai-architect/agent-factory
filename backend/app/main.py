import os
import sys
from pathlib import Path
from fastapi import FastAPI
from app.logger import get_logger, LOG_FILE

logger = get_logger(__name__)
logger.info(f"Agent Factory starting up. Log file: {LOG_FILE}")
from fastapi.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send
from starlette.responses import FileResponse
from sqlalchemy import text
from app.database import engine, Base, get_db, data_dir, workspace_dir
from app.routers import agents, groups, tasks, chat, models, providers, group_chat, files, summaries, feishu
from app.task_engine import start_scheduler

Base.metadata.create_all(bind=engine)

# SQLite migration: create file_summaries table if not exists
with engine.connect() as conn:
    try:
        conn.execute(text("SELECT 1 FROM file_summaries LIMIT 1"))
    except Exception:
        conn.execute(text("""
            CREATE TABLE file_summaries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content_hash VARCHAR UNIQUE,
                file_name VARCHAR NOT NULL,
                file_ext VARCHAR,
                file_size INTEGER,
                char_count INTEGER,
                summary TEXT NOT NULL,
                summary_char_count INTEGER,
                agent_id INTEGER,
                group_id INTEGER,
                model_id VARCHAR,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME
            )
        """))
        conn.execute(text("CREATE INDEX idx_file_summary_hash ON file_summaries(content_hash)"))
        conn.execute(text("CREATE INDEX idx_file_summary_agent ON file_summaries(agent_id)"))
        conn.execute(text("CREATE INDEX idx_file_summary_group ON file_summaries(group_id)"))
        conn.commit()

# SQLite migration: add config column to groups table if missing
with engine.connect() as conn:
    try:
        conn.execute(text("SELECT config FROM groups LIMIT 1"))
    except Exception:
        conn.execute(text("ALTER TABLE groups ADD COLUMN config TEXT DEFAULT '{}'"))
        conn.commit()

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

if os.environ.get("ENV") == "production":
    # Desktop app: WebView origin varies (tauri://localhost, http://localhost:PORT).
    # Use regex to allow any localhost port and the tauri protocol.
    allow_origins = []
    allow_origin_regex = r"^https?://localhost(:\d+)?$|^tauri://localhost$"
else:
    # Dev mode: allow common frontend dev server ports
    allow_origins = [
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ]
    allow_origin_regex = None

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_origin_regex=allow_origin_regex,
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
app.include_router(summaries.router, prefix="/api", tags=["summaries"])
app.include_router(feishu.router, prefix="/api", tags=["feishu"])


# ── Serve frontend static files (desktop mode) ──────────────────────────────
def _get_static_dir() -> str | None:
    """Auto-detect frontend/dist directory for static file serving.

    Priority:
      1. AGENT_FACTORY_STATIC_DIR env var
      2. PyInstaller onefile mode — dist/ next to the original executable
      3. Dev mode — ../../frontend/dist relative to this file
    """
    # 1. explicit env var
    env_dir = os.environ.get("AGENT_FACTORY_STATIC_DIR")
    if env_dir and os.path.isdir(env_dir) and os.path.exists(os.path.join(env_dir, "index.html")):
        return env_dir

    # 2. PyInstaller onefile mode — dist/ inside the MEIPASS temp dir
    if hasattr(sys, "_MEIPASS"):
        meipass_dist = os.path.join(sys._MEIPASS, "dist")
        if os.path.isdir(meipass_dist) and os.path.exists(os.path.join(meipass_dist, "index.html")):
            return meipass_dist

    # 3. Desktop .app bundle — Resources/dist/ next to the original binary
    exe_path = os.path.abspath(sys.argv[0] if hasattr(sys, "argv") and sys.argv else sys.executable)
    exe_dir = os.path.dirname(exe_path)
    for candidate in (
        os.path.join(exe_dir, "dist"),
        os.path.normpath(os.path.join(exe_dir, "..", "dist")),
        os.path.normpath(os.path.join(exe_dir, "..", "Resources", "dist")),
    ):
        if os.path.isdir(candidate) and os.path.exists(os.path.join(candidate, "index.html")):
            return candidate

    # 3. dev mode — relative to backend/app/main.py
    dev_dir = Path(__file__).parent.parent.parent / "frontend" / "dist"
    if dev_dir.exists() and (dev_dir / "index.html").exists():
        return str(dev_dir.resolve())

    return None


@app.get("/api/health")
def health_check():
    return {"status": "ok"}


# ── Static files middleware (SPA mode) ──────────────────────────────────────
class StaticFilesMiddleware:
    """Serve frontend static files without breaking FastAPI redirect_slashes."""

    def __init__(self, app: ASGIApp, static_dir: str):
        self.app = app
        self.static_dir = static_dir

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope["path"]

        # Let API requests pass through to FastAPI router
        if path.startswith("/api"):
            await self.app(scope, receive, send)
            return

        # Try to serve the requested file
        file_path = os.path.join(self.static_dir, path.lstrip("/"))
        if os.path.exists(file_path) and os.path.isfile(file_path):
            response = FileResponse(file_path)
            await response(scope, receive, send)
            return

        # Fallback to index.html for SPA routes
        index_path = os.path.join(self.static_dir, "index.html")
        if os.path.exists(index_path):
            response = FileResponse(index_path)
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)


static_dir = _get_static_dir()
if static_dir:
    app.add_middleware(StaticFilesMiddleware, static_dir=static_dir)


@app.on_event("startup")
def on_startup():
    db = next(get_db())
    try:
        providers.init_builtin_providers(db)
        
        from sqlalchemy import text, inspect
        
        # Auto-add missing columns for SQLite
        inspector = inspect(db.bind)
        for table_name, column_name, column_def, default_val in [
            ("tasks", "file_root_dir", "VARCHAR", "''"),
            ("groups", "file_root_dir", "VARCHAR", "''"),
            ("tasks", "workflow_plan", "JSON", "NULL"),
            ("tasks", "workflow_status", "VARCHAR", "''"),
            ("tasks", "workflow_config", "JSON", "NULL"),
            ("workflow_steps", "output_type", "VARCHAR", "''"),
        ]:
            columns = [c["name"] for c in inspector.get_columns(table_name)]
            if column_name not in columns:
                db.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_def} DEFAULT {default_val}"))
                db.commit()
        
        # Ensure workflow_steps table exists
        from app import models
        Base.metadata.create_all(bind=db.bind, tables=[models.WorkflowStep.__table__])
        
        # Start Feishu WebSocket clients for all enabled agents
        if os.environ.get("AGENT_FACTORY_NO_FEISHU") != "1":
            from app.feishu_ws import start_feishu_ws
            from app import models as app_models
            agents = db.query(app_models.Agent).all()
            for agent in agents:
                feishu_cfg = (agent.config or {}).get("feishu", {})
                if feishu_cfg.get("enabled"):
                    start_feishu_ws(agent)
    finally:
        db.close()
    start_scheduler()


@app.on_event("shutdown")
def on_shutdown():
    from app.feishu_ws import stop_all_feishu_ws
    stop_all_feishu_ws()
