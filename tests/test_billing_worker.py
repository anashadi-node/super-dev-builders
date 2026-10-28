"""Uji billing (uang) dan worker (lease) — fokus pada hal yang TIDAK boleh salah.

Yang diuji bukan "fungsi mengembalikan nilai", tetapi invarian:
- kredit tidak pernah negatif, dan saldo selalu = jumlah seluruh entri ledger
- pesanan kredit (hold) dilepas tepat sekali: job sukses -> charge, gagal/batal -> release
- tagih ganda tidak mungkin (job_charges unik per job)
- dua worker tidak bisa mengklaim job yang sama
- worker mati -> lease kedaluwarsa -> job kembali ke antrean, bukan hilang
- invoice = snapshot abadi ber-hash; mengubah baris lama merusak rantai
"""
from __future__ import annotations

import datetime as dt
import os
import sys
import threading

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from sdb_platform.control_plane.app import Api, serve
from sdb_platform.control_plane.billing import (
    PLAN_PRICE_PER_MTOK,
    TRIAL_CREDIT,
    BillingError,
    price_tokens,
)
from sdb_platform.control_plane.store import ControlPlaneError, Store
from sdb_platform.runtime.worker import ExecutionResult, Worker, echo_executor, failing_executor

ADMIN = "admin-" + "y" * 40
WKEY = "worker-" + "z" * 40


@pytest.fixture()
def store():
    return Store(":memory:")


def _tenant(store, plan="pro", limits=None, name=None):
    t = store.create_tenant(plan=plan, limits=limits, name=name)
    return t, store.add_api_key(t["tenant_id"])


def _job(store, tenant, key="kunci-0001", tokens=5000, seconds=600, type_="recon"):
    job, _ = store.create_job(tenant["tenant_id"], type_, {"id": "sdb-recon", "version": "1.0.0"},
                              "artifact://a/1", {"tokens": tokens, "seconds": seconds}, key)
    return job


# ------------------------------------------------------------------ harga
def test_harga_token_bulat_dan_ceil():
    assert price_tokens(1_000_000, "starter") == 2_000_000
    assert price_tokens(1_000_000, "pro") == 1_600_000
    assert price_tokens(3, "pro") == 5          # 4,8 μUSD -> 5 (tidak ada token gratis)
    assert price_tokens(0, "pro") == 0
    assert price_tokens(5000, "pro") == 8_000   # 5000 * 1,6 = 8000


def test_plan_tak_dikenal_ditolak():
    with pytest.raises(BillingError):
        price_tokens(10, "gratis")


def test_kredit_uji_sesuai_plan(store):
    for plan, expected in TRIAL_CREDIT.items():
        t = store.create_tenant(plan=plan)
        assert store.billing.balance(t["tenant_id"])["credit_microusd"] == expected


def test_topup_dan_validasi(store):
    t, _ = _tenant(store, "starter")
    before = store.billing.balance(t["tenant_id"])["credit_microusd"]
    store.billing.topup(t["tenant_id"], 10_000_000, "topup uji")
    assert store.billing.balance(t["tenant_id"])["credit_microusd"] == before + 10_000_000
    for bad in (0, -5, 1_000_001 * 1_000_000):
        with pytest.raises(BillingError):
            store.billing.topup(t["tenant_id"], bad)


# ------------------------------------------------------------------ hold/settle
def test_job_memesankan_kredit(store):
    t, _ = _tenant(store, "pro")
    start = store.billing.balance(t["tenant_id"])["credit_microusd"]
    _job(store, t, tokens=5000)
    b = store.billing.balance(t["tenant_id"])
    assert b["held_microusd"] == 8_000
    assert b["credit_microusd"] == start - 8_000


