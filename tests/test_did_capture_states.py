"""Uji penangkap state: loopback wajib, rahasia tidak boleh bocor, SPA tidak diklaim kosong."""
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import did_capture_states as cs

SPA_SHELL = "<html><body><div id='app'>Belum ada data</div><script src='/app.js'></script></body></html>"


def _server(modus="spa"):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _kirim(self, code, body, ctype="text/html"):
            data = body.encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            if code == 200 and self.path == "/api/login":
                self.send_header("Set-Cookie", "sid=abc; Path=/")
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self):
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n) or b"{}")
            if self.path == "/api/login":
                if modus == "bocor":
                    return self._kirim(401, json.dumps({"error": "salah: " + str(body.get("password"))}),
                                       "application/json")
                if body.get("password") == "rahasia-uji":
                    return self._kirim(200, '{"ok":true}', "application/json")
                return self._kirim(401, '{"error":"bad"}', "application/json")
            if self.path == "/api/dues":
                return self._kirim(400, '{"error":"invalid_amount"}', "application/json")
            self._kirim(404, "{}")

        def do_GET(self):
            if modus == "spa":
                return self._kirim(200, SPA_SHELL)
            if modus == "bocor":
                return self._kirim(200, "<html><body>debug: rahasia-uji</body></html>")
            if self.path == "/ada":
                return self._kirim(200, "<html><body><h1>Daftar</h1><table><tr><td>1</td></tr></table></body></html>")
            if self.path == "/kosong":
                return self._kirim(200, "<html><body><h1>Belum ada pengajuan</h1></body></html>")
            return self._kirim(200, "<html><body>Masuk</body></html>")

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def _cfg(srv, pages, **extra):
    cfg = {"schema": "sdb.did.state_probes/1", "target": "demo",
           "base_url": f"http://127.0.0.1:{srv.server_port}",
           "login": {"path": "/api/login"},
           "roles": [{"name": "warga", "email_env": "T_EMAIL", "password_env": "T_PASS",
                      "pages": pages,
                      "error_probes": [{"path": "/api/dues", "method": "POST", "body": {},
                                        "expect_status_min": 400}]}],
           "anon": [{"path": "/", "expect_status": 200, "expect_text": ["Masuk"]}]}
    cfg.update(extra)
    return cfg


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("T_EMAIL", "warga-uji")
    monkeypatch.setenv("T_PASS", "rahasia-uji")


def test_tolak_target_bukan_loopback():
    with pytest.raises(SystemExit):
        cs._loopback_saja("https://produksi.contoh.id", False)


def test_tolak_env_kredensial_kosong(monkeypatch, env):
    monkeypatch.delenv("T_PASS")
    with pytest.raises(SystemExit):
        cs._isi_env("${T_PASS}")


def test_spa_tidak_diklaim_kosong(env):
    srv = _server("spa")
    try:
        h = cs.tangkap(_cfg(srv, ["/satu", "/dua"]))
    finally:
        srv.shutdown()
    role = h["roles"][0]
    assert role["spa_shell"] is True
    assert all(p["kosong"] is None for p in role["pages"])


def test_halaman_statistik_dinilai_per_halaman(env):
    srv = _server("murni")
    try:
        h = cs.tangkap(_cfg(srv, ["/ada", "/kosong"]))
    finally:
        srv.shutdown()
    role = h["roles"][0]
    assert role["spa_shell"] is False
    assert [p["kosong"] for p in role["pages"]] == [False, True]


def test_error_probe_dan_anon_dihitung(env):
    srv = _server("murni")
    try:
        h = cs.tangkap(_cfg(srv, ["/ada"]))
    finally:
        srv.shutdown()
    assert h["anon"][0]["cocok"] is True
    assert h["roles"][0]["error_probes"][0]["cocok"] is True


def test_login_gagal_ditandai(env, monkeypatch):
    monkeypatch.setenv("T_PASS", "salah")
    srv = _server("murni")
    try:
        h = cs.tangkap(_cfg(srv, ["/ada"]))
    finally:
        srv.shutdown()
    assert h["roles"][0]["ok"] is False and h["roles"][0]["login_status"] == 401


def test_rahasia_bocor_menutup_gerbang(env):
    srv = _server("bocor")
    try:
        h = cs.tangkap(_cfg(srv, ["/bocor"]))
    finally:
        srv.shutdown()
    assert h["redaction_ok"] is False
