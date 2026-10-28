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


def test_empty_token_file_fails_closed(live):
    ws_api.TOKEN_FILE.write_text("")
    with pytest.raises(RuntimeError):
        ws_api.get_token()


def test_get_token_concurrent_first_use_single_value(tmp_path, monkeypatch):
    monkeypatch.setattr(ws_api, "DATA", tmp_path)
    monkeypatch.setattr(ws_api, "TOKEN_FILE", tmp_path / ".token")
    out = []
    ts = [threading.Thread(target=lambda: out.append(ws_api.get_token())) for _ in range(12)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert len(out) == 12 and len(set(out)) == 1 and out[0]
    assert [p.name for p in tmp_path.iterdir()] == [".token"]  # tanpa sisa berkas temp


def test_stage_01_cannot_be_rerun(live, monkeypatch):
    monkeypatch.setattr(ws_api, "find_project", lambda pid: {"id": pid, "name": "x", "kind": "baru"})
    with pytest.raises(ValueError, match="Gate #0"):
        ws_api.do_stage_run({"project": "p1", "stage": "01"})


def test_profile_cfg_non_dict_does_not_crash(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "PROFILES", tmp_path)
    for body in ("", "model: gpt\n", "- a\n- b\n"):
        (tmp_path / "p").mkdir(exist_ok=True)
        (tmp_path / "p" / "config.yaml").write_text(body)
        assert server.read_profile_cfg("p") is None


def test_lan_addr_picks_physical_iface_not_vpn(monkeypatch):
    """Rute default bisa lewat VPN (nordlynx); hanya en*/eth*/wl* boleh dipilih."""
    out = ("3: nordlynx    inet 10.5.0.2/32 scope global nordlynx\n"
           "2: wlp2s0    inet 192.168.1.7/24 brd 192.168.1.255 scope global dynamic wlp2s0\n")

    class R:
        stdout = out
    monkeypatch.setattr(server.subprocess, "run", lambda *a, **k: R())
    assert server.lan_addr(8484) == "192.168.1.7:8484"
    R.stdout = "3: nordlynx    inet 10.5.0.2/32 scope global nordlynx\n"
    assert server.lan_addr(8484) is None

    def boom(*a, **k):
        raise OSError("no ip")
    monkeypatch.setattr(server.subprocess, "run", boom)
    assert server.lan_addr(8484) is None


def test_frontend_escapes_all_five_html_metachars():
    """esc() di kedua front-end wajib menangani & < > \" ' (XSS lewat nilai profil/config)."""
    for rel in ("app.js", "ws/app.js"):
        src = (DASH / rel).read_text()
        assert "esc=" in src.replace(" ", "") or "function esc" in src, rel
        for ent in ("&amp;", "&lt;", "&gt;", "&quot;", "&#39;"):
            assert ent in src, f"{rel} tidak meng-escape {ent}"


def test_build_state_survives_non_dict_health(monkeypatch):
    monkeypatch.setattr(server, "load_health", lambda: ({"x": "bukan-dict"}, 1))
    assert isinstance(server.build_state(), dict)


# ---- Regresi ronde-3 Tahap 11 (T11-3, T11-4) ----
def test_artifact_symlink_escape_blocked(live, tmp_path):
    """T11-3: symlink di stages/ tidak boleh membaca berkas di luar direktori proyek."""
    base, tok = live
    stages = tmp_path / "projects" / "p1" / "stages"
    stages.mkdir(parents=True)
    rahasia = tmp_path / "rahasia.txt"
    rahasia.write_text("RAHASIA-JANGAN-KELUAR")
    (stages / "link.md").symlink_to(rahasia)
    code, _, _ = _get(base + "/api/ws/artifact?project=p1&file=link.md", {"X-SDB-Token": tok})
    assert code == 404


def test_artifact_normal_file_still_served(live, tmp_path):
    """Kontrol negatif T11-3: berkas biasa di stages/ TETAP terbaca (tambalan tidak over-block)."""
    base, tok = live
    stages = tmp_path / "projects" / "p1" / "stages"
    stages.mkdir(parents=True)
    (stages / "ok.md").write_text("halo dunia")
    code, body, _ = _get(base + "/api/ws/artifact?project=p1&file=ok.md", {"X-SDB-Token": tok})
    assert code == 200 and b"halo dunia" in body


def test_json_responses_are_nosniff(live, monkeypatch):
    """T11-4: jalur JSON (ws_api dan /api/state) wajib X-Content-Type-Options: nosniff."""
    base, _ = live
    assert _get(base + "/api/ws/whoami")[2]["X-Content-Type-Options"] == "nosniff"
    monkeypatch.setattr(server, "build_state", lambda: {"ok": True})
    r = _get(base + "/api/state")
    assert r[0] == 200 and r[2]["X-Content-Type-Options"] == "nosniff"


def test_static_ui_carries_csp(live):
    """T11-4: UI statis wajib membawa Content-Security-Policy yang membatasi sumber asing."""
    base, _ = live
    csp = _get(base + "/")[2]["Content-Security-Policy"]
    assert "default-src 'self'" in csp
    assert "object-src 'none'" in csp and "frame-ancestors 'none'" in csp and "base-uri 'none'" in csp
    assert "script-src 'self'" in csp


# --- audit fundamental 29 Okt: D1-D3 ------------------------------------------------------
@pytest.mark.parametrize("route", ["chat", "draft/approve", "stage/run"])
def test_body_json_bukan_objek_400_tanpa_bocor_internal(live, route):
    base, tok = live
    req = urllib.request.Request(f"{base}/api/ws/{route}", data=b"[1,2]", method="POST",
                                 headers={"X-SDB-Token": tok, "Content-Type": "application/json"})
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(req, timeout=5)
    assert exc.value.code == 400
    assert b"attribute" not in exc.value.read()


def test_handler_punya_socket_timeout():
    assert 0 < (server.Handler.timeout or 0) <= 60
