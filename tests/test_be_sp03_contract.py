"""BE-SP-03 — API Contract Engineering (control plane v1).

Kontrak mesin : fixtures/contracts/control_plane_v1.json
Sumber perilaku: sdb_platform/control_plane/app.py + store.py (READ-ONLY — file
produksi tidak diubah oleh capability ini; mutasi T9 berjalan pada SALINAN di
tmp_path, bukan pada file repo).

T1  valid request -> 201 sesuai kontrak; GET 200; replay idempotent 200.
T2  setiap field wajib hilang -> error (status, code) persis seperti kontrak.
T3  payload tidak sesuai -> ditangani sesuai kontrak.
T4  tanpa/salah otorisasi -> 401 unauthorized; tenant suspended -> 403.
T5  isolasi tenant: job tenant lain -> 404 job_not_found (bukan 403).
T6  error envelope + header keamanan sesuai perilaku aktual.
T7  tabel error kontrak dieksekusi (executable spec) + janji response job_object.
T8  tidak ada kebocoran info sensitif.
T9  mutasi terarah pada salinan scratch: guard auth & field wajib 'type'.
T10 invarian sistem: stages/agents/BE-SP-12/registry tidak berubah.

Semua request lewat server loopback (Store :memory:, port 0) — tidak ada
koneksi ke luar, tidak ada data produksi.
"""
from __future__ import annotations

import glob
import hashlib
import http.client
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

import pytest

from sdb_platform.control_plane.app import serve
from sdb_platform.control_plane.store import Store

REPO = Path(__file__).resolve().parents[1]
CONTRACT_PATH = REPO / "fixtures" / "contracts" / "control_plane_v1.json"


def _synthetic_key(label: str) -> str:
    """Deterministic synthetic API key derived at runtime; no key-shaped literal lives in source."""
    return "syn-" + hashlib.sha256(f"sdb-be-sp03-synthetic:{label}".encode()).hexdigest()[:28]


KEY_A = _synthetic_key("key_a")
KEY_B = _synthetic_key("key_b")
KEY_S = _synthetic_key("key_s")
KEY_Q = _synthetic_key("key_q")
KEY_R = _synthetic_key("key_r")
KEY_QJ = _synthetic_key("key_qj")
ADMIN_KEY = _synthetic_key("admin_key")
WRONG_KEY = _synthetic_key("wrong_key")


def _load_contract() -> dict:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


CONTRACT = _load_contract()


def _valid_body(ik: str = "be-sp03-valid-0001") -> dict:
    return {
        "type": "recon",
        "pack": {"id": "be-sp03-pack", "version": "1.0.0"},
        "target_ref": "artifact://demo/fixture/1",
        "budget": {"tokens": 1000, "seconds": 60},
        "idempotency_key": ik,
    }


def _req(port: int, method: str, path: str, body: dict | None = None,
         headers: dict | None = None,
         raw: str | bytes | None = None) -> "tuple[int, Any, dict[str, str]]":
    """Request HTTP ke server loopback; kembalikan (status, payload, headers_lower)."""
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
    payload = raw if raw is not None else (json.dumps(body) if body is not None else None)
    hdrs = dict(headers or {})
    if payload is not None and "Content-Type" not in hdrs:
        hdrs["Content-Type"] = "application/json"
    conn.request(method, path, body=payload, headers=hdrs)
    resp = conn.getresponse()
    data = resp.read()
    headers_out = {k.lower(): v for k, v in resp.getheaders()}
    conn.close()
    try:
        parsed = json.loads(data)
    except (ValueError, UnicodeDecodeError):
        parsed = data.decode("utf-8", "replace")
    return resp.status, parsed, headers_out


def _raw_socket(port: int, request_bytes: bytes) -> tuple[int, dict]:
    """Kirim bytes mentah (untuk header cacat yang http.client tolak dibuatnya)."""
    with socket.create_connection(("127.0.0.1", port), timeout=30) as sock:
        sock.sendall(request_bytes)
        chunks = []
        while True:
            chunk = sock.recv(65536)
            if not chunk:
                break
            chunks.append(chunk)
    raw = b"".join(chunks)
    head, _, body = raw.partition(b"\r\n\r\n")
    status = int(head.split(b" ")[1])
    try:
        parsed = json.loads(body) if body else {}
    except ValueError:
        parsed = {}
    return status, parsed


