#!/usr/bin/env python3
"""Antrean job build SDB — SQLite kecil, dipakai bot Telegram dan worker.

Alur status:
    spec_queued -> spec_running -> spec_ready --(/approve)--> build_queued
                                  \\--(/reject)--> rejected
    build_queued -> building -> done | failed
    (kapan saja, pemilik) -> cancelled

Kenapa dua tahap: spesifikasi dulu, disetujui manusia, baru kode. Ini yang
membedakan "premium" dengan "AI menebak lalu menghasilkan sampah".
"""
from __future__ import annotations

import os
import re
import sqlite3
import time
from pathlib import Path

DB = Path(os.environ.get("SDB_BUILD_DB", "~/.local/state/sdb/build_jobs.db")).expanduser()
BUILDS = Path(os.environ.get("SDB_BUILDS", "~/sdb-builds")).expanduser()

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  slug TEXT NOT NULL,
  title TEXT NOT NULL,
  brief TEXT NOT NULL,
  status TEXT NOT NULL,
  dir TEXT NOT NULL,
  model TEXT,
  session_spec TEXT,
  session_build TEXT,
  error TEXT,
  created REAL NOT NULL,
  updated REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS events(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  job_id INTEGER NOT NULL,
  ts REAL NOT NULL,
  kind TEXT NOT NULL,
  text TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_events_job ON events(job_id);
"""

OPEN_STATES = ("spec_queued", "spec_running", "spec_ready", "build_queued", "building")


def connect() -> sqlite3.Connection:
    DB.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB, timeout=15)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.executescript(SCHEMA)
    return con


def slugify(text: str, limit: int = 32) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return (s[:limit] or "proyek").strip("-")


def create_job(brief: str, title: str = "", model: str = "") -> int:
    now = time.time()
    brief = brief.strip()
    title = (title or brief.splitlines()[0])[:80]
    with connect() as con:
        cur = con.execute(
            "INSERT INTO jobs(slug,title,brief,status,dir,model,created,updated)"
            " VALUES(?,?,?,?,?,?,?,?)",
            (slugify(title), title, brief, "spec_queued", "", model, now, now))
        jid = int(cur.lastrowid or 0)
        if not jid:
            raise RuntimeError("gagal membuat job (lastrowid kosong)")
        d = BUILDS / f"{jid:03d}-{slugify(title)}"
        d.mkdir(parents=True, exist_ok=True)
        con.execute("UPDATE jobs SET dir=? WHERE id=?", (str(d), jid))
        con.execute("INSERT INTO events(job_id,ts,kind,text) VALUES(?,?,?,?)",
                    (jid, now, "created", brief[:2000]))
    return jid


def get(job_id: int) -> dict | None:
    with connect() as con:
        row = con.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    return dict(row) if row else None


def list_jobs(limit: int = 10, only_open: bool = False) -> list[dict]:
    sql = "SELECT * FROM jobs"
    args: tuple = ()
    if only_open:
        sql += " WHERE status IN (%s)" % ",".join("?" * len(OPEN_STATES))
        args = OPEN_STATES
    sql += " ORDER BY id DESC LIMIT ?"
    with connect() as con:
        return [dict(r) for r in con.execute(sql, args + (limit,))]


def set_status(job_id: int, status: str, note: str = "") -> None:
    with connect() as con:
        con.execute("UPDATE jobs SET status=?, updated=? WHERE id=?",
                    (status, time.time(), job_id))
        if note:
            con.execute("INSERT INTO events(job_id,ts,kind,text) VALUES(?,?,?,?)",
                        (job_id, time.time(), status, note[:4000]))


def set_field(job_id: int, **fields) -> None:
    allowed = {"model", "session_spec", "session_build", "error", "dir", "title"}
    cols = {k: v for k, v in fields.items() if k in allowed}
    if not cols:
        return
    sets = ", ".join(f"{k}=?" for k in cols)
    with connect() as con:
        con.execute(f"UPDATE jobs SET {sets}, updated=? WHERE id=?",
                    (*cols.values(), time.time(), job_id))


def add_event(job_id: int, kind: str, text: str) -> None:
    with connect() as con:
        con.execute("INSERT INTO events(job_id,ts,kind,text) VALUES(?,?,?,?)",
                    (job_id, time.time(), kind, text[:8000]))


def events(job_id: int, limit: int = 8) -> list[dict]:
    with connect() as con:
        rows = con.execute(
            "SELECT ts,kind,text FROM events WHERE job_id=? ORDER BY id DESC LIMIT ?",
            (job_id, limit)).fetchall()
    return [dict(r) for r in reversed(rows)]


def claim(status: str, running: str) -> dict | None:
    """Ambil satu job berstatus `status` dan kunci sebagai `running` (atomik)."""
    with connect() as con:
        con.execute("BEGIN IMMEDIATE")
        row = con.execute(
            "SELECT * FROM jobs WHERE status=? ORDER BY id LIMIT 1", (status,)).fetchone()
        if not row:
            con.execute("COMMIT")
            return None
        con.execute("UPDATE jobs SET status=?, updated=? WHERE id=?",
                    (running, time.time(), row["id"]))
        con.execute("COMMIT")
    return dict(row)


def stats() -> dict:
    with connect() as con:
        rows = con.execute("SELECT status, COUNT(*) FROM jobs GROUP BY status").fetchall()
    return {s: n for s, n in rows}


if __name__ == "__main__":
    import json
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "stats":
        print(json.dumps(stats()))
    else:
        for j in list_jobs(20):
            print(f"{j['id']:3d} {j['status']:<12} {j['title'][:50]}")
