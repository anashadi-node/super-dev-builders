"""Tes bot Telegram read-only SDB — tanpa jaringan, tanpa token nyata."""
from __future__ import annotations

import sqlite3

import pytest

from scripts import sdb_tg_bot as bot


@pytest.fixture()
def db(tmp_path, monkeypatch):
    """DB minimal bergaya control plane: tenants, jobs, ledger."""
    p = tmp_path / "control.db"
    c = sqlite3.connect(p)
    c.executescript(
        """
        CREATE TABLE tenants (tenant_id TEXT PRIMARY KEY, plan TEXT, status TEXT);
        CREATE TABLE jobs (job_id TEXT PRIMARY KEY, tenant_id TEXT, status TEXT);
        CREATE TABLE ledger (id INTEGER PRIMARY KEY, tenant_id TEXT, kind TEXT, amount INTEGER);
        """)
    c.execute("INSERT INTO tenants VALUES ('t1','pro','active')")
    c.execute("INSERT INTO jobs VALUES ('j1','t1','succeeded')")
    c.executemany("INSERT INTO ledger (tenant_id,kind,amount) VALUES (?,?,?)",
                  [("t1", "topup", 50000000), ("t1", "charge", -2429), ("t1", "refund", 100)])
    c.commit()
    c.close()
    monkeypatch.setattr(bot, "DB_PATH", p)
    monkeypatch.setattr(bot, "DECK_STATE", tmp_path / "state")
    return p


def test_db_dibuka_read_only(db):
    """Kunci keamanan: koneksi bot menolak tulisan secara fisik."""
    conn = bot._db_ro()
    assert conn is not None
    with pytest.raises(sqlite3.OperationalError):
        conn.execute("INSERT INTO ledger (tenant_id,kind,amount) VALUES ('t1','evil',1)")
    conn.close()


def test_db_tidak_ada_mengembalikan_none(tmp_path, monkeypatch):
    monkeypatch.setattr(bot, "DB_PATH", tmp_path / "tidak-ada.db")
    assert bot._db_ro() is None


def test_status_menghitung_tenant_dan_job(db):
    teks = bot.cmd_status()
    assert "1 tenant, 1 job" in teks
    # control plane boleh mati: status tidak boleh melempar galat
    assert "control plane" in teks


def test_revenue_agregat_per_kind(db):
    teks = bot.cmd_revenue()
    assert "topup" in teks and "50,000,000" in teks
    assert "charge" in teks and "-2,429" in teks


def test_revenue_tanpa_db(tmp_path, monkeypatch):
    monkeypatch.setattr(bot, "DB_PATH", tmp_path / "kosong.db")
    assert "tidak ditemukan" in bot.cmd_revenue()


def test_hanya_pemilik_yang_dilayani(monkeypatch):
    """Chat lain diabaikan diam-diam: tidak ada balasan sama sekali."""
    terkirim = []
    monkeypatch.setattr(bot, "OWNER", "111")
    monkeypatch.setattr(bot, "_post_api", lambda m, p: terkirim.append((m, p)) or {"ok": True})
    bot.process_update({"message": {"chat": {"id": 999}, "text": "/status"}})
    assert terkirim == []
    bot.process_update({"message": {"chat": {"id": 111}, "text": "/help"}})
    assert len(terkirim) == 1 and "SDB Bot" in terkirim[0][1]["text"]


def test_perintah_tak_dikenal_tidak_mengeksekusi_apa_pun(monkeypatch):
    terkirim = []
    monkeypatch.setattr(bot, "OWNER", "111")
    monkeypatch.setattr(bot, "_post_api", lambda m, p: terkirim.append(p) or {"ok": True})
    bot.process_update({"message": {"chat": {"id": 111}, "text": "/topup 1000000"}})
    assert len(terkirim) == 1
    assert "read-only" in terkirim[0]["text"].lower()
