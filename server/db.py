"""Хранилище на SQLite: один файл, никаких внешних сервисов."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id            TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    project       TEXT NOT NULL DEFAULT 'default',
    status        TEXT NOT NULL DEFAULT 'running',
    source        TEXT NOT NULL DEFAULT 'sdk',
    host          TEXT,
    created_at    REAL NOT NULL,
    heartbeat_at  REAL,
    finished_at   REAL,
    total_steps   INTEGER,
    main_metric   TEXT,
    config        TEXT NOT NULL DEFAULT '{}',
    env           TEXT NOT NULL DEFAULT '{}',
    tags          TEXT NOT NULL DEFAULT '[]',
    notes         TEXT NOT NULL DEFAULT '',
    error         TEXT,
    summary       TEXT,
    dirty         INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS metrics (
    run_id  TEXT NOT NULL,
    key     TEXT NOT NULL,
    step    INTEGER NOT NULL,
    value   REAL,
    ts      REAL,
    PRIMARY KEY (run_id, key, step)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS hosts (
    host     TEXT PRIMARY KEY,
    info     TEXT NOT NULL,
    seen_at  REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS sys_samples (
    host  TEXT NOT NULL,
    ts    REAL NOT NULL,
    data  TEXT NOT NULL,
    PRIMARY KEY (host, ts)
) WITHOUT ROWID;
"""

_JSON_FIELDS = ("config", "env", "tags", "summary")
_EDITABLE = ("name", "project", "tags", "notes", "main_metric", "total_steps", "config", "env")
HEARTBEAT_TIMEOUT = 90


