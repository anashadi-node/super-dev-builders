"""Test rotasi kredensial control-plane (scripts/rotate_control_keys.py).

Kontrak yang diuji:
  * hanya kunci target yang berubah; kunci lain (mis. token Telegram), urutan,
    dan komentar tetap utuh;
  * penulisan env atomik dengan mode 0600 dan tanpa sisa berkas sementara;
  * --dry-run tidak menyentuh berkas;
  * tidak ada jalur kode yang mencetak nilai kredensial ke stdout/stderr;
  * verifikasi menuntut kunci baru diterima (2xx) DAN kunci lama ditolak (401).

Hermetik: uji HTTP memakai stub server lokal di 127.0.0.1 porta acak.
"""
from __future__ import annotations

import http.server
import importlib.util
import os
import socketserver
import threading

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(REPO, "scripts")


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(SCRIPTS, name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


rot = load("rotate_control_keys")

SAMPLE = """# kredensial control-plane SDB
SDB_TG_BOT_TOKEN=token-tetap-tidak-boleh-berubah
SDB_TG_CHAT_ID=123456789

SDB_ADMIN_KEY=admin-lama-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
SDB_WORKER_KEY=worker-lama-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
"""


def test_rotasi_hanya_mengubah_kunci_target():
    tokens = rot.parse_env(SAMPLE)
    new_tokens, changed = rot.rotate_tokens(tokens)
    text = rot.render(new_tokens)

    after = rot.env_values(new_tokens)
    before = rot.env_values(tokens)
    assert set(changed) == {"SDB_ADMIN_KEY", "SDB_WORKER_KEY"}
    assert after["SDB_TG_BOT_TOKEN"] == before["SDB_TG_BOT_TOKEN"]
    assert after["SDB_TG_CHAT_ID"] == before["SDB_TG_CHAT_ID"]
    assert after["SDB_ADMIN_KEY"] != before["SDB_ADMIN_KEY"]
    assert after["SDB_WORKER_KEY"] != before["SDB_WORKER_KEY"]

    # komentar, urutan, dan baris kosong dipertahankan
    assert text.splitlines()[0] == "# kredensial control-plane SDB"
    assert [ln.split("=")[0] for ln in text.splitlines() if "=" in ln] == [
        "SDB_TG_BOT_TOKEN", "SDB_TG_CHAT_ID", "SDB_ADMIN_KEY", "SDB_WORKER_KEY"]
    assert "" in text.splitlines()


def test_kunci_hilang_ditambahkan_di_akhir():
    tokens = rot.parse_env("SDB_ADMIN_KEY=abc\n")
    new_tokens, changed = rot.rotate_tokens(tokens)
    assert "SDB_WORKER_KEY" in rot.env_values(new_tokens)
    assert changed["SDB_WORKER_KEY"][0] == ""


def test_penulisan_atomik_mode_0600_tanpa_sisa(tmp_path):
    target = tmp_path / "control.env"
    rot.write_atomic(target, "SDB_ADMIN_KEY=x\n")
    assert oct(target.stat().st_mode & 0o777) == "0o600"
    assert [p.name for p in tmp_path.iterdir()] == ["control.env"]


def test_cadangan_mode_0600_dan_isi_lama(tmp_path):
    target = tmp_path / "control.env"
    target.write_text(SAMPLE)
    kept = rot.backup(target)
    assert kept.read_text() == SAMPLE
    assert oct(kept.stat().st_mode & 0o777) == "0o600"


def test_dry_run_tidak_mengubah_berkas(tmp_path, capsys):
    target = tmp_path / "control.env"
    target.write_text(SAMPLE)
    rc = rot.main(["--env", str(target), "--dry-run"])
    assert rc == 0
    assert target.read_text() == SAMPLE
    out = capsys.readouterr().out
    assert "dry-run" in out
    for secret in ("admin-lama", "worker-lama"):
        assert secret not in out


def test_keluaran_tidak_memuat_nilai_kredensial(tmp_path, capsys):
    target = tmp_path / "control.env"
    target.write_text(SAMPLE)
    rc = rot.main(["--env", str(target)])
    assert rc == 0
    out = capsys.readouterr().out
    after = rot.env_values(rot.parse_env(target.read_text()))
    assert after["SDB_ADMIN_KEY"] not in out
    assert after["SDB_WORKER_KEY"] not in out
    assert "admin-lama" not in out and "worker-lama" not in out
    assert "BERUBAH" in out


class _Handler(http.server.BaseHTTPRequestHandler):
    good_key = ""

    def _respond(self):
        if self.path.startswith("/healthz"):
            self.send_response(200)
        elif self.headers.get("X-Admin-Key") == self.good_key:
            self.send_response(200)
        else:
            self.send_response(401)
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"{}")

    do_GET = _respond
    do_POST = _respond

    def log_message(self, format, *args):  # senyap saat uji
        return


