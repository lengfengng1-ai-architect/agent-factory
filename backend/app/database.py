import os
import platform
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base


def _get_data_dir() -> Path:
    env_dir = os.environ.get("AGENT_FACTORY_DATA_DIR")
    if env_dir:
        return Path(env_dir)

    system = platform.system()
    if system == "Windows":
        appdata = os.environ.get("APPDATA", os.path.expanduser("~"))
        return Path(appdata) / "Agent Factory"
    else:
        return Path.home() / ".agent-factory"


data_dir = _get_data_dir()
os.makedirs(data_dir, exist_ok=True)

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