@pytest.fixture(scope="module")
def plane():
    """Satu server loopback + Store :memory: untuk seluruh modul."""
    store = Store(":memory:")
    ta = store.create_tenant(plan="pro")["tenant_id"]
    tb = store.create_tenant(plan="pro")["tenant_id"]
    ts = store.create_tenant(plan="pro")["tenant_id"]
    tq = store.create_tenant(plan="starter")["tenant_id"]
    tqj = store.create_tenant(plan="starter", limits={"jobs_per_month": 2})["tenant_id"]
    tr = store.create_tenant(plan="pro", limits={"rate_per_min": 1})["tenant_id"]
    store.add_api_key(ta, KEY_A)
    store.add_api_key(tb, KEY_B)
    store.add_api_key(ts, KEY_S)
    store.add_api_key(tq, KEY_Q)
    store.add_api_key(tqj, KEY_QJ)
    store.add_api_key(tr, KEY_R)
    store.set_status(ts, "suspended")

    # Default rate dibesarkan HANYA untuk server uji: ~40 request lintas-test
    # dari tenant A tidak boleh memicu 429 palsu (kapasitas default 600/min =
    # ~20 token). Mekanisme limiter tetap diverifikasi penuh lewat tenant R
    # (override per-tenant rate_per_min=1) di T7. Tidak menyentuh source/produksi.
    old_rate = os.environ.get("SDB_RATE_PER_MIN")
    os.environ["SDB_RATE_PER_MIN"] = "60000"
    try:
        httpd = serve(store, ADMIN_KEY, port=0)
    finally:
        if old_rate is None:
            os.environ.pop("SDB_RATE_PER_MIN", None)
        else:
            os.environ["SDB_RATE_PER_MIN"] = old_rate
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield {
            "port": httpd.server_port,
            "ta": ta, "tb": tb, "tq": tq, "tqj": tqj,
            "store": store,
        }
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=10)


# ---------------------------------------------------------------- T1


def _check_type(value, decl: str) -> bool:
    base = decl.split(" ", 1)[0].split("{", 1)[0].strip()
    if decl.endswith("|null") and value is None:
        return True
    if base == "string":
        return isinstance(value, str)
    if base == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if base == "boolean":
        return isinstance(value, bool)
    if base == "object":
        return isinstance(value, dict)
    return True  # deklarasi deskriptif: keberadaan field tetap dicek terpisah


def test_t1_valid_request_sesuai_kontrak(plane):
    port, ta = plane["port"], plane["ta"]
    body = _valid_body("be-sp03-t1-0001")
    status, payload, headers = _req(
        port, "POST", "/v1/jobs", body, headers={"X-API-Key": KEY_A})

    post = next(e for e in CONTRACT["endpoints"] if e["route"] == "/v1/jobs")
    assert status == 201, post["success"][0]
    assert payload["replayed"] is False
    assert headers["content-type"].startswith("application/json")

    job = payload["job"]
    # Janji job_object: SEMUA field kontrak ada, dengan tipe yang cocok.
    assert set(job.keys()) == set(CONTRACT["job_object"].keys())
    for field, decl in CONTRACT["job_object"].items():
        assert _check_type(job[field], decl), f"field {field} tidak cocok tipe {decl}"
    assert job["tenant_id"] == ta
    assert job["type"] == "recon"
    assert job["pack"] == {"id": "be-sp03-pack", "version": "1.0.0"}
    assert job["budget"] == {"tokens": 1000, "seconds": 60}
    assert job["status"] == "queued"
    assert job["tokens_used"] == 0
    assert job["gate_verdict"] is None and job["finished_at"] is None
    assert re.fullmatch(r"j_[0-9A-HJKMNP-TV-Z]{26}", job["job_id"])
    jid = job["job_id"]

    # GET /v1/jobs/:id
    status, got, _ = _req(port, "GET", f"/v1/jobs/{jid}", headers={"X-API-Key": KEY_A})
    assert status == 200
    assert got["job"]["job_id"] == jid

    # Replay idempotent -> 200 + replayed True + job sama
    status, replay, _ = _req(
        port, "POST", "/v1/jobs", body, headers={"X-API-Key": KEY_A})
    assert status == 200
    assert replay["replayed"] is True
    assert replay["job"]["job_id"] == jid


