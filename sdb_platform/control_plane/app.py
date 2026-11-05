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
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .metrics import Metrics, RateLimited, RateLimiter
from .store import ControlPlaneError, Store

JOB_ARTIFACTS_RE = re.compile(r"^/v1/jobs/([A-Za-z0-9_]+)/artifacts$")
JOB_HEARTBEAT_RE = re.compile(r"^/v1/jobs/([A-Za-z0-9_]+)/heartbeat$")
JOB_COMPLETE_RE = re.compile(r"^/v1/jobs/([A-Za-z0-9_]+)/complete$")
JOB_CANCEL_RE = re.compile(r"^/v1/jobs/([A-Za-z0-9_]+)/cancel$")
JOB_FINISH_RE = re.compile(r"^/v1/jobs/([A-Za-z0-9_]+)/finish$")
JOB_RE = re.compile(r"^/v1/jobs/([A-Za-z0-9_]+)$")
TENANT_STATUS_RE = re.compile(r"^/v1/admin/tenants/([A-Za-z0-9_]+)/status$")
MAX_BODY = 256 * 1024
SOCKET_TIMEOUT = 30  # detik; klien lambat (slowloris) tidak boleh menahan thread selamanya


def _same(given: str, expected: str) -> bool:
    """compare_digest pada bytes: dengan str, header non-ASCII melempar TypeError (=500)."""
    return secrets.compare_digest(given.encode("utf-8", "surrogateescape"), expected.encode("utf-8"))


def _obj(body: dict, key: str) -> dict:
    value = body.get(key)
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ControlPlaneError(400, f"invalid_{key}", f"{key} harus objek JSON")
    return value


