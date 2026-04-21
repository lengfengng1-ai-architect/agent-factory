from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import engine, Base
from app.routers import agents, groups, tasks, chat

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Agent Factory API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(agents.router, prefix="/api/agents", tags=["agents"])
app.include_router(groups.router, prefix="/api/groups", tags=["groups"])
app.include_router(tasks.router, prefix="/api/tasks", tags=["tasks"])
app.include_router(chat.router, prefix="/api/agents", tags=["chat"])


@app.get("/api/health")
def health_check():
    return {"status": "ok"}
