#!/usr/bin/env python3
"""Baca kiriman Intake Command Deck dari disk (stdlib saja).

Satu sumber kebenaran untuk akar direktori: variabel lingkungan
`SDB_INTAKE_ROOT`, default `~/sdb-workspace/intake`. Dashboard
(`dashboard/inbox_api.py`) memakai nilai yang sama, jadi apa yang ditulis UI
adalah apa yang dibaca runner.

Keamanan: id intake divalidasi ketat (`YYYYMMDD-HHMMSS-<6 hex>`) dan direktori
hasil resolve wajib tetap di dalam akar intake — argumen CLI tidak boleh
menjadi jalan keluar dari folder itu (CWE-22).
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

ID_RE = re.compile(r"^\d{8}-\d{6}-[a-z0-9]{6}$")


def root() -> Path:
    """Akar direktori intake."""
    env = os.environ.get("SDB_INTAKE_ROOT")
    return Path(env).expanduser() if env else Path.home() / "sdb-workspace" / "intake"


def validate_id(iid: str) -> str:
    """Id intake yang sah; ValueError bila tidak (fail-closed)."""
    if not isinstance(iid, str):
        raise ValueError(f"id intake harus string, dapat {type(iid).__name__}")
    s = iid.strip()
    if not ID_RE.match(s):
        raise ValueError(
            f"id intake tidak sah: {iid!r} — bentuknya YYYYMMDD-HHMMSS-abcdef"
        )
    return s


def list_ids(base: Path | None = None) -> list[str]:
    """Semua id intake, terbaru lebih dulu."""
    b = base or root()
    if not b.is_dir():
        return []
    out = [p.name for p in b.iterdir() if p.is_dir() and ID_RE.match(p.name)]
    return sorted(out, reverse=True)


def latest(base: Path | None = None) -> str | None:
    ids = list_ids(base)
    return ids[0] if ids else None


def load(iid: str, base: Path | None = None) -> dict:
    """Muat satu intake: meta, path brief, dan daftar lampiran absolut."""
    iid = validate_id(iid)
    b = (base or root()).resolve()
    d = (b / iid).resolve()
    if not d.is_relative_to(b):
        raise ValueError(f"id intake keluar dari akar intake: {iid!r}")
    if not d.is_dir():
        raise FileNotFoundError(f"intake {iid} tidak ada di {b}")
    meta_path = d / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.is_file() else {}
    brief_path = d / "brief.md"
    files_dir = d / "files"
    files = []
    for f in sorted(meta.get("files") or [], key=lambda x: str(x.get("name", ""))):
        name = str(f.get("name") or "")
        p = (files_dir / name)
        files.append({
            "name": name,
            "size": f.get("size"),
            "sha256": f.get("sha256"),
            "path": str(p) if p.is_file() else "",
            "exists": p.is_file(),
        })
    return {
        "id": iid,
        "dir": str(d),
        "meta": meta,
        "brief": brief_path.read_text(encoding="utf-8") if brief_path.is_file() else "",
        "brief_path": str(brief_path),
        "files": files,
    }