def _row(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    d = dict(row)
    for f in _JSON_FIELDS:
        if f in d:
            d[f] = json.loads(d[f]) if d[f] else None
    return d


def clean_tags(tags) -> list:
    out = []
    for t in tags or []:
        t = str(t).strip()[:40]
        if t and t not in out:
            out.append(t)
    return out[:20]


class DB:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._c = sqlite3.connect(str(self.path), timeout=30, check_same_thread=False)
        self._c.row_factory = sqlite3.Row
        self._c.execute("PRAGMA journal_mode=WAL")
        self._c.execute("PRAGMA synchronous=NORMAL")
        self._c.executescript(SCHEMA)
        self._c.commit()

    def close(self):
        with self._lock:
            self._c.close()

    def _q(self, sql: str, args=()) -> list:
        with self._lock:
            return self._c.execute(sql, args).fetchall()

    def _x(self, sql: str, args=()) -> int:
        with self._lock, self._c:
            return self._c.execute(sql, args).rowcount

    def create_run(self, data: dict) -> dict:
        """Создаёт запуск; повторный вызов с тем же id обновляет описание (переподключение SDK)."""
        run_id = str(data.get("id") or uuid.uuid4().hex[:12])
        now = time.time()
        existing = self.get_run(run_id)
        if existing:
            fields = {k: data[k] for k in ("config", "env", "total_steps", "main_metric", "host") if data.get(k)}
            if data.get("tags"):
                fields["tags"] = clean_tags(existing["tags"] + list(data["tags"]))
            if existing["status"] != "running" and not data.get("status"):
                fields.update(status="running", finished_at=None, heartbeat_at=now, error=None)
            self.update_run(run_id, fields, internal=True)
            return self.get_run(run_id)
        status = data.get("status") or "running"
        with self._lock, self._c:
            self._c.execute(
                "INSERT INTO runs (id, name, project, status, source, host, created_at, heartbeat_at, finished_at,"
                " total_steps, main_metric, config, env, tags, notes) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (run_id, str(data.get("name") or run_id)[:200], str(data.get("project") or "default")[:100], status,
                 data.get("source") or "sdk", data.get("host"), data.get("created_at") or now,
                 now if status == "running" else None, data.get("finished_at"), data.get("total_steps"),
                 data.get("main_metric"), json.dumps(data.get("config") or {}, ensure_ascii=False, default=str),
                 json.dumps(data.get("env") or {}, ensure_ascii=False, default=str),
                 json.dumps(clean_tags(data.get("tags")), ensure_ascii=False), str(data.get("notes") or "")))
        return self.get_run(run_id)

    def get_run(self, run_id: str) -> dict | None:
        rows = self._q("SELECT * FROM runs WHERE id = ?", (run_id,))
        return _row(rows[0]) if rows else None

    def list_runs(self, project: str | None = None) -> list:
        if project:
            rows = self._q("SELECT * FROM runs WHERE project = ? ORDER BY created_at DESC", (project,))
        else:
            rows = self._q("SELECT * FROM runs ORDER BY created_at DESC")
        return [_row(r) for r in rows]

    def update_run(self, run_id: str, fields: dict, internal: bool = False) -> bool:
        sets, args = [], []
        for key, value in fields.items():
            if key not in _EDITABLE and not internal:
                continue
            if key == "tags":
                value = clean_tags(value)
            if key in _JSON_FIELDS:
                value = json.dumps(value, ensure_ascii=False, default=str)
            sets.append(f"{key} = ?")
            args.append(value)
        if not sets:
            return self.get_run(run_id) is not None
        return self._x(f"UPDATE runs SET {', '.join(sets)}, dirty = 1 WHERE id = ?", (*args, run_id)) > 0

    def delete_run(self, run_id: str) -> bool:
        with self._lock, self._c:
            self._c.execute("DELETE FROM metrics WHERE run_id = ?", (run_id,))
            return self._c.execute("DELETE FROM runs WHERE id = ?", (run_id,)).rowcount > 0

    def heartbeat(self, run_id: str, env: dict | None = None) -> bool:
        now = time.time()
        if env:
            self._x("UPDATE runs SET env = ? WHERE id = ?", (json.dumps(env, ensure_ascii=False, default=str), run_id))
        return self._x("UPDATE runs SET heartbeat_at = ?, status = CASE WHEN status = 'crashed' THEN 'running'"
                       " ELSE status END, finished_at = CASE WHEN status = 'crashed' THEN NULL ELSE finished_at END"
                       " WHERE id = ?", (now, run_id)) > 0

    def finish_run(self, run_id: str, status: str = "finished", error: str | None = None,
                   finished_at: float | None = None) -> bool:
        if status not in ("finished", "failed", "stopped", "crashed"):
            status = "finished"
        return self._x("UPDATE runs SET status = ?, error = ?, finished_at = ?, dirty = 1 WHERE id = ?",
                       (status, error, finished_at or time.time(), run_id)) > 0

    def mark_stale(self) -> int:
        """Запуски, от которых давно нет вестей, помечаются как прерванные."""
        limit = time.time() - HEARTBEAT_TIMEOUT
        return self._x("UPDATE runs SET status = 'crashed', finished_at = heartbeat_at, dirty = 1"
                       " WHERE status = 'running' AND heartbeat_at IS NOT NULL AND heartbeat_at < ?", (limit,))

    def has_running(self) -> bool:
        return bool(self._q("SELECT 1 FROM runs WHERE status = 'running' LIMIT 1"))

    def save_summary(self, run_id: str, summary: dict):
        self._x("UPDATE runs SET summary = ?, dirty = 0 WHERE id = ?",
                (json.dumps(summary, ensure_ascii=False), run_id))

    def projects(self) -> list:
        return [r[0] for r in self._q("SELECT project FROM runs GROUP BY project ORDER BY MAX(created_at) DESC")]

    def add_metrics(self, run_id: str, points: list) -> int:
        rows = []
        for p in points:
            try:
                value = p.get("value")
                value = float(value) if value is not None else None
                if value is not None and (value != value or value in (float("inf"), float("-inf"))):
                    value = None
                rows.append((run_id, str(p["key"])[:200], int(p.get("step") or 0), value, p.get("ts")))
            except (TypeError, ValueError, KeyError, AttributeError):
                continue
        if not rows:
            return 0
        with self._lock, self._c:
            self._c.executemany("INSERT OR REPLACE INTO metrics (run_id, key, step, value, ts) VALUES (?,?,?,?,?)", rows)
            self._c.execute("UPDATE runs SET dirty = 1 WHERE id = ?", (run_id,))
        return len(rows)

    def series(self, run_id: str, keys: list | None = None) -> dict:
        """{ключ: [(step, value, ts), ...]} по возрастанию шага."""
        sql, args = "SELECT key, step, value, ts FROM metrics WHERE run_id = ?", [run_id]
        if keys:
            sql += f" AND key IN ({','.join('?' * len(keys))})"
            args += keys
        out: dict = {}
        for key, step, value, ts in self._q(sql + " ORDER BY key, step", args):
            out.setdefault(key, []).append((step, value, ts))
        return out

    def save_host(self, host: str, info: dict):
        self._x("INSERT OR REPLACE INTO hosts (host, info, seen_at) VALUES (?,?,?)",
                (host, json.dumps(info, ensure_ascii=False), time.time()))

    def add_sample(self, host: str, sample: dict):
        self._x("INSERT OR REPLACE INTO sys_samples (host, ts, data) VALUES (?,?,?)",
                (host, sample["ts"], json.dumps(sample, ensure_ascii=False, separators=(",", ":"))))

    def samples(self, host: str, t0: float, t1: float) -> list:
        rows = self._q("SELECT data FROM sys_samples WHERE host = ? AND ts >= ? AND ts <= ? ORDER BY ts", (host, t0, t1))
        return [json.loads(r[0]) for r in rows]

    def delete_samples(self, host: str):
        self._x("DELETE FROM sys_samples WHERE host = ?", (host,))
        self._x("DELETE FROM hosts WHERE host = ?", (host,))
