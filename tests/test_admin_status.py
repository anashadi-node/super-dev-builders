"""Rute admin untuk menonaktifkan tenant — dulu hanya bisa lewat Python (tidak layak produksi)."""
from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request

import pytest

from sdb_platform.control_plane.app import serve
from sdb_platform.control_plane.store import Store

ADMIN = "admin-key-status-" + "a" * 20
TKEY = "kunci-tenant-status-" + "t" * 20
PACK = {"id": "sdb-recon", "version": "1.0.0"}


@pytest.fixture()
def srv():
    store = Store(":memory:")
    tid = store.create_tenant(plan="pro")["tenant_id"]
    store.add_api_key(tid, TKEY)
    httpd = serve(store, ADMIN, "127.0.0.1", 0, None)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}", store, tid
    httpd.shutdown()
    httpd.server_close()


def _post(base, path, body, headers):
    req = urllib.request.Request(base + path, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def test_admin_menonaktifkan_tenant_lewat_http(srv):
    base, store, tid = srv
    status, payload = _post(base, f"/v1/admin/tenants/{tid}/status", {"status": "suspended"},
                            {"X-Admin-Key": ADMIN})
    assert status == 200, payload
    assert payload["tenant"]["status"] == "suspended"
    assert store.get_tenant(tid)["status"] == "suspended"


def test_tenant_tidak_boleh_mengubah_status_sendiri(srv):
    base, store, tid = srv
    status, payload = _post(base, f"/v1/admin/tenants/{tid}/status", {"status": "active"},
                            {"X-API-Key": TKEY})
    assert status == 401 and payload["error"]["code"] == "unauthorized"
    assert store.get_tenant(tid)["status"] == "active"


def test_status_tidak_sah_ditolak_400(srv):
    base, _, tid = srv
    status, payload = _post(base, f"/v1/admin/tenants/{tid}/status", {"status": "moon"},
                            {"X-Admin-Key": ADMIN})
    assert status == 400 and payload["error"]["code"] == "invalid_status"


def test_tenant_suspended_tidak_bisa_membuat_job(srv):
    base, _store, tid = srv
    _post(base, f"/v1/admin/tenants/{tid}/status", {"status": "suspended"}, {"X-Admin-Key": ADMIN})
    status, payload = _post(base, "/v1/jobs", {
        "type": "recon", "pack": PACK, "target_ref": f"artifact://{tid}/t/1",
        "budget": {"tokens": 5000, "seconds": 600}, "idempotency_key": "status-uji-0001"},
        {"X-API-Key": TKEY})
    assert status in (400, 403) and payload["error"]["code"] in ("tenant_inactive", "tenant_deleted"), payload


def test_tenant_tidak_ada_404(srv):
    base, _, _ = srv
    status, payload = _post(base, "/v1/admin/tenants/01JTAKADA00000000000000000/status",
                            {"status": "suspended"}, {"X-Admin-Key": ADMIN})
    assert status == 404 and payload["error"]["code"] == "tenant_not_found"
