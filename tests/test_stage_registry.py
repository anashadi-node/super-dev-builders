"""Registry tahap tunggal: workflow runner dan dashboard tidak boleh berbeda pendapat.

Konteks: audit 2026-11-05 (AR1/WF1) menemukan 18 tahap di scripts/workflow_run.py (kini 19
dengan tahap 01C DID, 2026-11-06)
vs 16 tahap di dashboard/ws_api.py, dengan arti berbeda untuk nomor yang sama.
Uji ini mengunci perbaikan: satu YAML, dua penurun, dan tidak boleh ada daftar kedua.
"""
from __future__ import annotations

import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "dashboard"))

import stage_registry
import workflow_run as wf


def test_registry_valid_dan_unik():
    rows = stage_registry.stages()
    # 2026-11-06: 18 -> 19 (tahap 01C DID). Angka dikunci agar penambahan tahap
    # selalu disengaja, bukan efek samping.
    assert len(rows) == 19, f"registry berisi {len(rows)} tahap, perkiraan 19"
    codes = [r["code"] for r in rows]
    assert len(codes) == len(set(codes)), f"kode ganda: {codes}"
    assert codes[0] == "01" and codes[-1] == "16"
    assert {"01A", "01B", "01C"} <= set(codes), "tahap gate/recon/DID hilang dari registry"


def test_runner_dan_dashboard_dari_sumber_sama():
    dash = stage_registry.as_dashboard_rows()
    cli = stage_registry.as_cli_rows()
    assert [c[0] for c in cli] == [d[0] for d in dash]
    assert [c[1] for c in cli] == [d[1] for d in dash]
    assert wf.STAGES == cli
    assert len(dash) == len(cli) == 19


def test_tahap_manusia_tidak_pernah_aman_dijalankan_web():
    for r in stage_registry.stages():
        if r["human"] or r["kind"] in {"gate", "approval"}:
            kind = next(k for c, _n, _p, k in stage_registry.as_dashboard_rows() if c == r["code"])
            assert kind == "exec", f"{r['code']} ({r['kind']}, human={r['human']}) ditandai doc"


def test_tidak_ada_daftar_tahap_kedua():
    """Setiap modul non-uji yang menulis literal STAGES = [ ... ] melanggar aturan satu sumber."""
    offenders = []
    pat = re.compile(r"^\s*STAGES\s*(?::[^=]+)?=\s*\[", re.M)
    for base in ("scripts", "dashboard", "sdb_platform", "tools"):
        for dirpath, _dirs, files in os.walk(os.path.join(ROOT, base)):
            if "__pycache__" in dirpath:
                continue
            for fn in files:
                if not fn.endswith(".py") or fn.startswith("test_"):
                    continue
                p = os.path.join(dirpath, fn)
                if pat.search(open(p, encoding="utf-8").read()):
                    offenders.append(os.path.relpath(p, ROOT))
    assert offenders == [], f"daftar tahap kedua ditemukan di: {offenders}"


def test_validasi_menolak_registry_rusak():
    good = {"code": "01", "name": "X", "artifacts": ["a/{t}"], "tool": "-",
            "profile": "p", "kind": "doc", "human": False}
    with pytest.raises(ValueError):
        stage_registry.validate([good, dict(good)])           # kode ganda
    with pytest.raises(ValueError):
        stage_registry.validate([{k: v for k, v in good.items() if k != "artifacts"}])
    with pytest.raises(ValueError):
        stage_registry.validate([dict(good, kind="ajaib")])
    with pytest.raises(ValueError):
        stage_registry.validate([dict(good, code="1")])
    with pytest.raises(ValueError):
        stage_registry.validate([dict(good, human="true")])
    with pytest.raises(ValueError):
        stage_registry.validate([])
