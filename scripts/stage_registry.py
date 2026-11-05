#!/usr/bin/python3
"""Sumber tunggal daftar tahap SDB — pembaca `workflows/stages.yaml`.

Masalah yang diselesaikan (audit 2026-11-05, temuan AR1/WF1): daftar tahap pernah
hidup dua kali — 18 tahap di `scripts/workflow_run.py` dan 16 di `dashboard/ws_api.py` —
dengan arti berbeda untuk nomor yang sama (05 = "HUMAN DESIGN APPROVAL" vs "Recon").
Dua daftar yang saling bertentangan berarti dashboard bisa menampilkan "tahap 12 selesai"
padahal runner menganggap tahap 12 adalah RELEASE GATE dan verdict belum ada.

Sejak berkas ini ada: YAML = satu-satunya definisi; runner dan dashboard menurunkannya.
`tests/test_stage_registry.py` gagal bila ada modul yang menulis daftar tahap kedua.

Pemakaian:
    from stage_registry import stages
    for s in stages():
        s["code"], s["name"], s["artifacts"], s["tool"], s["kind"], s["human"]
"""
from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sdb_common import load_yaml, repo_path

KINDS = {"doc", "exec", "gate", "approval"}
REQUIRED = ("code", "name", "artifacts", "tool", "profile", "kind", "human")
CODE_RE = re.compile(r"^(\d{2})([A-Z])?$")

_cached: tuple[str, str, list[dict]] | None = None


def _path() -> str:
    return os.path.join(repo_path(), "workflows", "stages.yaml")


def validate(rows: list[dict]) -> None:
    """Tolak registry yang tidak konsisten — lebih baik gagal di sini daripada di produksi."""
    if not rows:
        raise ValueError("stages.yaml: daftar stages kosong")
    seen: set[str] = set()
    last_num = 0
    for i, r in enumerate(rows, 1):
        missing = [k for k in REQUIRED if k not in r]
        if missing:
            raise ValueError(f"stages.yaml tahap #{i} ({r.get('code', '?')}): field hilang {missing}")
        code = str(r["code"])
        if not CODE_RE.match(code):
            raise ValueError(f"stages.yaml: kode tidak sah {code!r} (format NN atau NNX)")
        if code in seen:
            raise ValueError(f"stages.yaml: kode ganda {code!r}")
        seen.add(code)
        if r["kind"] not in KINDS:
            raise ValueError(f"stages.yaml {code}: kind {r['kind']!r} bukan {sorted(KINDS)}")
        if not isinstance(r["artifacts"], list) or not r["artifacts"]:
            raise ValueError(f"stages.yaml {code}: artifacts harus daftar tidak kosong")
        if not isinstance(r["human"], bool):
            raise ValueError(f"stages.yaml {code}: human harus boolean")
        m = CODE_RE.match(code)
        assert m is not None  # sudah dijamin di atas; jaga tipe tetap sempit
        num = int(m.group(1))
        if num < last_num:
            raise ValueError(f"stages.yaml: urutan nomor mundur di {code}")
        last_num = num


def stages(path: str | None = None) -> list[dict]:
    """Baca + validasi registry. Hasil di-cache selama berkas tidak berubah (mtime+size)."""
    global _cached
    p = path or _path()
    st = os.stat(p)
    key = f"{st.st_mtime_ns}:{st.st_size}"
    if _cached and _cached[0] == p and _cached[1] == key:
        return _cached[2]
    data = load_yaml(p)
    rows = data.get("stages") or []
    validate(rows)
    _cached = (p, key, rows)
    return rows


def as_cli_rows(path: str | None = None) -> list[tuple[str, str, list[str], str]]:
    """Bentuk yang dipakai `scripts/workflow_run.py`: (kode, nama, pola artefak, tool)."""
    return [(s["code"], s["name"], list(s["artifacts"]), s["tool"]) for s in stages(path)]


def as_dashboard_rows(path: str | None = None) -> list[tuple[str, str, str, str]]:
    """Bentuk yang dipakai `dashboard/ws_api.py`: (kode, nama, profil, doc|exec).

    `doc` = aman dijalankan dari web (keluaran dokumen); gate/approval/exec butuh
    eksekusi nyata di repo sehingga ditandai `exec`. Approval manusia TIDAK pernah `doc`.
    """
    rows = []
    for s in stages(path):
        kind = "doc" if s["kind"] == "doc" and not s["human"] else "exec"
        rows.append((s["code"], s["name"], s["profile"], kind))
    return rows


if __name__ == "__main__":
    for r in stages():
        print(f'{r["code"]:>4}  {r["kind"]:<8} human={int(r["human"])}  {r["name"]}')