# ---------------------------------------------------------------- T2


def test_t2_field_wajib_hilang_ditolak(plane):
    """Setiap required field kontrak: hilangkan -> (status, code) kontrak."""
    port = plane["port"]
    post = next(e for e in CONTRACT["endpoints"] if e["route"] == "/v1/jobs")
    for spec in post["request"]["required"]:
        body = _valid_body(f"be-sp03-t2-{spec['name'][:4]}-01")
        body.pop(spec["name"])
        status, payload, _ = _req(
            port, "POST", "/v1/jobs", body, headers={"X-API-Key": KEY_A})
        assert status == spec["error"]["status"], (
            f"tanpa {spec['name']}: status {status}, kontrak {spec['error']['status']}")
        assert payload["error"]["code"] == spec["error"]["code"], (
            f"tanpa {spec['name']}: code {payload['error']['code']}, "
            f"kontrak {spec['error']['code']}")


# ---------------------------------------------------------------- T3


def test_t3_payload_tidak_sesuai(plane):
    port = plane["port"]
    cases = [
        ("body bukan objek JSON", {"__raw__": "[1,2]"}, 400, "invalid_json"),
        ("type bukan string", {"type": 123}, 400, "invalid_type"),
        ("pack bukan objek", {"pack": "teks"}, 400, "invalid_pack"),
        ("pack.id tidak sah", {"pack": {"id": "X!", "version": "1.0.0"}}, 400, "invalid_pack"),
        ("pack.version bukan semver", {"pack": {"id": "be-sp03-pack", "version": "1.0"}}, 400, "invalid_pack"),
        ("budget bukan objek", {"budget": [1]}, 400, "invalid_budget"),
        ("budget.tokens bool", {"budget": {"tokens": True, "seconds": 60}}, 400, "invalid_budget"),
        ("budget.tokens di bawah minimum", {"budget": {"tokens": 999, "seconds": 60}}, 400, "invalid_budget"),
        ("budget.seconds di bawah minimum", {"budget": {"tokens": 1000, "seconds": 59}}, 400, "invalid_budget"),
        ("target_ref skema salah", {"target_ref": "http://contoh"}, 400, "invalid_target"),
        ("idempotency_key terlalu pendek", {"idempotency_key": "abc1234"}, 400, "invalid_idempotency_key"),
    ]
    for label, field, exp_status, exp_code in cases:
        if "__raw__" in field:
            status, payload, _ = _req(
                port, "POST", "/v1/jobs", headers={"X-API-Key": KEY_A},
                raw=field["__raw__"])
        else:
            body = _valid_body(f"be-sp03-t3-{exp_code[:6]}-{label[:4]}")
            body.update(field)
            status, payload, _ = _req(
                port, "POST", "/v1/jobs", body, headers={"X-API-Key": KEY_A})
        assert status == exp_status, f"{label}: status {status} != {exp_status}"
        assert payload["error"]["code"] == exp_code, f"{label}: {payload}"


# ---------------------------------------------------------------- T4


def test_t4_tanpa_otorisasi_ditolak(plane):
    port = plane["port"]
    body = _valid_body("be-sp03-t4-0001")

    status, payload, _ = _req(port, "POST", "/v1/jobs", body)
    assert (status, payload["error"]["code"]) == (401, "unauthorized")

    status, payload, _ = _req(
        port, "POST", "/v1/jobs", body, headers={"X-API-Key": WRONG_KEY})
    assert (status, payload["error"]["code"]) == (401, "unauthorized")

    # Key admin TIDAK berlaku di rute tenant.
    status, payload, _ = _req(
        port, "POST", "/v1/jobs", body, headers={"X-API-Key": ADMIN_KEY})
    assert (status, payload["error"]["code"]) == (401, "unauthorized")

    status, payload, _ = _req(port, "GET", "/v1/jobs/j_doesnotmatter0000000")
    assert (status, payload["error"]["code"]) == (401, "unauthorized")

    # Tenant aktif-key tapi suspended -> 403 tenant_inactive (authz).
    status, payload, _ = _req(
        port, "POST", "/v1/jobs", _valid_body("be-sp03-t4-0002"),
        headers={"X-API-Key": KEY_S})
    assert (status, payload["error"]["code"]) == (403, "tenant_inactive")


