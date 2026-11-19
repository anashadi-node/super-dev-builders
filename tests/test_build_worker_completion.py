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
import re
import sys
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


def _event_verify(jobs, jid, **isi):
    """Tulis event verify sintetis; default = PASS yang sah untuk job ini."""
    badan = {"schema": 1, "job_id": jid, "dir_real": "", "tree_sha256": "", "verdict": "PASS"}
    badan.update(isi)
    jobs.add_event(jid, "verify", json.dumps(badan))
    return badan


def _status(jobs, jid):
    return jobs.get(jid)["status"]


# ---------- A01/A12: dokumen ada bukan bukti ----------
def test_A01_dokumen_ada_tanpa_bukti_verified_tidak_done(w, monkeypatch):
    wk, jobs = w
    monkeypatch.setenv("SDB_DONE_POLICY", "verified")
    jid, job = _buat_job(jobs)
    wk.do_build(job)
    assert _status(jobs, jid) == "paused"
    assert jobs.get(jid)["error"] == "UNVERIFIED"


def test_A12_rc_hermes_nol_dan_klaim_selesai_tetap_tidak_done(w, monkeypatch):
    wk, jobs = w
    monkeypatch.setenv("SDB_DONE_POLICY", "verified")
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
def test_A08_bukti_milik_job_lain_ditolak(w, monkeypatch):
    wk, jobs = w
    monkeypatch.setenv("SDB_DONE_POLICY", "verified")
    jid, job = _buat_job(jobs)
    lain, _ = _buat_job(jobs)
    real = Path(job["dir"]).resolve()
    _event_verify(jobs, jid, job_id=lain, dir_real=str(real),
                  tree_sha256=wk.tree_digest(real)[0])
    wk.do_build(jobs.get(jid))
    assert jobs.get(jid)["error"] == "EVIDENCE_INVALID"


def test_A09_isi_workspace_berubah_setelah_verifikasi_ditolak(w, monkeypatch):
    wk, jobs = w
    monkeypatch.setenv("SDB_DONE_POLICY", "verified")
    jid, job = _buat_job(jobs)
    real = Path(job["dir"]).resolve()
    _event_verify(jobs, jid, dir_real=str(real), tree_sha256=wk.tree_digest(real)[0])
    (real / "app.py").write_text("print('berubah')\n", encoding="utf-8")
    wk.do_build(jobs.get(jid))
    assert jobs.get(jid)["error"] == "EVIDENCE_INVALID"


def test_A10_bukti_verdict_fail_menghasilkan_verify_fail(w, monkeypatch):
    wk, jobs = w
    monkeypatch.setenv("SDB_DONE_POLICY", "verified")
    jid, job = _buat_job(jobs)
    real = Path(job["dir"]).resolve()
    _event_verify(jobs, jid, dir_real=str(real), tree_sha256=wk.tree_digest(real)[0],
                  verdict="FAIL")
    wk.do_build(jobs.get(jid))
    assert jobs.get(jid)["error"] == "VERIFY_FAIL"
    assert _status(jobs, jid) == "paused"


def test_A16_event_verify_json_rusak_tidak_mematikan_worker(w, monkeypatch):
    wk, jobs = w
    monkeypatch.setenv("SDB_DONE_POLICY", "verified")
    jid, _job = _buat_job(jobs)
    jobs.add_event(jid, "verify", "{bukan json")
    wk.do_build(jobs.get(jid))
    assert jobs.get(jid)["error"] == "EVIDENCE_INVALID"
    assert _status(jobs, jid) == "paused"


# ---------- A11: jalur sukses verified ----------
def test_A11_bukti_sah_policy_verified_menjadi_done(w, monkeypatch):
    wk, jobs = w
    monkeypatch.setenv("SDB_DONE_POLICY", "verified")
    jid, job = _buat_job(jobs)
    real = Path(job["dir"]).resolve()
    _event_verify(jobs, jid, dir_real=str(real), tree_sha256=wk.tree_digest(real)[0])
    wk.do_build(jobs.get(jid))
    assert _status(jobs, jid) == "done"
    ev = [e for e in jobs.events(jid, 40) if e["kind"] == "completion"]
    assert json.loads(ev[-1]["text"])["level"] == "VERIFIED"
    assert "VERIFIED" in wk.sent[-1]


