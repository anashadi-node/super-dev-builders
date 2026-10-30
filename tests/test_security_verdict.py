"""Uji `scripts/security_verdict.py` — produsen reports/security-verdict.json.

Yang dijaga di sini adalah sifat KESELAMATAN skrip, bukan sekadar bentuk keluaran:

* PASS hanya boleh lahir dari alat yang benar-benar keluar 0. Kalau alatnya hilang,
  hasilnya BLOCKED — sebab "tidak diperiksa" tidak pernah boleh jadi "bersih".
* Prosa alat tidak mengikat. Alat yang mencetak "OK semua aman" tetapi keluar 1 harus
  tetap FAIL; kebalikannya, alat yang keluar 0 walau keluarannya sedikit tetap PASS.
"""
import json
import os
import shutil
import stat
import subprocess
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


def test_tools_dir_jatuh_ke_toolchain_bersama_untuk_run_baru(tmp_path):
    """Regresi 30 Okt 2026: run baru tanpa tools/ sendiri dulu selalu BLOCKED."""
    run = str(tmp_path / "runs" / "baru")
    os.makedirs(run)
    bersama = sv.repo_path("tools")
    assert sv.resolve_tools_dir(run, None) == bersama
    assert os.path.isfile(os.path.join(bersama, "scan-keamanan.sh"))
    assert os.path.isfile(os.path.join(bersama, "scan-privasi-media.py"))


def test_tools_dir_eksplisit_dan_milik_run_dimenangkan(tmp_path):
    run = tmp_path / "runs" / "lama"
    os.makedirs(run / "tools")
    assert sv.resolve_tools_dir(str(run), None) == str(run / "tools")
    eksplisit = tmp_path / "alat"
    eksplisit.mkdir()
    assert sv.resolve_tools_dir(str(run), str(eksplisit)) == str(eksplisit)


def _jalankan_privasi(script, project, run_dir):
    env = {**os.environ, "SDB_RUN_DIR": str(run_dir), "SDB_TOOLS_DIR": os.path.dirname(str(script))}
    p = subprocess.run([sys.executable, str(script), str(project), "--tulis-json"],
                       capture_output=True, text=True, timeout=120, env=env)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def test_privasi_media_tanpa_media_di_repo_berisi_adalah_na(tmp_path):
    """Proyek backend tanpa aset visual: N/A yang jujur, bukan FAIL dan bukan 'bersih'."""
    project = tmp_path / "api"
    (project / "src").mkdir(parents=True)
    (project / "src" / "app.py").write_text("print(1)\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(project)], check=True)
    subprocess.run(["git", "-C", str(project), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(project), "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-qm", "init"], check=True)
    run = tmp_path / "runs" / "api"
    (run / "reports").mkdir(parents=True)
    code, out = _jalankan_privasi(sv.repo_path("tools/scan-privasi-media.py"), project, run)
    assert code == 0, out
    assert "TIDAK BERLAKU" in out and "TERLACAK git" in out


def test_privasi_media_repo_tanpa_berkas_terlacak_tetap_tak_diverifikasi(tmp_path):
    """Cakupan tidak diketahui == tidak boleh lulus, meski kebetulan 0 media."""
    project = tmp_path / "kosong"
    project.mkdir()
    subprocess.run(["git", "init", "-q", str(project)], check=True)
    run = tmp_path / "runs" / "kosong"
    (run / "reports").mkdir(parents=True)
    code, out = _jalankan_privasi(sv.repo_path("tools/scan-privasi-media.py"), project, run)
    assert code == 2, out
    assert "TAK DIVERIFIKASI" in out


def test_privasi_media_tanpa_daftar_larangan_fail_closed(tmp_path):
    """Daftar larangan kosong-tak-dikonfigurasi tidak boleh menghasilkan 'BERSIH'.

    Prasyarat: tesseract. Tanpa itu alat menolak lebih awal (juga fail-closed) dan
    pesan yang diuji tidak pernah tercapai — itu keterbatasan lingkungan, bukan
    kelalaian gerbang. Di CI tesseract dipasang eksplisit (lihat .github/workflows/ci.yml),
    jadi jalur ini benar-benar dijalankan di sana.
    """
    if not shutil.which("tesseract"):
        pytest.skip("tesseract tidak terpasang — jalur media tidak dapat diuji di host ini")
    project = tmp_path / "tanpa-terms"
    (project / "src").mkdir(parents=True)
    (project / "src" / "app.py").write_text("print(1)\n", encoding="utf-8")
    # media HARUS ada: daftar larangan hanya relevan bila ada yang dipindai
    (project / "src" / "logo.png").write_bytes(
        bytes.fromhex("89504e470d0a1a0a0000000d494844520000000100000001080600000"
                      "01f15c4890000000a49444154789c6300010000050001") )
    subprocess.run(["git", "init", "-q", str(project)], check=True)
    subprocess.run(["git", "-C", str(project), "add", "-A"], check=True)
    run = tmp_path / "runs" / "tanpa-terms"
    (run / "reports").mkdir(parents=True)
    code, out = _jalankan_privasi(sv.repo_path("tools/scan-privasi-media.py"), project, run)
    assert code == 2, out
    assert "daftar larangan identitas tidak ditemukan" in out


def test_inti_keamanan_ruff_tidak_bisa_dimatikan_oleh_ruff_toml_proyek():
    """Regresi 30 Okt 2026: proyek yang memilih aturan longgar dulu meloloskan eval().

    Yang dijaga: alat sendiri memaksa S/BLE/E9 dengan --isolated, jadi ruff.toml proyek
    hanya bisa MENAMBAH aturan, tidak bisa mematikan deteksi keamanan.
    """
    skrip = open(sv.repo_path("tools/scan-keamanan.sh"), encoding="utf-8").read()
    assert "--isolated --select S,BLE,E9" in skrip
    assert "ruff-inti" in skrip
    # Temuan inti tidak boleh berhenti pada "daftar panjang lalu FAIL": wajib ditriase
    # terhadap baseline ber-alasan supaya temuan sah tidak menenggelamkan temuan baru.
    assert "triase-sast.py" in skrip and "sast-diterima.json" in skrip


def test_cakupan_inti_mengecualikan_artefak_dan_mengizinkan_assert_di_tests():
    """Regresi 30 Okt 2026: gerbang menilai artefak TANGKAPAN sebagai kode produk.

    Dua hal yang dijaga di skrip: (1) direktori artefak (targets/, runs/, evidence/, ...)
    dikecualikan dari ruff inti maupun trivy — isinya milik proyek yang diaudit, bukan
    produk ini; (2) S101 hanya diabaikan di tests/ (assert = mekanisme tes), bukan di
    kode produk.
    """
    skrip = open(sv.repo_path("tools/scan-keamanan.sh"), encoding="utf-8").read()
    assert "--exclude targets --exclude evidence --exclude runs" in skrip
    assert '--per-file-ignores "tests/*:S101"' in skrip
    assert "--skip-dirs runs --skip-dirs evidence" in skrip


def test_konfigurasi_ruff_boleh_berada_di_pyproject_toml():
    """Repo yang sudah mem-pin aturan di pyproject.toml dulu gagal tanpa alasan."""
    skrip = open(sv.repo_path("tools/scan-keamanan.sh"), encoding="utf-8").read()
    assert '[ -f "$PROYEK/pyproject.toml" ] && grep -q "^\\[tool\\.ruff"' in skrip


if __name__ == "__main__":
    sys.exit(pytest.main([os.path.abspath(__file__), "-q"]))
