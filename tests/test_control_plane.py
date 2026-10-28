"""Control plane — uji bahwa isolasi tenant, kuota, idempotensi, dan redaksi benar-benar DITOLAK.

Yang diuji bukan "endpoint ada", tetapi "batas tidak bisa dilewati":
- tenant B tidak bisa membaca job tenant A (404, bukan 403 — jangan bocorkan keberadaan)
- job ke-3 saat kuota 2 -> 402, dan job gagal tidak boleh mengurangi kuota orang lain
- retry dengan idempotency_key sama tidak menggandakan job
- artefak tanpa status redaksi / berstatus blocked tidak pernah terdaftar
- token melebihi budget -> status budget_exceeded, bukan sukses
"""
from __future__ import annotations

import json
import os
import sys
import threading
import urllib.error
import urllib.request

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from sdb_platform.control_plane.app import Api, serve
from sdb_platform.control_plane.store import ControlPlaneError, Store

ADMIN = "admin-" + "x" * 40


@pytest.fixture()
def store():
    return Store(":memory:")


def _tenant(store, plan="pro", limits=None, name=None):
    t = store.create_tenant(plan=plan, limits=limits, name=name)
    return t, store.add_api_key(t["tenant_id"])


def _job_body(**over):
    body = {
        "type": "recon",
        "pack": {"id": "sdb-recon", "version": "1.0.0"},
        "target_ref": "artifact://upload/app.zip",
        "budget": {"tokens": 5000, "seconds": 600},
        "idempotency_key": "recon-2026-10-26-001",
    }
    body.update(over)
    return body


# ------------------------------------------------------------------ domain
def test_tenant_default_limits_mengikuti_plan(store):
    t, _ = _tenant(store, "starter")
    assert t["jobs_per_month"] == 50
    assert t["isolation"] == "pool"
    assert store.usage(t["tenant_id"])["tokens_remaining"] == 2_000_000


def test_plan_tidak_dikenal_ditolak(store):
    with pytest.raises(ControlPlaneError) as exc:
        store.create_tenant(plan="gratis-selamanya")
    assert exc.value.status == 400


def test_api_key_salah_ditolak(store):
    _tenant(store)
    with pytest.raises(ControlPlaneError) as exc:
        store.tenant_for_key("kunci-palsu-yang-cukup-panjang")
    assert exc.value.status == 401


def test_tenant_suspend_tidak_bisa_pakai_api_key(store):
    t, key = _tenant(store)
    store.set_status(t["tenant_id"], "suspended")
    with pytest.raises(ControlPlaneError) as exc:
        store.tenant_for_key(key)
    assert exc.value.status == 403


def test_kuota_job_ditegakkan(store):
    t, _ = _tenant(store, limits={"jobs_per_month": 2, "tokens_per_month": 1_000_000, "storage_gb": 1})
    store.create_job(t["tenant_id"], "recon", {"id": "sdb-recon", "version": "1.0.0"},
                     "artifact://a/1", {"tokens": 5000, "seconds": 600}, "kunci-0001")
    store.create_job(t["tenant_id"], "recon", {"id": "sdb-recon", "version": "1.0.0"},
                     "artifact://a/2", {"tokens": 5000, "seconds": 600}, "kunci-0002")
    with pytest.raises(ControlPlaneError) as exc:
        store.create_job(t["tenant_id"], "recon", {"id": "sdb-recon", "version": "1.0.0"},
                         "artifact://a/3", {"tokens": 5000, "seconds": 600}, "kunci-0003")
    assert exc.value.code == "quota_jobs_exceeded"
    assert exc.value.status == 402


def test_kuota_token_ditegakkan(store):
    t, _ = _tenant(store, limits={"jobs_per_month": 10, "tokens_per_month": 6000, "storage_gb": 1})
    store.create_job(t["tenant_id"], "recon", {"id": "sdb-recon", "version": "1.0.0"},
                     "artifact://a/1", {"tokens": 5000, "seconds": 600}, "kunci-0001")
    with pytest.raises(ControlPlaneError) as exc:
        store.create_job(t["tenant_id"], "recon", {"id": "sdb-recon", "version": "1.0.0"},
                         "artifact://a/2", {"tokens": 2000, "seconds": 600}, "kunci-0002")
    assert exc.value.code == "quota_tokens_exceeded"


def test_idempotency_tidak_menggandakan_job(store):
    t, _ = _tenant(store)
    j1, replay1 = store.create_job(t["tenant_id"], "recon", {"id": "sdb-recon", "version": "1.0.0"},
                                   "artifact://a/1", {"tokens": 5000, "seconds": 600}, "kunci-sama")
    j2, replay2 = store.create_job(t["tenant_id"], "recon", {"id": "sdb-recon", "version": "1.0.0"},
                                   "artifact://a/1", {"tokens": 5000, "seconds": 600}, "kunci-sama")
    assert replay1 is False and replay2 is True
    assert j1["job_id"] == j2["job_id"]
    assert store.usage(t["tenant_id"])["jobs_used"] == 1


