"""Pack manifest — uji bahwa manifest benar-benar mengikat (hash, lisensi, batas ukuran).

Konteks: ADR-0003 memindahkan distribusi skill dari "salin direktori ke tiap profil" menjadi
manifest ber-hash. Manifest tanpa uji hash hanyalah daftar keinginan.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
import pack_build

PACK_DIR = Path(REPO) / "platform" / "packs"


def _pack(name="sdb-recon"):
    with open(PACK_DIR / f"{name}.json", encoding="utf-8") as fh:
        return json.load(fh)


def test_semua_pack_terverifikasi():
    r = subprocess.run([sys.executable, os.path.join(REPO, "scripts", "pack_build.py"), "verify"],
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "PASS" in r.stdout


def test_build_deterministik(tmp_path):
    r = subprocess.run([sys.executable, os.path.join(REPO, "scripts", "pack_build.py"),
                        "build", "--out", str(tmp_path)],
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr
    built = sorted(p.name for p in tmp_path.glob("*.json"))
    committed = sorted(p.name for p in PACK_DIR.glob("*.json"))
    assert built == committed
    for name in built:
        assert (tmp_path / name).read_bytes() == (PACK_DIR / name).read_bytes(), f"{name} tidak deterministik"


@pytest.mark.parametrize("pack_name", [p.stem for p in PACK_DIR.glob("*.json")])
def test_setiap_pack_patuh_aturan(pack_name):
    pack = _pack(pack_name)
    assert pack["license"] == "BUSL-1.1"
    assert pack["version"] == pack_build.PACK_VERSION
    assert pack["required_native"], "skill pipeline wajib harus tercatat"
    total = len(pack["skills"]) + len(pack["required_native"])
    assert total <= pack_build.MAX_SKILLS, total
    assert pack_build.pack_errors(pack) == []
    assert pack_build.registry_drift(pack) == []


def test_hash_berubah_terdeteksi():
    pack = _pack()
    pack["skills"][0]["sha256"] = "0" * 64
    errs = pack_build.pack_errors(pack)
    assert any("sha256 drift" in e for e in errs), errs


def test_lisensi_share_alike_ditolak_dalam_paket_busl():
    pack = _pack()
    pack["skills"][0]["license"] = "CC-BY-SA-4.0"
    errs = pack_build.pack_errors(pack)
    assert any("tidak boleh masuk paket" in e for e in errs), errs


def test_skill_hilang_dari_registry_terdeteksi():
    pack = _pack()
    pack["skills"].append({"id": "skill-karangan", "path": "skills/skill-karangan",
                           "sha256": "0" * 64, "license": "BUSL-1.1"})
    errs = pack_build.registry_drift(pack)
    assert any("skill-karangan" in e for e in errs), errs


def test_pack_menolak_lebih_dari_batas():
    pack = _pack()
    pack["required_native"] = list(range(30))
    errs = pack_build.pack_errors(pack)
    assert any("batas" in e for e in errs), errs