def _int(body: dict, key: str, default: int) -> int:
    value = body.get(key, default)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ControlPlaneError(400, f"invalid_{key}", f"{key} harus bilangan bulat")
    return value


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
        self.metrics = Metrics()
        # Jatah laju per tenant (permintaan/menit). Dapat ditimpa per tenant lewat limits.rate_per_min.
        self.limiter = RateLimiter(int(os.environ.get("SDB_RATE_PER_MIN", "600") or 600))

    def _admin(self, headers: dict) -> None:
        if not _same(headers.get("x-admin-key", ""), self.admin_key):
            raise ControlPlaneError(401, "unauthorized", "X-Admin-Key tidak sah")

    def _worker(self, headers: dict) -> None:
        if not self.worker_key:
            raise ControlPlaneError(503, "worker_disabled", "endpoint worker tidak diaktifkan")
        if not _same(headers.get("x-worker-key", ""), self.worker_key):
            raise ControlPlaneError(401, "unauthorized", "X-Worker-Key tidak sah")

    def _tenant(self, headers: dict) -> str:
        key = headers.get("x-api-key", "")
        if not key:
            raise ControlPlaneError(401, "unauthorized", "X-API-Key wajib")
        tid = self.store.tenant_for_key(key)
        # Pembatas laju per tenant: satu tenant yang membombardir API tidak boleh menghabiskan
        # CPU/lock bersama. Diterapkan setelah auth supaya tenant lain tetap terlayani.
        try:
            self.limiter.check(tid, self.store.get_tenant(tid).get("rate_per_min") or None)
        except RateLimited:
            self.metrics.inc("sdb_rate_limited_total")
            raise
        return tid

    def handle(self, method: str, path: str, headers: dict, body: dict | None) -> tuple[int, dict]:
        h = {k.lower(): v for k, v in headers.items()}
        body = body or {}

        if method == "GET" and path == "/healthz":
            return 200, {"status": "ok"}

        if method == "GET" and path == "/metrics":
            # Admin-only: angka per tenant/penolakan kuota bukan informasi publik.
            self._admin(h)
            return 200, self.metrics.render()  # str -> teks Prometheus (bukan JSON)

        if method == "POST" and path == "/v1/tenants":
            self._admin(h)
            tenant = self.store.create_tenant(
                plan=body.get("plan", ""), name=body.get("name"),
                isolation=body.get("isolation", "pool"), limits=body.get("limits"))
            # Kunci dibuat setelah tenant; kalau gagal, tenant tanpa kunci tidak berbahaya (admin bisa buat ulang).
            key = self.store.add_api_key(tenant["tenant_id"])
            return 201, {"tenant": tenant, "api_key": key}

        if method == "POST" and path == "/v1/jobs":
            tid = self._tenant(h)
            job, replayed = self.store.create_job(
                tid, body.get("type", ""), _obj(body, "pack"), body.get("target_ref", ""),
                _obj(body, "budget"), body.get("idempotency_key", ""))
            if not replayed:
                self.metrics.inc("sdb_jobs_created_total", {"type": str(job.get("type", ""))[:40]})
            return (200 if replayed else 201), {"job": job, "replayed": replayed}

        m = JOB_FINISH_RE.match(path)
        if method == "POST" and m:
            # Dicabut (v0.5.1): tenant yang menutup job sendiri bisa membatalkan tagihan atas kerja
            # yang sedang dibayar worker. Penutupan hanya lewat worker (/complete) atau /cancel.
            raise ControlPlaneError(410, "endpoint_removed",
                                    "gunakan POST /v1/jobs/{id}/cancel; penyelesaian job dilakukan worker")

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
            job = self.store.claim_next_job(body.get("worker_id", ""), _int(body, "lease_seconds", 120))
            return 200, {"job": job}

        m = JOB_HEARTBEAT_RE.match(path)
        if method == "POST" and m:
            self._worker(h)
            job = self.store.heartbeat(body.get("worker_id", ""), m.group(1),
                                       _int(body, "lease_seconds", 120))
            return 200, {"job": job}

        m = JOB_COMPLETE_RE.match(path)
        if method == "POST" and m:
            self._worker(h)
            done = self._complete(m.group(1), body)
            self.metrics.inc("sdb_jobs_completed_total", {"status": str(done.get("status", ""))})
            self.metrics.inc("sdb_tokens_used_total", value=float(done.get("tokens_used") or 0))
            return 200, {"job": done}

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

        if method == "GET" and path == "/v1/invoices":
            return 200, {"invoices": self.store.billing.invoices(self._tenant(h))}

        if method == "POST" and path == "/v1/admin/invoices":
            # Penerbitan invoice = peran admin. Kalau tenant boleh menerbitkan, ia bisa memesan periode
            # aneh lebih dulu sehingga invoice bulanan resmi tertolak karena tumpang-tindih.
            self._admin(h)
            tid = body.get("tenant_id", "")
            if not isinstance(tid, str):
                raise ControlPlaneError(400, "invalid_tenant_id", "tenant_id harus teks")
            inv = self.store.billing.issue_invoice(tid, body.get("period_start", ""), body.get("period_end", ""))
            return (200 if inv.get("replayed") else 201), {"invoice": inv}

        m = TENANT_STATUS_RE.match(path)
        if method == "POST" and m:
            # Tanpa rute ini admin harus masuk lewat Python untuk menonaktifkan tenant penyalah guna —
            # tidak dapat diterima untuk operasi produksi 24/7.
            self._admin(h)
            tenant = self.store.set_status(m.group(1), body.get("status", ""))
            return 200, {"tenant": tenant}

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
        if not isinstance(worker_id, str) or not worker_id:
            raise ControlPlaneError(400, "invalid_worker", "worker_id wajib")
        row = self.store.db.execute("SELECT tenant_id FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
        if row is None:
            raise ControlPlaneError(404, "job_not_found", "job tidak ditemukan")
        # Pemeriksaan pemilik lease dilakukan DI DALAM transaksi finish_job (bukan di sini) agar
        # tidak ada celah antara cek dan tulis.
        return self.store.finish_job(row["tenant_id"], job_id, body.get("status", ""),
                                     _int(body, "tokens_used", -1), body.get("gate_verdict"),
                                     body.get("error"), worker_id=worker_id)


def _route_class(path: str) -> str:
    """Normalisasi path ke templat rute: label metrik tidak boleh meledak per job_id (kardinalitas)."""
    for rx, template in ((TENANT_STATUS_RE, "/v1/admin/tenants/:id/status"),
                         (JOB_ARTIFACTS_RE, "/v1/jobs/:id/artifacts"), (JOB_HEARTBEAT_RE, "/v1/jobs/:id/heartbeat"),
                         (JOB_COMPLETE_RE, "/v1/jobs/:id/complete"), (JOB_CANCEL_RE, "/v1/jobs/:id/cancel"),
                         (JOB_FINISH_RE, "/v1/jobs/:id/finish"), (JOB_RE, "/v1/jobs/:id")):
        if rx.match(path):
            return template
    return path if len(path) <= 64 else "/lainnya"


def make_handler(api: Api):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        # TCP_NODELAY: tanpa ini respons kecil + keep-alive kena delayed-ACK ~40 ms
        # per permintaan (diukur 40,28 ms -> 0,23 ms; audit SK2).
        disable_nagle_algorithm = True
        server_version = "sdb-control-plane/0.5"
        timeout = SOCKET_TIMEOUT

        def _read_body(self) -> dict | None:
            raw_len = self.headers.get("Content-Length") or "0"
            if not raw_len.isdigit():
                self.close_connection = True  # panjang tak dikenal: sisa body tidak bisa dibuang dengan aman
                raise ControlPlaneError(400, "invalid_content_length", "Content-Length tidak sah")
            length = int(raw_len)
            if length == 0:
                return None
            if length > MAX_BODY:
                self.close_connection = True
                raise ControlPlaneError(413, "body_too_large", "body melebihi 256 KB")
            raw = self.rfile.read(length)
            try:
                data = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                raise ControlPlaneError(400, "invalid_json", "body bukan JSON yang sah") from None
            if not isinstance(data, dict):
                raise ControlPlaneError(400, "invalid_json", "body harus objek JSON")
            return data

        def _send(self, status: int, payload, extra: dict | None = None) -> None:
            text = isinstance(payload, str)  # teks siap kirim: /metrics (Prometheus)
            data = (payload if text else json.dumps(payload, ensure_ascii=False)).encode()
            self.send_response(status)
            self.send_header("Content-Type",
                             "text/plain; version=0.0.4; charset=utf-8" if text
                             else "application/json; charset=utf-8")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            if self.close_connection:
                self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(data)

        def _handle(self, method: str) -> None:
            extra: dict | None = None
            path = self.path.split("?")[0]
            try:
                if method != "POST" and (self.headers.get("Content-Length") or "0") != "0":
                    self.close_connection = True  # body GET tidak dibaca: jangan pakai ulang koneksi
                body = self._read_body() if method == "POST" else None
                if method == "GET" and path == "/healthz":
                    # Probes tidak boleh menunggu lock tulis: endpoint ini konstan (tanpa DB),
                    # sehingga aman dilayani tanpa api.lock. Diukur: dengan lock global, satu
                    # klaim 92 ms membuat healthz ikut tertahan.
                    status, payload = 200, {"status": "ok"}
                else:
                    with api.lock:
                        status, payload = api.handle(method, path, dict(self.headers.items()), body)
            except RateLimited as exc:
                status = 429
                payload = {"error": {"code": "rate_limited",
                                     "message": "jatah permintaan per menit habis; coba lagi nanti"}}
                extra = {"Retry-After": str(exc.retry_after)}
            except Exception as exc:  # noqa: BLE001 — batas HTTP: domain error beragam bentuknya, wajib fail-closed + dicatat operator (lihat else di bawah)
                if hasattr(exc, "status") and hasattr(exc, "code"):
                    status = exc.status
                    payload = {"error": {"code": exc.code, "message": exc.message}}
                else:  # fail-closed: jangan bocorkan stack trace ke klien, tapi catat untuk operator
                    status, payload = 500, {"error": {"code": "internal_error",
                                                      "message": type(exc).__name__}}
                    # Hanya method + path + traceback; header/body tidak dicatat (bisa memuat kunci).
                    print(f"[control-plane] 500 {method} {path}", file=sys.stderr)
                    traceback.print_exc(file=sys.stderr)
            api.metrics.inc("sdb_http_requests_total",
                            {"method": method, "route": _route_class(path), "status": str(status)})
            self._send(status, payload, extra)

        def do_GET(self) -> None:
            self._handle("GET")

        def do_POST(self) -> None:
            self._handle("POST")

        def log_message(self, format: str, *args) -> None:  # senyap: log ke stdout aplikasi
            return

    return Handler


def serve(store: Store, admin_key: str, host: str = "127.0.0.1", port: int = 8088,
          worker_key: str | None = None) -> ThreadingHTTPServer:
    class Server(ThreadingHTTPServer):
        # Backlog default socketserver = 5. Diukur: 16 koneksi paralel -> 296 req/s
        # (SYN queue penuh, klien retransmisi ~1 s); dengan 128 -> lihat laporan audit.
        request_queue_size = 128
        daemon_threads = True  # thread koneksi tidak menahan proses saat shutdown

    api = Api(store, admin_key, worker_key)
    httpd = Server((host, port), make_handler(api))
    httpd.api = api  # dipakai uji & operasional (introspeksi lock/metrics tanpa membuka request)
    return httpd


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
