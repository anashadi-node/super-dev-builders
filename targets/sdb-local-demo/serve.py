#!/usr/bin/python3
'''Server demo milik sendiri (localhost saja).'''
import http.server, json, os, time, functools, sys

ROOT = os.path.dirname(os.path.abspath(__file__))

class H(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=ROOT, **kw)
    def log_message(self, fmt, *args):
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))
    def do_GET(self):
        if self.path.startswith("/api/status"):
            body = json.dumps({"state": "ok", "ts": int(time.time())}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("X-Demo-Session", "demo-local-cookie-value-1234")   # uji redaksi
            self.send_header("Set-Cookie", "sdb_session=demo-local-cookie-value-1234; Path=/; HttpOnly")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        return super().do_GET()
    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(n)
        body = json.dumps({"saved": True}).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8100
    http.server.ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()
