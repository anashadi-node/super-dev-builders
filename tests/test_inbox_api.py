"""Intake API — kanal input per skenario (teks, link, lampiran).

Diuji lewat HTTP nyata (ThreadingHTTPServer), bukan hanya unit: yang dijamin
adalah perilaku yang benar-benar dipakai Command Deck.
"""
import json
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
import inbox_api
import server
import ws_api


@pytest.fixture()
def live(tmp_path, monkeypatch):
    monkeypatch.setattr(ws_api, "DATA", tmp_path / "ws")
    monkeypatch.setattr(ws_api, "TOKEN_FILE", tmp_path / "ws" / ".token")
    monkeypatch.setattr(inbox_api, "ROOT", tmp_path / "intake")
    ws_api.rate_401.clear()
    srv = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}", ws_api.get_token(), tmp_path / "intake"
    srv.shutdown()


def _post(base, path, data=b"", token=None, ctype="application/json"):
    req = urllib.request.Request(base + path, data=data, method="POST")
    req.add_header("Content-Type", ctype)
    if token:
        req.add_header("X-SDB-Token", token)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def _get(base, path, token=None):
    req = urllib.request.Request(base + path)
    if token:
        req.add_header("X-SDB-Token", token)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, r.read(), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read(), dict(e.headers)


def _submit(base, token, **kw):
    body = {"scen": "A", "scen_title": "Clone / Reverse Engineering", "stage": "01A",
            "text": "Buat ulang dashboard contoh dengan Next.js.", "links": ["https://example.com/demo"]}
    body.update(kw)
    return _post(base, "/api/inbox/submit", json.dumps(body).encode(), token)


def test_submit_dan_upload_tersimpan(live):
    base, token, root = live
    st, j = _submit(base, token)
    assert st == 200 and j["id"]
    iid = j["id"]

    payload = b"# dokumen uji\nisi\n"
    st2, j2 = _post(base, f"/api/inbox/file?id={iid}&name=catatan.md", payload, token, "text/markdown")
    assert st2 == 200
    assert j2["file"]["size"] == len(payload)
    assert j2["file"]["name"] == "catatan.md"

    d = root / iid
    assert (d / "files" / "catatan.md").read_bytes() == payload
    meta = json.loads((d / "meta.json").read_text())
    assert meta["scen"] == "A"
    assert meta["links"] == ["https://example.com/demo"]
    assert meta["files"][0]["sha256"]

    brief = (d / "brief.md").read_text()
    assert "Buat ulang dashboard contoh" in brief
    assert "catatan.md" in brief
    assert "https://example.com/demo" in brief


def test_tanpa_token_ditolak(live):
    base, _token, _root = live
    st, _ = _post(base, "/api/inbox/submit", b'{"text":"x"}')
    assert st == 401
    st2, _, _ = _get(base, "/api/inbox/list")
    assert st2 == 401


def test_nama_file_traversal_dikurung(live):
    base, token, root = live
    _, j = _submit(base, token)
    st, j2 = _post(base, f"/api/inbox/file?id={j['id']}&name=../../evil.txt", b"x", token, "text/plain")
    assert st == 200
    assert j2["file"]["stored"] == "evil.txt"
    files = list((root / j["id"] / "files").iterdir())
    assert [f.name for f in files] == ["evil.txt"]
    assert not (root.parent / "evil.txt").exists()


def test_oversize_ditolak(live, monkeypatch):
    base, token, _root = live
    monkeypatch.setattr(inbox_api, "MAX_FILE", 8)
    _, j = _submit(base, token)
    st, j2 = _post(base, f"/api/inbox/file?id={j['id']}&name=besar.bin", b"x" * 64, token)
    assert st == 413
    assert "error" in j2


def test_link_non_http_ditolak(live):
    base, token, _root = live
    st, j = _submit(base, token, links=["javascript:alert(1)"])
    assert st == 400
    assert "http" in j["error"].lower()


def test_brief_kosong_ditolak(live):
    base, token, _root = live
    st, j = _submit(base, token, text="  ", links=[])
    assert st == 400
    assert "kosong" in j["error"].lower()


def test_id_tidak_valid_ditolak(live):
    base, token, _root = live
    st, _j, _ = _get(base, "/api/inbox/get?id=../../etc/passwd", token)
    assert st == 400


def test_download_paksa_attachment(live):
    base, token, _root = live
    _, j = _submit(base, token)
    _post(base, f"/api/inbox/file?id={j['id']}&name=jahat.html", b"<script>alert(1)</script>", token, "text/html")
    st, _body, hdrs = _get(base, f"/api/inbox/download?id={j['id']}&name=jahat.html", token)
    assert st == 200
    assert hdrs["Content-Type"] == "application/octet-stream"
    assert hdrs["Content-Disposition"].startswith("attachment")
    assert hdrs["X-Content-Type-Options"] == "nosniff"


def test_list_dan_delete(live):
    base, token, root = live
    _, j = _submit(base, token)
    st, body, _ = _get(base, "/api/inbox/list", token)
    assert st == 200
    items = json.loads(body)["items"]
    assert [i["id"] for i in items] == [j["id"]]

    st2, _ = _post(base, "/api/inbox/delete", json.dumps({"id": j["id"]}).encode(), token)
    assert st2 == 200
    assert not (root / j["id"]).exists()
    _, body2, _ = _get(base, "/api/inbox/list", token)
    assert json.loads(body2)["items"] == []
