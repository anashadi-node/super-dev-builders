"""Gerbang higiene: path tak ter-expand (R6) dan symlink absolut (R7).

Konteks audit 2026-11-05 (ST1/ST2): repo pernah melacak 8 berkas di bawah direktori
literal `$HOME/` (artefak profil Chromium) dan satu symlink absolut ke /home/<user>.
Keduanya lolos karena gerbang higiene tidak punya aturan untuk itu.
"""
from __future__ import annotations

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import repo_hygiene


def _git_repo(tmp_path):
    root = str(tmp_path)
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@e",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@e")
    subprocess.run(["git", "init", "-q", root], check=True)
    for f, body in (("README.md", "# uji\n"), ("app.py", "print('x')\n")):
        with open(os.path.join(root, f), "w", encoding="utf-8") as fh:
            fh.write(body)
    subprocess.run(["git", "-C", root, "add", "."], check=True)
    subprocess.run(["git", "-C", root, "commit", "-qm", "awal"], check=True, env=env)
    return root


def test_path_variabel_tak_terexpand_ditolak(tmp_path):
    root = _git_repo(tmp_path)
    junk = os.path.join(root, "$HOME", ".local", "share", "sdb-deck")
    os.makedirs(junk)
    with open(os.path.join(junk, "Preferences"), "w", encoding="utf-8") as fh:
        fh.write("{}\n")
    subprocess.run(["git", "-C", root, "add", "-f", "$HOME"], check=True)

    result = repo_hygiene.run(root)
    rules = [f["rule"] for f in result["fails"]]
    assert "R6_unexpanded_path" in rules, result["fails"]


def test_symlink_absolut_diperingatkan(tmp_path):
    root = _git_repo(tmp_path)
    target = tmp_path / "di_luar_repo"
    target.mkdir()
    os.symlink(str(target), os.path.join(root, "targets_lokal"))
    subprocess.run(["git", "-C", root, "add", "targets_lokal"], check=True)

    result = repo_hygiene.run(root)
    warns = [w["rule"] for w in result["warns"]]
    assert "R7_absolute_symlink" in warns, result["warns"]


def test_repo_ini_bersih_dari_kedua_pola():
    result = repo_hygiene.run(ROOT)
    bad = [f for f in result["fails"] if f["rule"].startswith(("R6", "R7"))]
    assert bad == [], f"repo masih memuat path tak portabel: {bad}"
    warns = [w for w in result["warns"] if w["rule"] == "R7_absolute_symlink"]
    assert warns == [], f"symlink absolut masih terlacak: {warns}"