def test_kredit_habis_job_ditolak_dan_tidak_tercipta(store):
    t, _ = _tenant(store, "starter", limits={"jobs_per_month": 50, "tokens_per_month": 10_000_000,
                                             "storage_gb": 1})
    # habiskan kredit uji ($5 -> 5.000.000 μUSD) dengan hold besar
    _job(store, t, key="kunci-besar", tokens=2_000_000)
    with pytest.raises(BillingError) as exc:
        _job(store, t, key="kunci-kedua", tokens=2_000_000)
    assert exc.value.status == 402 and exc.value.code == "insufficient_credit"
    assert store.usage(t["tenant_id"])["jobs_used"] == 1  # rollback: job gagal tidak tercatat


def test_sukses_menagih_pemakaian_dan_mengembalikan_sisa(store):
    t, _ = _tenant(store, "pro")
    start = store.billing.balance(t["tenant_id"])["credit_microusd"]
    job = _job(store, t, tokens=5000)
    store.finish_job(t["tenant_id"], job["job_id"], "succeeded", 1000)
    b = store.billing.balance(t["tenant_id"])
    assert b["held_microusd"] == 0
    assert b["credit_microusd"] == start - price_tokens(1000, "pro")
    charges = store.db.execute("SELECT * FROM job_charges WHERE job_id = ?", (job["job_id"],)).fetchone()
    assert charges["micro_usd"] == price_tokens(1000, "pro")


def test_gagal_melepas_seluruh_pesanan(store):
    t, _ = _tenant(store, "pro")
    start = store.billing.balance(t["tenant_id"])["credit_microusd"]
    job = _job(store, t)
    store.finish_job(t["tenant_id"], job["job_id"], "failed", 0, None, "boom")
    b = store.billing.balance(t["tenant_id"])
    assert b["credit_microusd"] == start and b["held_microusd"] == 0
    assert store.db.execute("SELECT micro_usd FROM job_charges WHERE job_id = ?",
                            (job["job_id"],)).fetchone()["micro_usd"] == 0


def test_token_melebihi_budget_ditagih_sebatas_pesanan(store):
    t, _ = _tenant(store, "pro")
    start = store.billing.balance(t["tenant_id"])["credit_microusd"]
    job = _job(store, t, tokens=5000)
    done = store.finish_job(t["tenant_id"], job["job_id"], "succeeded", 99_999)
    assert done["status"] == "budget_exceeded"
    b = store.billing.balance(t["tenant_id"])
    assert start - b["credit_microusd"] == price_tokens(5000, "pro")  # tidak melebihi pesanan


def test_settle_idempoten_tidak_menagih_dua_kali(store):
    t, _ = _tenant(store, "pro")
    job = _job(store, t)
    hold = 8_000
    r1 = store.billing.settle(t["tenant_id"], job["job_id"], 1000, "pro", hold)
    after1 = store.billing.balance(t["tenant_id"])["credit_microusd"]
    r2 = store.billing.settle(t["tenant_id"], job["job_id"], 1000, "pro", hold)
    assert r1["replayed"] is False and r2["replayed"] is True
    assert store.billing.balance(t["tenant_id"])["credit_microusd"] == after1


def test_ledger_rantai_hash_dan_invarian_saldo(store):
    t, _ = _tenant(store, "starter")
    job = _job(store, t)
    store.finish_job(t["tenant_id"], job["job_id"], "succeeded", 1200)
    store.billing.topup(t["tenant_id"], 3_000_000)
    v = store.billing.verify_chain(t["tenant_id"])
    assert v["ok"] is True
    total = store.db.execute("SELECT SUM(amount) s FROM ledger WHERE tenant_id = ?",
                             (t["tenant_id"],)).fetchone()["s"]
    assert total == store.billing.balance(t["tenant_id"])["credit_microusd"]


def test_ledger_dirusak_terdeteksi(store):
    t, _ = _tenant(store)
    job = _job(store, t)
    store.finish_job(t["tenant_id"], job["job_id"], "succeeded", 500)
    store.db.execute("UPDATE ledger SET amount = amount + 1000 WHERE tenant_id = ? AND kind = 'charge'",
                     (t["tenant_id"],))
    store.db.commit()
    assert store.billing.verify_chain(t["tenant_id"])["ok"] is False


