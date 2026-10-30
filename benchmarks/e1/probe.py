"""Probe buta (black-box) terhadap target E1 — Zona A, D1.

Hanya HTTP: tidak membaca source target. Keluaran = observations.json
(bukti observasi ber-Evidence ID) yang menjadi dasar SPEC.md.

Jalankan: python3 benchmarks/e1/probe.py http://127.0.0.1:8110
"""

import http.client
import json
import sys
from urllib.parse import urlparse

OBS = []


def call(base, method, path, body=None, token=None):
    u = urlparse(base)
    conn = http.client.HTTPConnection(u.hostname, u.port or 80, timeout=10)
    headers = {}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    conn.request(method, path, body=data, headers=headers)
    r = conn.getresponse()
    raw = r.read()
    conn.close()
    try:
        parsed = json.loads(raw) if raw else None
    except json.JSONDecodeError:
        parsed = raw.decode(errors="replace")
    return r.status, parsed


def obs(eid, desc, method, path, **kw):
    st, body = call(BASE, method, path, **kw)
    OBS.append({"id": eid, "desc": desc, "method": method, "path": path,
                "status": st, "body": body})
    return st, body


if __name__ == "__main__":
    BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8110"

    obs("E1", "health endpoint", "GET", "/health")
    obs("E2", "daftar item awal", "GET", "/api/items")
    st, tok = obs("E3", "login password benar", "POST", "/api/login", body={"password": "rahasia-demo"})
    obs("E4", "login password salah", "POST", "/api/login", body={"password": "salah"})
    token = (tok or {}).get("token") if isinstance(tok, dict) else None
    st, created = obs("E5", "buat item tanpa token", "POST", "/api/items", body={"name": "x"})
    st, created = obs("E6", "buat item dengan token", "POST", "/api/items",
                      body={"name": "item-probe"}, token=token)
    iid = created.get("id") if isinstance(created, dict) else None
    obs("E7", "buat item nama kosong", "POST", "/api/items", body={"name": "   "}, token=token)
    obs("E8", "ambil item ada", "GET", f"/api/items/{iid}")
    obs("E9", "ambil item tidak ada", "GET", "/api/items/999999")
    obs("E10", "ubah nama item", "PATCH", f"/api/items/{iid}", body={"name": "item-ubah"}, token=token)
    obs("E11", "ubah tanpa token", "PATCH", f"/api/items/{iid}", body={"name": "y"})
    obs("E12", "paginasi limit=1 offset=1", "GET", "/api/items?limit=1&offset=1")
    obs("E13", "filter completed=true", "GET", "/api/items?completed=true")
    obs("E14", "filter completed=false", "GET", "/api/items?completed=false")
    obs("E15", "hapus item", "DELETE", f"/api/items/{iid}", token=token)
    obs("E16", "hapus lagi (sudah tidak ada)", "DELETE", f"/api/items/{iid}", token=token)

    print(json.dumps(OBS, indent=1))
