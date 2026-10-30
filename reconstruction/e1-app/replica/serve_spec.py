"""Replika E1 — dibangun D4/D5 HANYA dari reconstruction/e1-app/SPEC.md.

Tidak membaca targets/e1-app/. Perilaku mengikuti SPEC bagian 2-5.
Jalankan: python3 serve.py [port]
"""

import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

DEMO_PASSWORD = "rahasia-demo"
DEMO_TOKEN = "tok-e1-demo"

STORE = {
    1: {"id": 1, "name": "contoh satu", "completed": False},
    2: {"id": 2, "name": "contoh dua", "completed": True},
    3: {"id": 3, "name": "contoh tiga", "completed": False},
}
NEXT = [4]


class Api(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format, *args):  # noqa: A002 - signature induk
        return

    def reply(self, status, payload=None):
        raw = b"" if payload is None else json.dumps(payload).encode()
        self.send_response(status)
        if payload is not None:
            self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        if raw:
            self.wfile.write(raw)

    def token_ok(self):
        return self.headers.get("Authorization", "") == "Bearer " + DEMO_TOKEN

    def payload(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length == 0:
            return {}
        blob = self.rfile.read(length)
        try:
            return json.loads(blob)
        except json.JSONDecodeError:
            return None

    @staticmethod
    def item_id(path):
        tail = path.rsplit("/", 1)[-1]
        if not tail.isdigit():
            return None
        return int(tail)

    def do_GET(self):
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        if parsed.path == "/health":
            return self.reply(200, {"status": "ok"})
        if parsed.path == "/api/items":
            rows = [
                dict(r) for r in sorted(STORE.values(), key=lambda r: r["id"])
            ]
            if "completed" in query:
                flag = query["completed"][0].lower() == "true"
                rows = [r for r in rows if r["completed"] is flag]
            if "limit" in query or "offset" in query:
                start = int(query.get("offset", ["0"])[0])
                count = int(query.get("limit", ["10"])[0])
                rows = rows[start:start + count]
            return self.reply(200, rows)
        if parsed.path.startswith("/api/items/"):
            iid = self.item_id(parsed.path)
            if iid is not None and iid in STORE:
                return self.reply(200, dict(STORE[iid]))
            return self.reply(404, {"error": "not found"})
        return self.reply(404, {"error": "not found"})

    def do_POST(self):
        parsed = urlparse(self.path)
        body = self.payload()
        if body is None:
            return self.reply(400, {"error": "invalid json"})
        if parsed.path == "/api/login":
            if body.get("password") == DEMO_PASSWORD:
                return self.reply(200, {"token": DEMO_TOKEN})
            return self.reply(401, {"error": "unauthorized"})
        if parsed.path == "/api/items":
            if not self.token_ok():
                return self.reply(401, {"error": "unauthorized"})
            name = str(body.get("name") or "").strip()
            if name == "":
                return self.reply(422, {"error": "name wajib diisi"})
            row = {
                "id": NEXT[0],
                "name": name,
                "completed": bool(body.get("completed", False)),
            }
            NEXT[0] += 1
            STORE[row["id"]] = row
            return self.reply(201, dict(row))
        return self.reply(404, {"error": "not found"})

    def do_PATCH(self):
        parsed = urlparse(self.path)
        if not self.token_ok():
            return self.reply(401, {"error": "unauthorized"})
        iid = self.item_id(parsed.path) if parsed.path.startswith("/api/items/") else None
        if iid is None or iid not in STORE:
            return self.reply(404, {"error": "not found"})
        body = self.payload()
        if body is None:
            return self.reply(400, {"error": "invalid json"})
        row = STORE[iid]
        if "name" in body:
            name = str(body["name"]).strip()
            if name == "":
                return self.reply(422, {"error": "name wajib diisi"})
            row["name"] = name
        if "completed" in body:
            row["completed"] = bool(body["completed"])
        return self.reply(200, dict(row))

    def do_DELETE(self):
        parsed = urlparse(self.path)
        if not self.token_ok():
            return self.reply(401, {"error": "unauthorized"})
        iid = self.item_id(parsed.path) if parsed.path.startswith("/api/items/") else None
        if iid is None or iid not in STORE:
            return self.reply(404, {"error": "not found"})
        del STORE[iid]
        return self.reply(204)


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8111
    ThreadingHTTPServer(("127.0.0.1", port), Api).serve_forever()
