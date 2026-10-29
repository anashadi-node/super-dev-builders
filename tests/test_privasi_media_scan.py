"""Regression tests for tracked-media privacy release gate.

No customer identifier appears here. A synthetic brand is used throughout.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCANNER = (
    Path(__file__).resolve().parents[1]
    / "tools/scan-privasi-media.py"
)


def load_scanner():
    spec = importlib.util.spec_from_file_location("sdb_privacy_media_scan", SCANNER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestTrackedMediaPrivacyGate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "real_system").mkdir()
        (self.root / "real_system/__init__.py").write_text("", encoding="utf-8")
        (self.root / "real_system/privacy_scan.py").write_text(
            'TERLARANG = ["syntheticbrand"]\n', encoding="utf-8"
        )
        self.image = self.root / "sample.png"
        self.image.write_bytes(b"synthetic image bytes")
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        subprocess.run(
            ["git", "-C", str(self.root), "add", "sample.png"], check=True
        )
        self.tools = self.root / "tools"
        self.tools.mkdir()
        self.module = load_scanner()
        # Redirect scanner-owned baseline/raw paths into the isolated fixture.
        self.module.__file__ = str(self.tools / "scan-privasi-media.py")
        sys.modules.pop("real_system", None)
        sys.modules.pop("real_system.privacy_scan", None)

    def tearDown(self):
        sys.path = [p for p in sys.path if p != str(self.root)]
        sys.modules.pop("real_system", None)
        sys.modules.pop("real_system.privacy_scan", None)
        self.tmp.cleanup()

    def run_gate(self, text="syntheticbrand"):
        with (
            mock.patch.object(self.module, "alat_kurang", return_value=[]),
            mock.patch.object(self.module, "ocr_gambar", return_value=text),
        ):
            return self.module.main(["scan-privasi-media.py", str(self.root)])

    def write_baseline(self, status):
        digest = hashlib.sha256(self.image.read_bytes()).hexdigest()
        (self.tools / "media-diketahui.json").write_text(
            json.dumps({
                "_catatan": "synthetic regression fixture",
                digest: {"status": status},
            }),
            encoding="utf-8",
        )

    def test_new_identity_blocks_with_exit_one(self):
        self.assertEqual(self.run_gate(), 1)

    def test_known_open_identity_blocks_release_with_exit_three(self):
        self.write_baseline("TERBUKA")
        self.assertEqual(self.run_gate(), 3)

    def test_owner_accepted_identity_is_conditional_exit_zero(self):
        self.write_baseline("DITERIMA-OLEH-PEMILIK")
        self.assertEqual(self.run_gate(), 0)

    def test_blind_ocr_fails_closed_with_exit_two(self):
        self.write_baseline("TERBUKA")
        self.assertEqual(self.run_gate(text=""), 2)

    def test_missing_git_fails_closed_with_exit_two(self):
        with mock.patch.object(self.module.shutil, "which", return_value=None):
            self.assertEqual(
                self.module.main(["scan-privasi-media.py", str(self.root)]), 2
            )


if __name__ == "__main__":
    unittest.main()
