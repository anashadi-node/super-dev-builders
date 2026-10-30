"""Target fixture E1 — aplikasi milik sendiri (kelas A), stdlib saja.

10 fitur yang diuji benchmark:
 F01 GET  /health                     -> 200 {"status":"ok"}
 F02 GET  /api/items                  -> 200 daftar item
 F03 POST /api/items                  -> 201 item baru (butuh token)
 F04 GET  /api/items/<id>             -> 200 item | 404
 F05 PATCH /api/items/<id>            -> 200 item terubah (butuh token)
 F06 DELETE /api/items/<id>           -> 204 (butuh token)
 F07 POST /api/login                  -> 200 {"token": ...} untuk password benar, 401 salah
 F08 POST /api/items name kosong      -> 422 {"error": ...}
 F09 GET  /api/items?limit=&offset=   -> paginasi
 F10 GET  /api/items?completed=true   -> filter

Jalankan: python3 serve.py [port]
"""

import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

PASSWORD = "rahasia-demo"
TOKEN = "tok-e1-demo"
ITEMS = [
    {"id": 1, "name": "beli kopi", "completed": False},
    {"id": 2, "name": "tulis laporan", "completed": True},
    {"id": 3, "name": "rapat sore", "completed": False},
]
NEXT_ID = 4


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _send(self, code, payload=None):
        body = b"" if payload is None else json.dumps(payload).encode()
        self.send_response(code)
        if payload is not None:
            self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _auth_ok(self):
        return self.headers.get("Authorization", "") == f"Bearer {TOKEN}"

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n) or b"{}")
        except json.JSONDecodeError:
            return None

    def log_message(self, format, *args):  # noqa: A002 - signature induk
        pass

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if u.path == "/health":
            return self._send(200, {"status": "ok"})
        if u.path == "/api/items":
            rows = ITEMS
            if "completed" in q:
                want = q["completed"][0].lower() == "true"
                rows = [r for r in rows if r["completed"] is want]
            if "limit" in q or "offset" in q:
                limit = int(q.get("limit", ["10"])[0])
                offset = int(q.get("offset", ["0"])[0])
                rows = rows[offset: offset + limit]
            return self._send(200, rows)
        if u.path.startswith("/api/items/"):
            try:
                iid = int(u.path.rsplit("/", 1)[1])
            except ValueError:
                return self._send(404, {"error": "not found"})
            for r in ITEMS:
                if r["id"] == iid:
                    return self._send(200, r)
            return self._send(404, {"error": "not found"})
        return self._send(404, {"error": "not found"})

    def do_POST(self):
        global NEXT_ID
        u = urlparse(self.path)
        data = self._body()
        if data is None:
            return self._send(400, {"error": "invalid json"})
        if u.path == "/api/login":
            if data.get("password") == PASSWORD:
                return self._send(200, {"token": TOKEN})
            return self._send(401, {"error": "unauthorized"})
        if u.path == "/api/items":
            if not self._auth_ok():
                return self._send(401, {"error": "unauthorized"})
            name = (data.get("name") or "").strip()
            if not name:
                return self._send(422, {"error": "name wajib diisi"})
            item = {"id": NEXT_ID, "name": name, "completed": bool(data.get("completed", False))}
            NEXT_ID += 1
            ITEMS.append(item)
            return self._send(201, item)
        return self._send(404, {"error": "not found"})

    def do_PATCH(self):
        u = urlparse(self.path)
        if not self._auth_ok():
            return self._send(401, {"error": "unauthorized"})
        if not u.path.startswith("/api/items/"):
            return self._send(404, {"error": "not found"})
        try:
            iid = int(u.path.rsplit("/", 1)[1])
        except ValueError:
            return self._send(404, {"error": "not found"})
        data = self._body()
        if data is None:
            return self._send(400, {"error": "invalid json"})
        for r in ITEMS:
            if r["id"] == iid:
                if "name" in data:
                    if not str(data["name"]).strip():
                        return self._send(422, {"error": "name wajib diisi"})
                    r["name"] = str(data["name"]).strip()
                if "completed" in data:
                    r["completed"] = bool(data["completed"])
                return self._send(200, r)
        return self._send(404, {"error": "not found"})

    def do_DELETE(self):
        u = urlparse(self.path)
        if not self._auth_ok():
            return self._send(401, {"error": "unauthorized"})
        if not u.path.startswith("/api/items/"):
            return self._send(404, {"error": "not found"})
        try:
            iid = int(u.path.rsplit("/", 1)[1])
        except ValueError:
            return self._send(404, {"error": "not found"})
        for i, r in enumerate(ITEMS):
            if r["id"] == iid:
                ITEMS.pop(i)
                return self._send(204)
        return self._send(404, {"error": "not found"})


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8110
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
