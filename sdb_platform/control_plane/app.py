"""HTTP tipis di atas Store — stdlib `http.server`, tanpa framework.

Kenapa tanpa FastAPI: Fase 2 harus membuktikan *kontrak* (isolasi tenant, kuota, idempotensi,
redaksi artefak) dengan permukaan sekecil mungkin. Menambah framework sekarang hanya menambah
permukaan serangan dan dependensi yang harus diaudit.

Jalankan:  SDB_ADMIN_KEY=... python3 -m sdb_platform.control_plane.app --db data/control.db --port 8088
"""
from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .store import ControlPlaneError, Store

JOB_ARTIFACTS_RE = re.compile(r"^/v1/jobs/([A-Za-z0-9_]+)/artifacts$")
JOB_HEARTBEAT_RE = re.compile(r"^/v1/jobs/([A-Za-z0-9_]+)/heartbeat$")
JOB_COMPLETE_RE = re.compile(r"^/v1/jobs/([A-Za-z0-9_]+)/complete$")
JOB_CANCEL_RE = re.compile(r"^/v1/jobs/([A-Za-z0-9_]+)/cancel$")
JOB_FINISH_RE = re.compile(r"^/v1/jobs/([A-Za-z0-9_]+)/finish$")
JOB_RE = re.compile(r"^/v1/jobs/([A-Za-z0-9_]+)$")
MAX_BODY = 256 * 1024


class Api:
    def __init__(self, store: Store, admin_key: str, worker_key: str | None = None):
        if len(admin_key) < 24:
            raise SystemExit("admin key minimal 24 karakter")
        if worker_key is not None and len(worker_key) < 24:
            raise SystemExit("worker key minimal 24 karakter")
        self.store = store
        self.admin_key = admin_key
        self.worker_key = worker_key
        # MVP satu proses: serialisasi semua mutasi supaya cek-kuota + INSERT tidak balapan.
        # Skala horizontal nanti = Postgres dengan transaksi/row lock, bukan mengandalkan lock ini.
        self.lock = threading.Lock()

    def _admin(self, headers: dict) -> None:
        if not secrets.compare_digest(headers.get("x-admin-key", ""), self.admin_key):
            raise ControlPlaneError(401, "unauthorized", "X-Admin-Key tidak sah")

    def _worker(self, headers: dict) -> None:
        if not self.worker_key:
            raise ControlPlaneError(503, "worker_disabled", "endpoint worker tidak diaktifkan")
        if not secrets.compare_digest(headers.get("x-worker-key", ""), self.worker_key):
            raise ControlPlaneError(401, "unauthorized", "X-Worker-Key tidak sah")

    def _tenant(self, headers: dict) -> str:
        key = headers.get("x-api-key", "")
        if not key:
            raise ControlPlaneError(401, "unauthorized", "X-API-Key wajib")
        return self.store.tenant_for_key(key)

    def handle(self, method: str, path: str, headers: dict, body: dict | None) -> tuple[int, dict]:
        h = {k.lower(): v for k, v in headers.items()}
        body = body or {}

        if method == "GET" and path == "/healthz":
            return 200, {"status": "ok"}

        if method == "POST" and path == "/v1/tenants":
            self._admin(h)
            tenant = self.store.create_tenant(
                plan=body.get("plan", ""), name=body.get("name"),
                isolation=body.get("isolation", "pool"), limits=body.get("limits"))
            key = self.store.add_api_key(tenant["tenant_id"])
            return 201, {"tenant": tenant, "api_key": key}

        if method == "POST" and path == "/v1/jobs":
            tid = self._tenant(h)
            job, replayed = self.store.create_job(
                tid, body.get("type", ""), body.get("pack") or {}, body.get("target_ref", ""),
                body.get("budget") or {}, body.get("idempotency_key", ""))
            return (200 if replayed else 201), {"job": job, "replayed": replayed}

        m = JOB_FINISH_RE.match(path)
        if method == "POST" and m:
            tid = self._tenant(h)
            return 200, {"job": self.store.finish_job(
                tid, m.group(1), body.get("status", ""), body.get("tokens_used", -1),
                body.get("gate_verdict"))}

        m = JOB_ARTIFACTS_RE.match(path)
        if m:
            tid = self._tenant(h)
            if method == "GET":
                return 200, {"artifacts": self.store.list_artifacts(tid, m.group(1))}
            if method == "POST":
                art = self.store.register_artifact(
                    tid, m.group(1), body.get("kind", ""), body.get("sha256", ""),
                    body.get("size", -1), body.get("redaction_status", ""),
                    body.get("retention_until", ""), body.get("uri", ""), body.get("media_type"))
                return 201, {"artifact": art}

        m = JOB_RE.match(path)
        if method == "GET" and m:
            tid = self._tenant(h)
            return 200, {"job": self.store.get_job(tid, m.group(1))}

        if method == "GET" and path == "/v1/usage":
            return 200, {"usage": self.store.usage(self._tenant(h))}

        # ---------------------------------------------------------- worker
        if method == "POST" and path == "/v1/worker/claim":
            self._worker(h)
            job = self.store.claim_next_job(body.get("worker_id", ""), int(body.get("lease_seconds", 120)))
            return 200, {"job": job}

        m = JOB_HEARTBEAT_RE.match(path)
        if method == "POST" and m:
            self._worker(h)
            job = self.store.heartbeat(body.get("worker_id", ""), m.group(1),
                                       int(body.get("lease_seconds", 120)))
            return 200, {"job": job}

        m = JOB_COMPLETE_RE.match(path)
        if method == "POST" and m:
            self._worker(h)
            return 200, {"job": self._complete(m.group(1), body)}

        m = JOB_CANCEL_RE.match(path)
        if method == "POST" and m:
            tid = self._tenant(h)
            return 200, {"job": self.store.request_cancel(tid, m.group(1))}

        # --------------------------------------------------------- billing
        if method == "GET" and path == "/v1/billing":
            tid = self._tenant(h)
            return 200, {"billing": self.store.billing.balance(tid),
                         "invoices": self.store.billing.invoices(tid)}

        if method == "GET" and path == "/v1/ledger":
            tid = self._tenant(h)
            return 200, {"ledger": self.store.billing.ledger(tid)}

        if path == "/v1/invoices":
            tid = self._tenant(h)
            if method == "GET":
                return 200, {"invoices": self.store.billing.invoices(tid)}
            if method == "POST":
                return 201, {"invoice": self.store.billing.issue_invoice(
                    tid, body.get("period_start", ""), body.get("period_end", ""))}

        if method == "POST" and path == "/v1/credits/topup":
            self._admin(h)
            return 201, {"entry": self.store.billing.topup(
                body.get("tenant_id", ""), body.get("amount_microusd", 0), body.get("memo", "topup"))}

        if method == "GET" and path == "/v1/admin/revenue":
            self._admin(h)
            return 200, {"revenue": self.store.billing.revenue()}

        raise ControlPlaneError(404, "not_found", f"rute tidak ada: {method} {path}")

    def _complete(self, job_id: str, body: dict) -> dict:
        worker_id = body.get("worker_id", "")
        row = self.store.db.execute("SELECT tenant_id, lease_owner FROM jobs WHERE job_id = ?",
                                    (job_id,)).fetchone()
        if row is None:
            raise ControlPlaneError(404, "job_not_found", "job tidak ditemukan")
        if row["lease_owner"] != worker_id:
            raise ControlPlaneError(409, "lease_lost", "job tidak sedang dipegang worker ini")
        return self.store.finish_job(row["tenant_id"], job_id, body.get("status", ""),
                                     int(body.get("tokens_used", -1)), body.get("gate_verdict"),
                                     body.get("error"))