# ------------------------------------------------------------------- invoice
def test_invoice_menjumlahkan_charge_periode(store):
    t, _ = _tenant(store, "pro")
    job = _job(store, t)
    store.finish_job(t["tenant_id"], job["job_id"], "succeeded", 2000)
    start = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=1)).isoformat(timespec="seconds")
    end = dt.datetime.now(dt.timezone.utc).isoformat(timespec="microseconds")  # periode sudah tertutup
    inv = store.billing.issue_invoice(t["tenant_id"], start, end)
    assert inv["total_microusd"] == price_tokens(2000, "pro") and inv["jobs"] == 1
    again = store.billing.issue_invoice(t["tenant_id"], start, end)
    assert again["replayed"] is True and again["invoice_id"] == inv["invoice_id"]
    assert store.billing.verify_invoice(inv["invoice_id"])["ok"] is True


def test_invoice_abadi_saat_snapshot_diubah(store):
    t, _ = _tenant(store, "pro")
    job = _job(store, t)
    store.finish_job(t["tenant_id"], job["job_id"], "succeeded", 700)
    start = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=1)).isoformat(timespec="seconds")
    end = dt.datetime.now(dt.timezone.utc).isoformat(timespec="microseconds")  # periode sudah tertutup
    inv = store.billing.issue_invoice(t["tenant_id"], start, end)
    store.db.execute("UPDATE invoices SET total_microusd = 0 WHERE invoice_id = ?", (inv["invoice_id"],))
    store.db.commit()
    assert store.billing.verify_invoice(inv["invoice_id"])["ok"] is False


def test_invoice_tidak_mencampur_tenant(store):
    a, _ = _tenant(store, "pro")
    b, _ = _tenant(store, "pro")
    ja = _job(store, a)
    store.finish_job(a["tenant_id"], ja["job_id"], "succeeded", 1000)
    start = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=1)).isoformat(timespec="seconds")
    end = dt.datetime.now(dt.timezone.utc).isoformat(timespec="microseconds")  # periode sudah tertutup
    inv = store.billing.issue_invoice(b["tenant_id"], start, end)
    assert inv["total_microusd"] == 0 and inv["jobs"] == 0


# -------------------------------------------------------------------- worker
def test_claim_atomik_dan_attempts(store):
    t, _ = _tenant(store)
    job = _job(store, t)
    claimed = store.claim_next_job("worker-alpha", 60)
    assert claimed["job_id"] == job["job_id"] and claimed["status"] == "running"
    assert claimed["attempts"] == 1 and claimed["lease_owner"] == "worker-alpha"
    assert store.claim_next_job("worker-beta", 60) is None


def test_dua_worker_paralel_tidak_dobel(tmp_path):
    path = str(tmp_path / "cp.db")
    s1, s2 = Store(path), Store(path)
    t = s1.create_tenant(plan="pro")
    s1.create_job(t["tenant_id"], "recon", {"id": "sdb-recon", "version": "1.0.0"},
                  "artifact://a/1", {"tokens": 5000, "seconds": 600}, "kunci-0001")
    barrier = threading.Barrier(2)
    got: list[str | None] = []

    def grab(store, name):
        barrier.wait()
        job = store.claim_next_job(name, 60)
        got.append(job["job_id"] if job else None)

    threads = [threading.Thread(target=grab, args=(s1, "worker-1")),
               threading.Thread(target=grab, args=(s2, "worker-2"))]
    for th in threads:
        th.start()
    for th in threads:
        th.join(timeout=15)
    assert len([g for g in got if g]) == 1, got


def test_worker_sukses_menagih_dan_menutup_job(store):
    t, _ = _tenant(store, "pro")
    job = _job(store, t, tokens=5000)
    w = Worker(store, echo_executor, "worker-test-1", lease_seconds=60)
    summary = w.run_once()
    assert summary["claimed"] == job["job_id"] and summary["status"] == "succeeded"
    assert store.get_job(t["tenant_id"], job["job_id"])["status"] == "succeeded"
    assert summary["tokens_used"] == min(1000 + 37 * len("artifact://a/1"), 5000)
    assert store.billing.balance(t["tenant_id"])["held_microusd"] == 0


