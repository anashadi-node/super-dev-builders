"""Regresi keamanan dashboard (ronde-3, 11 Okt): traversal id proyek, token non-ASCII,
Content-Length negatif, allowlist berkas statis, izin berkas token."""
import json
import socket
import stat
import sys
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

DASH = Path(__file__).resolve().parents[1] / "dashboard"
sys.path.insert(0, str(DASH))
pytest.importorskip("yaml")
import server
import ws_api


@pytest.fixture()
def live(tmp_path, monkeypatch):
    monkeypatch.setattr(ws_api, "DATA", tmp_path)
    monkeypatch.setattr(ws_api, "TOKEN_FILE", tmp_path / ".token")
    srv = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}", ws_api.get_token()
    srv.shutdown()


def _get(url, headers=None):
    try:
        r = urllib.request.urlopen(urllib.request.Request(url, headers=headers or {}), timeout=5)
        return r.status, r.read(), r.headers
    except urllib.error.HTTPError as e:
        return e.code, e.read(), e.headers


@pytest.mark.parametrize("bad", ["../x", "../../etc", "/etc", "a/b", "", "A", "x" * 61, None, 5])
def test_pdir_rejects_traversal_and_junk(bad):
    with pytest.raises(ValueError):
        ws_api.pdir(bad)


def test_pdir_accepts_valid_ids():
    assert ws_api.pdir("rt-rw-portal").name == "rt-rw-portal"


def test_token_file_created_0600(live):
    mode = stat.S_IMODE(ws_api.TOKEN_FILE.stat().st_mode)
    assert mode == 0o600


def test_non_ascii_token_gives_401_not_crash(live):
    base, _ = live
    code, _, _ = _get(base + "/api/ws/projects", {"X-SDB-Token": "caf\u00e9".encode("latin-1").decode("latin-1")})
    assert code == 401


def test_wrong_ascii_token_401_and_right_token_200(live):
    base, tok = live
    assert _get(base + "/api/ws/projects", {"X-SDB-Token": "salah"})[0] == 401
    assert _get(base + "/api/ws/projects", {"X-SDB-Token": tok})[0] == 200


def test_negative_content_length_rejected(live):
    base, tok = live
    host, port = base.replace("http://", "").split(":")
    s = socket.create_connection((host, int(port)), timeout=5)
    s.sendall(f"POST /api/ws/chat HTTP/1.1\r\nHost: x\r\nX-SDB-Token: {tok}\r\n"
              "Content-Length: -1\r\nConnection: close\r\n\r\n".encode())
    assert b" 413 " in s.recv(4096).split(b"\r\n")[0] + b" "
    s.close()


def test_artifact_traversal_blocked(live):
    base, tok = live
    code, body, _ = _get(base + "/api/ws/artifact?project=../..&file=x.md", {"X-SDB-Token": tok})
    assert code == 400 and b"tidak valid" in body


@pytest.mark.parametrize("p", ["/server.py", "/ws_api.py", "/__pycache__/ws_api.cpython-312.pyc",
                               "/state/health.json", "/../etc/passwd"])
def test_source_and_state_not_served(live, p):
    base, _ = live
    assert _get(base + p)[0] in (403, 404)


def test_whoami_hides_pin_on_dns_rebinding_host(live):
    """Host asing (DNS-rebinding) dari loopback tidak boleh mendapat PIN."""
    base, tok = live
    ok = json.loads(_get(base + "/api/ws/whoami", {"Host": "127.0.0.1:8484"})[1])
    assert ok["token"] == tok
    for evil in ("evil.test", "evil.test:8484", "127.0.0.1.evil.test", "192.168.1.9:8484", ""):
        d = json.loads(_get(base + "/api/ws/whoami", {"Host": evil})[1])
        assert d["token"] is None, evil


def test_static_ui_served_with_security_headers(live):
    base, _ = live
    code, _, h = _get(base + "/")
    assert code == 200
    assert h["X-Content-Type-Options"] == "nosniff" and h["X-Frame-Options"] == "DENY"
    assert json.loads(_get(base + "/api/ws/whoami")[1])["local"] is True
