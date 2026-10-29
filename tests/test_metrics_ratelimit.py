"""Fase 2c: pembatas laju per tenant dan endpoint /metrics (format Prometheus).

Diuji lewat HTTP sungguhan karena yang berbahaya justru integrasi handler: apakah 429 benar-benar
sampai ke klien dengan Retry-After, dan apakah metrik menghitung apa yang sungguh terjadi.
"""
from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request

import pytest

from sdb_platform.control_plane.app import serve
from sdb_platform.control_plane.metrics import Metrics, RateLimited, RateLimiter
from sdb_platform.control_plane.store import Store

ADMIN = "admin-key-fase2c-" + "a" * 20  # >=24 char
K1 = "kunci-uji-1-" + "x" * 20
KA = "kunci-a-" + "y" * 20
KB = "kunci-b-" + "z" * 20
KC = "kunci-c-" + "q" * 20
KL = "kunci-lambat-" + "s" * 20
WKEY = "worker-key-fase2c-" + "w" * 20
PACK = {"id": "sdb-recon", "version": "1.0.0"}


@pytest.fixture()
def srv():
    store = Store(":memory:")
    store.add_api_key(store.create_tenant(plan="pro")["tenant_id"], K1)
    httpd = serve(store, ADMIN, "127.0.0.1", 0, WKEY)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}", store
    httpd.shutdown()
    httpd.server_close()