def test_worker_gagal_melepas_pesanan(store):
    t, _ = _tenant(store, "pro")
    start = store.billing.balance(t["tenant_id"])["credit_microusd"]
    _job(store, t)
    w = Worker(store, failing_executor, "worker-test-2", lease_seconds=60)
    summary = w.run_once()
    assert summary["status"] == "failed" and "executor sengaja gagal" in summary["error"]
    assert store.billing.balance(t["tenant_id"])["credit_microusd"] == start


def test_worker_memotong_token_melebihi_budget(store):
    t, _ = _tenant(store, "pro")
    job = _job(store, t, tokens=1000)

    def boros(_job):
        return ExecutionResult(status="succeeded", tokens_used=10**6)

    summary = Worker(store, boros, "worker-test-3", lease_seconds=60).run_once()
    assert summary["status"] == "budget_exceeded" and summary["tokens_used"] == 1000
    assert store.get_job(t["tenant_id"], job["job_id"])["status"] == "budget_exceeded"


def test_heartbeat_dan_lease_hilang(store):
    t, _ = _tenant(store)
    job = _job(store, t)
    store.claim_next_job("worker-a", 60)
    assert store.heartbeat("worker-a", job["job_id"], 60)["lease_owner"] == "worker-a"
    with pytest.raises(ControlPlaneError) as exc:
        store.heartbeat("worker-b", job["job_id"], 60)
    assert exc.value.code == "lease_lost"


def _expire(store, job_id):
    past = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=5)).isoformat(timespec="seconds")
    store.db.execute("UPDATE jobs SET lease_until = ? WHERE job_id = ?", (past, job_id))
    store.db.commit()


def test_lease_kedaluwarsa_diantre_ulang(store):
    t, _ = _tenant(store)
    job = _job(store, t)
    store.claim_next_job("worker-mati", 60)
    _expire(store, job["job_id"])
    out = store.reap_expired_leases(max_attempts=3)
    assert out == [{"job_id": job["job_id"], "result": "requeued"}]
    again = store.get_job(t["tenant_id"], job["job_id"])
    assert again["status"] == "queued" and again["lease_owner"] is None


def test_lease_kedaluwarsa_habis_percobaan_jadi_gagal_dan_refund(store):
    t, _ = _tenant(store, "pro")
    start = store.billing.balance(t["tenant_id"])["credit_microusd"]
    job = _job(store, t)
    store.db.execute("UPDATE jobs SET attempts = 3 WHERE job_id = ?", (job["job_id"],))
    store.claim_next_job("worker-mati", 60)  # attempts -> 4
    _expire(store, job["job_id"])
    out = store.reap_expired_leases(max_attempts=3)
    assert out == [{"job_id": job["job_id"], "result": "failed"}]
    assert store.get_job(t["tenant_id"], job["job_id"])["status"] == "failed"
    assert store.billing.balance(t["tenant_id"])["credit_microusd"] == start


def test_cancel_job_antrean_melepas_kredit(store):
    t, _ = _tenant(store, "pro")
    start = store.billing.balance(t["tenant_id"])["credit_microusd"]
    job = _job(store, t)
    done = store.request_cancel(t["tenant_id"], job["job_id"])
    assert done["status"] == "cancelled"
    assert store.billing.balance(t["tenant_id"])["credit_microusd"] == start


