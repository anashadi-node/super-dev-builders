"""Release Gate (tahap 12) — uji positif DAN negatif.

Alasan file ini ada: sebelum 2026-11-06 `scripts/release_check.py` tak punya satu
tes pun, jadi satu-satunya cara "membuktikan" gerbang rilis bekerja adalah klaim
di dokumen. Gerbang yang tak pernah dieksekusi = prosa. Uji di sini memakai
direktori sementara, bukan evidence nyata di `runs/`.
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import release_check

ARTEFAK = {
    "requirements.md": "requirement",
    "logs/build-20261106.log": "build",
    "logs/tests-20261106.log": "tests",
    "reports/review-20261106.md": "review",
    "reports/security-gate.md": "security",
    "reports/assurance-audit.md": "audit",
    "docs/README-rilis.md": "docs",
}


def _tulis(project, rel, isi="ok\n"):
    path = os.path.join(project, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(isi)


def _verdict(project, nilai):
    _tulis(project, "reports/security-verdict.json", json.dumps({"verdict": nilai}))


def _proyek_lengkap(tmp_path):
    for rel in ARTEFAK:
        _tulis(tmp_path, rel)
    _verdict(tmp_path, "PASS")
    return tmp_path


def test_pass_bila_semua_artefak_fresh_dan_verdict_pass(tmp_path):
    project = _proyek_lengkap(tmp_path)
    rc = release_check.main(["--project", str(project)])
    assert rc == 0
    hasil = json.load(open(os.path.join(project, "reports", "release-verdict.json")))
    assert hasil["verdict"] == "PASS"
    assert len(hasil["satisfied"]) >= len(ARTEFAK)


def test_fail_bila_satu_artefak_hilang(tmp_path):
    project = _proyek_lengkap(tmp_path)
    os.remove(os.path.join(project, "logs/tests-20261106.log"))
    rc = release_check.main(["--project", str(project)])
    assert rc == 1
    hasil = json.load(open(os.path.join(project, "reports", "release-verdict.json")))
    gagal = {item["gate"] for item in hasil["failures"]}
    assert "tests" in gagal


def test_fail_bila_verdict_isi_fail(tmp_path):
    """Keberadaan + kesegaran tak cukup: isi verdict adalah kontrak mesin."""
    project = _proyek_lengkap(tmp_path)
    _verdict(project, "FAIL")
    rc = release_check.main(["--project", str(project)])
    assert rc == 1
    hasil = json.load(open(os.path.join(project, "reports", "release-verdict.json")))
    assert any(f["gate"] == "security-verdict" for f in hasil["failures"])


def test_fail_bila_artefak_kedaluwarsa(tmp_path):
    project = _proyek_lengkap(tmp_path)
    lama = time.time() - 48 * 3600
    os.utime(os.path.join(project, "logs/build-20261106.log"), (lama, lama))
    rc = release_check.main(["--project", str(project)])
    assert rc == 1
    hasil = json.load(open(os.path.join(project, "reports", "release-verdict.json")))
    assert any("kedaluwarsa" in f["reason"] for f in hasil["failures"])


def test_run_did_ditolak_cepat_bukan_tujuh_baris_menyesatkan(tmp_path, capsys):
    """Run DID bukan kandidat rilis: harus jelas dan gagal-cepat (exit 2)."""
    _tulis(tmp_path, "did/handoff.json", json.dumps({"target": "e1-app"}))
    rc = release_check.main(["--project", str(tmp_path)])
    assert rc == 2
    err = capsys.readouterr().err
    assert "investigasi DID" in err
    assert "make did" in err


def test_slug_tidak_sah_ditolak(tmp_path):
    rc = release_check.main(["../etc"])
    assert rc == 2
