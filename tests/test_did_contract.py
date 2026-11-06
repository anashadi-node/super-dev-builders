"""Kontrak Divisi Investigasi (DID): validator harus menolak klaim tanpa bukti.

Yang diuji bukan "skrip bisa jalan", tetapi janji mutu:
  - handoff sah diterima,
  - setiap pelanggaran (hash, falsifikasi, coverage, must, disiplin, anggaran, rahasia)
    ditolak dengan kode aturan yang tepat,
  - matematika benchmark benar.

Semua fixture dibuat di tmp_path; tidak menyentuh evidence nyata.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import did_validate as dv

WEB_COVERAGE = ["routes", "states", "components", "network", "auth_flow", "assets", "responsive"]


def _write(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


@pytest.fixture()
def repo(tmp_path):
    """Repo mini: profil asli + gate PASS + satu berkas evidence ber-hash."""
    _write(os.path.join(tmp_path, "platform", "did_profiles.json"),
           open(os.path.join(ROOT, "platform", "did_profiles.json"), encoding="utf-8").read())
    _write(os.path.join(tmp_path, "reports", "t1", "gate0-verdict.json"), '{"verdict": "PASS"}')
    ev = os.path.join(tmp_path, "evidence", "t1", "ev.json")
    _write(ev, '{"page": "/katalog", "items": 12}')
    digest = hashlib.sha256(open(ev, "rb").read()).hexdigest()
    return {"root": str(tmp_path), "evidence": ev, "sha256": digest}


def _handoff(repo, **over):
    h = {
        "schema": "sdb.did.handoff/1",
        "generated_at": "2026-11-06T10:00:00+07:00",
        "target": {"slug": "t1", "name": "Target Uji", "type": "web",
                   "authorization": {"gate0_verdict": "PASS", "manifest": "evidence/t1/authorization.yaml"}},
        "scope": {"depth": "L2", "profile": "web", "in_scope": ["publik"], "out_of_scope": ["login"]},
        "evidence_manifest": [{"id": "E-001", "path": "evidence/t1/ev.json", "sha256": repo["sha256"],
                               "captured_at": "2026-11-06T09:00:00+07:00", "status": "OBSERVED"}],
        "findings": [
            {"id": "F-001", "status": "OBSERVED", "claim": "Halaman /katalog menampilkan 12 item.",
             "locator": "/katalog", "evidence": ["E-001"]},
            {"id": "F-002", "status": "INFERRED", "confidence": 80, "claim": "Pagination 1-based.",
             "locator": "GET /api/products?page=2", "evidence": ["E-001"],
             "falsification": {"test": "bandingkan page=1 dan page=2", "expected": "item berbeda"}},
            {"id": "F-003", "status": "UNKNOWN", "claim": "page_size maksimum belum teramati.", "evidence": []},
        ],
        "unknowns": [{"id": "U-001", "question": "page_size maksimum?", "impact": "non-blocking",
                      "probe": "uji 24/48/96"}],
        "coverage": [{"category": c, "status": "COVERED", "found": 1, "evidence": ["E-001"]} for c in WEB_COVERAGE],
        "features": [{"id": "FT-01", "name": "Katalog", "priority": "must", "status": "OBSERVED",
                      "findings": ["F-001"], "evidence": ["E-001"],
                      "acceptance_tests": [{"given": "12 item", "when": "buka /katalog", "then": "12 kartu tampil"}]}],
        "build_seeds": {"entities": [{"name": "Product", "status": "OBSERVED", "fields": [{"name": "id"}]}],
                        "api": [{"method": "GET", "path": "/api/products", "status": "OBSERVED", "evidence": ["E-001"]}],
                        "states": [{"name": "kosong", "status": "OBSERVED"}],
                        "design_tokens": {"colors": ["#111827"]},
                        "non_functional": []},
        "handoff": {"builders_ready": True, "blocking_unknowns": 0, "summary": "Siap.", "next_actions": []},
        "budget": {"used": {"tool_calls": 10, "minutes": 20, "evidence_bytes": 1024}},
        "discipline": {"replica_skill_used": False, "wrote_code": False, "mcp_registered": False,
                       "redaction_applied": True},
    }
    h.update(over)
    return h


def _ids(rep):
    return {c["id"] for c in rep.failed}


def test_handoff_sah_diterima(repo):
    rep = dv.validate(_handoff(repo), repo["root"])
    assert rep.passed, [c for c in rep.failed]
    assert rep.metrics["must_features"] == 1
    assert rep.metrics["coverage_covered"] == len(WEB_COVERAGE)


def test_hash_berubah_ditolak(repo):
    h = _handoff(repo)
    h["evidence_manifest"][0]["sha256"] = "f" * 64
    assert "R04d_hash" in _ids(dv.validate(h, repo["root"]))


def test_inferred_tanpa_falsifikasi_ditolak(repo):
    h = _handoff(repo)
    del h["findings"][1]["falsification"]
    assert "R05d_inferred_conf+falsify" in _ids(dv.validate(h, repo["root"]))


def test_unknown_tanpa_probe_ditolak(repo):
    h = _handoff(repo)
    h["unknowns"][0].pop("probe")
    assert "R06_unknowns_complete" in _ids(dv.validate(h, repo["root"]))


def test_coverage_wajib_hilang_ditolak(repo):
    h = _handoff(repo)
    h["coverage"] = [c for c in h["coverage"] if c["category"] != "auth_flow"]
    assert "R07a_coverage_present" in _ids(dv.validate(h, repo["root"]))


def test_must_tanpa_bukti_observed_ditolak(repo):
    h = _handoff(repo)
    h["features"][0]["findings"] = ["F-002"]        # hanya INFERRED
    h["features"][0].pop("evidence")
    assert "R08a_must_has_observed" in _ids(dv.validate(h, repo["root"]))


def test_must_tanpa_tes_terima_ditolak(repo):
    h = _handoff(repo)
    h["features"][0]["acceptance_tests"] = [{"given": "x"}]
    assert "R08b_must_has_tests" in _ids(dv.validate(h, repo["root"]))


def test_replica_skill_ditolak(repo):
    h = _handoff(repo)
    h["discipline"]["replica_skill_used"] = True
    assert "R10a_no_replica" in _ids(dv.validate(h, repo["root"]))


def test_menulis_kode_ditolak(repo):
    h = _handoff(repo)
    h["discipline"]["wrote_code"] = True
    assert "R10b_readonly" in _ids(dv.validate(h, repo["root"]))


def test_anggaran_dilewati_ditolak(repo):
    h = _handoff(repo)
    h["budget"]["used"]["tool_calls"] = 999
    assert "R11_budget" in _ids(dv.validate(h, repo["root"]))


def test_rahasia_dalam_evidence_ditolak(repo):
    fake = '{"token": "sk-' + "a" * 24 + '"}'   # dirangkai agar pemindai rahasia repo tidak menandai uji ini
    _write(repo["evidence"], fake)
    h = _handoff(repo)
    h["evidence_manifest"][0]["sha256"] = hashlib.sha256(open(repo["evidence"], "rb").read()).hexdigest()
    assert "R04e_no_secret" in _ids(dv.validate(h, repo["root"]))


def test_gate0_disk_bukan_pass_ditolak(repo):
    _write(os.path.join(repo["root"], "reports", "t1", "gate0-verdict.json"), '{"verdict": "BLOCKED"}')
    assert "R03_gate0" in _ids(dv.validate(_handoff(repo), repo["root"]))


def test_template_contoh_lengkap():
    """Template harus memuat semua kunci yang dibaca validator (dokumentasi hidup)."""
    tpl = json.load(open(os.path.join(ROOT, "skills", "did-handoff", "templates", "handoff.contoh.json"),
                         encoding="utf-8"))
    for key in ("schema", "target", "scope", "evidence_manifest", "findings", "unknowns",
                "coverage", "features", "build_seeds", "handoff", "budget", "discipline"):
        assert key in tpl, f"template kehilangan kunci {key}"


def test_bench_matematika():
    handoff = {"features": [
        {"id": "C1", "name": "Filter harga", "claim": "slider harga", "status": "OBSERVED"},
        {"id": "C2", "name": "Keranjang belanja", "claim": "cart", "status": "OBSERVED"},
    ]}
    truth = {"features": [
        {"id": "F02", "name": "Filter harga", "keywords": ["filter harga"]},
        {"id": "F03", "name": "Pencarian", "keywords": ["search", "pencarian"]},
    ]}
    res = dv.bench(handoff, truth)
    assert res["true_positives"] == 1
    assert res["precision"] == pytest.approx(0.5)
    assert res["recall"] == pytest.approx(0.5)
    assert res["f1"] == pytest.approx(0.5)
    assert res["hallucinated"] == ["C2"]
    assert res["hallucination_rate"] == pytest.approx(0.5)


def test_profiles_konsisten():
    prof = dv.profiles(ROOT)
    assert {"L1", "L2", "L3", "L4"} <= set((prof.get("depths") or {}))
    allowed_seeds = {"entities", "api", "states", "design_tokens", "non_functional"}
    for name, p in (prof.get("profiles") or {}).items():
        assert p.get("required_categories"), f"{name} tanpa kategori wajib"
        bad = set(p.get("required_seeds") or []) - allowed_seeds
        assert not bad, f"{name}: seed tak dikenal {bad}"
        assert p.get("default_depth") in (prof.get("depths") or {}), f"{name}: depth default tidak ada"
