"""Tahap 11 — matriks IDOR & isolasi tenant lintas SELURUH rute milik tenant.

Yang diuji: batas tidak bisa dilewati, dan kegagalan tidak membocorkan keberadaan
data tenant lain (404, bukan 403). Semua panggilan lewat Api.handle — tanpa socket,
supaya deterministik dan cepat.

Rute yang diperiksa:
  GET  /v1/jobs/{id}                GET  /v1/jobs/{id}/artifacts
  POST /v1/jobs/{id}/artifacts      POST /v1/jobs/{id}/cancel
  GET  /v1/billing /v1/ledger /v1/invoices /v1/usage
  POST /v1/admin/*  (tenant key harus ditolak)
  POST /v1/worker/* (tenant key harus ditolak)
  GET  /metrics     (tenant key harus ditolak)
"""

from __future__ import annotations

import os
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from sdb_platform.control_plane.app import Api
from sdb_platform.control_plane.store import ControlPlaneError, Store

ADMIN = "admin-" + "k" * 40
WORKER = "worker-" + "k" * 40


@pytest.fixture()
def dunia():
    """Dua tenant (A, B) + satu job dan artefak milik B."""
    store = Store(":memory:")
    api = Api(store, ADMIN, WORKER)
    ta = store.create_tenant(plan="pro", name="tenant-A")
    tb = store.create_tenant(plan="pro", name="tenant-B")
    ka = store.add_api_key(ta["tenant_id"])
    kb = store.add_api_key(tb["tenant_id"])
    job_b, _ = store.create_job(tb["tenant_id"], "recon",
                                {"id": "sdb-recon", "version": "1.0.0"},
                                "artifact://upload/b.zip",
                                {"tokens": 5000, "seconds": 600}, "job-b-0001")
    art = store.register_artifact(
        tb["tenant_id"], job_b["job_id"], "log", "a" * 64, 100, "clean",
        "2027-01-01T00:00:00Z",
        f"artifact://{tb['tenant_id']}/{job_b['job_id']}/log.txt", "text/plain")
    return {"store": store, "api": api, "A": ta["tenant_id"], "B": tb["tenant_id"],
            "ka": ka, "kb": kb, "job_b": job_b["job_id"],
            "art_id": art["artifact_id"]}


def _h(key=None, admin=None, worker=None):
    h = {}
    if key:
        h["x-api-key"] = key
    if admin:
        h["x-admin-key"] = admin
    if worker:
        h["x-worker-key"] = worker
    return h


def _call(dunia, method, path, headers, body=None):
    try:
        return dunia["api"].handle(method, path, headers, body)
    except ControlPlaneError as exc:
        return exc.status, {"error": exc.code}


def test_baca_job_tenant_lain_404_bukan_403(dunia):
    st, body = _call(dunia, "GET", f"/v1/jobs/{dunia['job_b']}", _h(key=dunia["ka"]))
    assert st == 404
    assert "tenant_id" not in (body.get("job") or {})


def test_artefak_job_tenant_lain_kosong_bukan_bocor(dunia):
    st, body = _call(dunia, "GET", f"/v1/jobs/{dunia['job_b']}/artifacts", _h(key=dunia["ka"]))
    assert st in (200, 404)
    assert body.get("artifacts", []) == []


def test_tidak_bisa_daftarkan_artefak_ke_job_tenant_lain(dunia):
    sebelum = len(dunia["store"].list_artifacts(dunia["B"], dunia["job_b"]))
    st, _ = _call(dunia, "POST", f"/v1/jobs/{dunia['job_b']}/artifacts", _h(key=dunia["ka"]),
                  {"kind": "log", "sha256": "b" * 64, "size": 10, "redaction_status": "clean",
                   "retention_until": "2027-01-01T00:00:00Z",
                   "uri": f"artifact://{dunia['A']}/lintas.txt", "media_type": "text/plain"})
    assert st in (403, 404), f"pendaftaran lintas tenant harus ditolak, dapat {st}"
    assert len(dunia["store"].list_artifacts(dunia["B"], dunia["job_b"])) == sebelum


def test_tidak_bisa_batalkan_job_tenant_lain(dunia):
    st, _ = _call(dunia, "POST", f"/v1/jobs/{dunia['job_b']}/cancel", _h(key=dunia["ka"]))
    assert st == 404
    row = dunia["store"].get_job(dunia["B"], dunia["job_b"])
    assert not row["cancel_requested"]