def test_cancel_job_berjalan_ditutup_worker_tanpa_tagihan(store):
    t, _ = _tenant(store, "pro")
    start = store.billing.balance(t["tenant_id"])["credit_microusd"]
    job = _job(store, t)
    store.claim_next_job("worker-x", 60)

    def lambat(_job):
        return ExecutionResult(status="succeeded", tokens_used=4000)

    store.request_cancel(t["tenant_id"], job["job_id"])
    summary = Worker(store, lambat, "worker-x", lease_seconds=60).run_once()
    assert summary["claimed"] is None  # job sudah berstatus running, bukan queued
    done = store.finish_job(t["tenant_id"], job["job_id"], "cancelled", 0, None, "cancelled_by_tenant")
    assert done["status"] == "cancelled"
    assert store.billing.balance(t["tenant_id"])["credit_microusd"] == start


# ---------------------------------------------------------------------- HTTP
@pytest.fixture()
def server():
    httpd = serve(Store(":memory:"), ADMIN, host="127.0.0.1", port=0, worker_key=WKEY)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield httpd, f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


def _http(base, method, path, body=None, key=None, admin=None, worker=None):
    import json as _json
    import urllib.error
    import urllib.request
    data = _json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, method=method)
    if data:
        req.add_header("Content-Type", "application/json")
    if key:
        req.add_header("X-API-Key", key)
    if admin:
        req.add_header("X-Admin-Key", admin)
    if worker:
        req.add_header("X-Worker-Key", worker)
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, _json.loads(r.read())
    except urllib.error.HTTPError as exc:
        return exc.code, _json.loads(exc.read())


def test_http_topup_dan_saldo(server):
    _, base = server
    _, t = _http(base, "POST", "/v1/tenants", {"plan": "starter"}, admin=ADMIN)
    tid = t["tenant"]["tenant_id"]
    assert _http(base, "POST", "/v1/credits/topup",
                 {"tenant_id": tid, "amount_microusd": 2_000_000}, admin=ADMIN)[0] == 201
    status, payload = _http(base, "GET", "/v1/billing", key=t["api_key"])
    assert status == 200 and payload["billing"]["credit_microusd"] == TRIAL_CREDIT["starter"] + 2_000_000
    assert _http(base, "GET", "/v1/ledger", key=t["api_key"])[1]["ledger"][0]["kind"] == "topup"


def test_http_worker_butuh_kunci(server):
    _, base = server
    _, t = _http(base, "POST", "/v1/tenants", {"plan": "pro"}, admin=ADMIN)
    _, job = _http(base, "POST", "/v1/jobs", {
        "type": "recon", "pack": {"id": "sdb-recon", "version": "1.0.0"},
        "target_ref": "artifact://a/1", "budget": {"tokens": 4000, "seconds": 300},
        "idempotency_key": "http-worker-1"}, key=t["api_key"])
    assert _http(base, "POST", "/v1/worker/claim", {"worker_id": "w-http-1"})[0] == 401
    status, payload = _http(base, "POST", "/v1/worker/claim", {"worker_id": "w-http-1"}, worker=WKEY)
    assert status == 200 and payload["job"]["job_id"] == job["job"]["job_id"]

    status, payload = _http(base, "POST", f"/v1/jobs/{job['job']['job_id']}/complete",
                            {"worker_id": "w-salah", "status": "succeeded", "tokens_used": 10}, worker=WKEY)
    assert status == 409 and payload["error"]["code"] == "lease_lost"

    status, payload = _http(base, "POST", f"/v1/jobs/{job['job']['job_id']}/complete",
                            {"worker_id": "w-http-1", "status": "succeeded", "tokens_used": 2000}, worker=WKEY)
    assert status == 200 and payload["job"]["status"] == "succeeded"