# ---------------------------------------------------------------- T5


def test_t5_isolasi_tenant(plane):
    port = plane["port"]
    ik = "be-sp03-t5-shared-01"
    status, created, _ = _req(
        port, "POST", "/v1/jobs", _valid_body(ik), headers={"X-API-Key": KEY_A})
    assert status == 201
    jid_a = created["job"]["job_id"]

    # Tenant B membaca job tenant A -> 404 job_not_found (bukan 403): tidak bocor.
    status, payload, _ = _req(
        port, "GET", f"/v1/jobs/{jid_a}", headers={"X-API-Key": KEY_B})
    assert (status, payload["error"]["code"]) == (404, "job_not_found")

    # Idempotency unik PER TENANT: key sama di tenant B = job B sendiri (201 baru).
    status, again, _ = _req(
        port, "POST", "/v1/jobs", _valid_body(ik), headers={"X-API-Key": KEY_B})
    assert status == 201
    assert again["job"]["job_id"] != jid_a
    jid_b = again["job"]["job_id"]

    # Tenant B membaca job miliknya sendiri -> 200.
    status, got, _ = _req(port, "GET", f"/v1/jobs/{jid_b}", headers={"X-API-Key": KEY_B})
    assert status == 200 and got["job"]["job_id"] == jid_b
    assert got["job"]["tenant_id"] == plane["tb"]


# ---------------------------------------------------------------- T6


def test_t6_error_envelope_dan_header(plane):
    port = plane["port"]
    samples = [
        (401, _req(port, "POST", "/v1/jobs", _valid_body("be-sp03-t6-01"))),
        (400, _req(port, "POST", "/v1/jobs", _valid_body("be-sp03-t6-02"),
                   headers={"X-API-Key": KEY_A, "Content-Type": "text/plain"},
                   raw=b"{bukan json")),
        (404, _req(port, "GET", "/v1/jobs/j_tidakada0000000000000000",
                   headers={"X-API-Key": KEY_A})),
        (404, _req(port, "POST", "/v1/tidak-ada", None, headers={"X-API-Key": KEY_A})),
        (410, _req(port, "POST", "/v1/jobs/j_apapun00000000000/finish",
                   headers={"X-API-Key": KEY_A})),
    ]
    for exp_status, (status, payload, headers) in samples:
        assert status == exp_status, (status, payload)
        assert set(payload.keys()) == {"error"}, payload
        assert set(payload["error"].keys()) == {"code", "message"}, payload
        assert isinstance(payload["error"]["code"], str) and payload["error"]["code"]
        assert isinstance(payload["error"]["message"], str) and payload["error"]["message"]
        assert headers["x-content-type-options"] == "nosniff"
        assert headers["cache-control"] == "no-store"
        assert headers["content-type"].startswith("application/json")

    # Header Content-Length cacat -> 400 invalid_content_length (socket mentah).
    status, payload = _raw_socket(
        port,
        b"POST /v1/jobs HTTP/1.1\r\nHost: t\r\nX-API-Key: " + KEY_A.encode()
        + b"\r\nContent-Length: abc\r\n\r\n{}")
    assert (status, payload["error"]["code"]) == (400, "invalid_content_length")

    # Body > 256 KB -> 413 body_too_large.
    status, payload, _ = _req(
        port, "POST", "/v1/jobs", headers={"X-API-Key": KEY_A},
        raw=b"x" * (256 * 1024 + 1))
    assert (status, payload["error"]["code"]) == (413, "body_too_large")


# ---------------------------------------------------------------- T7


