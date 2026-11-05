"""Regresi untuk temuan kinerja & ketahanan control plane (audit 2026-11-05).

Angka acuan sebelum perbaikan (diukur di mesin audit, 50.000 job antre):
  - claim_next_job : 92,28 ms  (kueri mengurutkan seluruh antrean tiap klaim)
  - create_job     : 21,59 ms  (fsync per commit, journal_mode=delete)
  - /healthz keep-alive : 40,28 ms (Nagle + delayed ACK), healthz ikut menunggu api.lock
  - 16 koneksi paralel  : 296 req/s (backlog listen = 5)
Sesudah: claim 0,06 ms; create 9,72 ms; healthz 0,20 ms; 16 paralel 4.538 req/s.

Uji di sini menjaga MEKANISME, bukan angka detik (angka bisa berubah karena mesin CI):
indeks dipakai, WAL aktif, TCP_NODELAY menyala, backlog cukup, healthz tidak menunggu lock.
"""
from __future__ import annotations

import http.client
import os
import sys
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from sdb_platform.control_plane.app import serve
from sdb_platform.control_plane.store import Store


def _seed(store: Store, n: int, tenant_id: str) -> None:
    rows = [(f"j{i:07d}", tenant_id, "build", "sdb-recon", "1.0.0", "git://x", 1000, 60,
             f"i{i}", "queued", "2026-11-01T00:00:00Z") for i in range(n)]
    store.db.execute("BEGIN IMMEDIATE")
    store.db.executemany(
        "INSERT INTO jobs (job_id,tenant_id,type,pack_id,pack_version,target_ref,budget_tokens,"
        "budget_seconds,idempotency_key,status,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows)
    store.db.commit()


def test_wal_aktif_untuk_db_berkas(tmp_path):
    store = Store(str(tmp_path / "cp.db"))
    assert store.db.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"


def test_klaim_memakai_indeks_antrean(tmp_path):
    store = Store(str(tmp_path / "cp.db"))
    plan = " ".join(r[3] for r in store.db.execute(
        "EXPLAIN QUERY PLAN SELECT job_id FROM jobs WHERE tenant_id = ? AND status = 'queued'"
        " AND cancel_requested = 0 ORDER BY created_at, rowid LIMIT 1", ("t",)))
    assert "idx_jobs_claim" in plan, f"klaim tidak memakai indeks parsial: {plan}"


def test_klaim_tidak_melonjak_dengan_panjang_antrean(tmp_path):
    """Rasio 10x antrean tidak boleh membuat klaim >5x lebih lambat (batas longgar untuk CI)."""
    def median_claim(n: int) -> float:
        store = Store(str(tmp_path / f"q{n}.db"))
        tenant = store.create_tenant(plan="enterprise", name="b")["tenant_id"]
        store.billing.grant_trial(tenant, 10 ** 12)
        _seed(store, n, tenant)
        for _ in range(3):
            store.claim_next_job("warm")
        samples = []
        for _ in range(15):
            t0 = time.perf_counter()
            store.claim_next_job("bench")
            samples.append(time.perf_counter() - t0)
        samples.sort()
        return samples[len(samples) // 2]

    small, big = median_claim(2_000), median_claim(20_000)
    assert big < max(small * 5, 0.02), f"klaim tumbuh bersama antrean: {small*1000:.2f} ms -> {big*1000:.2f} ms"


def test_server_menyalakan_nodelay_dan_backlog():
    store = Store(":memory:")
    httpd = serve(store, "x" * 32, "127.0.0.1", 0)
    try:
        assert httpd.RequestHandlerClass.disable_nagle_algorithm is True
        assert httpd.request_queue_size >= 128, "backlog listen terlalu kecil (default 5)"
        assert httpd.daemon_threads is True
    finally:
        httpd.server_close()


def test_healthz_tetap_menjawab_saat_lock_ditahan():
    """Health check tidak boleh ikut macet ketika ada penulisan panjang di control plane."""
    store = Store(":memory:")
    httpd = serve(store, "x" * 32, "127.0.0.1", 0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        lock = httpd.api.lock
        lock.acquire()
        try:
            conn = http.client.HTTPConnection("127.0.0.1", httpd.server_address[1], timeout=2)
            conn.request("GET", "/healthz")
            resp = conn.getresponse()
            assert resp.status == 200
            assert b"ok" in resp.read()
            conn.close()
        finally:
            lock.release()
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_create_job_tetap_menulis_dan_idempoten(tmp_path):
    store = Store(str(tmp_path / "cp.db"))
    tenant = store.create_tenant(plan="team", name="b")["tenant_id"]
    job, replayed_first = store.create_job(
        tenant, "recon", {"id": "sdb-recon", "version": "1.0.0"}, "git://x",
        {"tokens": 1000, "seconds": 60}, "kunci-unik-0001")
    again, replayed_second = store.create_job(
        tenant, "recon", {"id": "sdb-recon", "version": "1.0.0"}, "git://x",
        {"tokens": 1000, "seconds": 60}, "kunci-unik-0001")
    assert replayed_first is False and replayed_second is True, "kunci sama harus diputar ulang, bukan job baru"
    assert job["job_id"] == again["job_id"]
