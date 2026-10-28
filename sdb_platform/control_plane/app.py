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
JOB_FINISH_RE = re.compile(r"^/v1/jobs/([A-Za-z0-9_]+)/finish$")
JOB_RE = re.compile(r"^/v1/jobs/([A-Za-z0-9_]+)$")
MAX_BODY = 256 * 1024


class Api:
    def __init__(self, store: Store, admin_key: str):
        if len(admin_key) < 24:
            raise SystemExit("admin key minimal 24 karakter")
        self.store = store
        self.admin_key = admin_key
        # MVP satu proses: serialisasi semua mutasi supaya cek-kuota + INSERT tidak balapan.
        # Skala horizontal nanti = Postgres dengan transaksi/row lock, bukan mengandalkan lock ini.
        self.lock = threading.Lock()

    def _admin(self, headers: dict) -> None:
        if not secrets.compare_digest(headers.get("x-admin-key", ""), self.admin_key):
            raise ControlPlaneError(401, "unauthorized", "X-Admin-Key tidak sah")

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

        raise ControlPlaneError(404, "not_found", f"rute tidak ada: {method} {path}")


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
            except ControlPlaneError as exc:
                status, payload = exc.status, exc.as_dict()
            except Exception as exc:  # fail-closed: jangan bocorkan stack trace ke klien
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


def serve(store: Store, admin_key: str, host: str = "127.0.0.1", port: int = 8088) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), make_handler(Api(store, admin_key)))


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
    httpd = serve(Store(args.db), admin_key, args.host, args.port)
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