def test_t7_error_table_executable(plane):
    """Setiap baris errors[] kontrak dipicu dan hasilnya harus identik."""
    port = plane["port"]
    post = next(e for e in CONTRACT["endpoints"] if e["route"] == "/v1/jobs")
    get = next(e for e in CONTRACT["endpoints"] if e["route"] == "/v1/jobs/:id")

    def trig_unauthorized():
        return _req(port, "POST", "/v1/jobs", _valid_body("be-sp03-t7-01"))

    def trig_invalid_type():
        b = _valid_body("be-sp03-t7-02")
        b["type"] = "bukan-tipe"
        return _req(port, "POST", "/v1/jobs", b, headers={"X-API-Key": KEY_A})

    def trig_invalid_pack():
        b = _valid_body("be-sp03-t7-03")
        b["pack"] = "teks"
        return _req(port, "POST", "/v1/jobs", b, headers={"X-API-Key": KEY_A})

    def trig_invalid_target():
        b = _valid_body("be-sp03-t7-04")
        b["target_ref"] = "http://x"
        return _req(port, "POST", "/v1/jobs", b, headers={"X-API-Key": KEY_A})

    def trig_invalid_budget():
        b = _valid_body("be-sp03-t7-05")
        b["budget"] = {"tokens": 999, "seconds": 60}
        return _req(port, "POST", "/v1/jobs", b, headers={"X-API-Key": KEY_A})

    def trig_invalid_idempotency_key():
        b = _valid_body("be-sp03-t7-06")
        b["idempotency_key"] = "abc1234"
        return _req(port, "POST", "/v1/jobs", b, headers={"X-API-Key": KEY_A})

    def trig_invalid_json():
        return _req(port, "POST", "/v1/jobs", headers={"X-API-Key": KEY_A}, raw="[1,2]")

    def trig_invalid_content_length():
        st, pl = _raw_socket(
            port, b"POST /v1/jobs HTTP/1.1\r\nHost: t\r\nX-API-Key: "
            + KEY_A.encode() + b"\r\nContent-Length: abc\r\n\r\n{}")
        return st, pl, {}

    def trig_body_too_large():
        return _req(port, "POST", "/v1/jobs", headers={"X-API-Key": KEY_A},
                    raw=b"x" * (256 * 1024 + 1))

    def trig_tenant_inactive():
        return _req(port, "POST", "/v1/jobs", _valid_body("be-sp03-t7-07"),
                    headers={"X-API-Key": KEY_S})

    def trig_quota_tokens_exceeded():
        # starter: 2_000_000 token/bulan; job 1.5jt -> sisa 0.5jt < budget 1jt.
        b1 = _valid_body("be-sp03-t7-q1")
        b1["budget"] = {"tokens": 1_500_000, "seconds": 60}
        st, pl, _ = _req(port, "POST", "/v1/jobs", b1, headers={"X-API-Key": KEY_Q})
        assert st == 201, (st, pl)
        b2 = _valid_body("be-sp03-t7-q2")
        b2["budget"] = {"tokens": 1_000_000, "seconds": 60}
        return _req(port, "POST", "/v1/jobs", b2, headers={"X-API-Key": KEY_Q})

    def trig_quota_jobs_exceeded():
        # limits.jobs_per_month = 2: dua job lalu ketiga ditolak.
        for i in (1, 2):
            b = _valid_body(f"be-sp03-t7-qj{i}")
            st, pl, _ = _req(port, "POST", "/v1/jobs", b, headers={"X-API-Key": KEY_QJ})
            assert st == 201, (st, pl)
        return _req(port, "POST", "/v1/jobs", _valid_body("be-sp03-t7-qj3"),
                    headers={"X-API-Key": KEY_QJ})

    def trig_idempotency_conflict():
        _req(port, "POST", "/v1/jobs", _valid_body("be-sp03-t7-ic1"),
             headers={"X-API-Key": KEY_A})
        b = _valid_body("be-sp03-t7-ic1")
        b["target_ref"] = "artifact://beda/1"
        return _req(port, "POST", "/v1/jobs", b, headers={"X-API-Key": KEY_A})

    def trig_rate_limited():
        # rate_per_min=1 -> kapasitas bucket 5; 8 request serial memicu 429.
        results = []
        for i in range(8):
            st, pl, hd = _req(port, "POST", "/v1/jobs", _valid_body(f"be-sp03-t7-rl{i}"),
                              headers={"X-API-Key": KEY_R})
            results.append((st, pl, hd))
        limited = [r for r in results if r[0] == 429]
        assert limited, "8 request serial pada tenant rate 1/menit harus memicu 429"
        for _, pl, hd in limited:
            assert pl["error"]["code"] == "rate_limited"
            assert int(hd["retry-after"]) >= 1
        # Invarian kontrak: banjir tenant R tidak boleh mengganggu tenant A.
        st, pl, _ = _req(port, "POST", "/v1/jobs", _valid_body("be-sp03-t7-rl-other"),
                         headers={"X-API-Key": KEY_A})
        assert st == 201, "tenant lain harus tetap terlayani saat tenant R dibatasi"
        return limited[0]

    def trig_get_unauthorized():
        return _req(port, "GET", "/v1/jobs/j_apapun000000000000000")

    def trig_get_job_not_found():
        return _req(port, "GET", "/v1/jobs/j_tidakada000000000000000",
                    headers={"X-API-Key": KEY_A})

    triggers_post = {
        "invalid_json": trig_invalid_json,
        "invalid_content_length": trig_invalid_content_length,
        "body_too_large": trig_body_too_large,
        "unauthorized": trig_unauthorized,
        "tenant_inactive": trig_tenant_inactive,
        "quota_jobs_exceeded": trig_quota_jobs_exceeded,
        "quota_tokens_exceeded": trig_quota_tokens_exceeded,
        "idempotency_conflict": trig_idempotency_conflict,
        "rate_limited": trig_rate_limited,
    }
    # Field wajib: error kontraknya dideklarasikan di required[].error.
    field_triggers = {
        "type": trig_invalid_type,
        "pack": trig_invalid_pack,
        "target_ref": trig_invalid_target,
        "budget": trig_invalid_budget,
        "idempotency_key": trig_invalid_idempotency_key,
    }
    triggers_get = {
        "unauthorized": trig_get_unauthorized,
        "job_not_found": trig_get_job_not_found,
    }
    # Kontrak dan test harus sejalan: tidak ada baris kontrak tanpa trigger.
    post_codes = ({spec["error"]["code"] for spec in post["request"]["required"]}
                  | {e["code"] for e in post["errors"]})
    assert post_codes == (set(triggers_post)
                          | {spec["error"]["code"]
                             for spec in post["request"]["required"]})
    assert {spec["name"] for spec in post["request"]["required"]} == set(field_triggers)
    assert {e["code"] for e in get["errors"]} == set(triggers_get)

    for spec in post["request"]["required"]:
        status, payload, _ = field_triggers[spec["name"]]()
        assert status == spec["error"]["status"], (
            f"{spec['name']}: {status} != {spec['error']['status']}")
        assert payload["error"]["code"] == spec["error"]["code"], spec["name"]

    for spec in post["errors"]:
        status, payload, _ = triggers_post[spec["code"]]()
        assert status == spec["status"], f"{spec['code']}: {status} != {spec['status']}"
        assert payload["error"]["code"] == spec["code"], spec["code"]

    for spec in get["errors"]:
        status, payload, _ = triggers_get[spec["code"]]()
        assert status == spec["status"], f"{spec['code']}: {status} != {spec['status']}"
        assert payload["error"]["code"] == spec["code"], spec["code"]

    # Sukses persis seperti kontrak: 201 baru / 200 replay / 200 GET.
    st, pl, _ = _req(port, "POST", "/v1/jobs", _valid_body("be-sp03-t7-ok1"),
                     headers={"X-API-Key": KEY_A})
    assert st == 201 and pl["replayed"] is False
    st, pl, _ = _req(port, "POST", "/v1/jobs", _valid_body("be-sp03-t7-ok1"),
                     headers={"X-API-Key": KEY_A})
    assert st == 200 and pl["replayed"] is True
    jid = pl["job"]["job_id"]
    st, pl, _ = _req(port, "GET", f"/v1/jobs/{jid}", headers={"X-API-Key": KEY_A})
    assert st == 200

    # Janji job_object: field eksak sama dengan kontrak (breaking change gagal).
    assert set(pl["job"].keys()) == set(CONTRACT["job_object"].keys())