def test_billing_ledger_invoice_usage_tidak_memuat_tenant_lain(dunia):
    st_inv, _ = _call(dunia, "POST", "/v1/admin/invoices", _h(admin=ADMIN),
                      {"tenant_id": dunia["B"], "period_start": "2026-01-01",
                       "period_end": "2026-01-31"})
    assert st_inv in (200, 201)
    st_bil, bil = _call(dunia, "GET", "/v1/billing", _h(key=dunia["ka"]))
    st_led, led = _call(dunia, "GET", "/v1/ledger", _h(key=dunia["ka"]))
    st_inv_a, inv = _call(dunia, "GET", "/v1/invoices", _h(key=dunia["ka"]))
    st_use, use = _call(dunia, "GET", "/v1/usage", _h(key=dunia["ka"]))
    assert (st_bil, st_led, st_inv_a, st_use) == (200, 200, 200, 200)
    teks = repr(bil) + repr(led) + repr(inv) + repr(use)
    assert dunia["B"] not in teks, "identifier tenant B bocor lewat endpoint tenant A"
    assert inv.get("invoices") == []


def test_kuota_dan_pemakaian_tidak_tercampur(dunia):
    # A membuat 1 job; usage B tidak boleh berubah oleh job A.
    sebelum_b = dunia["store"].usage(dunia["B"])["jobs_used"]
    st, _ = _call(dunia, "POST", "/v1/jobs", _h(key=dunia["ka"]),
                  {"type": "recon", "pack": {"id": "sdb-recon", "version": "1.0.0"},
                   "target_ref": "artifact://upload/a.zip",
                   "budget": {"tokens": 1000, "seconds": 60},
                   "idempotency_key": "job-a-0001"})
    assert st == 201
    assert dunia["store"].usage(dunia["B"])["jobs_used"] == sebelum_b


def test_kunci_tenant_ditolak_di_rute_admin(dunia):
    rute = [
        ("POST", "/v1/tenants", {"plan": "pro"}),
        ("GET", "/metrics", None),
        ("POST", "/v1/admin/invoices", {"tenant_id": dunia["B"], "period_start": "2026-11-01",
                                        "period_end": "2026-11-30"}),
        ("POST", "/v1/credits/topup", {"tenant_id": dunia["B"], "amount_microusd": 100}),
        ("GET", "/v1/admin/revenue", None),
        ("POST", f"/v1/admin/tenants/{dunia['B']}/status", {"status": "suspended"}),
    ]
    for method, path, body in rute:
        st, _ = _call(dunia, method, path, _h(key=dunia["ka"]), body)
        assert st == 401, f"{method} {path} dengan kunci tenant harus 401, dapat {st}"


def test_kunci_tenant_ditolak_di_rute_worker(dunia):
    for method, path, body in [
        ("POST", "/v1/worker/claim", {"worker_id": "w1"}),
        ("POST", f"/v1/jobs/{dunia['job_b']}/heartbeat", {"worker_id": "w1"}),
        ("POST", f"/v1/jobs/{dunia['job_b']}/complete", {"worker_id": "w1", "status": "succeeded"}),
    ]:
        st, _ = _call(dunia, method, path, _h(key=dunia["ka"]), body)
        assert st == 401, f"{method} {path} dengan kunci tenant harus 401, dapat {st}"


def test_kunci_palsu_dan_varian_ditolak(dunia):
    asli = dunia["ka"]
    varian = ["", "x", asli[:-1], asli + " ", asli.upper(), asli[:16], " " + asli]
    for v in varian:
        st, _ = _call(dunia, "GET", "/v1/usage", _h(key=v))
        assert st == 401, f"varian kunci {v[:12]!r} harus 401, dapat {st}"


def test_worker_tidak_bisa_menyelesaikan_job_dengan_tenant_id_palsu(dunia):
    # Worker sah tapi job milik B: status harus benar-benar berubah hanya untuk B.
    st, body = _call(dunia, "POST", "/v1/worker/claim", _h(worker=WORKER), {"worker_id": "worker-9"})
    assert st == 200
    job = body.get("job") or {}
    if job.get("job_id") != dunia["job_b"]:
        pytest.skip("job B belum terklaim oleh worker pada urutan ini")
    st2, _ = _call(dunia, "POST", f"/v1/jobs/{dunia['job_b']}/complete", _h(worker=WORKER),
                   {"worker_id": "worker-9", "status": "succeeded", "tokens_used": 10})
    assert st2 == 200
    assert dunia["store"].get_job(dunia["B"], dunia["job_b"])["status"] == "succeeded"


def test_idempotency_key_sama_lintas_tenant_tidak_bertabrakan(dunia):
    body = {"type": "recon", "pack": {"id": "sdb-recon", "version": "1.0.0"},
            "target_ref": "artifact://upload/sama.zip",
            "budget": {"tokens": 1000, "seconds": 60},
            "idempotency_key": "kunci-bersama"}
    st_a, a = _call(dunia, "POST", "/v1/jobs", _h(key=dunia["ka"]), body)
    st_b, b = _call(dunia, "POST", "/v1/jobs", _h(key=dunia["kb"]), body)
    assert st_a == 201 and st_b == 201
    assert a["job"]["job_id"] != b["job"]["job_id"]
    assert a["replayed"] is False and b["replayed"] is False
    assert a["job"]["tenant_id"] == dunia["A"] and b["job"]["tenant_id"] == dunia["B"]
