"""10 uji buta E1 — dijalankan identik pada target, replika SPEC, dan kontrol naif.

Uji diturunkan dari SPEC (perilaku), bukan dari kode. Tiap uji membersihkan
item yang ia buat agar urutan tidak memengaruhi hasil.
Jalankan: python3 benchmarks/e1/checks.py <base_url>
"""

import http.client
import json
import os
import sys
from urllib.parse import urlparse

# Kredensial FIXTURE lokal (bukan rahasia); dapat ditimpa env untuk CI.
PASSWORD = os.environ.get("E1_PASSWORD", "rahasia-demo")
TOKEN = os.environ.get("E1_TOKEN", "tok-e1-demo")


def req(base, method, path, body=None, token=None):
    u = urlparse(base)
    conn = http.client.HTTPConnection(u.hostname, u.port or 80, timeout=10)
    headers = {}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = "Bearer " + token
    try:
        conn.request(method, path, body=data, headers=headers)
        r = conn.getresponse()
        raw = r.read()
        status = r.status
    finally:
        conn.close()
    try:
        parsed = json.loads(raw) if raw else None
    except json.JSONDecodeError:
        parsed = None
    return status, parsed


def _login(base):
    _st, body = req(base, "POST", "/api/login", {"password": PASSWORD})
    return body.get("token") if isinstance(body, dict) else None


def _create(base, name, token, **extra):
    payload = {"name": name, **extra}
    return req(base, "POST", "/api/items", payload, token=token)


def _cleanup(base, iid, token):
    # Kegagalan bersih-bersih tidak boleh menutupi hasil uji utama; cukup dicatat.
    try:
        req(base, "DELETE", f"/api/items/{iid}", token=token)
    except (OSError, http.client.HTTPException, ValueError) as exc:
        print(f"  (bersih-bersih gagal id={iid}: {type(exc).__name__})", file=sys.stderr)


def f01(base):
    st, b = req(base, "GET", "/health")
    return st == 200 and isinstance(b, dict) and b.get("status") == "ok", f"{st} {b}"


def f02(base):
    st, b = req(base, "GET", "/api/items")
    if st != 200 or not isinstance(b, list):
        return False, f"{st} bukan larik"
    ids = {r.get("id") for r in b if isinstance(r, dict)}
    bools = all(isinstance(r.get("completed"), bool) for r in b if isinstance(r, dict))
    return {1, 2, 3} <= ids and bools, f"ids={sorted(i for i in ids if i is not None)[:5]} bool={bools}"


def f03(base):
    tok = _login(base)
    if not tok:
        return False, "login gagal"
    st, b = _create(base, "uji-f03", tok)
    ok = st == 201 and isinstance(b, dict) and b.get("name") == "uji-f03" and isinstance(b.get("id"), int)
    if isinstance(b, dict) and isinstance(b.get("id"), int):
        _cleanup(base, b["id"], tok)
    return ok, f"{st} {b}"


def f04(base):
    st1, b1 = req(base, "GET", "/api/items/1")
    st2, b2 = req(base, "GET", "/api/items/987654")
    ok404 = st2 == 404 and isinstance(b2, dict) and b2.get("error") == "not found"
    return st1 == 200 and isinstance(b1, dict) and b1.get("id") == 1 and ok404, f"{st1}/{st2}"


def f05(base):
    tok = _login(base)
    if not tok:
        return False, "login gagal"
    st, created = _create(base, "uji-f05-a", tok)
    if st != 201 or not isinstance(created, dict):
        return False, f"buat gagal {st}"
    iid = created["id"]
    stp, patched = req(base, "PATCH", f"/api/items/{iid}", {"name": "uji-f05-b"}, token=tok)
    stq, _ = req(base, "PATCH", f"/api/items/{iid}", {"name": "x"})
    _cleanup(base, iid, tok)
    return stp == 200 and isinstance(patched, dict) and patched.get("name") == "uji-f05-b" and stq == 401, f"{stp}/{stq}"


def f06(base):
    tok = _login(base)
    if not tok:
        return False, "login gagal"
    st, created = _create(base, "uji-f06", tok)
    if st != 201 or not isinstance(created, dict):
        return False, f"buat gagal {st}"
    iid = created["id"]
    std, body = req(base, "DELETE", f"/api/items/{iid}", token=tok)
    st2, _ = req(base, "DELETE", f"/api/items/{iid}", token=tok)
    return std == 204 and body is None and st2 == 404, f"{std} body={body} ulang={st2}"


def f07(base):
    st, b = req(base, "POST", "/api/login", {"password": PASSWORD})
    ok1 = st == 200 and isinstance(b, dict) and isinstance(b.get("token"), str) and b["token"]
    st2, b2 = req(base, "POST", "/api/login", {"password": "salah"})
    ok2 = st2 == 401 and isinstance(b2, dict) and b2.get("error") == "unauthorized"
    return ok1 and ok2, f"{st}/{st2}"


def f08(base):
    tok = _login(base)
    if not tok:
        return False, "login gagal"
    st, b = _create(base, "   ", tok)
    return st == 422 and isinstance(b, dict) and b.get("error") == "name wajib diisi", f"{st} {b}"


def f09(base):
    st, b = req(base, "GET", "/api/items?limit=1&offset=1")
    ok = st == 200 and isinstance(b, list) and len(b) == 1 and b[0].get("id") == 2
    return ok, f"{st} {b}"


def f10(base):
    st1, b1 = req(base, "GET", "/api/items?completed=true")
    st2, b2 = req(base, "GET", "/api/items?completed=false")
    ok1 = st1 == 200 and isinstance(b1, list) and b1 and all(r.get("completed") is True for r in b1)
    ok2 = st2 == 200 and isinstance(b2, list) and len(b2) >= 2 and all(r.get("completed") is False for r in b2)
    return ok1 and ok2, f"true={len(b1) if isinstance(b1, list) else '?'} false={len(b2) if isinstance(b2, list) else '?'}"


CHECKS = [("F01", f01), ("F02", f02), ("F03", f03), ("F04", f04), ("F05", f05),
          ("F06", f06), ("F07", f07), ("F08", f08), ("F09", f09), ("F10", f10)]


def run(base):
    results = []
    for fid, fn in CHECKS:
        try:
            ok, note = fn(base)
        except (OSError, http.client.HTTPException, KeyError, ValueError) as exc:
            # satu fitur error = gagal fitur itu, bukan crash seluruh benchmark
            ok, note = False, f"exception {type(exc).__name__}: {exc}"
        results.append({"id": fid, "pass": bool(ok), "note": note})
    return results


if __name__ == "__main__":
    base = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8110"
    res = run(base)
    passed = sum(1 for r in res if r["pass"])
    for r in res:
        print(f"{r['id']} {'PASS' if r['pass'] else 'FAIL'}  {r['note']}")
    print(f"skor={passed}/{len(res)}")
