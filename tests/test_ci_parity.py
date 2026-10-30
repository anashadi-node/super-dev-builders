"""Paritas CI ↔ lokal — mencegah kelas kegagalan "lokal hijau, CI merah".

Kegagalan 30 Okt 2026 punya dua akar, keduanya paritas:
  1) gerbang higiene hanya memindai berkas TERLACAK, jadi berkas baru (belum
     `git add`) luput lokal tetapi dinilai CI -> merah setelah push;
  2) uji keamanan berprasyarat tesseract, sedangkan image CI tidak punya alat itu
     -> merah berhari-hari tanpa ada yang mengubah kode terkait.

Uji ini menjaga: setiap prasyarat alat di skrip keamanan benar-benar dipasang di
workflow CI, dan langkah gerbang di CI sama dengan `make check` lokal.
"""

from __future__ import annotations

import os
import re

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CI = os.path.join(REPO, ".github", "workflows", "ci.yml")
PRIVASI = os.path.join(REPO, "tools", "scan-privasi-media.py")


def _baca(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _alat_wajib() -> list[str]:
    """Ambil daftar `perlu = [...]` dari pemindai media (sumber tunggal prasyarat)."""
    m = re.search(r"^\s*perlu\s*=\s*\[([^\]]*)\]", _baca(PRIVASI), re.MULTILINE)
    assert m, "daftar prasyarat `perlu` tidak ditemukan di scan-privasi-media.py"
    return re.findall(r"[\"']([^\"']+)[\"']", m.group(1))


def test_setiap_alat_wajib_dipasang_di_ci():
    ci = _baca(CI)
    terpasang = " ".join(baris for baris in ci.splitlines() if "apt-get install" in baris)
    kurang = [a for a in _alat_wajib() if a not in terpasang]
    assert not kurang, f"workflow CI tidak memasang prasyarat: {kurang}"


def test_ci_menjalankan_gerbang_yang_sama_dengan_lokal():
    ci = _baca(CI)
    for langkah in ("make lint", "make lint-registry", "make test", "make hygiene", "make packs"):
        assert langkah in ci, f"langkah '{langkah}' hilang dari CI — paritas rusak"