def test_budget_di_luar_batas_ditolak(store):
    t, _ = _tenant(store)
    with pytest.raises(ControlPlaneError) as exc:
        store.create_job(t["tenant_id"], "recon", {"id": "sdb-recon", "version": "1.0.0"},
                         "artifact://a/1", {"tokens": 9_000_000, "seconds": 600}, "kunci-0001")
    assert exc.value.code == "invalid_budget"


def test_isolasi_tenant_lintas_baca(store):
    a, _ = _tenant(store)
    b, _ = _tenant(store)
    job, _ = store.create_job(a["tenant_id"], "recon", {"id": "sdb-recon", "version": "1.0.0"},
                              "artifact://a/1", {"tokens": 5000, "seconds": 600}, "kunci-aa01")
    with pytest.raises(ControlPlaneError) as exc:
        store.get_job(b["tenant_id"], job["job_id"])
    assert exc.value.status == 404
    assert exc.value.code == "job_not_found"


def test_token_melebihi_budget_jadi_budget_exceeded(store):
    t, _ = _tenant(store)
    job, _ = store.create_job(t["tenant_id"], "recon", {"id": "sdb-recon", "version": "1.0.0"},
                              "artifact://a/1", {"tokens": 5000, "seconds": 600}, "kunci-aa01")
    done = store.finish_job(t["tenant_id"], job["job_id"], "succeeded", 6000)
    assert done["status"] == "budget_exceeded"


def test_job_selesai_tidak_bisa_ditutup_dua_kali(store):
    t, _ = _tenant(store)
    job, _ = store.create_job(t["tenant_id"], "recon", {"id": "sdb-recon", "version": "1.0.0"},
                              "artifact://a/1", {"tokens": 5000, "seconds": 600}, "kunci-aa01")
    store.finish_job(t["tenant_id"], job["job_id"], "succeeded", 100)
    with pytest.raises(ControlPlaneError) as exc:
        store.finish_job(t["tenant_id"], job["job_id"], "succeeded", 100)
    assert exc.value.status == 409


SHA = "a" * 64


def _job(store):
    t, _ = _tenant(store)
    job, _ = store.create_job(t["tenant_id"], "recon", {"id": "sdb-recon", "version": "1.0.0"},
                              "artifact://a/1", {"tokens": 5000, "seconds": 600}, "kunci-aa01")
    return t, job


def test_artefak_tanpa_redaksi_ditolak(store):
    t, job = _job(store)
    with pytest.raises(ControlPlaneError) as exc:
        store.register_artifact(t["tenant_id"], job["job_id"], "evidence", SHA, 10, "", "2027-01-01", "s3://b/x")
    assert exc.value.code == "invalid_redaction"


def test_artefak_blocked_ditolak(store):
    t, job = _job(store)
    with pytest.raises(ControlPlaneError) as exc:
        store.register_artifact(t["tenant_id"], job["job_id"], "evidence", SHA, 10, "blocked",
                                "2027-01-01", "s3://b/x")
    assert exc.value.status == 422


def test_artefak_uri_lokal_ditolak(store):
    t, job = _job(store)
    with pytest.raises(ControlPlaneError) as exc:
        store.register_artifact(t["tenant_id"], job["job_id"], "evidence", SHA, 10, "clean",
                                "2027-01-01", "/home/anashadi/evidence/x.json")
    assert exc.value.code == "invalid_uri"


def test_artefak_sah_tercatat_dan_kuota_storage_dihitung(store):
    t, job = _job(store)
    art = store.register_artifact(t["tenant_id"], job["job_id"], "evidence", SHA, 1024, "redacted",
                                  "2027-01-01", "s3://sdb-artifacts/x", "application/json")
    assert art["artifact_id"].startswith("a_")
    assert store.usage(t["tenant_id"])["storage_bytes"] == 1024
    assert len(store.list_artifacts(t["tenant_id"], job["job_id"])) == 1


def test_kuota_storage_ditegakkan(store):
    t, _ = _tenant(store, limits={"jobs_per_month": 5, "tokens_per_month": 1_000_000, "storage_gb": 1})
    job, _ = store.create_job(t["tenant_id"], "recon", {"id": "sdb-recon", "version": "1.0.0"},
                              "artifact://a/1", {"tokens": 5000, "seconds": 600}, "kunci-aa01")
    with pytest.raises(ControlPlaneError) as exc:
        store.register_artifact(t["tenant_id"], job["job_id"], "capture", SHA, 2 * 1024 ** 3, "clean",
                                "2027-01-01", "s3://b/x")
    assert exc.value.code == "quota_storage_exceeded"