def _req(base, method, path, key=None, body=None, admin=False, worker=False):
    headers = {}
    if key:
        headers["X-API-Key"] = key
    if admin:
        headers["X-Admin-Key"] = ADMIN
    if worker:
        headers["X-Worker-Key"] = WKEY
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(base + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, r.read().decode(), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(), dict(e.headers)


# ------------------------------------------------------------------ laju (unit)
def test_limiter_menolak_lebih_dari_jatah_dan_memberi_retry_after():
    lim = RateLimiter(default_per_min=60)  # 1 req/dtk, burst 5
    for _ in range(5):
        lim.check("t_x")
    with pytest.raises(RateLimited) as err:
        lim.check("t_x")
    assert 1 <= err.value.retry_after <= 2


def test_limiter_tenant_lain_tidak_terpengaruh():
    lim = RateLimiter(default_per_min=60)
    for _ in range(5):
        lim.check("t_a")
    with pytest.raises(RateLimited):
        lim.check("t_a")
    lim.check("t_b")  # ember terpisah per tenant


def test_limiter_mengisi_ulang_seiring_waktu():
    lim = RateLimiter(default_per_min=60)
    for _ in range(5):
        lim.check("t_x")
    with pytest.raises(RateLimited):
        lim.check("t_x")
    # kapasitas 5, laju 1/dtk: majukan jam 3 detik => 3 token baru
    import time as _t
    real = _t.monotonic
    try:
        _t.monotonic = lambda: real() + 3.0
        for _ in range(3):
            lim.check("t_x")
        with pytest.raises(RateLimited):
            lim.check("t_x")
    finally:
        _t.monotonic = real


# ------------------------------------------------------------------ laju (HTTP)
def test_http_429_dengan_retry_after_untuk_tenant_yang_melebihi_jatah(srv):
    base, store = srv
    tid = store.create_tenant(plan="pro", limits={"rate_per_min": 5})["tenant_id"]
    store.add_api_key(tid, KL)
    codes = [_req(base, "GET", "/v1/usage", key=KL)[0] for _ in range(8)]
    assert codes[:5] == [200] * 5, codes
    assert codes[5] == 429, codes
    status, body, head = _req(base, "GET", "/v1/usage", key=KL)
    assert status == 429
    assert json.loads(body)["error"]["code"] == "rate_limited"
    assert int(head["Retry-After"]) >= 1


def test_tenant_lain_tetap_dilayani_saat_satu_tenant_dibatasi(srv):
    base, store = srv
    a = store.create_tenant(plan="pro", limits={"rate_per_min": 3})["tenant_id"]
    b = store.create_tenant(plan="pro")["tenant_id"]
    store.add_api_key(a, KA)
    store.add_api_key(b, KB)
    for _ in range(6):
        _req(base, "GET", "/v1/usage", key=KA)
    assert _req(base, "GET", "/v1/usage", key=KA)[0] == 429
    assert _req(base, "GET", "/v1/usage", key=KB)[0] == 200


def test_admin_dan_worker_tidak_kena_jatah_tenant(srv):
    base, store = srv
    tid = store.create_tenant(plan="pro", limits={"rate_per_min": 2})["tenant_id"]
    store.add_api_key(tid, KC)
    for _ in range(6):
        _req(base, "GET", "/v1/usage", key=KC)
    assert _req(base, "GET", "/v1/usage", key=KC)[0] == 429
    # jalur admin/worker bukan jalur tenant: tidak boleh ikut tertahan
    assert _req(base, "POST", "/v1/worker/claim", worker=True,
                body={"worker_id": "w-uji-1", "lease_seconds": 120})[0] == 200


# ------------------------------------------------------------------ metrik
def test_metrics_hanya_untuk_admin(srv):
    base, _ = srv
    assert _req(base, "GET", "/metrics")[0] == 401
    assert _req(base, "GET", "/metrics", key=K1)[0] == 401  # API key tenant bukan admin


def test_metrics_format_prometheus_dan_menghitung_permintaan(srv):
    base, _store = srv
    _req(base, "GET", "/v1/usage", key=K1)
    _req(base, "GET", "/v1/usage")  # 401
    status, body, head = _req(base, "GET", "/metrics", admin=True)
    assert status == 200
    assert head["Content-Type"].startswith("text/plain")
    assert "# TYPE sdb_http_requests_total counter" in body
    assert 'route="/v1/usage",status="200"' in body
    assert 'route="/v1/usage",status="401"' in body
    assert "# TYPE sdb_uptime_seconds gauge" in body


def test_metrics_menghitung_job_dan_token(srv):
    base, _store = srv
    st, body, _ = _req(base, "POST", "/v1/jobs", key=K1, body={
        "type": "recon", "pack": PACK, "target_ref": "artifact://t/1",
        "budget": {"tokens": 5000, "seconds": 600}, "idempotency_key": "metrik-uji-0001"})
    assert st == 201, body
    jid = json.loads(body)["job"]["job_id"]
    assert _req(base, "POST", "/v1/worker/claim", worker=True,
                body={"worker_id": "w-uji-2", "lease_seconds": 120})[0] == 200
    assert _req(base, "POST", f"/v1/jobs/{jid}/complete", worker=True,
                body={"status": "succeeded", "tokens_used": 1500, "worker_id": "w-uji-2"})[0] == 200
    _, text, _ = _req(base, "GET", "/metrics", admin=True)
    assert "sdb_jobs_created_total" in text and 'type="recon"' in text
    assert 'sdb_jobs_completed_total{status="succeeded"} 1' in text
    assert "sdb_tokens_used_total 1500" in text


def test_metrics_kardinalitas_rute_tidak_meledak(srv):
    base, _store = srv
    _req(base, "POST", "/v1/jobs", key=K1, body={
        "type": "recon", "pack": PACK, "target_ref": "artifact://t/1",
        "budget": {"tokens": 5000, "seconds": 600}, "idempotency_key": "metrik-uji-0002"})
    _, text, _ = _req(base, "GET", "/metrics", admin=True)
    assert 'route="/v1/jobs"' in text
    # tidak ada label berisi id job (ULID 26 karakter) — kardinalitas tetap rendah
    labels = [part.split('"')[1] for part in text.splitlines() if '="' in part]
    assert not [x for x in labels if len(x) == 26]


def test_metrics_objek_aman_dipakai_paralel():
    m = Metrics()

    def work():
        for _ in range(500):
            m.inc("sdb_uji_total", {"k": "v"})

    threads = [threading.Thread(target=work) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert "sdb_uji_total{k=\"v\"} 4000" in m.render()
