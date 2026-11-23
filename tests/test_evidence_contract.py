"""C2-B1 — tes kontrak evidence `sdb.verify.evidence/1`.

Semua kunci di sini **sintetis** dan dibuat di direktori sementara: tidak ada
kunci produksi, tidak ada jaringan, tidak ada database produksi.

Yang diuji (positif dan negatif):
  * tanda tangan sah hanya diterima dari signer yang diotorisasi,
  * tanda tangan palsu / kunci lain / namespace lain ditolak,
  * job_id, sidik workspace, snapshot, dan nonce terikat (replay & nonce lama ditolak),
  * evidence kedaluwarsa ditolak,
  * evidence tanpa tanda tangan ditolak,
  * `exit 0` TIDAK otomatis menjadi penerimaan (ACCEPTANCE),
  * `RELEASE_ELIGIBLE` tidak pernah diberikan modul verifikasi.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

import sdb_evidence as evd

NOW = int(time.time())
DIGEST = "a" * 64
CRITERIA = "c" * 64
VERIFIER = "sdb-verifier-test"


@pytest.fixture(scope="module")
def k(tmp_path_factory):
    """Dua kunci ed25519 sintetis + satu `allowed_signers` (hanya kunci A)."""
    d = tmp_path_factory.mktemp("evkeys")
    key_a, key_b = d / "key_a", d / "key_b"
    for p in (key_a, key_b):
        subprocess.run(["ssh-keygen", "-t", "ed25519", "-N", "", "-C", "sdb-test",
                        "-f", str(p)], check=True, capture_output=True)
    pub = (d / "key_a.pub").read_text().strip().split()
    allowed = d / "allowed_signers"
    allowed.write_text(f"{VERIFIER} {pub[0]} {pub[1]}\n", encoding="utf-8")
    os.chmod(allowed, 0o600)
    return {"dir": d, "key_a": key_a, "key_b": key_b, "allowed": allowed,
            "nonce": "1" * 64}


def _sign(evidence: dict, key: Path, namespace: str = evd.NAMESPACE) -> str:
    proc = subprocess.run(["ssh-keygen", "-Y", "sign", "-f", str(key), "-n", namespace],
                          input=evd.signable_bytes(evidence), capture_output=True,
                          check=True)
    return proc.stdout.decode()


def _payload(**over) -> dict:
    badan = {
        "schema": evd.SCHEMA,
        "digest_alg": evd.DIGEST_ALG,
        "project_id": "super-dev-builders",
        "job_id": 7,
        "request_nonce": "1" * 64,
        "snapshot": {"snapshot_id": "sha256:" + "b" * 64,
                     "file_count": 12, "total_bytes": 4096,
                     "complete": True, "created_at": NOW - 30},
        "workspace_digest": DIGEST,
        "artifact_manifest": [{"path": "app.py", "sha256": "d" * 64, "size": 10}],
        "dependencies": [{"ecosystem": "pip", "name": "pytest", "version": "8.3.3",
                          "source": "lockfile", "lockfile_digest": "e" * 64}],
        "test_command": {"argv": ["pytest", "-q"], "cwd": "/workspace", "allowlisted": True},
        "execution": {"exit_code": 0, "duration_ms": 1000, "timed_out": False,
                      "stdout_sha256": "f" * 64, "stderr_sha256": "0" * 64,
                      "tests": {"collected": 12, "passed": 12, "failed": 0,
                                "skipped": 0, "deselected": 0}},
        "sandbox": {"engine": "bwrap", "engine_version": "0.11.1",
                    "profile_id": "sdb-verify-sbx-1", "network": "none",
                    "new_privileges": False, "caps_dropped": True,
                    "writable_paths": ["/workspace", "/tmp", "/run"]},
        "limits": {"cpu_quota": "200%", "memory_max": "2G", "pids_max": 256,
                   "wall_clock_s": 600, "snapshot_max_mb": 2048},
        "timestamps": {"issued_at": NOW - 20, "started_at": NOW - 18,
                       "finished_at": NOW - 10, "expires_at": NOW + 600},
        "verifier": {"id": VERIFIER, "host": "vfy-1", "key_fingerprint": "SHA256:" + "9" * 43},
        "acceptance_criteria": {"id": "cap-BE-03/v1", "criteria_digest": CRITERIA,
                                "checks": [{"id": "tests-all-pass", "ok": True}]},
        "verdict": {"execution": "PASS", "acceptance": "PASS",
                    "release_eligible": True, "failure_reason": None},
    }
    for kunci, nilai in over.items():
        badan[kunci] = nilai
    return badan


def _signed(k, key: Path | None = None, namespace: str = evd.NAMESPACE, **over) -> dict:
    ev = _payload(**over)
    sig = _sign(ev, key or k["key_a"], namespace)
    ev["signature"] = {"alg": "ssh-ed25519", "namespace": namespace,
                       "signer": (ev.get("verifier") or {}).get("id", ""), "sig": sig}
    return ev


def _run(k, ev, **over):
    kw = {
        "job_id": 7, "workspace_digest": DIGEST, "digest_complete": True, "now": NOW,
        "nonce_issued": {k["nonce"]}, "nonce_used": set(),
        "allowed_signers": k["allowed"], "verifier_ids": {VERIFIER},
        "pinned_criteria_digest": CRITERIA,
    }
    kw.update(over)
    return evd.validate(ev, **kw)


# ---------- B01: jalur bahagia ----------
def test_B01_tanda_tangan_sah_dan_terikat_diterima(k):
    hasil = _run(k, _signed(k))
    assert hasil["ok"] is True, hasil
    assert hasil["code"] == ""
    assert hasil["level"] == evd.LEVEL_ACCEPTANCE
    assert hasil["acceptance"] is True


def test_B01b_evidence_ditolak_bila_data_diubah_setelah_ditandatangani(k):
    ev = _signed(k)
    ev["execution"]["tests"]["failed"] = 3      # diubah setelah tanda tangan
    hasil = _run(k, ev)
    assert hasil["ok"] is False
    assert hasil["code"] == "EVIDENCE_UNTRUSTED_SIGNER"


# ---------- B02/B03: tanda tangan & identitas ----------
def test_B02_tanda_tangan_dari_kunci_lain_ditolak(k):
    hasil = _run(k, _signed(k, key=k["key_b"]))
    assert hasil["ok"] is False
    assert hasil["code"] == "EVIDENCE_UNTRUSTED_SIGNER"


def test_B02b_tanpa_tanda_tangan_ditolak(k):
    ev = _payload()
    hasil = _run(k, ev)
    assert hasil["ok"] is False
    assert hasil["code"] == "EVIDENCE_NO_SIGNATURE"


def test_B02c_namespace_tanda_tangan_salah_ditolak(k):
    hasil = _run(k, _signed(k, namespace="namespace-lain"))
    assert hasil["ok"] is False
    assert hasil["code"] == "EVIDENCE_SIGNATURE_ALG"


def test_B03_job_id_salah_ditolak(k):
    hasil = _run(k, _signed(k, job_id=8))
    assert hasil["ok"] is False
    assert hasil["code"] == "EVIDENCE_JOB_MISMATCH"


def test_B03b_verifier_tidak_diizinkan_ditolak(k):
    hasil = _run(k, _signed(k), verifier_ids={"verifier-lain"})
    assert hasil["ok"] is False
    assert hasil["code"] == "EVIDENCE_UNKNOWN_VERIFIER"


# ---------- B04: sidik & snapshot ----------
def test_B04_sidik_workspace_salah_ditolak(k):
    hasil = _run(k, _signed(k, workspace_digest="f" * 64))
    assert hasil["ok"] is False
    assert hasil["code"] == "EVIDENCE_DIGEST_MISMATCH"


def test_B04b_sidik_tidak_lengkap_ditolak(k):
    hasil = _run(k, _signed(k), digest_complete=False)
    assert hasil["ok"] is False
    assert hasil["code"] == "EVIDENCE_DIGEST_INCOMPLETE"


def test_B04c_snapshot_tidak_lengkap_ditolak(k):
    ev = _signed(k)
    ev["snapshot"]["complete"] = False
    # payload berubah setelah tanda tangan -> harus gagal juga, jadi tandatangani ulang
    hasil = _run(k, _signed(k, snapshot={**ev["snapshot"]}))
    assert hasil["ok"] is False
    assert hasil["code"] == "EVIDENCE_SNAPSHOT_INCOMPLETE"


# ---------- B05/B06: nonce & waktu ----------
def test_B05_replay_nonce_lama_ditolak(k):
    hasil = _run(k, _signed(k), nonce_used={k["nonce"]})
    assert hasil["ok"] is False
    assert hasil["code"] == "EVIDENCE_REPLAY"


def test_B05b_nonce_bukan_milik_job_ditolak(k):
    hasil = _run(k, _signed(k), nonce_issued={"2" * 64})
    assert hasil["ok"] is False
    assert hasil["code"] == "EVIDENCE_NONCE_UNKNOWN"


def test_B05c_tanpa_nonce_ditolak(k):
    hasil = _run(k, _signed(k, request_nonce="bukan-hex"))
    assert hasil["ok"] is False
    assert hasil["code"] == "EVIDENCE_NO_NONCE"


def test_B06_evidence_kedaluwarsa_ditolak(k):
    waktu = {"issued_at": NOW - 3000, "started_at": NOW - 2990,
             "finished_at": NOW - 2900, "expires_at": NOW - 100}
    hasil = _run(k, _signed(k, timestamps=waktu))
    assert hasil["ok"] is False
    assert hasil["code"] == "EVIDENCE_EXPIRED"


def test_B06b_waktu_terbit_di_masa_depan_ditolak(k):
    waktu = {"issued_at": NOW + 5000, "started_at": NOW + 5001,
             "finished_at": NOW + 5002, "expires_at": NOW + 9000}
    hasil = _run(k, _signed(k, timestamps=waktu))
    assert hasil["ok"] is False
    assert hasil["code"] == "EVIDENCE_CLOCK"


# ---------- B07: skema ----------
def test_B07_skema_lain_ditolak(k):
    hasil = _run(k, _signed(k, schema="sdb.verify.evidence/9"))
    assert hasil["ok"] is False
    assert hasil["code"] == "EVIDENCE_SCHEMA"


def test_B07b_algoritma_sidik_lain_ditolak(k):
    hasil = _run(k, _signed(k, digest_alg="md5"))
    assert hasil["ok"] is False
    assert hasil["code"] == "EVIDENCE_SCHEMA"


def test_B07c_payload_bukan_objek_ditolak(k):
    hasil = _run(k, ["bukan", "objek"])
    assert hasil["ok"] is False
    assert hasil["code"] == "EVIDENCE_SCHEMA"


# ---------- B08: exit 0 bukan penerimaan ----------
def test_B08_exit_nol_tanpa_tes_bukan_penerimaan(k):
    eksekusi = {"exit_code": 0, "duration_ms": 5, "timed_out": False,
                "stdout_sha256": "f" * 64, "stderr_sha256": "0" * 64,
                "tests": {"collected": 0, "passed": 0, "failed": 0,
                          "skipped": 0, "deselected": 0}}
    hasil = _run(k, _signed(k, execution=eksekusi))
    assert hasil["ok"] is True
    assert hasil["acceptance"] is False
    assert hasil["level"] == evd.LEVEL_EXECUTION
    assert "NO_TESTS" in hasil["reason"]


def test_B08b_tes_gagal_bukan_penerimaan(k):
    eksekusi = {"exit_code": 0, "duration_ms": 5, "timed_out": False,
                "stdout_sha256": "f" * 64, "stderr_sha256": "0" * 64,
                "tests": {"collected": 10, "passed": 9, "failed": 1,
                          "skipped": 0, "deselected": 0}}
    hasil = _run(k, _signed(k, execution=eksekusi))
    assert hasil["acceptance"] is False
    assert "TESTS_FAILED" in hasil["reason"]


def test_B08c_deselect_tanpa_alasan_bukan_penerimaan(k):
    eksekusi = {"exit_code": 0, "duration_ms": 5, "timed_out": False,
                "stdout_sha256": "f" * 64, "stderr_sha256": "0" * 64,
                "tests": {"collected": 10, "passed": 9, "failed": 0,
                          "skipped": 0, "deselected": 1}}
    hasil = _run(k, _signed(k, execution=eksekusi))
    assert hasil["acceptance"] is False
    assert "SILENT_DESELECT" in hasil["reason"]


def test_B08d_kriteria_tidak_dipin_bukan_penerimaan(k):
    hasil = _run(k, _signed(k), pinned_criteria_digest=None)
    assert hasil["ok"] is True
    assert hasil["acceptance"] is False
    assert "CRITERIA_UNPINNED" in hasil["reason"]


def test_B08e_kriteria_berbeda_bukan_penerimaan(k):
    hasil = _run(k, _signed(k), pinned_criteria_digest="9" * 64)
    assert hasil["acceptance"] is False
    assert "CRITERIA_MISMATCH" in hasil["reason"]


# ---------- B09: rilis tidak pernah diberikan modul ----------
def test_B09_release_eligible_tidak_pernah_diberikan(k):
    # payload bahkan mengklaim release_eligible true; modul tetap menolak menaikkan.
    hasil = _run(k, _signed(k))
    assert hasil["release_eligible"] is False
    assert _payload()["verdict"]["release_eligible"] is True


def test_B09b_eksekusi_gagal_tidak_diterima(k):
    hasil = _run(k, _signed(k, verdict={"execution": "FAIL", "acceptance": "FAIL",
                                        "release_eligible": False,
                                        "failure_reason": "tests failed"}))
    assert hasil["ok"] is False
    assert hasil["code"] == "VERIFY_FAIL"


def test_B09c_eksekusi_timeout_tidak_diterima(k):
    hasil = _run(k, _signed(k, verdict={"execution": "TIMEOUT", "acceptance": "FAIL",
                                        "release_eligible": False,
                                        "failure_reason": "timeout"}))
    assert hasil["ok"] is False
    assert hasil["code"] == "VERIFY_TIMEOUT"


# ---------- B10: kanonikalisasi & signer store ----------
def test_B10_urutan_kunci_tidak_mengubah_byte_ditandatangani():
    a = {"b": 2, "a": {"y": 1, "x": [1, 2]}}
    b = {"a": {"x": [1, 2], "y": 1}, "b": 2}
    assert evd.signable_bytes(a) == evd.signable_bytes(b)
    assert evd.signable_bytes({"a": 1, "signature": {"sig": "x"}}) == \
        evd.canonical_bytes({"a": 1})


def test_B10b_allowed_signers_symlink_ditolak(k, tmp_path):
    tautan = tmp_path / "tautan_signers"
    tautan.symlink_to(k["allowed"])
    hasil = _run(k, _signed(k), allowed_signers=tautan)
    assert hasil["ok"] is False
    assert hasil["code"] == "EVIDENCE_SIGNER_STORE"


def test_B10c_allowed_signers_world_writable_ditolak(k, tmp_path):
    terbuka = tmp_path / "signers_terbuka"
    terbuka.write_text(k["allowed"].read_text(encoding="utf-8"), encoding="utf-8")
    os.chmod(terbuka, 0o666)
    hasil = _run(k, _signed(k), allowed_signers=terbuka)
    assert hasil["ok"] is False
    assert hasil["code"] == "EVIDENCE_SIGNER_STORE"


def test_B10d_allowed_signers_hilang_ditolak(k, tmp_path):
    hasil = _run(k, _signed(k), allowed_signers=tmp_path / "tidak-ada")
    assert hasil["ok"] is False
    assert hasil["code"] == "EVIDENCE_SIGNER_STORE"


# ---------- B11: mode legacy vs strict ----------
def test_B11_mode_default_legacy_dan_nilai_aneh_jadi_strict():
    assert evd.evidence_mode(None) == "legacy"
    assert evd.evidence_mode("  legacy ") == "legacy"
    assert evd.evidence_mode("") == "strict"
    assert evd.evidence_mode("longgar") == "strict"
    assert evd.evidence_mode("STRICT") == "strict"


def test_B11b_parse_allowed_signers_mengabaikan_baris_rusak(k):
    principals, keys = evd.parse_allowed_signers(
        "# komentar\n\nrusak\n"
        f"{VERIFIER} ssh-ed25519 AAAA\n")
    assert principals == {VERIFIER}
    assert len(keys) == 1
