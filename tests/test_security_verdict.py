"""Uji `scripts/security_verdict.py` — produsen reports/security-verdict.json.

Yang dijaga di sini adalah sifat KESELAMATAN skrip, bukan sekadar bentuk keluaran:

* PASS hanya boleh lahir dari alat yang benar-benar keluar 0. Kalau alatnya hilang,
  hasilnya BLOCKED — sebab "tidak diperiksa" tidak pernah boleh jadi "bersih".
* Prosa alat tidak mengikat. Alat yang mencetak "OK semua aman" tetapi keluar 1 harus
  tetap FAIL; kebalikannya, alat yang keluar 0 walau keluarannya sedikit tetap PASS.
"""
import json
import os
import stat
import sys
import textwrap

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import security_verdict as sv


def _alat(run_dir, nama, isi):
    tools = os.path.join(run_dir, "tools")
    os.makedirs(tools, exist_ok=True)
    path = os.path.join(tools, nama)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(textwrap.dedent(isi))
    os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR)
    return path


def _kanal_lengkap(run_dir, kode_keamanan=0, kode_privasi=0, prosa_aman=True):
    prosa = 'echo "OK: kelima alat selesai dengan kode keluar 0"' if prosa_aman else 'echo "GAGAL: bukti tidak lengkap"'
    _alat(run_dir, "scan-keamanan.sh", f"""#!/bin/bash
{prosa}
exit {kode_keamanan}
""")
    _alat(run_dir, "scan-privasi-media.py", f"""#!/usr/bin/env python3
print("privasi-media: selesai")
raise SystemExit({kode_privasi})
""")


def _jalankan(run_dir, project):
    out = os.path.join(run_dir, "v.json")
    code = sv.main(["--run-dir", run_dir, "--project", project, "--out", out])
    with open(out, encoding="utf-8") as handle:
        return code, json.load(handle)


def test_pass_hanya_bila_semua_kanal_keluar_nol(tmp_path):
    run = str(tmp_path / "runs" / "demo")
    os.makedirs(run)
    _kanal_lengkap(run)
    code, v = _jalankan(run, str(tmp_path))
    assert code == 0 and v["verdict"] == "PASS"
    assert all(c["exit_code"] == 0 for c in v["checks"])
    assert "tidak ada jalur manual" in v["policy"]


def test_temuan_terbuka_memblokir_rilis_jadi_fail(tmp_path):
    run = str(tmp_path / "runs" / "demo")
    os.makedirs(run)
    _kanal_lengkap(run, kode_privasi=3)
    code, v = _jalankan(run, str(tmp_path))
    assert code == 1 and v["verdict"] == "FAIL"
    assert any("exit 3" in b["reason"] for b in v["blocking"])


def test_prosa_aman_tidak_bisa_menutupi_kode_keluar_gagal(tmp_path):
    run = str(tmp_path / "runs" / "demo")
    os.makedirs(run)
    _kanal_lengkap(run, kode_keamanan=1, prosa_aman=True)
    code, v = _jalankan(run, str(tmp_path))
    assert code == 1 and v["verdict"] == "FAIL", "alat yang keluar 1 wajib FAIL walau prosa berbunyi aman"


def test_alat_hilang_jadi_blocked_bukan_pass(tmp_path):
    run = str(tmp_path / "runs" / "demo")
    os.makedirs(run)
    _alat(run, "scan-keamanan.sh", "#!/bin/bash\nexit 0\n")  # privasi-media sengaja tidak ada
    code, v = _jalankan(run, str(tmp_path))
    assert code == 2 and v["verdict"] == "BLOCKED"
    assert any("tidak ada" in b["reason"] for b in v["blocking"])


def test_log_mentah_disimpan_untuk_jejak_bukti(tmp_path):
    run = str(tmp_path / "runs" / "demo")
    os.makedirs(run)
    _kanal_lengkap(run)
    _, v = _jalankan(run, str(tmp_path))
    for c in v["checks"]:
        assert os.path.isfile(c["log"]), f"log kanal {c['name']} wajib tersimpan"


def test_run_dir_tidak_ada_ditolak(tmp_path):
    assert sv.main(["--run-dir", str(tmp_path / "tidak-ada")]) == 2


def test_slug_tidak_sah_ditolak():
    assert sv.main(["../../etc"]) == 2


if __name__ == "__main__":
    sys.exit(pytest.main([os.path.abspath(__file__), "-q"]))