@pytest.fixture()
def stub_server():
    handler = type("H", (_Handler,), {"good_key": ""})
    with socketserver.TCPServer(("127.0.0.1", 0), handler) as srv:
        thread = threading.Thread(target=srv.serve_forever, daemon=True)
        thread.start()
        yield srv, handler
        srv.shutdown()


def test_verifikasi_lolos_bila_baru_200_dan_lama_401(tmp_path, capsys, stub_server, monkeypatch):
    srv, handler = stub_server
    target = tmp_path / "control.env"
    target.write_text(SAMPLE)

    fresh = iter(["admin" + "a" * 38, "worker" + "b" * 37])
    monkeypatch.setattr(rot.secrets, "token_urlsafe", lambda n=32: next(fresh))
    handler.good_key = "admin" + "a" * 38

    base = f"http://127.0.0.1:{srv.server_address[1]}"
    rc = rot.main(["--env", str(target), "--verify", f"GET {base}/v1/admin/revenue X-Admin-Key",
                   "--healthz", base + "/healthz"])
    out = capsys.readouterr().out
    assert rc == 0, out
    assert "baru=200 lama=401" in out


def test_parse_verify_mempertahankan_badan_json():
    (method, _url, header, key_name, body), = rot.parse_verify(
        ['POST http://127.0.0.1:8088/v1/worker/claim X-Worker-Key {"worker_id":"w1"}'])
    assert (method, header, key_name) == ("POST", "X-Worker-Key", "SDB_WORKER_KEY")
    assert body == b'{"worker_id":"w1"}'


def test_spesifikasi_verify_tidak_lengkap_ditolak_tanpa_menyentuh_berkas(tmp_path, capsys):
    target = tmp_path / "control.env"
    target.write_text(SAMPLE)
    rc = rot.main(["--env", str(target), "--verify", "GET saja"])
    assert rc == 2
    assert "GAGAL" in capsys.readouterr().out
    assert target.read_text() == SAMPLE  # validasi mendahului rotasi


def test_header_tidak_dikenal_ditolak(tmp_path, capsys):
    target = tmp_path / "control.env"
    target.write_text(SAMPLE)
    rc = rot.main(["--env", str(target), "--verify", "GET http://127.0.0.1:9/x X-Lain"])
    assert rc == 2
    assert "tidak dikenali" in capsys.readouterr().out


def test_wait_ready_benar_saat_koneksi_diterima(stub_server):
    srv, _handler = stub_server
    assert rot.wait_ready(f"http://127.0.0.1:{srv.server_address[1]}/healthz", timeout=2.0) is True


def test_wait_ready_menyerah_saat_porta_mati():
    # porta 9 (discard) biasanya menolak koneksi -> harus berhenti, bukan menggantung
    assert rot.wait_ready("http://127.0.0.1:9/healthz", timeout=0.6, pause=0.1) is False


def test_verifikasi_gagal_bila_kunci_lama_masih_diterima(tmp_path, capsys, stub_server, monkeypatch):
    srv, handler = stub_server
    target = tmp_path / "control.env"
    target.write_text(SAMPLE)

    fresh = iter(["admin" + "a" * 38, "worker" + "b" * 37])
    monkeypatch.setattr(rot.secrets, "token_urlsafe", lambda n=32: next(fresh))
    handler.good_key = "admin-lama-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"  # server masih percaya kunci lama

    base = f"http://127.0.0.1:{srv.server_address[1]}"
    rc = rot.main(["--env", str(target), "--verify", f"GET {base}/v1/admin/revenue X-Admin-Key",
                   "--healthz", base + "/healthz"])
    out = capsys.readouterr().out
    assert rc == 1
    assert "GAGAL" in out
