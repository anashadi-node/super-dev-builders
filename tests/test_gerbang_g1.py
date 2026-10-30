"""Test G1 firewall spesifikasi + audit-log append-only.

Termasuk UJI NEGATIF wajib: masukan berbahaya HARUS ditolak. Penilai yang selalu
PASS dianggap rusak (aturan 7 & 9 riset-penelitian).
"""

import json
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
G1 = ROOT / "tools" / "gerbang-spec.py"
AUDIT = ROOT / "tools" / "audit-log.py"

SPEC_BERSIH = """# SPEC uji

- Endpoint health mengembalikan 200. [E1 · observasi]

| ID | Perilaku | Label |
|---|---|---|
| F01 | 200 status ok | observasi [E1] |
"""


def run(*args):
    # argv tetap (interpreter + alat repo + path temporer) — tidak ada input tak tepercaya.
    return subprocess.run([sys.executable, *map(str, args)],
                          capture_output=True, text=True, timeout=60)


def test_g1_spec_bersih_pass():
    with tempfile.TemporaryDirectory() as td:
        p = pathlib.Path(td) / "SPEC.md"
        p.write_text(SPEC_BERSIH)
        r = run(G1, p)
        assert r.returncode == 0, r.stdout + r.stderr
        assert "PASS" in r.stdout


def test_g1_tolak_blok_kode():
    with tempfile.TemporaryDirectory() as td:
        p = pathlib.Path(td) / "SPEC.md"
        p.write_text("# S\n\n- Klaim dengan bukti. [E1 · observasi]\n\n```python\ndef login():\n    pass\n```\n")
        r = run(G1, p)
        assert r.returncode == 1, r.stdout


def test_g1_tolak_rahasia_dan_email():
    with tempfile.TemporaryDirectory() as td:
        p = pathlib.Path(td) / "SPEC.md"
        kunci_palsu = "AKIA" + "ABCDEFGHIJKLMNOP"  # dirangkai agar pemindai statis tidak menandai berkas uji
        # Email juga dirangkai runtime: gerbang higiene repo (R3_pii) memindai berkas uji ini.
        surel = "a" + "@" + "b" + ".co.id"
        p.write_text(f"# S\n\n- Kunci contoh: {kunci_palsu} dan hubungi {surel} [E1 · observasi]\n")
        r = run(G1, p)
        assert r.returncode == 1
        assert "rahasia" in r.stdout


def test_g1_tolak_klaim_tanpa_bukti():
    with tempfile.TemporaryDirectory() as td:
        p = pathlib.Path(td) / "SPEC.md"
        p.write_text("# S\n\n- Endpoint ini mengembalikan 200 tanpa bukti apa pun.\n")
        r = run(G1, p)
        assert r.returncode == 1
        assert "klaim-tanpa-bukti" in r.stdout


def test_g1_alat_rusak_bukan_pass():
    r = run(G1, "/berkas/tidak/ada.md")
    assert r.returncode == 2, "berkas hilang wajib exit 2, bukan PASS"


def test_audit_append_dan_verify():
    with tempfile.TemporaryDirectory() as td:
        log = pathlib.Path(td) / "audit.jsonl"
        for i in range(3):
            r = run(AUDIT, "append", "--log", log, "--actor", "D1", "--tool", "uji",
                    "--target", f"t{i}", "--action", "act", "--result", "ok")
            assert r.returncode == 0, r.stdout + r.stderr
        r = run(AUDIT, "verify", "--log", log)
        assert r.returncode == 0
        assert "3 entri" in r.stdout


def test_audit_tamper_terdeteksi():
    with tempfile.TemporaryDirectory() as td:
        log = pathlib.Path(td) / "audit.jsonl"
        run(AUDIT, "append", "--log", log, "--actor", "D1", "--tool", "uji",
            "--target", "x", "--action", "act", "--result", "ok")
        lines = log.read_text().splitlines()
        obj = json.loads(lines[0])
        obj["result"] = "diubah"  # manipulasi tanpa memperbarui hash
        log.write_text(json.dumps(obj) + "\n")
        r = run(AUDIT, "verify", "--log", log)
        assert r.returncode == 1, r.stdout
        assert "diubah" in r.stdout or "hash" in r.stdout


def test_audit_append_ditolak_bila_rantai_rusak():
    with tempfile.TemporaryDirectory() as td:
        log = pathlib.Path(td) / "audit.jsonl"
        run(AUDIT, "append", "--log", log, "--actor", "D1", "--tool", "uji",
            "--target", "x", "--action", "act", "--result", "ok")
        log.write_text(log.read_text().replace('"actor": "D1"', '"actor": "D9"'))
        r = run(AUDIT, "append", "--log", log, "--actor", "D2", "--tool", "uji",
                "--target", "y", "--action", "act", "--result", "ok")
        assert r.returncode == 2, f"append pada rantai rusak wajib exit 2, dapat {r.returncode}: {r.stdout}{r.stderr}"
