"""SQLite documents, jobs and append-only task events; no pickle or raw PDF retention."""

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4


class Store:
    def __init__(self, data_dir: Path):
        self.path = data_dir / "paperpilot.sqlite"
        with self.connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS sources(id TEXT PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS chunks(id TEXT PRIMARY KEY, source_id TEXT NOT NULL,
                    payload TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS chunks_source ON chunks(source_id);
                CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL, payload TEXT NOT NULL);
            """)

    def connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=20)

    def add_source(self, kind: str, title: str, metadata: dict, chunks: list[dict]) -> dict:
        source_id = uuid4().hex
        source = dict(id=source_id, kind=kind, title=title, metadata=metadata, chunks=len(chunks))
        with self.connect() as db:
            db.execute("INSERT INTO sources VALUES (?,?)", (source_id, json.dumps(source, ensure_ascii=False)))
            for chunk in chunks:
                chunk["id"] = uuid4().hex
                db.execute("INSERT INTO chunks VALUES (?,?,?)",
                           (chunk["id"], source_id, json.dumps(chunk, ensure_ascii=False)))
        return source

    def source(self, source_id: str) -> dict:
        with self.connect() as db:
            row = db.execute("SELECT payload FROM sources WHERE id=?", (source_id,)).fetchone()
        if row is None:
            raise KeyError("来源不存在")
        return json.loads(row[0])

    def chunks(self, source_id: str) -> list[dict]:
        with self.connect() as db:
            rows = db.execute("SELECT payload FROM chunks WHERE source_id=? ORDER BY rowid",
                              (source_id,)).fetchall()
        return [json.loads(row[0]) for row in rows]

    def save_job(self, job: dict) -> None:
        with self.connect() as db:
            db.execute("INSERT INTO jobs VALUES (?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload",
                       (job["id"], json.dumps(job, ensure_ascii=False)))

    def job(self, job_id: str) -> dict:
        with self.connect() as db:
            row = db.execute("SELECT payload FROM jobs WHERE id=?", (job_id,)).fetchone()
        if row is None:
            raise KeyError("任务不存在")
        return json.loads(row[0])

    def jobs(self) -> list[dict]:
        with self.connect() as db:
            rows = db.execute("SELECT payload FROM jobs ORDER BY rowid DESC LIMIT 50").fetchall()
        return [json.loads(row[0]) for row in rows]

    def event(self, job_id: str, stage: str, detail: Any) -> None:
        payload = dict(time=datetime.now(UTC).isoformat(), stage=stage, detail=detail)
        with self.connect() as db:
            db.execute("INSERT INTO events(job_id,payload) VALUES (?,?)",
                       (job_id, json.dumps(payload, ensure_ascii=False)))

    def events(self, job_id: str) -> list[dict]:
        with self.connect() as db:
            rows = db.execute("SELECT payload FROM events WHERE job_id=? ORDER BY seq", (job_id,)).fetchall()
        return [json.loads(row[0]) for row in rows]