# ---------------------------------------------------------------- T8


def test_t8_tidak_ada_info_sensitif_bocor(plane):
    port = plane["port"]
    # Key yang salah tidak boleh di-echo balik.
    status, payload, _ = _req(
        port, "POST", "/v1/jobs", _valid_body("be-sp03-t8-01"),
        headers={"X-API-Key": WRONG_KEY})
    blob = json.dumps(payload)
    assert WRONG_KEY not in blob
    assert "Traceback" not in blob and "/home/" not in blob and ".py" not in blob

    # Response job tidak memuat kunci/basis data internal.
    status, payload, _ = _req(
        port, "POST", "/v1/jobs", _valid_body("be-sp03-t8-02"),
        headers={"X-API-Key": KEY_A})
    blob = json.dumps(payload)
    assert KEY_A not in blob
    for banned in ("key_hash", "api_key", "sha256", "password", "secret", "token_"):
        assert banned not in blob.lower(), banned

    # 404 lintas tenant tidak menyebut tenant pemilik.
    status, payload, _ = _req(
        port, "GET", f"/v1/jobs/{payload['job']['job_id']}",
        headers={"X-API-Key": KEY_B})
    assert status == 404
    blob = json.dumps(payload)
    assert plane["ta"] not in blob
    assert payload["error"]["message"] == "job tidak ditemukan"

    # Semua response membawa header keamanan kontrak.
    _, _, headers_ok = _req(port, "GET", "/v1/jobs/j_apapun000000000000000",
                            headers={"X-API-Key": KEY_A})
    assert headers_ok["x-content-type-options"] == "nosniff"
    assert headers_ok["cache-control"] == "no-store"
    assert headers_ok["content-type"].startswith("application/json")


