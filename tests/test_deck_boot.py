"""Regresi boot Command Deck SDB — kelas bug "Menyiapkan… loading terus".

Bug asli: di PC yang tidak bisa membuat konteks WebGL (mis. `No suitable EGL configs
found`), `new THREE.WebGLRenderer()` melempar error di top-level modul sehingga
overlay "Menyiapkan Super Dev Builders Workspace…" TIDAK PERNAH ditutup — deck
tampak menggantung selamanya walau server sehat.

Kontrak yang dikunci di sini:
1. WebGL gagal  -> deck tetap terbuka dalam mode 2D (loader hilang, panel hidup).
2. WebGL normal -> mode 3D dengan scene terbangun.
3. Launcher wajib memakai `--enable-unsafe-swiftshader` (Chrome boleh jatuh ke
   renderer perangkat lunak alih-alih mematikan WebGL).
"""
from __future__ import annotations

import json
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
INSTALL = REPO / "scripts" / "install_shortcuts.sh"
HEAL = REPO / "scripts" / "sdb-fix-launcher.sh"
APP_JS = REPO / "dashboard" / "ws" / "app.js"
WORLD_JS = REPO / "dashboard" / "ws" / "world.js"

CHROME_CANDIDATES = ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser")


def _chrome() -> str:
    for name in CHROME_CANDIDATES:
        p = shutil.which(name)
        if p:
            return p
    pytest.skip("Chrome/Chromium tidak tersedia untuk uji boot deck")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture(scope="module")
def deck_url():
    port = _free_port()
    proc = subprocess.Popen(
        [sys.executable, "server.py", "--host", "127.0.0.1", "--port", str(port)],
        cwd=str(REPO / "dashboard"),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    url = f"http://127.0.0.1:{port}/"
    try:
        for _ in range(60):
            if proc.poll() is not None:
                pytest.skip("server deck gagal start")
            try:
                with urllib.request.urlopen(url, timeout=1) as r:
                    if r.status == 200:
                        break
            except (urllib.error.URLError, OSError):
                time.sleep(0.25)
        else:
            pytest.skip("server deck tidak siap")
        yield url
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


def _dump_dom(url: str, *flags: str, budget_ms: int = 9000) -> str:
    r = subprocess.run(
        [_chrome(), "--headless=new", "--no-sandbox", "--disable-dev-shm-usage", *flags,
         f"--virtual-time-budget={budget_ms}", "--dump-dom", url],
        capture_output=True, text=True, timeout=120,
    )
    assert r.returncode == 0, r.stderr[-800:]
    return r.stdout


def test_webgl_gagal_deck_tetap_terbuka(deck_url: str) -> None:
    """GL rusak (tanpa izin Swiftshader) -> mode 2D, loader HILANG, pesan jelas."""
    dom = _dump_dom(deck_url, "--use-gl=angle", "--use-angle=gl")

    assert re.search(r'data-mode="2d"', dom), "harus jatuh ke mode 2D"
    assert re.search(r'data-mode-why="WEBGL_UNAVAILABLE"', dom), "alasan kegagalan harus tercatat"
    assert "Menyiapkan Super Dev Builders Workspace" not in dom, "overlay loader tidak boleh tersisa"
    assert "Mode 2D" in dom, "user harus diberi tahu 3D dimatikan, bukan layar kosong"
    assert re.search(r'id="panel"', dom), "UI panel harus tetap ada dalam mode 2D"


def test_webgl_normal_mode_3d(deck_url: str) -> None:
    """Swiftshader diizinkan -> world terbangun dan loader ditutup."""
    dom = _dump_dom(deck_url, "--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader")

    assert re.search(r'data-mode="3d"', dom), "harus mode 3D"
    assert "Menyiapkan Super Dev Builders Workspace" not in dom, "loader wajib hilang"
    m = re.search(r'data-stats="([^"]+)"', dom)
    assert m, "statistik scene harus dilaporkan"
    stats = json.loads(m.group(1).replace("&quot;", '"'))
    assert stats["rooms"] >= 10 and stats["meshes"] > 100, stats


def test_launcher_wajib_izinkan_swiftshader() -> None:
    """Tanpa flag ini, Chrome mematikan WebGL saat GPU/EGL rusak -> layar abadi."""
    for f in (INSTALL, HEAL):
        body = f.read_text(encoding="utf-8")
        assert "--enable-unsafe-swiftshader" in body, f"{f.name} tidak mengizinkan Swiftshader"


def test_launcher_pakai_profil_khusus() -> None:
    """Flag Chrome hanya berlaku pada proses baru: ikon harus memakai profil sendiri.

    Kalau ikon menumpang sesi Chrome yang sudah jalan, flag diabaikan dan WebGL
    tetap mati. Juga: `%h` BUKAN field code yang sah untuk Exec (xdg desktop-entry
    menolaknya) dan `$HOME` tidak di-expand di dalam heredoc berkutip.
    """
    body = INSTALL.read_text(encoding="utf-8")
    assert "@PROFILE@" in body, "path profil harus disubstitusi setelah heredoc"
    assert "sdb-deck/profile" in body, "profil khusus deck harus dipakai"
    assert "user-data-dir=%h" not in body, "%h bukan field code Exec yang sah"
    heal = HEAL.read_text(encoding="utf-8")
    assert "--user-data-dir" in heal, "self-heal harus mengembalikan profil khusus"
    # .desktop terpasang (kalau ada) harus sah menurut desktop-file-validate
    import shutil as sh
    import subprocess as sp
    if sh.which("desktop-file-validate"):
        for p in (Path.home() / ".local/share/applications/sdb-command-deck.desktop",
                  Path.home() / "Desktop/sdb-command-deck.desktop"):
            if p.exists():
                r = sp.run(["desktop-file-validate", str(p)], capture_output=True, text=True)
                assert r.returncode == 0, r.stdout + r.stderr
                assert "--user-data-dir=" in p.read_text(encoding="utf-8")


def test_kode_punya_jalur_gagal_dan_watchdog() -> None:
    app = APP_JS.read_text(encoding="utf-8")
    assert "WEBGL_UNAVAILABLE" in WORLD_JS.read_text(encoding="utf-8"), "world.js harus melempar kode error"
    assert "stubWorld" in app, "app.js butuh world pengganti agar UI tetap jalan"
    assert "BOOT_TIMEOUT_MS" in app and "hideLoader" in app, "watchdog loader wajib ada"