def make_handler(api: Api):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        server_version = "sdb-control-plane/0.1"

        def _read_body(self) -> dict | None:
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0:
                return None
            if length > MAX_BODY:
                raise ControlPlaneError(413, "body_too_large", "body melebihi 256 KB")
            raw = self.rfile.read(length)
            try:
                return json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                raise ControlPlaneError(400, "invalid_json", "body bukan JSON yang sah")

        def _send(self, status: int, payload: dict) -> None:
            data = json.dumps(payload, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _handle(self, method: str) -> None:
            try:
                body = self._read_body() if method == "POST" else None
                with api.lock:
                    status, payload = api.handle(
                        method, self.path.split("?")[0], dict(self.headers.items()), body)
            except Exception as exc:  # ControlPlaneError & BillingError berbagi bentuk status/code/message
                if hasattr(exc, "status") and hasattr(exc, "code"):
                    status = exc.status
                    payload = {"error": {"code": exc.code, "message": exc.message}}
                else:  # fail-closed: jangan bocorkan stack trace ke klien
                    status, payload = 500, {"error": {"code": "internal_error",
                                                      "message": type(exc).__name__}}
            self._send(status, payload)

        def do_GET(self) -> None:
            self._handle("GET")

        def do_POST(self) -> None:
            self._handle("POST")

        def log_message(self, format: str, *args) -> None:  # senyap: log ke stdout aplikasi
            return

    return Handler


def serve(store: Store, admin_key: str, host: str = "127.0.0.1", port: int = 8088,
          worker_key: str | None = None) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), make_handler(Api(store, admin_key, worker_key)))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="SDB control plane (Fase 2, stdlib)")
    ap.add_argument("--db", default=os.path.expanduser("~/super-dev-builders/data/control.db"))
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8088)
    args = ap.parse_args(argv)
    admin_key = os.environ.get("SDB_ADMIN_KEY", "")
    if len(admin_key) < 24:
        print("SDB_ADMIN_KEY wajib (>=24 karakter). Contoh: "
              "export SDB_ADMIN_KEY=$(python3 -c 'import secrets;print(secrets.token_urlsafe(32))')",
              file=sys.stderr)
        return 2
    worker_key = os.environ.get("SDB_WORKER_KEY") or None
    if worker_key and len(worker_key) < 24:
        print("SDB_WORKER_KEY minimal 24 karakter", file=sys.stderr)
        return 2
    httpd = serve(Store(args.db), admin_key, args.host, args.port, worker_key)
    print(f"control plane: http://{args.host}:{args.port} (db {args.db})")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