# ---------------------------------------------------------------- T9 (mutasi pada salinan scratch)

MUT_FILES = [
    "sdb_platform/__init__.py",
    "sdb_platform/control_plane/__init__.py",
    "sdb_platform/control_plane/app.py",
    "sdb_platform/control_plane/store.py",
    "sdb_platform/control_plane/metrics.py",
    "sdb_platform/control_plane/billing.py",
]

DRIVER_SOURCE = '''\
import hashlib
import sys

root, mode = sys.argv[1], sys.argv[2]
sys.path.insert(0, root)

from sdb_platform.control_plane.app import Api
from sdb_platform.control_plane.store import Store

KEY = "syn-" + hashlib.sha256(b"sdb-be-sp03-synthetic:driver").hexdigest()[:28]


def main():
    store = Store(":memory:")
    tid = store.create_tenant(plan="pro")["tenant_id"]
    store.add_api_key(tid, KEY)
    api = Api(store, "syn-" + hashlib.sha256(b"sdb-be-sp03-synthetic:driver-admin").hexdigest()[:28])
    body = {
        "type": "recon",
        "pack": {"id": "be-sp03-pack", "version": "1.0.0"},
        "target_ref": "artifact://mutasi/x/1",
        "budget": {"tokens": 1000, "seconds": 60},
        "idempotency_key": "be-sp03-mut-0001",
    }
    headers = {}
    if mode == "mandatory":
        body.pop("type")
        headers = {"x-api-key": KEY}
    try:
        status, payload = api.handle("POST", "/v1/jobs", headers, body)
        code = payload.get("error", {}).get("code", "") if isinstance(payload, dict) else ""
        print("RESULT %s %s" % (status, code))
    except Exception as exc:
        print("RESULT %s %s" % (getattr(exc, "status", "EXC"),
                                 getattr(exc, "code", type(exc).__name__)))


main()
'''


def _make_module_copy(tmp_path: Path) -> Path:
    root = tmp_path / "modroot"
    for rel in MUT_FILES:
        dst = root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO / rel, dst)
    return root


def _run_driver(root: Path, mode: str) -> str:
    proc = subprocess.run(
        [sys.executable, str(_driver_path(root.parent)), str(root), mode],
        capture_output=True, text=True, timeout=120)
    lines = [ln for ln in proc.stdout.splitlines() if ln.startswith("RESULT")]
    assert lines, f"driver tanpa output: rc={proc.returncode} err={proc.stderr[-400:]}"
    return lines[0]


def _driver_path(parent: Path) -> Path:
    path = parent / "driver_be_sp03.py"
    path.write_text(DRIVER_SOURCE, encoding="utf-8")
    return path


