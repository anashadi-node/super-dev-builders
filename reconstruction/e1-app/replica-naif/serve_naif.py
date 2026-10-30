"""Kontrol E1 — replika "tanpa SPEC": tebakan REST generik yang wajar.

Ini sengaja TIDAK mengikuti SPEC dan TIDAK membaca target. Tujuannya mengukur
apakah spesifikasi memberi nilai tambah (delta paritas), bukan membuatnya tampak
bagus. Pilihan umum yang dipakai: 200 untuk semua sukses, pesan galat "message",
tanpa auth, tanpa validasi, tanpa paginasi/filter.
"""

import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROWS = [
    {"id": 1, "name": "satu", "completed": False},
    {"id": 2, "name": "dua", "completed": True},
    {"id": 3, "name": "tiga", "completed": False},
]


class Simple(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format, *args):  # noqa: A002 - signature induk
        return

    def out(self, code, obj=None):
        raw = b"" if obj is None else json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        if raw:
            self.wfile.write(raw)

    def read_json(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}") if n else {}

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/health":
            return self.out(200, {"status": "ok"})
        if path == "/api/items":
            return self.out(200, ROWS)
        if path.startswith("/api/items/"):
            iid = path.rsplit("/", 1)[-1]
            for r in ROWS:
                if str(r["id"]) == iid:
                    return self.out(200, r)
            return self.out(404, {"message": "not found"})
        return self.out(404, {"message": "not found"})

    def do_POST(self):
        body = self.read_json()
        path = self.path.split("?")[0]
        if path == "/api/login":
            if body.get("password") == "rahasia-demo":
                return self.out(200, {"token": "tok-e1-demo"})
            return self.out(401, {"message": "unauthorized"})
        if path == "/api/items":
            row = {"id": len(ROWS) + 1, "name": body.get("name", ""), "completed": False}
            ROWS.append(row)
            return self.out(200, row)
        return self.out(404, {"message": "not found"})

    def do_PATCH(self):
        body = self.read_json()
        iid = self.path.rsplit("/", 1)[-1]
        for r in ROWS:
            if str(r["id"]) == iid:
                r.update({k: body[k] for k in ("name", "completed") if k in body})
                return self.out(200, r)
        return self.out(404, {"message": "not found"})

    def do_DELETE(self):
        iid = self.path.rsplit("/", 1)[-1]
        for i, r in enumerate(ROWS):
            if str(r["id"]) == iid:
                ROWS.pop(i)
                return self.out(200, {"ok": True})
        return self.out(404, {"message": "not found"})


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8112
    ThreadingHTTPServer(("127.0.0.1", port), Simple).serve_forever()
