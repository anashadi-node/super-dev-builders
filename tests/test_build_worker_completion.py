"""C2-A — tes gerbang penyelesaian (`done`) worker build.

Fokus: status `done` tidak boleh lahir dari keberadaan berkas saja.
Semua fixture sintetis di `tmp_path`; tidak ada DB produksi, Telegram nyata,
atau pemanggilan Hermes nyata. `run_hermes` dan `notify` selalu diganti.

Kontrak yang diuji (lihat laporan C2-A):
  * workspace divalidasi fail-closed (di dalam SDB_BUILDS, bukan symlink, awalan ID job),
  * README.md/VERIFY.md harus berkas regular non-kosong dan bukan symlink,
  * isi VERIFY.md tidak pernah diperlakukan sebagai bukti mesin,
  * kebijakan `verified` hanya menerima event `verify` PASS yang terikat
    job + direktori nyata + digest isi workspace,
  * kebijakan tak dikenal diperlakukan `verified` (fail-closed),
  * default tetap `attested` agar perubahan tidak aktif tanpa persetujuan Owner,
  * tidak ada auto-upgrade status job historis.
"""
from __future__ import annotations

import hashlib
import importlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "scripts"
sys.path.insert(0, str(SCRIPTS))

# Hash konstanta prompt pada baseline 6f1cfc2 — C2-A tidak boleh mengubah perilaku ronde.
BASELINE_PROMPT_HASH = {
    "GUARD": "096491264fde2a66",
    "SPEC_PROMPT": "fdedb84243750343",
    "DOCS_PROMPT": "ce83ed22a615fbf6",
    "CONTINUE_PROMPT": "a813066db38d29cc",
    "BUILD_PROMPT": "c575d02f4c9f82c9",
}


@pytest.fixture()
def w(tmp_path, monkeypatch):
    """Lingkungan terisolasi: DB job, builds, dan Telegram palsu di tmp_path."""
    monkeypatch.setenv("SDB_BUILD_DB", str(tmp_path / "jobs.db"))
    monkeypatch.setenv("SDB_BUILDS", str(tmp_path / "builds"))
    monkeypatch.setenv("SDB_TG_BOT_TOKEN", "123:CANARY-TOKEN")
    monkeypatch.setenv("SDB_TG_CHAT_ID", "777")
    monkeypatch.delenv("SDB_DONE_POLICY", raising=False)
    (tmp_path / "builds").mkdir()
    for mod in ("sdb_jobs", "sdb_build_worker"):
        sys.modules.pop(mod, None)
    jobs = importlib.import_module("sdb_jobs")
    wk = importlib.import_module("sdb_build_worker")

    sent: list[str] = []
    monkeypatch.setattr(wk, "notify", sent.append)
    monkeypatch.setattr(wk, "run_hermes", lambda *a, **k: ("ringkas", "sid-uji", 0))
    # Tidak ada jalan keluar ke jaringan dari sesi tes.
    monkeypatch.setattr(wk.urllib.request, "urlopen",
                        lambda *a, **k: pytest.fail("jaringan dipanggil saat tes"))
    wk.sent = sent
    return wk, jobs


def _buat_job(jobs, readme: str | None = "README isi", verify: str | None = "VERIFY isi",
              docs: bool = True):
    """Buat job nyata di DB tmp, lalu isi dokumen bila diminta."""
    jid = jobs.create_job("Bangun situs katalog villa dengan filter harga dan booking WhatsApp")
    d = Path(jobs.get(jid)["dir"])
    if docs:
        if readme is not None:
            (d / "README.md").write_text(readme, encoding="utf-8")
        if verify is not None:
            (d / "VERIFY.md").write_text(verify, encoding="utf-8")
    return jid, jobs.get(jid)


def _event_legacy(jobs, jid, **isi):
    """Event verify gaya C2-A: TANPA tanda tangan (hanya untuk menguji penolakan)."""
    badan = {"schema": 1, "job_id": jid, "dir_real": "", "tree_sha256": "", "verdict": "PASS"}
    badan.update(isi)
    jobs.add_event(jid, "verify", json.dumps(badan))
    return badan


def _gabung_dalam(dasar: dict, ubah: dict) -> dict:
    for k, v in ubah.items():
        if isinstance(v, dict) and isinstance(dasar.get(k), dict):
            _gabung_dalam(dasar[k], v)
        else:
            dasar[k] = v
    return dasar


def _event_verify(jobs, jid, kunci, ubah: dict | None = None):
    """Tulis event verify berisi bukti BERTANDA TANGAN yang sah untuk job ini.

    Sejak C2-B1 kebijakan `verified` hanya menerima bukti bertanda tangan
    (`strict`). Tes C2-A yang dulu memakai event tanpa tanda tangan dimigrasikan
    ke jalur ini supaya tetap menguji perilakunya, bukan celahnya.
    """
    wk = sys.modules["sdb_build_worker"]
    real = Path(jobs.get(jid)["dir"]).resolve()
    ev = _payload_evidence(jid, wk.tree_digest(real)[0], wk.issue_nonce(jid))
    if ubah:
        _gabung_dalam(ev, ubah)
    ev = _tandatangani(ev, kunci["key"])
    jobs.add_event(jid, "verify", json.dumps(ev))
    return ev


def _status(jobs, jid):
    return jobs.get(jid)["status"]


