from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import os
from typing import Annotated

from fastapi import FastAPI, HTTPException, Path as PathParam, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

DB_PATH = Path(os.getenv("DATABASE_PATH", Path(__file__).resolve().parent.parent / "timekeeper.db"))


def connect() -> sqlite3.Connection:
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    return db


def initialize_database() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with connect() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                started_at TEXT NOT NULL,
                stopped_at TEXT
            );
            """
        )


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database()
    yield


app = FastAPI(title="Time Keeper API", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4200", "http://localhost:8080"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class TaskCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    notes: str = Field(default="", max_length=1000)


class Task(BaseModel):
    id: int
    name: str
    notes: str
    created_at: datetime
    total_seconds: int
    running: bool


class Session(BaseModel):
    id: int
    task_id: int
    started_at: datetime
    stopped_at: datetime | None
    duration_seconds: int | None


def serialize_task(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "notes": row["notes"],
        "created_at": row["created_at"],
        "total_seconds": row["total_seconds"] or 0,
        "running": bool(row["running"]),
    }


def get_task(db: sqlite3.Connection, task_id: int) -> sqlite3.Row:
    row = db.execute(
        """SELECT t.*, COALESCE(SUM(CASE
                   WHEN s.stopped_at IS NULL THEN
                       CAST(strftime('%s','now') AS INTEGER) - CAST(strftime('%s',s.started_at) AS INTEGER)
                   ELSE CAST(strftime('%s',s.stopped_at) AS INTEGER) - CAST(strftime('%s',s.started_at) AS INTEGER)
               END), 0) AS total_seconds,
               EXISTS(SELECT 1 FROM sessions r WHERE r.task_id=t.id AND r.stopped_at IS NULL) AS running
           FROM tasks t LEFT JOIN sessions s ON s.task_id=t.id WHERE t.id=? GROUP BY t.id""",
        (task_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return row


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/tasks", response_model=list[Task])
def list_tasks() -> list[dict]:
    with connect() as db:
        rows = db.execute(
            """SELECT t.*, COALESCE(SUM(CASE
                       WHEN s.stopped_at IS NULL THEN
                           CAST(strftime('%s','now') AS INTEGER) - CAST(strftime('%s',s.started_at) AS INTEGER)
                       ELSE CAST(strftime('%s',s.stopped_at) AS INTEGER) - CAST(strftime('%s',s.started_at) AS INTEGER)
                   END), 0) AS total_seconds,
                   EXISTS(SELECT 1 FROM sessions r WHERE r.task_id=t.id AND r.stopped_at IS NULL) AS running
               FROM tasks t LEFT JOIN sessions s ON s.task_id=t.id GROUP BY t.id ORDER BY t.created_at DESC"""
        ).fetchall()
        return [serialize_task(row) for row in rows]


@app.post("/api/tasks", response_model=Task, status_code=status.HTTP_201_CREATED)
def create_task(body: TaskCreate) -> dict:
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Task name cannot be blank")
    with connect() as db:
        cursor = db.execute(
            "INSERT INTO tasks(name, notes, created_at) VALUES (?, ?, ?)",
            (name, body.notes.strip(), datetime.now(timezone.utc).isoformat()),
        )
        return serialize_task(get_task(db, cursor.lastrowid))


@app.delete("/api/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(task_id: Annotated[int, PathParam(gt=0)]) -> None:
    with connect() as db:
        cursor = db.execute("DELETE FROM tasks WHERE id=?", (task_id,))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Task not found")


@app.get("/api/sessions", response_model=list[Session])
def list_sessions(task_id: int | None = None) -> list[dict]:
    query = "SELECT * FROM sessions"
    params: tuple = ()
    if task_id is not None:
        query += " WHERE task_id=?"
        params = (task_id,)
    query += " ORDER BY started_at DESC"
    now = datetime.now(timezone.utc)
    with connect() as db:
        rows = db.execute(query, params).fetchall()
        return [
            {
                "id": row["id"],
                "task_id": row["task_id"],
                "started_at": row["started_at"],
                "stopped_at": row["stopped_at"],
                "duration_seconds": (
                    int(((datetime.fromisoformat(row["stopped_at"]) if row["stopped_at"] else now)
                         - datetime.fromisoformat(row["started_at"])).total_seconds())
                    if row["stopped_at"] or row["started_at"] else None
                ),
            }
            for row in rows
        ]


@app.post("/api/tasks/{task_id}/start", response_model=Session, status_code=status.HTTP_201_CREATED)
def start_timer(task_id: Annotated[int, PathParam(gt=0)]) -> dict:
    with connect() as db:
        get_task(db, task_id)
        active = db.execute("SELECT id FROM sessions WHERE stopped_at IS NULL LIMIT 1").fetchone()
        if active:
            raise HTTPException(status_code=409, detail="A timer is already running")
        started_at = datetime.now(timezone.utc).isoformat()
        cursor = db.execute(
            "INSERT INTO sessions(task_id, started_at) VALUES (?, ?)", (task_id, started_at)
        )
        return {
            "id": cursor.lastrowid,
            "task_id": task_id,
            "started_at": started_at,
            "stopped_at": None,
            "duration_seconds": None,
        }


@app.post("/api/sessions/{session_id}/stop", response_model=Session)
def stop_timer(session_id: Annotated[int, PathParam(gt=0)]) -> dict:
    stopped_at = datetime.now(timezone.utc).isoformat()
    with connect() as db:
        row = db.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Session not found")
        if row["stopped_at"] is not None:
            raise HTTPException(status_code=409, detail="Timer is already stopped")
        db.execute("UPDATE sessions SET stopped_at=? WHERE id=?", (stopped_at, session_id))
        duration = int((datetime.fromisoformat(stopped_at) - datetime.fromisoformat(row["started_at"])).total_seconds())
        return {
            "id": row["id"],
            "task_id": row["task_id"],
            "started_at": row["started_at"],
            "stopped_at": stopped_at,
            "duration_seconds": max(0, duration),
        }
