"""Uji triase SAST: baseline harus beralasan, berkedaluwarsa, dan tidak menelan temuan baru."""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

import sdb_common

AKAR = pathlib.Path(sdb_common.repo_path())
ALAT = AKAR / "tools" / "triase-sast.py"


def _tulis(tmp_path, temuan, aturan):
    (tmp_path / "temuan.json").write_text(json.dumps(temuan), encoding="utf-8")
    (tmp_path / "baseline.json").write_text(json.dumps({"aturan": aturan}), encoding="utf-8")


def _jalan(tmp_path, hari=None):
    perintah = [sys.executable, str(ALAT),
                "--temuan", str(tmp_path / "temuan.json"),
                "--baseline", str(tmp_path / "baseline.json"),
                "--akar", str(tmp_path)]
    if hari:
        perintah += ["--hari", hari]
    return subprocess.run(perintah, capture_output=True, text=True)


def _temuan(kode, berkas, baris=1):
    return {"code": kode, "filename": str(berkas), "location": {"row": baris}, "message": "x"}


def _aturan(kode, berkas, kedaluwarsa="2099-12-31", sebab="alasan"):
    return {"kode": kode, "berkas": berkas, "sebab": sebab,
            "pemilik": "D8", "kedaluwarsa": kedaluwarsa}


def test_temuan_tercakup_diterima(tmp_path):
    """Berkas/kode yang ada di baseline tidak menggagalkan gerbang."""
    _tulis(tmp_path, [_temuan("S603", tmp_path / "skrip.py")],
           [_aturan("S603", "skrip.py")])
    hasil = _jalan(tmp_path)
    assert hasil.returncode == 0, hasil.stderr
    assert "baru=0" in hasil.stdout and "diterima=1" in hasil.stdout


def test_temuan_baru_menolak(tmp_path):
    """Temuan yang tidak ada di baseline = BARU -> gerbang menolak (regresi inti)."""
    _tulis(tmp_path, [_temuan("S603", tmp_path / "skrip.py"),
                      _temuan("S307", tmp_path / "baru.py", 42)],
           [_aturan("S603", "skrip.py")])
    hasil = _jalan(tmp_path)
    assert hasil.returncode == 1
    assert "baru=1" in hasil.stdout
    assert "S307" in hasil.stderr and "baru.py:42" in hasil.stderr


def test_baseline_kedaluwarsa_tidak_berlaku(tmp_path):
    """Baseline kedaluwarsa bukan izin selamanya: temuan kembali BARU."""
    _tulis(tmp_path, [_temuan("S310", tmp_path / "skrip.py")],
           [_aturan("S310", "skrip.py", kedaluwarsa="2026-01-01")])
    hasil = _jalan(tmp_path, hari="2026-10-30")
    assert hasil.returncode == 1
    assert "kedaluwarsa=1" in hasil.stdout
    assert "KEDALUWARSA" in hasil.stderr


def test_entri_tanpa_alasan_atau_tanpa_batas_waktu_diabaikan(tmp_path):
    """Baseline tanpa sebab/kedaluwarsa = jalan pintas; harus diabaikan, bukan dipatuhi."""
    tanpa_sebab = _aturan("S603", "skrip.py")
    tanpa_sebab.pop("sebab")
    tanpa_batas = _aturan("S603", "skrip.py")
    tanpa_batas.pop("kedaluwarsa")
    _tulis(tmp_path, [_temuan("S603", tmp_path / "skrip.py")], [tanpa_sebab, tanpa_batas])
    hasil = _jalan(tmp_path)
    assert hasil.returncode == 1
    assert "baru=1" in hasil.stdout
    assert "diabaikan" in hasil.stderr


def test_baseline_rusak_fail_closed(tmp_path):
    """JSON rusak tidak boleh dianggap 'tidak ada temuan'."""
    (tmp_path / "temuan.json").write_text("[]", encoding="utf-8")
    (tmp_path / "baseline.json").write_text("{bukan json", encoding="utf-8")
    hasil = _jalan(tmp_path)
    assert hasil.returncode == 2
    assert "TAK DIVERIFIKASI" in hasil.stdout


def test_baseline_repo_sah_dan_semua_entri_lengkap():
    """Baseline yang dipakai gerbang SDB sendiri harus lolos aturan kelengkapan."""
    data = json.loads((AKAR / "tools" / "sast-diterima.json").read_text(encoding="utf-8"))
    aturan = data["aturan"]
    assert aturan, "baseline kosong bukan penyelesaian"
    kurang = [a for a in aturan
              if not all(a.get(k) for k in ("kode", "berkas", "sebab", "pemilik", "kedaluwarsa"))]
    assert not kurang, f"entri baseline tidak lengkap: {kurang[:2]}"
