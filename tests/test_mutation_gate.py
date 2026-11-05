"""Keselamatan mutation gate: repo tidak boleh tertinggal termutasi bila proses dibunuh.

Audit 2026-11-05 (PQ/AR): `try/finally` mengembalikan berkas untuk exception biasa,
tetapi SIGKILL/OOM tidak menjalankan `finally`. Cadangan `.mutation-backup` + pemulihan
saat start menutup celah itu. Uji ini mengunci mekanismenya.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import mutation_gate as mg


def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(mg, "REPO", tmp_path)
    monkeypatch.setattr(mg, "BACKUP", tmp_path / ".mutation-backup")


def test_cadangan_dipulihkan_setelah_proses_mati(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    target = tmp_path / "scripts" / "gate.py"
    target.parent.mkdir()
    original = "if not allowed:\n    raise SystemExit(1)\n"
    target.write_text(original, encoding="utf-8")

    mg.backup_write("scripts/gate.py", original, mg._sha(original))
    target.write_text("if False:\n    raise SystemExit(1)\n", encoding="utf-8")  # "proses mati" di sini

    restored = mg.recover_stale(verbose=False)
    assert restored == ["scripts/gate.py"]
    assert target.read_text(encoding="utf-8") == original
    assert not mg.BACKUP.exists(), "cadangan harus dibersihkan setelah pulih"


def test_berkas_tidak_disentuh_bila_tidak_ada_sisa(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    target = tmp_path / "a.py"
    target.write_text("x = 1\n", encoding="utf-8")
    assert mg.recover_stale(verbose=False) == []
    assert target.read_text(encoding="utf-8") == "x = 1\n"


def test_backup_clear_menghapus_kedua_berkas(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    mg.backup_write("a.py", "x = 1\n", mg._sha("x = 1\n"))
    assert mg.BACKUP.is_dir()
    mg.backup_clear("a.py")
    assert list(mg.BACKUP.glob("*")) == []
