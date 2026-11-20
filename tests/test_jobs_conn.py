"""CR-SDB-DB-01 — penutupan koneksi SQLite deterministik di `sdb_jobs`.

Latar: `with connect() as con:` hanya mengurus transaksi (commit/rollback).
Modul `sqlite3` TIDAK menutup koneksi pada `__exit__`, sehingga fd dan handle
WAL bergantung pada refcount/GC. Probe pra-perbaikan: 200x `get()` menahan 403
fd `jobs.db` sampai `gc.collect()` dipanggil.

Yang diuji:
  * setiap jalur publik menutup koneksi yang dibukanya (tanpa bantuan GC),
  * transaksi tetap commit pada sukses dan rollback pada galat,
  * `claim()` tetap atomik (BEGIN IMMEDIATE) dan tetap menutup koneksi,
  * tidak ada fd `jobs.db` yang menumpuk pada pemakaian berulang.

Semua fixture sintetis di `tmp_path`; tidak menyentuh DB produksi.
"""
from __future__ import annotations

import gc
import importlib
import os
import sqlite3
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))


@pytest.fixture()
def jobs(tmp_path, monkeypatch):
    monkeypatch.setenv("SDB_BUILD_DB", str(tmp_path / "jobs.db"))
    monkeypatch.setenv("SDB_BUILDS", str(tmp_path / "builds"))
    (tmp_path / "builds").mkdir()
    sys.modules.pop("sdb_jobs", None)
    return importlib.import_module("sdb_jobs")


class _ConWrapped:
    """Proxy koneksi: menghitung `close()` tanpa mengubah perilaku sqlite3."""

    def __init__(self, con, spy):
        object.__setattr__(self, "_con", con)
        object.__setattr__(self, "_spy", spy)

    def __getattr__(self, nama):
        return getattr(object.__getattribute__(self, "_con"), nama)

    def __setattr__(self, nama, nilai):
        setattr(object.__getattribute__(self, "_con"), nama, nilai)

    def close(self) -> None:
        object.__getattribute__(self, "_spy").ditutup += 1
        object.__getattribute__(self, "_con").close()


class _Spy:
    """Bungkus `sqlite3.connect` dan hitung koneksi yang dibuka/ditutup."""

    def __init__(self, asli):
        self.asli = asli
        self.dibuka = 0
        self.ditutup = 0

    def __call__(self, *a, **k):
        con = self.asli(*a, **k)
        self.dibuka += 1
        return _ConWrapped(con, self)


def _spy(monkeypatch, jobs) -> _Spy:
    spy = _Spy(jobs.sqlite3.connect)
    monkeypatch.setattr(jobs.sqlite3, "connect", spy)
    return spy


def test_setiap_jalur_publik_menutup_koneksi(jobs, monkeypatch):
    spy = _spy(monkeypatch, jobs)
    jid = jobs.create_job("uji penutupan koneksi\n")
    jobs.get(jid)
    jobs.list_jobs(5)
    jobs.list_jobs(5, only_open=True)
    jobs.set_status(jid, "spec_running", "catatan")
    jobs.set_field(jid, title="judul baru")
    jobs.add_event(jid, "uji", "teks")
    jobs.events(jid)
    jobs.claim("spec_running", "spec_running")  # tidak ada job cocok -> None
    jobs.stats()
    assert spy.dibuka > 0
    assert spy.ditutup == spy.dibuka, (spy.dibuka, spy.ditutup)


def test_tidak_bergantung_pada_gc(jobs, monkeypatch):
    """Dengan GC dimatikan, fd `jobs.db` tidak boleh menumpuk."""
    if not os.path.isdir("/proc/self/fd"):  # pragma: no cover - non-Linux
        pytest.skip("/proc tidak tersedia")
    jid = jobs.create_job("uji fd\n")

    def fd_db() -> int:
        n = 0
        for nama in os.listdir("/proc/self/fd"):
            try:
                target = os.readlink(f"/proc/self/fd/{nama}")
            except OSError:
                continue
            if target.endswith("jobs.db"):
                n += 1
        return n

    gc.collect()
    gc.disable()
    try:
        awal = fd_db()
        for _ in range(100):
            jobs.get(jid)
        akhir = fd_db()
    finally:
        gc.enable()
    assert akhir <= awal, (awal, akhir)


def test_commit_pada_sukses(jobs):
    jid = jobs.create_job("commit\n")
    jobs.set_status(jid, "spec_running", "jalan")
    assert jobs.get(jid)["status"] == "spec_running"
    # Baca ulang lewat koneksi baru: data benar-benar tersimpan.
    with sqlite3.connect(jobs.DB) as con:
        assert con.execute("SELECT status FROM jobs WHERE id=?", (jid,)).fetchone()[0] == "spec_running"


def test_rollback_pada_galat(jobs, monkeypatch):
    jid = jobs.create_job("rollback\n")
    asli = jobs.conn

    def rusak():
        with asli() as con:
            con.execute("UPDATE jobs SET status='dirusak' WHERE id=?", (jid,))
            raise RuntimeError("gagal di tengah transaksi")

    with pytest.raises(RuntimeError):
        rusak()
    assert jobs.get(jid)["status"] == "spec_queued"


def test_claim_tetap_atomik_dan_menutup(jobs, monkeypatch):
    jid = jobs.create_job("claim\n")
    spy = _spy(monkeypatch, jobs)
    row = jobs.claim("spec_queued", "building")
    assert row is not None and row["id"] == jid
    assert jobs.get(jid)["status"] == "building"
    assert jobs.claim("spec_queued", "building") is None
    assert spy.ditutup == spy.dibuka


def test_galat_setup_koneksi_tidak_bocor(jobs, monkeypatch):
    """R1 review: kegagalan PRAGMA/executescript saat membuka koneksi tidak boleh
    meninggalkan fd — `conn()` belum memegang koneksi pada titik itu."""
    spy = _spy(monkeypatch, jobs)
    monkeypatch.setattr(jobs, "SCHEMA", "BUKAN SQL YANG SAH;")
    with pytest.raises(sqlite3.Error):
        jobs.stats()
    assert spy.dibuka == 1, spy.dibuka
    assert spy.ditutup == spy.dibuka, (spy.dibuka, spy.ditutup)


def test_galat_sqlite_tidak_meninggalkan_koneksi(jobs, monkeypatch):
    jid = jobs.create_job("galat sqlite\n")
    spy = _spy(monkeypatch, jobs)
    with pytest.raises(sqlite3.IntegrityError):
        jobs.set_status(jid, None)  # kolom status NOT NULL
    assert spy.ditutup == spy.dibuka
    assert jobs.get(jid)["status"] == "spec_queued"