def test_http_invoice_dan_isolasi(server):
    _, base = server
    _, a = _http(base, "POST", "/v1/tenants", {"plan": "pro"}, admin=ADMIN)
    _, b = _http(base, "POST", "/v1/tenants", {"plan": "pro"}, admin=ADMIN)
    _, job = _http(base, "POST", "/v1/jobs", {
        "type": "recon", "pack": {"id": "sdb-recon", "version": "1.0.0"},
        "target_ref": "artifact://a/1", "budget": {"tokens": 4000, "seconds": 300},
        "idempotency_key": "http-inv-1"}, key=a["api_key"])
    _http(base, "POST", "/v1/worker/claim", {"worker_id": "w-http-inv"}, worker=WKEY)
    _http(base, "POST", f"/v1/jobs/{job['job']['job_id']}/complete",
          {"worker_id": "w-http-inv", "status": "succeeded", "tokens_used": 1000}, worker=WKEY)
    start = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=1)).isoformat(timespec="seconds")
    end = dt.datetime.now(dt.timezone.utc).isoformat(timespec="microseconds")  # periode sudah tertutup
    assert _http(base, "POST", "/v1/admin/invoices", {"tenant_id": a["tenant"]["tenant_id"],
                 "period_start": start, "period_end": end}, key=a["api_key"])[0] == 401  # tenant tak boleh terbitkan
    status, inv = _http(base, "POST", "/v1/admin/invoices", {"tenant_id": a["tenant"]["tenant_id"],
                        "period_start": start, "period_end": end}, admin=ADMIN)
    assert status == 201 and inv["invoice"]["total_microusd"] == price_tokens(1000, "pro")
    status, mine = _http(base, "GET", "/v1/invoices", key=a["api_key"])
    assert status == 200 and len(mine["invoices"]) == 1
    status, other = _http(base, "GET", "/v1/invoices", key=b["api_key"])
    assert status == 200 and other["invoices"] == []


def test_api_menolak_worker_key_pendek():
    with pytest.raises(SystemExit):
        Api(Store(":memory:"), ADMIN, worker_key="pendek")


def test_harga_semua_plan_positif_dan_urut():
    assert all(v > 0 for v in PLAN_PRICE_PER_MTOK.values())
    assert PLAN_PRICE_PER_MTOK["starter"] > PLAN_PRICE_PER_MTOK["pro"] > PLAN_PRICE_PER_MTOK["team"] >= 1_000_000

def test_banyak_worker_menyelesaikan_banyak_job_tepat_sekali(tmp_path):
    """Uji tekanan: 4 worker x 12 job. Setiap job harus sukses tepat sekali dan tagihan konsisten."""
    path = str(tmp_path / "stress.db")
    setup = Store(path)
    t = setup.create_tenant(plan="team")
    start = setup.billing.balance(t["tenant_id"])["credit_microusd"]
    jobs = [setup.create_job(t["tenant_id"], "recon", {"id": "sdb-recon", "version": "1.0.0"},
                             f"artifact://stress/{i}", {"tokens": 4000, "seconds": 600},
                             f"stress-{i:04d}")[0]["job_id"] for i in range(12)]
    barriers = threading.Barrier(4)
    hasil: list[dict] = []
    lock = threading.Lock()

    def kerja(nama):
        store = Store(path)
        worker = Worker(store, echo_executor, nama, lease_seconds=60)
        barriers.wait()
        while True:
            ringkas = worker.run_once()
            if not ringkas.get("claimed"):
                break
            with lock:
                hasil.append(ringkas)

    threads = [threading.Thread(target=kerja, args=(f"w-stress-{i}",)) for i in range(4)]
    for th in threads:
        th.start()
    for th in threads:
        th.join(timeout=120)

    selesai = Store(path)
    assert len(hasil) == 12, hasil
    assert all(h["status"] == "succeeded" for h in hasil)
    assert {h["claimed"] for h in hasil} == set(jobs)  # tidak ada job dikerjakan dua kali
    for jid in jobs:
        row = selesai.db.execute("SELECT COUNT(*) n FROM job_charges WHERE job_id = ?", (jid,)).fetchone()
        assert row["n"] == 1
    total = selesai.db.execute("SELECT SUM(micro_usd) s FROM job_charges WHERE tenant_id = ?",
                               (t["tenant_id"],)).fetchone()["s"]
    assert start - selesai.billing.balance(t["tenant_id"])["credit_microusd"] == total
    assert selesai.billing.verify_chain(t["tenant_id"])["ok"] is True