# ---------- A01/A12: dokumen ada bukan bukti ----------
def test_A01_dokumen_ada_tanpa_bukti_verified_tidak_done(w, monkeypatch, kunci):
    wk, jobs = w
    monkeypatch.setenv("SDB_DONE_POLICY", "verified")
    _mode_strict(monkeypatch, kunci)
    jid, job = _buat_job(jobs)
    wk.do_build(job)
    assert _status(jobs, jid) == "paused"
    assert jobs.get(jid)["error"] == "UNVERIFIED"


def test_A12_rc_hermes_nol_dan_klaim_selesai_tetap_tidak_done(w, monkeypatch, kunci):
    wk, jobs = w
    monkeypatch.setenv("SDB_DONE_POLICY", "verified")
    _mode_strict(monkeypatch, kunci)
    monkeypatch.setattr(wk, "run_hermes", lambda *a, **k: ("SELESAI semua beres", "sid", 0))
    jid, job = _buat_job(jobs)
    wk.do_build(job)
    assert _status(jobs, jid) == "paused"
    assert jobs.get(jid)["error"] == "UNVERIFIED"


# ---------- A02: default belum aktif (keputusan Owner #3) ----------
def test_A02_default_attested_tetap_done_dengan_label(w, ):
    wk, jobs = w
    assert wk.done_policy() == "attested"
    jid, job = _buat_job(jobs)
    wk.do_build(job)
    assert _status(jobs, jid) == "done"
    ev = [e for e in jobs.events(jid, 40) if e["kind"] == "completion"]
    assert ev and json.loads(ev[-1]["text"])["level"] == "ATTESTED"
    assert "ATTESTED" in wk.sent[-1]
    assert "TIDAK diverifikasi mesin" in wk.sent[-1]


# ---------- A03/A04: validasi dokumen ----------
def test_A03_verify_md_kosong_ditolak(w, monkeypatch):
    wk, jobs = w
    monkeypatch.setenv("SDB_DONE_POLICY", "attested")
    jid, job = _buat_job(jobs, verify="   \n\t ")
    wk.do_build(job)
    assert _status(jobs, jid) == "paused"
    assert jobs.get(jid)["error"] == "DOCS_INVALID"


def test_A04_verify_md_symlink_ditolak_dan_isi_target_tidak_dibocorkan(w, monkeypatch, tmp_path):
    wk, jobs = w
    monkeypatch.setenv("SDB_DONE_POLICY", "attested")
    rahasia = tmp_path / "rahasia.txt"
    rahasia.write_text("KUNCI-RAHASIA-JANGAN-BOCOR", encoding="utf-8")
    jid = jobs.create_job("Bangun dasbor CRM dengan pipeline dan ekspor CSV")
    d = Path(jobs.get(jid)["dir"])
    (d / "README.md").write_text("isi", encoding="utf-8")
    (d / "VERIFY.md").symlink_to(rahasia)
    assert (d / "VERIFY.md").exists()  # symlink menggantung tidak, jadi exists() True

    wk.do_build(jobs.get(jid))
    assert _status(jobs, jid) == "paused"
    assert jobs.get(jid)["error"] == "DOCS_INVALID"
    assert all("KUNCI-RAHASIA" not in m for m in wk.sent)


def test_A04b_readme_symlink_ditolak(w, monkeypatch, tmp_path):
    wk, jobs = w
    monkeypatch.setenv("SDB_DONE_POLICY", "attested")
    luar = tmp_path / "luar.md"
    luar.write_text("isi luar", encoding="utf-8")
    jid, job = _buat_job(jobs, readme=None)
    d = Path(job["dir"])
    (d / "README.md").symlink_to(luar)
    wk.do_build(jobs.get(jid))
    assert jobs.get(jid)["error"] == "DOCS_INVALID"


# ---------- A05/A06/A07/A18: identitas & workspace ----------
def test_A05_dir_di_luar_builds_ditolak(w, monkeypatch, tmp_path):
    wk, jobs = w
    monkeypatch.setenv("SDB_DONE_POLICY", "attested")
    jid, _job = _buat_job(jobs)
    luar = tmp_path / "luar"
    luar.mkdir()
    (luar / "README.md").write_text("isi", encoding="utf-8")
    (luar / "VERIFY.md").write_text("isi", encoding="utf-8")
    jobs.set_field(jid, dir=str(luar))
    wk.do_build(jobs.get(jid))
    assert _status(jobs, jid) == "paused"
    assert jobs.get(jid)["error"] == "WORKSPACE_INVALID"


def test_A06_dir_symlink_ditolak(w, monkeypatch, tmp_path):
    wk, jobs = w
    monkeypatch.setenv("SDB_DONE_POLICY", "attested")
    jid, job = _buat_job(jobs, docs=False)
    d = Path(job["dir"])
    luar = tmp_path / "target"
    luar.mkdir()
    (luar / "README.md").write_text("isi", encoding="utf-8")
    (luar / "VERIFY.md").write_text("isi", encoding="utf-8")
    d.rmdir()
    d.symlink_to(luar, target_is_directory=True)
    wk.do_build(jobs.get(jid))
    assert jobs.get(jid)["error"] == "WORKSPACE_INVALID"


def test_A07_nama_dir_tanpa_awalan_id_ditolak(w, monkeypatch):
    wk, jobs = w
    monkeypatch.setenv("SDB_DONE_POLICY", "attested")
    jid, job = _buat_job(jobs)
    d = Path(job["dir"])
    baru = d.parent / "999-bukan-job-ini"
    d.rename(baru)
    jobs.set_field(jid, dir=str(baru))
    wk.do_build(jobs.get(jid))
    assert jobs.get(jid)["error"] == "WORKSPACE_INVALID"


