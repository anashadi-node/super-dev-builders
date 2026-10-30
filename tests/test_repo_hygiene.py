"""Gerbang higiene repo — uji bahwa aturan benar-benar MENOLAK, bukan sekadar ada.

Konteks: audit 2026-10-26 menemukan 20 MB artefak pelanggan di git dan email pihak ketiga di log.
Gerbang yang tidak punya uji negatif akan diam-diam berubah menjadi hiasan.
"""
import json
import os
import subprocess
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(REPO, "scripts", "repo_hygiene.py")

# Disusun runtime: berkas tes ini ikut dipindai gerbang, jadi tidak boleh memuat email literal.
_AT = "@"
EMAIL_PELANGGAN = "budi.santoso" + _AT + "gmail" + ".com"
EMAIL_UJI = "admin" + _AT + "uji-railway" + "." + "id"


def _git(root, *args):
    subprocess.run(["git", "-C", root, *args], check=True, capture_output=True, text=True)


def _make_repo(tmp_path, files: dict[str, str], baseline: dict | None = None):
    root = tmp_path / "repo"
    root.mkdir()
    _git(str(root), "init", "-q")
    _git(str(root), "config", "user.email", "uji@example.com")
    _git(str(root), "config", "user.name", "uji")
    for rel, content in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    if baseline is not None:
        b = root / "platform" / "hygiene-baseline.json"
        b.parent.mkdir(parents=True, exist_ok=True)
        b.write_text(json.dumps(baseline), encoding="utf-8")
    _git(str(root), "add", "-A")
    return str(root)


def _run(root):
    r = subprocess.run([sys.executable, SCRIPT, "--root", root, "--json"],
                       capture_output=True, text=True, timeout=120)
    return r.returncode, json.loads(r.stdout)


def _rules(result):
    return {row["rule"] for row in result["fails"]}


def test_repo_asli_lolos(tmp_path):
    r = subprocess.run([sys.executable, SCRIPT], capture_output=True, text=True, timeout=180)
    assert r.returncode == 0, r.stdout + r.stderr


def test_berkas_besar_baru_ditolak(tmp_path):
    root = _make_repo(tmp_path, {"artefak/besar.bin": "x" * (600 * 1024), "LICENSE": "x"})
    rc, res = _run(root)
    assert rc == 1
    assert "R1_big_file" in _rules(res)


def test_berkas_raw_dan_env_ditolak(tmp_path):
    root = _make_repo(tmp_path, {"evidence/a.raw": "{}", ".env": "A=1", "LICENSE": "x"})
    rc, res = _run(root)
    assert rc == 1
    assert "R2_forbidden_file" in _rules(res)


def test_email_baru_di_artefak_ditolak(tmp_path):
    root = _make_repo(tmp_path, {"runs/x/log.txt": "kontak: " + EMAIL_PELANGGAN + "\n", "LICENSE": "x"})
    rc, res = _run(root)
    assert rc == 1
    assert "R3_pii" in _rules(res)


def test_berkas_belum_commit_tetap_dinilai(tmp_path):
    """Regresi 30 Okt 2026: gerbang lokal PASS, CI FAIL karena `git ls-files` saja.

    Berkas baru tanpa `git add` tetap masuk commit berikutnya, jadi gerbang WAJIB
    menilainya — kalau tidak, hasil lokal dan CI berbeda untuk isi yang sama.
    """
    root = _make_repo(tmp_path, {"LICENSE": "x"})
    baru = os.path.join(root, "catatan", "baru.txt")
    os.makedirs(os.path.dirname(baru), exist_ok=True)
    with open(baru, "w", encoding="utf-8") as fh:
        fh.write("kontak: " + EMAIL_PELANGGAN + "\n")
    rc, res = _run(root)
    assert rc == 1, res
    assert "R3_pii" in _rules(res)


def test_email_teknis_tidak_dianggap_pii(tmp_path):
    root = _make_repo(tmp_path, {
        "runs/x/sbom.json": '{"pkg": "click@8.6.0.dev"}\n',
        "runs/x/log.txt": "commit oleh git@github.com\n",
        "LICENSE": "x",
    })
    rc, res = _run(root)
    assert rc == 0, res["fails"]


def test_baseline_menjadikan_warn_bukan_fail(tmp_path):
    files = {"runs/lama/log.txt": EMAIL_UJI + "\n"}
    baseline = {
        "max_size_kb": 512,
        "allowed_large": [],
        "allowed_pii": [{"path": "runs/lama/log.txt", "reason": "uji"}],
        "structure_dirs": [],
    }
    root = _make_repo(tmp_path, files, baseline)
    rc, res = _run(root)
    assert rc == 0, res
    assert any(w["rule"] == "R3_pii" for w in res["warns"])
    assert not res["fails"]


def test_lisensi_hilang_hanya_warn(tmp_path):
    root = _make_repo(tmp_path, {"README.md": "# x\n"})
    rc, res = _run(root)
    assert rc == 0
    assert any(w["rule"] == "R5_no_license" for w in res["warns"])


@pytest.mark.parametrize("field", ["max_size_kb", "allowed_large", "allowed_pii", "structure_dirs"])
def test_baseline_punya_field_wajib(field):
    with open(os.path.join(REPO, "platform", "hygiene-baseline.json"), encoding="utf-8") as fh:
        assert field in json.load(fh)
