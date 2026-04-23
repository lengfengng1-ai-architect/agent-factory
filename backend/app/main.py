import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from app.database import engine, Base, get_db, data_dir
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

# Ensure workspace directory exists
workspace_dir = os.path.join(data_dir, "workspace")
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

if os.environ.get("ENV") == "production":
    # Desktop app: WebView and backend are same-origin, CORS not needed
    allow_origins = []
else:
    # Dev mode: allow common frontend dev server ports
    allow_origins = [
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
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


@app.get("/api/health")
def health_check():
    return {"status": "ok"}


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