def test_A18_dir_dict_tidak_cocok_dengan_db_ditolak(w, monkeypatch):
    wk, jobs = w
    monkeypatch.setenv("SDB_DONE_POLICY", "attested")
    jid, job = _buat_job(jobs)
    lain, job_lain = _buat_job(jobs)
    palsu = dict(job)
    palsu["dir"] = job_lain["dir"]
    wk.do_build(palsu)
    assert _status(jobs, jid) == "paused"
    assert jobs.get(jid)["error"] == "WORKSPACE_INVALID"
    assert _status(jobs, lain) != "done"


# ---------- A08/A09/A10/A16: validasi evidence ----------
def test_A08_bukti_milik_job_lain_ditolak(w, monkeypatch, kunci):
    wk, jobs = w
    monkeypatch.setenv("SDB_DONE_POLICY", "verified")
    _mode_strict(monkeypatch, kunci)
    jid, _job = _buat_job(jobs)
    lain, _ = _buat_job(jobs)
    _event_verify(jobs, jid, kunci, {"job_id": lain})
    wk.do_build(jobs.get(jid))
    assert jobs.get(jid)["error"] == "EVIDENCE_JOB_MISMATCH"


def test_A09_isi_workspace_berubah_setelah_verifikasi_ditolak(w, monkeypatch, kunci):
    wk, jobs = w
    monkeypatch.setenv("SDB_DONE_POLICY", "verified")
    _mode_strict(monkeypatch, kunci)
    jid, job = _buat_job(jobs)
    real = Path(job["dir"]).resolve()
    _event_verify(jobs, jid, kunci)
    (real / "app.py").write_text("print('berubah')\n", encoding="utf-8")
    wk.do_build(jobs.get(jid))
    assert jobs.get(jid)["error"] == "EVIDENCE_DIGEST_MISMATCH"


def test_A10_bukti_verdict_fail_menghasilkan_verify_fail(w, monkeypatch, kunci):
    wk, jobs = w
    monkeypatch.setenv("SDB_DONE_POLICY", "verified")
    _mode_strict(monkeypatch, kunci)
    jid, _job = _buat_job(jobs)
    _event_verify(jobs, jid, kunci,
                  {"verdict": {"execution": "FAIL", "acceptance": "FAIL"}})
    wk.do_build(jobs.get(jid))
    assert jobs.get(jid)["error"] == "VERIFY_FAIL"
    assert _status(jobs, jid) == "paused"


def test_A16_event_verify_json_rusak_tidak_mematikan_worker(w, monkeypatch, kunci):
    wk, jobs = w
    monkeypatch.setenv("SDB_DONE_POLICY", "verified")
    _mode_strict(monkeypatch, kunci)
    jid, _job = _buat_job(jobs)
    jobs.add_event(jid, "verify", "{bukan json")
    wk.do_build(jobs.get(jid))
    assert jobs.get(jid)["error"] == "EVIDENCE_INVALID"
    assert _status(jobs, jid) == "paused"


# ---------- A11: jalur sukses verified ----------
def test_A11_bukti_sah_policy_verified_menjadi_done(w, monkeypatch, kunci):
    wk, jobs = w
    monkeypatch.setenv("SDB_DONE_POLICY", "verified")
    _mode_strict(monkeypatch, kunci)
    jid, _job = _buat_job(jobs)
    _event_verify(jobs, jid, kunci)
    wk.do_build(jobs.get(jid))
    assert _status(jobs, jid) == "done"
    ev = [e for e in jobs.events(jid, 40) if e["kind"] == "completion"]
    assert json.loads(ev[-1]["text"])["level"] == "ACCEPTANCE_VERIFIED"
    assert "ACCEPTANCE_VERIFIED" in wk.sent[-1]


# ---------- A17: kebijakan tak dikenal fail-closed ----------
def test_A17_policy_tak_dikenal_diperlakukan_verified(w, monkeypatch, kunci):
    wk, jobs = w
    monkeypatch.setenv("SDB_DONE_POLICY", "attest")
    _mode_strict(monkeypatch, kunci)
    jid, job = _buat_job(jobs)
    wk.do_build(job)
    assert _status(jobs, jid) == "paused"
    assert jobs.get(jid)["error"] == "UNVERIFIED"


