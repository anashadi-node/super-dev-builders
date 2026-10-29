"""Regresi guard peluncur desktop SDB.

Kelas bug yang dicegah: launcher `.desktop` dipasang tanpa bit executable atau tanpa
metadata GNOME `trusted`, sehingga user melihat dialog "Invalid Permissions on Desktop
File" dan ikon X merah — padahal server deck sehat.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
INSTALL = REPO / "scripts" / "install_shortcuts.sh"
HEAL = REPO / "scripts" / "sdb-fix-launcher.sh"


def _bash() -> str:
    b = shutil.which("bash")
    if not b:
        pytest.skip("bash tidak tersedia")
    return b or "bash"


@pytest.mark.parametrize("script", [INSTALL, HEAL])
def test_script_syntax_ok(script: Path) -> None:
    assert script.is_file(), f"{script} hilang"
    r = subprocess.run([_bash(), "-n", str(script)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_install_sets_exec_bit_and_trust() -> None:
    body = INSTALL.read_text(encoding="utf-8")
    # Bit executable wajib untuk semua .desktop
    assert "chmod 755" in body
    # GNOME: ikon Desktop hanya bisa diklik bila metadata trusted true
    assert "metadata::trusted" in body
    # Verifikasi harus fail-loud, bukan sekadar peringatan
    assert "desktop-file-validate" in body
    assert "exit 1" in body


def test_install_copies_launcher_to_desktop() -> None:
    body = INSTALL.read_text(encoding="utf-8")
    assert "sdb-command-deck.desktop" in body
    assert "~/Desktop" not in body or "$HOME/Desktop" in body
    assert "$HOME/Desktop" in body


def test_heal_script_is_self_healing_and_unprivileged() -> None:
    body = HEAL.read_text(encoding="utf-8")
    assert "chmod 755" in body
    assert "gio set" in body and "metadata::trusted" in body
    assert "cp " in body  # memulihkan salinan Desktop bila hilang/berbeda
    # Tidak boleh butuh root — prinsip instalasi user-local
    assert "sudo" not in body


def test_no_root_requirement_in_installer() -> None:
    body = INSTALL.read_text(encoding="utf-8")
    assert "sudo" not in body


def test_workflow_doc_covers_all_scenarios() -> None:
    """Dokumen skenario wajib menyebut gate dan release gate yang nyata."""
    doc = REPO / "docs" / "WORKFLOW_SKENARIO.md"
    assert doc.is_file()
    text = doc.read_text(encoding="utf-8")
    for token in ("gate_check.py", "release_check.py", "Skenario A", "Skenario B", "Skenario C"):
        assert token in text, f"bagian hilang dari dokumen: {token}"
    assert "TODO" not in text