# ---------- A17: kebijakan tak dikenal fail-closed ----------
def test_A17_policy_tak_dikenal_diperlakukan_verified(w, monkeypatch):
    wk, jobs = w
    monkeypatch.setenv("SDB_DONE_POLICY", "attest")
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
def test_A15_error_pendek_dan_dibersihkan_saat_done(w, monkeypatch):
    wk, jobs = w
    monkeypatch.setenv("SDB_DONE_POLICY", "verified")
    jid, job = _buat_job(jobs)
    wk.do_build(jobs.get(jid))
    assert len(jobs.get(jid)["error"] or "") <= 200

    real = Path(job["dir"]).resolve()
    _event_verify(jobs, jid, dir_real=str(real), tree_sha256=wk.tree_digest(real)[0])
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
def test_A19_job_id_bukan_angka_di_bukti_ditolak(w, monkeypatch):
    wk, jobs = w
    monkeypatch.setenv("SDB_DONE_POLICY", "verified")
    jid, job = _buat_job(jobs)
    real = Path(job["dir"]).resolve()
    _event_verify(jobs, jid, job_id="abc", dir_real=str(real),
                  tree_sha256=wk.tree_digest(real)[0])
    wk.do_build(jobs.get(jid))
    assert jobs.get(jid)["error"] == "EVIDENCE_INVALID"
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
def test_A23_sidik_sebagian_menolak_bukti(w, monkeypatch):
    wk, jobs = w
    monkeypatch.setenv("SDB_DONE_POLICY", "verified")
    jid, job = _buat_job(jobs)
    real = Path(job["dir"]).resolve()
    _event_verify(jobs, jid, dir_real=str(real), tree_sha256=wk.tree_digest(real)[0])
    monkeypatch.setattr(wk, "DIGEST_BYTE_MAX", 0)      # anggaran habis -> partial
    _digest, lengkap = wk.tree_digest(real)
    assert lengkap is False
    wk.do_build(jobs.get(jid))
    assert jobs.get(jid)["error"] == "EVIDENCE_INVALID"
    assert _status(jobs, jid) == "paused"


# ---------- A24/A25: nilai env & tipe JSON ----------
def test_A24_policy_string_kosong_diperlakukan_verified(w, monkeypatch):
    wk, jobs = w
    monkeypatch.setenv("SDB_DONE_POLICY", "   ")
    assert wk.done_policy() == "verified"
    jid, job = _buat_job(jobs)
    wk.do_build(job)
    assert jobs.get(jid)["error"] == "UNVERIFIED"


def test_A25_schema_boolean_ditolak(w, monkeypatch):
    wk, jobs = w
    monkeypatch.setenv("SDB_DONE_POLICY", "verified")
    jid, job = _buat_job(jobs)
    real = Path(job["dir"]).resolve()
    _event_verify(jobs, jid, dir_real=str(real), tree_sha256=wk.tree_digest(real)[0],
                  schema=True)          # True == 1 di Python, harus tetap ditolak
    wk.do_build(jobs.get(jid))
    assert jobs.get(jid)["error"] == "EVIDENCE_INVALID"


# ---------- A26: bukti tidak boleh tenggelam oleh tumpukan event ----------
def test_A26_bukti_tetap_terbaca_setelah_banyak_event(w, monkeypatch):
    wk, jobs = w
    monkeypatch.setenv("SDB_DONE_POLICY", "verified")
    jid, job = _buat_job(jobs)
    real = Path(job["dir"]).resolve()
    _event_verify(jobs, jid, dir_real=str(real), tree_sha256=wk.tree_digest(real)[0])
    for i in range(60):
        jobs.add_event(jid, "build_output", f"ronde {i} rc=0")
    wk.do_build(jobs.get(jid))
    assert _status(jobs, jid) == "done"
    assert jobs.get(jid)["error"] == ""