# ---------- A13/A14: kompatibilitas ----------
def test_A13_kompatibilitas_skema_status_dan_jumlah_ronde(w, monkeypatch):
    wk, jobs = w
    monkeypatch.setenv("SDB_DONE_POLICY", "attested")
    with jobs.connect() as con:
        kolom = [r["name"] for r in con.execute("PRAGMA table_info(jobs)")]
        tabel = sorted(r["name"] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"))
    assert kolom == ["id", "slug", "title", "brief", "status", "dir", "model",
                     "session_spec", "session_build", "error", "created", "updated"]
    assert {"jobs", "events"} <= set(tabel)
    assert jobs.OPEN_STATES == ("spec_queued", "spec_running", "spec_ready",
                                "build_queued", "building")

    panggilan = []
    monkeypatch.setattr(wk, "run_hermes",
                        lambda *a, **k: (panggilan.append(1), ("r", "sid", 0))[1])
    jid, _job = _buat_job(jobs, docs=False)
    wk.do_build(jobs.get(jid))
    assert len(panggilan) == wk.ROUNDS + 1        # 3 ronde kerja + 1 ronde dokumentasi
    assert jobs.get(jid)["status"] == "paused"


def test_A13b_job_done_historis_tidak_diproses_ulang(w, monkeypatch):
    wk, jobs = w
    jid, _job = _buat_job(jobs)
    jobs.set_status(jid, "done", "historis")
    dipanggil = []
    monkeypatch.setattr(wk, "run_hermes", lambda *a, **k: (dipanggil.append(1), ("r", "", 0))[1])
    assert wk.once() == 0
    assert dipanggil == []
    assert jobs.get(jid)["status"] == "done"


def test_A14_konstanta_prompt_identik_baseline():
    src = (SCRIPTS / "sdb_build_worker.py").read_text(encoding="utf-8")
    for nama, mau in BASELINE_PROMPT_HASH.items():
        m = re.search(rf'^{nama} = """.*?"""', src, re.S | re.M)
        assert m, f"{nama} hilang"
        assert hashlib.sha256(m.group(0).encode()).hexdigest()[:16] == mau, f"{nama} berubah"


# ---------- A15: kolom error ----------
def test_A15_error_pendek_dan_dibersihkan_saat_done(w, monkeypatch, kunci):
    wk, jobs = w
    monkeypatch.setenv("SDB_DONE_POLICY", "verified")
    _mode_strict(monkeypatch, kunci)
    jid, _job = _buat_job(jobs)
    wk.do_build(jobs.get(jid))
    assert len(jobs.get(jid)["error"] or "") <= 200

    _event_verify(jobs, jid, kunci)
    jobs.set_status(jid, "building", "ulang")
    wk.do_build(jobs.get(jid))
    assert jobs.get(jid)["status"] == "done"
    assert jobs.get(jid)["error"] == ""


# ---------- utilitas digest ----------
def test_digest_berubah_bila_isi_berubah_dan_stabil_bila_tidak(w):
    wk, jobs = w
    _jid, job = _buat_job(jobs)
    d = Path(job["dir"])
    a = wk.tree_digest(d)[0]
    assert a == wk.tree_digest(d)[0]
    assert wk.tree_digest(d)[1] is True
    (d / "catatan.txt").write_text("x", encoding="utf-8")
    assert wk.tree_digest(d)[0] != a


# ---------- A19/A20: bukti rusak & kegagalan tak terduga ----------
def test_A19_job_id_bukan_angka_di_bukti_ditolak(w, monkeypatch, kunci):
    wk, jobs = w
    monkeypatch.setenv("SDB_DONE_POLICY", "verified")
    _mode_strict(monkeypatch, kunci)
    jid, _job = _buat_job(jobs)
    _event_verify(jobs, jid, kunci, {"job_id": "abc"})
    wk.do_build(jobs.get(jid))
    assert jobs.get(jid)["error"] == "EVIDENCE_JOB_MISMATCH"
    assert _status(jobs, jid) == "paused"


def test_A20_kegagalan_tak_terduga_tidak_menggantung_job(w, monkeypatch):
    wk, jobs = w
    monkeypatch.setenv("SDB_DONE_POLICY", "attested")

    def meledak(_d):
        raise OSError("disk bermasalah")

    monkeypatch.setattr(wk, "tree_digest", meledak)
    jid, _job = _buat_job(jobs)
    wk.do_build(jobs.get(jid))          # tidak boleh melempar exception
    assert jobs.get(jid)["error"] == "COMPLETION_ERROR"
    assert _status(jobs, jid) == "paused"


# ---------- A21: hardlink (temuan D8-3 reviewer) ----------
def test_A21_readme_hardlink_ke_berkas_rahasia_ditolak(w, monkeypatch, tmp_path):
    wk, jobs = w
    monkeypatch.setenv("SDB_DONE_POLICY", "attested")
    rahasia = tmp_path / "rahasia.txt"
    rahasia.write_text("KUNCI-RAHASIA-HARDLINK", encoding="utf-8")
    jid, job = _buat_job(jobs, readme=None)
    import os as _os
    _os.link(rahasia, Path(job["dir"]) / "README.md")   # S_ISREG, bukan symlink
    wk.do_build(jobs.get(jid))
    assert jobs.get(jid)["error"] == "DOCS_INVALID"
    assert all("KUNCI-RAHASIA" not in m for m in wk.sent)


# ---------- A22: dokumen stub tidak memutus ronde lebih awal ----------
def test_A22_verify_stub_tidak_memutus_ronde_awal(w, monkeypatch):
    wk, jobs = w
    monkeypatch.setenv("SDB_DONE_POLICY", "attested")
    panggilan = []
    monkeypatch.setattr(wk, "run_hermes",
                        lambda *a, **k: (panggilan.append(1), ("r", "sid", 0))[1])
    jid, _job = _buat_job(jobs, verify="   ")     # berkas ada, isi kosong
    wk.do_build(jobs.get(jid))
    assert len(panggilan) == wk.ROUNDS + 1       # semua ronde tetap dijalankan
    assert _status(jobs, jid) == "paused"


# ---------- A23: sidik sebagian tidak boleh menjadi bukti ----------
def test_A23_sidik_sebagian_menolak_bukti(w, monkeypatch, kunci):
    wk, jobs = w
    monkeypatch.setenv("SDB_DONE_POLICY", "verified")
    _mode_strict(monkeypatch, kunci)
    jid, job = _buat_job(jobs)
    real = Path(job["dir"]).resolve()
    _event_verify(jobs, jid, kunci)
    monkeypatch.setattr(wk, "DIGEST_BYTE_MAX", 0)      # anggaran habis -> partial
    _digest, lengkap = wk.tree_digest(real)
    assert lengkap is False
    wk.do_build(jobs.get(jid))
    assert jobs.get(jid)["error"] == "EVIDENCE_DIGEST_INCOMPLETE"
    assert _status(jobs, jid) == "paused"


# ---------- A24/A25: nilai env & tipe JSON ----------
def test_A24_policy_string_kosong_diperlakukan_verified(w, monkeypatch, kunci):
    wk, jobs = w
    monkeypatch.setenv("SDB_DONE_POLICY", "   ")
    _mode_strict(monkeypatch, kunci)
    assert wk.done_policy() == "verified"
    jid, job = _buat_job(jobs)
    wk.do_build(job)
    assert jobs.get(jid)["error"] == "UNVERIFIED"


def test_A25_schema_boolean_ditolak(w, monkeypatch, kunci):
    wk, jobs = w
    monkeypatch.setenv("SDB_DONE_POLICY", "verified")
    _mode_strict(monkeypatch, kunci)
    jid, _job = _buat_job(jobs)
    _event_verify(jobs, jid, kunci, {"schema": True})   # True == 1 di Python
    wk.do_build(jobs.get(jid))
    # `True` bukan nama skema kontrak, jadi jatuh ke jalur legacy dan ditolak strict.
    assert jobs.get(jid)["error"] == "EVIDENCE_LEGACY_REJECTED"


# ---------- A26: bukti tidak boleh tenggelam oleh tumpukan event ----------
def test_A26_bukti_tetap_terbaca_setelah_banyak_event(w, monkeypatch, kunci):
    wk, jobs = w
    monkeypatch.setenv("SDB_DONE_POLICY", "verified")
    _mode_strict(monkeypatch, kunci)
    jid, _job = _buat_job(jobs)
    _event_verify(jobs, jid, kunci)
    for i in range(60):
        jobs.add_event(jid, "build_output", f"ronde {i} rc=0")
    wk.do_build(jobs.get(jid))
    assert _status(jobs, jid) == "done"
    assert jobs.get(jid)["error"] == ""


# =====================================================================
# C2-B1 — integrasi kontrak evidence bertanda tangan ke worker.
# Kunci di sini SINTETIS (dibuat di tmp), bukan kunci produksi.
# =====================================================================
VERIFIER_UJI = "sdb-verifier-test"
KRITERIA_UJI = "c" * 64


@pytest.fixture(scope="module")
def kunci(tmp_path_factory):
    d = tmp_path_factory.mktemp("c2b1kunci")
    key = d / "key"
    subprocess.run(["ssh-keygen", "-t", "ed25519", "-N", "", "-C", "sdb-uji",
                    "-f", str(key)], check=True, capture_output=True)
    pub = (d / "key.pub").read_text().strip().split()
    allowed = d / "allowed_signers"
    allowed.write_text(f"{VERIFIER_UJI} {pub[0]} {pub[1]}\n", encoding="utf-8")
    os.chmod(allowed, 0o600)
    return {"key": key, "allowed": allowed}


def _payload_evidence(jid: int, digest: str, nonce: str) -> dict:
    sekarang = int(time.time())
    return {
        "schema": "sdb.verify.evidence/1", "digest_alg": "tree-sha256/1",
        "project_id": "super-dev-builders", "job_id": jid, "request_nonce": nonce,
        "snapshot": {"snapshot_id": "sha256:" + "b" * 64, "file_count": 5,
                     "total_bytes": 2048, "complete": True, "created_at": sekarang - 10},
        "workspace_digest": digest,
        "artifact_manifest": [{"path": "README.md", "sha256": "d" * 64, "size": 9}],
        "dependencies": [{"ecosystem": "pip", "name": "pytest", "version": "8.3.3",
                          "source": "lockfile", "lockfile_digest": "e" * 64}],
        "test_command": {"argv": ["pytest", "-q"], "cwd": "/workspace", "allowlisted": True},
        "execution": {"exit_code": 0, "duration_ms": 900, "timed_out": False,
                      "stdout_sha256": "f" * 64, "stderr_sha256": "0" * 64,
                      "tests": {"collected": 5, "passed": 5, "failed": 0,
                                "skipped": 0, "deselected": 0}},
        "sandbox": {"engine": "bwrap", "engine_version": "0.11.1",
                    "profile_id": "sdb-verify-sbx-1", "network": "none",
                    "new_privileges": False, "caps_dropped": True,
                    "writable_paths": ["/workspace", "/tmp", "/run"]},
        "limits": {"cpu_quota": "200%", "memory_max": "2G", "pids_max": 256,
                   "wall_clock_s": 600, "snapshot_max_mb": 2048},
        "timestamps": {"issued_at": sekarang - 10, "started_at": sekarang - 9,
                       "finished_at": sekarang - 5, "expires_at": sekarang + 600},
        "verifier": {"id": VERIFIER_UJI, "host": "vfy-uji",
                     "key_fingerprint": "SHA256:" + "9" * 43},
        "acceptance_criteria": {"id": "cap-BE-03/v1", "criteria_digest": KRITERIA_UJI,
                                "checks": [{"id": "tests-all-pass", "ok": True}]},
        "verdict": {"execution": "PASS", "acceptance": "PASS",
                    "release_eligible": True, "failure_reason": None},
    }


def _tandatangani(ev: dict, key: Path) -> dict:
    import sdb_evidence as evd
    proc = subprocess.run(["ssh-keygen", "-Y", "sign", "-f", str(key), "-n", evd.NAMESPACE],
                          input=evd.signable_bytes(ev), capture_output=True, check=True)
    ev["signature"] = {"alg": "ssh-ed25519", "namespace": evd.NAMESPACE,
                       "signer": ev["verifier"]["id"], "sig": proc.stdout.decode()}
    return ev


def _mode_strict(monkeypatch, kunci):
    monkeypatch.setenv("SDB_EVIDENCE_MODE", "strict")
    monkeypatch.setenv("SDB_EVIDENCE_ALLOWED_SIGNERS", str(kunci["allowed"]))
    monkeypatch.setenv("SDB_EVIDENCE_VERIFIERS", VERIFIER_UJI)
    monkeypatch.setenv("SDB_ACCEPTANCE_CRITERIA_DIGEST", KRITERIA_UJI)


def test_C01_evidence_bertanda_tangan_menjadi_done_dan_mencatat_tingkat(w, monkeypatch, kunci):
    wk, jobs = w
    monkeypatch.setenv("SDB_DONE_POLICY", "verified")
    _mode_strict(monkeypatch, kunci)
    jid, job = _buat_job(jobs)
    real = Path(job["dir"]).resolve()
    nonce = wk.issue_nonce(jid)
    ev = _tandatangani(_payload_evidence(jid, wk.tree_digest(real)[0], nonce), kunci["key"])
    jobs.add_event(jid, "verify", json.dumps(ev))
    wk.do_build(jobs.get(jid))
    assert _status(jobs, jid) == "done"
    kompl = [json.loads(e["text"]) for e in jobs.events(jid, 30)
             if e["kind"] == "completion"]
    assert kompl and kompl[-1]["evidence"]["level"] == "ACCEPTANCE_VERIFIED"
    assert kompl[-1]["evidence"]["release_eligible"] is False


def test_C02_evidence_tanpa_tanda_tangan_tetap_paused(w, monkeypatch, kunci):
    wk, jobs = w
    monkeypatch.setenv("SDB_DONE_POLICY", "verified")
    _mode_strict(monkeypatch, kunci)
    jid, job = _buat_job(jobs)
    real = Path(job["dir"]).resolve()
    nonce = wk.issue_nonce(jid)
    jobs.add_event(jid, "verify", json.dumps(
        _payload_evidence(jid, wk.tree_digest(real)[0], nonce)))
    wk.do_build(jobs.get(jid))
    assert jobs.get(jid)["error"] == "EVIDENCE_NO_SIGNATURE"
    assert _status(jobs, jid) == "paused"


def test_C03_mode_strict_menolak_evidence_legacy(w, monkeypatch, kunci):
    wk, jobs = w
    monkeypatch.setenv("SDB_DONE_POLICY", "verified")
    _mode_strict(monkeypatch, kunci)
    jid, job = _buat_job(jobs)
    real = Path(job["dir"]).resolve()
    _event_legacy(jobs, jid, dir_real=str(real), tree_sha256=wk.tree_digest(real)[0])
    wk.do_build(jobs.get(jid))
    assert jobs.get(jid)["error"] == "EVIDENCE_LEGACY_REJECTED"
    assert _status(jobs, jid) == "paused"


def test_C04_event_sampah_tidak_membakar_nonce_tapi_replay_tetap_ditolak(w, monkeypatch, kunci):
    wk, jobs = w
    monkeypatch.setenv("SDB_DONE_POLICY", "verified")
    _mode_strict(monkeypatch, kunci)
    jid, job = _buat_job(jobs)
    real = Path(job["dir"]).resolve()
    digest = wk.tree_digest(real)[0]
    nonce = wk.issue_nonce(jid)
    # Event sampah tanpa tanda tangan: tidak boleh membakar nonce sah (DoS diri sendiri).
    jobs.add_event(jid, "verify", json.dumps({"request_nonce": nonce, "catatan": "palsu"}))
    ev = _tandatangani(_payload_evidence(jid, digest, nonce), kunci["key"])
    jobs.add_event(jid, "verify", json.dumps(ev))
    wk.do_build(jobs.get(jid))
    assert _status(jobs, jid) == "done", jobs.get(jid)["error"]
    assert jobs.get(jid)["error"] == ""
    # Bukti yang sama dipakai ulang: nonce sudah tercatat diterima -> replay ditolak.
    jobs.set_status(jid, "building", "ulang")
    jobs.add_event(jid, "verify", json.dumps(ev))
    wk.do_build(jobs.get(jid))
    assert jobs.get(jid)["error"] == "EVIDENCE_REPLAY"
    assert _status(jobs, jid) == "paused"


def test_C05_reaper_memulihkan_job_building_yang_menggantung(w):
    wk, jobs = w
    jid, _job = _buat_job(jobs)
    with jobs.connect() as con:
        con.execute("UPDATE jobs SET status='building', updated=? WHERE id=?",
                    (time.time() - 10_000, jid))
    assert wk.reap_stale() == 1
    assert _status(jobs, jid) == "paused"
    assert jobs.get(jid)["error"] == "STALE_RUNNING"


def test_C05b_reaper_tidak_mengganggu_job_yang_masih_baru(w):
    wk, jobs = w
    jid, _job = _buat_job(jobs)
    with jobs.connect() as con:
        con.execute("UPDATE jobs SET status='building', updated=? WHERE id=?",
                    (time.time(), jid))
    assert wk.reap_stale() == 0
    assert _status(jobs, jid) == "building"


def test_C06_batas_entri_sidik_membuat_sidik_tidak_lengkap(w, monkeypatch, kunci):
    wk, jobs = w
    monkeypatch.setenv("SDB_DONE_POLICY", "verified")
    _mode_strict(monkeypatch, kunci)
    jid, job = _buat_job(jobs)
    real = Path(job["dir"]).resolve()
    monkeypatch.setattr(wk, "DIGEST_ENTRY_MAX", 1)
    _sidik, lengkap = wk.tree_digest(real)
    assert lengkap is False
    _event_verify(jobs, jid, kunci)
    wk.do_build(jobs.get(jid))
    assert jobs.get(jid)["error"] == "EVIDENCE_DIGEST_INCOMPLETE"
    assert _status(jobs, jid) == "paused"


def test_C07_issue_nonce_unik_dan_tercatat_sebagai_permintaan(w):
    wk, jobs = w
    jid, _job = _buat_job(jobs)
    a, b = wk.issue_nonce(jid), wk.issue_nonce(jid)
    assert a != b and len(a) == 64 and len(b) == 64
    minta = [json.loads(e["text"]) for e in jobs.events(jid, 20)
             if e["kind"] == "verify_request"]
    assert len(minta) == 2
    assert {m["nonce"] for m in minta} == {a, b}
    assert all(m["schema"] == "sdb.verify.request/1" for m in minta)
    assert all(m["expires_at"] > m["issued_at"] for m in minta)


def test_C08_readme_symlink_ditolak(w):
    wk, jobs = w
    jid, job = _buat_job(jobs, docs=False)
    d = Path(job["dir"])
    luar = d.parent / f"luar-{jid}.md"
    luar.write_text("isi dari luar workspace\n", encoding="utf-8")
    (d / "README.md").symlink_to(luar)
    (d / "VERIFY.md").write_text("verifikasi palsu\n", encoding="utf-8")
    kode, readme, _verify = wk.read_docs(d)
    assert kode == "DOCS_INVALID"
    assert readme == ""


def test_C09_safe_read_at_menolak_nama_berbahaya(w):
    wk, _jobs = w
    dirfd = os.open("/tmp", os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        assert wk._safe_read_at(dirfd, "../etc/passwd", 4096) is None
        assert wk._safe_read_at(dirfd, "/etc/passwd", 4096) is None
        assert wk._safe_read_at(dirfd, "..", 4096) is None
        assert wk._safe_read_at(dirfd, "", 4096) is None
    finally:
        os.close(dirfd)


def test_C10_read_docs_menolak_direktori_symlink(w, tmp_path):
    wk, _jobs = w
    asli = tmp_path / "asli"
    asli.mkdir()
    (asli / "README.md").write_text("a\n", encoding="utf-8")
    (asli / "VERIFY.md").write_text("b\n", encoding="utf-8")
    tautan = tmp_path / "tautan"
    tautan.symlink_to(asli, target_is_directory=True)
    kode, readme, verify = wk.read_docs(tautan)
    assert (kode, readme, verify) == ("DOCS_INVALID", "", "")


# =====================================================================
# C11-C21: temuan review independen D6/D8 siklus 1 (semua tutup di allowlist)
# =====================================================================
def test_C11_verified_tanpa_mode_strict_ditolak(w, monkeypatch):
    """D8-1: `verified` tidak boleh menerima bukti tanpa tanda tangan."""
    wk, jobs = w
    monkeypatch.setenv("SDB_DONE_POLICY", "verified")
    monkeypatch.delenv("SDB_EVIDENCE_MODE", raising=False)
    jid, _job = _buat_job(jobs)
    _event_legacy(jobs, jid)
    wk.do_build(jobs.get(jid))
    assert jobs.get(jid)["error"] == "EVIDENCE_MODE_REQUIRED"
    assert _status(jobs, jid) == "paused"


def test_C12_signer_store_di_direktori_world_writable_ditolak():
    """D8-3(a): parent world-writable (mis. /tmp) membatalkan pin signer."""
    evd = sys.modules["sdb_evidence"]
    d = Path(tempfile.mkdtemp(prefix="sdb-buka-", dir="/tmp"))
    try:
        f = d / "allowed_signers"
        f.write_text(f"{VERIFIER_UJI} ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIx\n",
                     encoding="utf-8")
        ok, kode, _p = evd.load_allowed_signers(f)
        assert ok is False and kode == "EVIDENCE_SIGNER_STORE"
        assert evd.read_store(f)[0] is None
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_C12b_signer_store_group_writable_ditolak(tmp_path):
    """D8-3(b): berkas signer group-writable = anggota grup bisa menambah kunci."""
    evd = sys.modules["sdb_evidence"]
    f = tmp_path / "allowed_signers"
    f.write_text(f"{VERIFIER_UJI} ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIx\n", encoding="utf-8")
    f.chmod(0o620)
    ok, kode, _p = evd.load_allowed_signers(f)
    assert ok is False and kode == "EVIDENCE_SIGNER_STORE"


def test_C13_tanpa_ssh_keygen_verifikasi_gagal_tertutup(monkeypatch):
    """D8-2: verifier harus path absolut milik root, bukan hasil pencarian PATH."""
    evd = sys.modules["sdb_evidence"]
    assert evd._ssh_keygen() is None or evd._ssh_keygen().startswith("/")
    monkeypatch.setattr(evd, "_SSH_KEYGEN_PATHS", ())
    ok, kode = evd.verify_signature(b"x", "-----BEGIN SSH SIGNATURE-----\n",
                                    Path("/nonexistent-allowed-signers"), VERIFIER_UJI)
    assert ok is False and kode == "EVIDENCE_VERIFIER_UNAVAILABLE"


def test_C14_permintaan_nonce_kedaluwarsa_ditolak(w, monkeypatch, kunci):
    """D8-4: jendela nonce harus ditegakkan, bukan sekadar ditulis."""
    wk, jobs = w
    monkeypatch.setenv("SDB_DONE_POLICY", "verified")
    _mode_strict(monkeypatch, kunci)
    jid, job = _buat_job(jobs)
    real = Path(job["dir"]).resolve()
    nonce = wk.issue_nonce(jid)
    ev = _tandatangani(_payload_evidence(jid, wk.tree_digest(real)[0], nonce), kunci["key"])
    kedaluwarsa = json.dumps({"schema": "sdb.verify.request/1", "job_id": jid,
                              "nonce": nonce, "issued_at": int(time.time()) - 100,
                              "expires_at": int(time.time()) - 10})
    with jobs.connect() as con:
        con.execute("UPDATE events SET text=? WHERE job_id=? AND kind='verify_request'",
                    (kedaluwarsa, jid))
    jobs.add_event(jid, "verify", json.dumps(ev))
    wk.do_build(jobs.get(jid))
    assert jobs.get(jid)["error"] == "EVIDENCE_REQUEST_EXPIRED"


def test_C15_evidence_melebihi_masa_permintaan_ditolak(w, monkeypatch, kunci):
    """D8-4: `expires_at` penanda tangan dibatasi jendela permintaan + TTL maksimum."""
    wk, jobs = w
    monkeypatch.setenv("SDB_DONE_POLICY", "verified")
    _mode_strict(monkeypatch, kunci)
    jid, job = _buat_job(jobs)
    real = Path(job["dir"]).resolve()
    nonce = wk.issue_nonce(jid)
    ev = _payload_evidence(jid, wk.tree_digest(real)[0], nonce)
    ev["timestamps"]["expires_at"] = ev["timestamps"]["issued_at"] + 7200
    jobs.add_event(jid, "verify", json.dumps(_tandatangani(ev, kunci["key"])))
    wk.do_build(jobs.get(jid))
    assert jobs.get(jid)["error"] == "EVIDENCE_EXPIRED"
    assert _status(jobs, jid) == "paused"


def test_C16_reaper_cas_tidak_menimpa_status_yang_berubah(w, monkeypatch):
    """D6-1: reaper tidak boleh mem-pause job yang selesai di tengah pengamatan."""
    wk, jobs = w
    jid, _job = _buat_job(jobs)
    with jobs.connect() as con:
        con.execute("UPDATE jobs SET status='building', updated=? WHERE id=?",
                    (time.time() - 10_000, jid))
    asli = wk.jobs.list_jobs

    def daftar_lalu_selesai(*a, **k):
        hasil = asli(*a, **k)
        jobs.set_status(jid, "done", "selesai di tengah reaper")
        return hasil

    monkeypatch.setattr(wk.jobs, "list_jobs", daftar_lalu_selesai)
    assert wk.reap_stale() == 0
    assert _status(jobs, jid) == "done"


def test_C17_heartbeat_memperbarui_updated_tanpa_mengubah_status(w):
    """D6-1(b): build panjang harus terlihat hidup."""
    wk, jobs = w
    jid, _job = _buat_job(jobs)
    jobs.set_status(jid, "building", "jalan")
    with jobs.connect() as con:
        con.execute("UPDATE jobs SET updated=? WHERE id=?", (1.0, jid))
    wk.heartbeat(jid)
    assert float(jobs.get(jid)["updated"]) > 1000
    assert _status(jobs, jid) == "building"


def test_C18_cli_issue_nonce_mencetak_nonce(w, monkeypatch, capsys):
    """D8-6: jalur resmi menerbitkan nonce (tanpa ini `verified` jalan buntu)."""
    wk, jobs = w
    jid, _job = _buat_job(jobs)
    monkeypatch.setattr(sys, "argv", ["sdb_build_worker.py", "--issue-nonce", str(jid)])
    assert wk.main() == 0
    keluaran = capsys.readouterr().out.strip()
    assert len(keluaran) == 64
    assert all(c in "0123456789abcdef" for c in keluaran)


def test_C18b_cli_issue_nonce_job_tidak_ada(w, monkeypatch, capsys):
    wk, _jobs = w
    monkeypatch.setattr(sys, "argv", ["sdb_build_worker.py", "--issue-nonce", "999999"])
    assert wk.main() == 1
    assert "tidak ada" in capsys.readouterr().err


def test_C19_bukti_bertanda_bentuk_salah_ditolak_dengan_kode(w, monkeypatch, kunci):
    """D6-3: tipe salah harus jadi kode penolakan, bukan AttributeError."""
    wk, jobs = w
    monkeypatch.setenv("SDB_DONE_POLICY", "verified")
    _mode_strict(monkeypatch, kunci)
    jid, job = _buat_job(jobs)
    real = Path(job["dir"]).resolve()
    ev = _payload_evidence(jid, wk.tree_digest(real)[0], wk.issue_nonce(jid))
    ev["execution"] = ["bukan", "objek"]
    jobs.add_event(jid, "verify", json.dumps(_tandatangani(ev, kunci["key"])))
    wk.do_build(jobs.get(jid))
    assert jobs.get(jid)["error"] == "EVIDENCE_SCHEMA"
    assert _status(jobs, jid) == "paused"


def test_C20_listing_tidak_menelusuri_direktori_berat(w):
    """D6-2: `node_modules` tidak boleh ikut ditelusuri (batas entri harus murah)."""
    wk, jobs = w
    _jid, job = _buat_job(jobs)
    d = Path(job["dir"])
    berat = d / "node_modules" / "paket"
    berat.mkdir(parents=True)
    (berat / "a.js").write_text("x" * 200, encoding="utf-8")
    teks = wk.listing(d)
    assert "node_modules" not in teks
    assert "README.md" in teks