def _mutate(path: Path, old: str, new: str) -> None:
    src = path.read_text(encoding="utf-8")
    assert src.count(old) == 1, f"anchor mutasi tidak unik di {path.name}"
    path.write_text(src.replace(old, new), encoding="utf-8")


def test_t9_mutation_authorization_guard_dihapus(tmp_path):
    """Skenario: guard `tid = self._tenant(h)` di POST /v1/jobs dihapus pada
    SALINAN scratch. Kontrak T4 (tanpa otorisasi -> 401) harus membunuh mutan."""
    root = _make_module_copy(tmp_path)

    healthy = _run_driver(root, "guard")
    assert healthy == "RESULT 401 unauthorized", healthy

    _mutate(
        root / "sdb_platform/control_plane/app.py",
        '        if method == "POST" and path == "/v1/jobs":\n'
        '            tid = self._tenant(h)',
        '        if method == "POST" and path == "/v1/jobs":\n'
        '            tid = ""  # BE-SP-03 MUTATION: authorization guard removed')

    mutated = _run_driver(root, "guard")
    assert mutated != "RESULT 401 unauthorized", (
        "mutasi guard TIDAK terdeteksi — contract test gagal membunuh mutan")
    assert mutated == "RESULT 404 tenant_not_found", mutated


def test_t9_mutation_field_wajib_type_dihapus(tmp_path):
    """Skenario: validasi mandatory field `type` dihapus pada SALINAN scratch.
    Kontrak T2 (tanpa type -> 400 invalid_type) harus membunuh mutan."""
    root = _make_module_copy(tmp_path)

    healthy = _run_driver(root, "mandatory")
    assert healthy == "RESULT 400 invalid_type", healthy

    _mutate(
        root / "sdb_platform/control_plane/store.py",
        '        _require(isinstance(type, str) and type in JOB_TYPES, 400, "invalid_type",\n'
        '                 f"type harus salah satu {JOB_TYPES}")',
        '        pass  # BE-SP-03 MUTATION: mandatory field "type" validation removed')

    mutated = _run_driver(root, "mandatory")
    assert mutated != "RESULT 400 invalid_type", (
        "mutasi field wajib TIDAK terdeteksi — contract test gagal membunuh mutan")
    assert mutated.startswith("RESULT 201"), mutated


# ---------------------------------------------------------------- T10


def test_t10_invarian_sistem_tidak_berubah():
    # Stage registry: 19 tahap, satu-satunya daftar sah.
    stages_text = (REPO / "workflows" / "stages.yaml").read_text(encoding="utf-8")
    assert len(re.findall(r"^\s*- code:", stages_text, flags=re.M)) == 19

    # Agent definitions: 9 divisi.
    assert len(glob.glob(str(REPO / "agents" / "*.yaml"))) == 9

    # Kontrak BE-SP-12 (capability sebelumnya) tetap utuh.
    assert (REPO / "docs" / "BE_SP12_EVIDENCE_CONTRACT.md").is_file()
    assert (REPO / "tests" / "test_capability_evidence.py").is_file()

    # Registry pilot masih memuat BE-SP-12 dan kini BE-SP-03.
    pilot = (REPO / "registry" / "capability_pilot.yaml").read_text(encoding="utf-8")
    assert "BE-SP-12" in pilot
    assert "BE-SP-03" in pilot

    # Evidence CLI BE-SP-12 masih bisa dikompilasi (tidak diubah capability ini).
    cli = REPO / "scripts" / "sdb_capability_evidence.py"
    compile(cli.read_text(encoding="utf-8"), str(cli), "exec")

    # CI workflow tidak disentuh scope ini.
    assert (REPO / ".github" / "workflows" / "ci.yml").is_file()

    # Kontrak ini hanya mencakup 2 keluarga endpoint + 1 endpoint dicabut.
    assert len(CONTRACT["endpoints"]) == 2
    assert {e["route"] for e in CONTRACT["endpoints"]} == {"/v1/jobs", "/v1/jobs/:id"}
    assert CONTRACT["removed_endpoints"][0]["route"] == "/v1/jobs/:id/finish"