def test_dump_tenant_tidak_memuat_tenant_lain(store):
    a, _ = _tenant(store, name="A")
    b, _ = _tenant(store, name="B")
    store.create_job(a["tenant_id"], "recon", {"id": "sdb-recon", "version": "1.0.0"},
                     "artifact://a/1", {"tokens": 5000, "seconds": 600}, "kunci-aa01")
    dump = json.loads(store.dump_tenant(b["tenant_id"]))
    assert dump["tenant"]["tenant_id"] == b["tenant_id"]
    assert dump["jobs"] == []


# -------------------------------------------------------------------- HTTP
@pytest.fixture()
def server():
    httpd = serve(Store(":memory:"), ADMIN, host="127.0.0.1", port=0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield httpd, f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


def _http(base, method, path, body=None, api_key=None, admin=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, method=method)
    if data:
        req.add_header("Content-Type", "application/json")
    if api_key:
        req.add_header("X-API-Key", api_key)
    if admin:
        req.add_header("X-Admin-Key", admin)
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def test_http_alur_lengkap(server):
    _, base = server
    assert _http(base, "GET", "/healthz")[0] == 200

    status, payload = _http(base, "POST", "/v1/tenants", {"plan": "pro", "name": "PT Uji"}, admin=ADMIN)
    assert status == 201
    key = payload["api_key"]

    status, payload = _http(base, "POST", "/v1/jobs", _job_body(), api_key=key)
    assert status == 201
    job_id = payload["job"]["job_id"]

    status, again = _http(base, "POST", "/v1/jobs", _job_body(), api_key=key)
    assert status == 200 and again["replayed"] is True and again["job"]["job_id"] == job_id

    assert _http(base, "GET", f"/v1/jobs/{job_id}", api_key=key)[0] == 200
    status, usage = _http(base, "GET", "/v1/usage", api_key=key)
    assert status == 200 and usage["usage"]["jobs_used"] == 1

    status, done = _http(base, "POST", f"/v1/jobs/{job_id}/finish",
                         {"status": "succeeded", "tokens_used": 1234, "gate_verdict": "PASS"}, api_key=key)
    assert status == 200 and done["job"]["status"] == "succeeded"

    status, art = _http(base, "POST", f"/v1/jobs/{job_id}/artifacts",
                        {"kind": "evidence", "sha256": SHA, "size": 10, "redaction_status": "redacted",
                         "retention_until": "2027-01-01", "uri": "s3://sdb-artifacts/x"}, api_key=key)
    assert status == 201 and art["artifact"]["kind"] == "evidence"


def test_http_admin_key_wajib_untuk_buat_tenant(server):
    _, base = server
    status, payload = _http(base, "POST", "/v1/tenants", {"plan": "pro"})
    assert status == 401 and payload["error"]["code"] == "unauthorized"


def test_http_tenant_lain_tidak_bisa_baca_job(server):
    _, base = server
    _, a = _http(base, "POST", "/v1/tenants", {"plan": "pro"}, admin=ADMIN)
    _, b = _http(base, "POST", "/v1/tenants", {"plan": "pro"}, admin=ADMIN)
    _, job = _http(base, "POST", "/v1/jobs", _job_body(), api_key=a["api_key"])
    status, payload = _http(base, "GET", f"/v1/jobs/{job['job']['job_id']}", api_key=b["api_key"])
    assert status == 404 and payload["error"]["code"] == "job_not_found"


def test_http_json_rusak_ditolak(server):
    _, base = server
    _, t = _http(base, "POST", "/v1/tenants", {"plan": "pro"}, admin=ADMIN)
    req = urllib.request.Request(base + "/v1/jobs", data=b"{bukan json", method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("X-API-Key", t["api_key"])
    try:
        urllib.request.urlopen(req, timeout=5)
        raise AssertionError("seharusnya 400")
    except urllib.error.HTTPError as exc:
        assert exc.code == 400
        assert json.loads(exc.read())["error"]["code"] == "invalid_json"


def test_api_menolak_admin_key_pendek():
    with pytest.raises(SystemExit):
        Api(Store(":memory:"), "pendek")


def test_validasi_pakai_schema_kontrak():
    """Kontrak di platform/schemas harus sejalan dengan penegakan domain."""
    with open(os.path.join(REPO, "platform", "schemas", "job.schema.json"), encoding="utf-8") as fh:
        schema = json.load(fh)
    assert schema["properties"]["budget"]["properties"]["tokens"]["maximum"] == 2_000_000
    assert schema["properties"]["budget"]["properties"]["seconds"]["maximum"] == 14_400
