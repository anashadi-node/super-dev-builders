"""Tes lapisan Telegram SDB: jobs queue, report, routing perintah, isolasi sandbox.

Fokus: hal-hal yang kalau salah bisa merusak/membocorkan —
  * pemilik-saja (pesan dari chat lain diabaikan),
  * status job hanya pindah lewat transisi sah (approve/reject/retry),
  * direktori job selalu di dalam SDB_BUILDS,
  * report tidak pernah memuat nilai token.
"""
from __future__ import annotations

import importlib
import os
import sqlite3
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))


@pytest.fixture()
def env(tmp_path, monkeypatch):
    """Lingkungan terisolasi: DB, builds, deck-state semua di tmp_path."""
    monkeypatch.setenv("SDB_BUILD_DB", str(tmp_path / "jobs.db"))
    monkeypatch.setenv("SDB_BUILDS", str(tmp_path / "builds"))
    monkeypatch.setenv("SDB_DECK_STATE", str(tmp_path / "state"))
    monkeypatch.setenv("SDB_DB_PATH", str(tmp_path / "control.db"))
    monkeypatch.setenv("SDB_REPO", str(tmp_path / "repo"))
    monkeypatch.setenv("SDB_TG_BOT_TOKEN", "123:SECRET-TOKEN")
    monkeypatch.setenv("SDB_TG_CHAT_ID", "777")
    (tmp_path / "repo" / "targets" / "demo").mkdir(parents=True)
    (tmp_path / "repo" / "targets" / "demo" / "main.py").write_text("print(1)\n")
    for mod in ("sdb_jobs", "sdb_report", "sdb_tg_bot"):
        sys.modules.pop(mod, None)
    jobs = importlib.import_module("sdb_jobs")
    report = importlib.import_module("sdb_report")
    bot = importlib.import_module("sdb_tg_bot")
    return jobs, report, bot


# ---------- antrean job ----------
def test_create_job_di_dalam_builds(env):
    jobs, _, _ = env
    jid = jobs.create_job("Website katalog villa dengan filter harga dan booking WA")
    job = jobs.get(jid)
    assert job["status"] == "spec_queued"
    builds = Path(os.environ["SDB_BUILDS"]).resolve()
    assert builds in Path(job["dir"]).resolve().parents
    assert Path(job["dir"]).is_dir()


def test_brief_pendek_tidak_membuat_job(env):
    _, _, bot = env
    out = bot.cmd_build("bikin web")
    assert "terlalu pendek" in out.lower()
    assert not bot.jobs.list_jobs(5)


def test_approve_hanya_dari_spec_ready(env):
    jobs, _, bot = env
    jid = jobs.create_job("Aplikasi kasir warung: produk, transaksi, struk, laporan harian")
    assert "belum bisa" in bot.cmd_approve(jid)
    jobs.set_status(jid, "spec_ready")
    assert "disetujui" in bot.cmd_approve(jid)
    assert jobs.get(jid)["status"] == "build_queued"


def test_reject_dan_retry(env):
    jobs, _, bot = env
    jid = jobs.create_job("Landing page jasa les privat dengan form pendaftaran")
    jobs.set_status(jid, "spec_ready")
    bot.cmd_reject(jid, "budget belum ada")
    assert jobs.get(jid)["status"] == "rejected"
    bot.cmd_retry(jid)
    assert jobs.get(jid)["status"] == "spec_queued"


def test_revisi_menulis_arahan_dan_mengulang_spec(env):
    jobs, _, bot = env
    jid = jobs.create_job("Website portofolio fotografer dengan galeri dan kontak")
    jobs.set_status(jid, "spec_ready")
    bot.cmd_revise(jid, "tambah halaman harga paket")
    assert jobs.get(jid)["status"] == "spec_queued"
    assert "tambah halaman harga paket" in (Path(jobs.get(jid)["dir"]) / "ANSWERS.md").read_text()


def test_claim_atomik_tidak_double(env):
    jobs, _, _ = env
    jobs.create_job("Dashboard monitoring server dengan grafik CPU dan disk")
    first = jobs.claim("spec_queued", "spec_running")
    second = jobs.claim("spec_queued", "spec_running")
    assert first is not None and second is None
    assert first["status"] == "spec_queued"  # record asli sebelum diubah


def test_retry_menerima_status_paused(env):
    jobs, _, bot = env
    jid = jobs.create_job("Portal berita dengan kategori, pencarian, dan editor artikel")
    jobs.set_status(jid, "paused", "belum tuntas")
    assert "diantrekan ulang" in bot.cmd_retry(jid)
    assert jobs.get(jid)["status"] in ("spec_queued", "build_queued")


def test_cancel_tidak_menimpa_status_akhir(env):
    jobs, _, bot = env
    jid = jobs.create_job("Blog statis dengan penulis, tag, dan pencarian")
    jobs.set_status(jid, "done")
    assert "sudah done" in bot.cmd_cancel(jid)


# ---------- routing & keamanan ----------
def test_pesan_bukan_pemilik_diabaikan(env, monkeypatch):
    _, _, bot = env
    sent = []
    monkeypatch.setattr(bot, "_post_api", lambda m, p: sent.append(p) or {})
    bot.process_update({"update_id": 1, "message": {"chat": {"id": 999}, "text": "/status"}})
    assert sent == []


def test_pemilik_mendapat_balasan(env, monkeypatch):
    _, _, bot = env
    sent = []
    monkeypatch.setattr(bot, "_post_api", lambda m, p: sent.append(p) or {})
    bot.process_update({"update_id": 2, "message": {"chat": {"id": 777}, "text": "/help"}})
    assert sent and "/build" in sent[0]["text"]


def test_perintah_rusak_tidak_mematikan_poller(env, monkeypatch):
    _, _, bot = env
    sent = []
    monkeypatch.setattr(bot, "_post_api", lambda m, p: sent.append(p) or {})

    def boom(_):
        raise RuntimeError("simulasi")

    monkeypatch.setattr(bot, "handle", boom)
    bot.process_update({"update_id": 3, "message": {"chat": {"id": 777}, "text": "/eco"}})
    assert "Perintah gagal" in sent[0]["text"]


# ---------- report ----------
def test_report_memuat_proyek_dan_tidak_membocorkan_token(env):
    _, report, _ = env
    text = report.report("full")
    assert "demo" in text and "EKOSISTEM" in text
    assert "SECRET-TOKEN" not in text


def test_report_json_valid(env):
    _, report, _ = env
    data = report.collect()
    assert {"proyek", "layanan", "timer", "alert"} <= set(data)
    assert isinstance(data["proyek"], list)


def test_chunk_tidak_memecah_baris(env):
    _, report, _ = env
    text = "\n".join(f"baris {i} " + "x" * 100 for i in range(200))
    pieces = report.chunk(text)
    assert all(len(p) <= report.TG_LIMIT for p in pieces)
    assert "".join(pieces) == text


def test_build_queue_terbaca_readonly(env):
    _, report, _ = env
    db = Path(os.environ["SDB_BUILD_DB"])
    con = sqlite3.connect(db)
    con.executescript(
        "CREATE TABLE jobs(id INTEGER PRIMARY KEY, status TEXT);"
        "INSERT INTO jobs(status) VALUES('queued'),('done'),('failed');")
    con.commit()
    con.close()
    got = report.build_queue()
    assert got["ada"] and got["status"] == {"queued": 1, "done": 1, "failed": 1}
