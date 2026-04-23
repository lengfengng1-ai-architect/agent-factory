import os
import platform
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base


def _get_data_dir() -> Path:
    # 1. Explicit env var (highest priority, used by desktop app --data-dir)
    env_dir = os.environ.get("AGENT_FACTORY_DATA_DIR")
    if env_dir:
        return Path(env_dir)

    # 2. Desktop mode: ENV=production is set by Tauri launcher
    if os.environ.get("ENV") == "production":
        system = platform.system()
        if system == "Windows":
            appdata = os.environ.get("APPDATA", os.path.expanduser("~"))
            return Path(appdata) / "Agent Factory"
        else:
            return Path.home() / ".agent-factory"

    # 3. Web dev mode: keep backward compatibility, use current directory
    return Path(".")


data_dir = _get_data_dir()
os.makedirs(data_dir, exist_ok=True)

workspace_dir = data_dir / "workspace"
os.makedirs(workspace_dir, exist_ok=True)

SQLALCHEMY_DATABASE_URL = f"sqlite:///{data_dir / 'agent_factory.db'}"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
