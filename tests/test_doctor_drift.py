"""Deteksi drift skill terpasang vs sumber repo (doctor.py --drift-only)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from doctor import _same_tree, _skill_names


def _mk(root, files):
    for rel, body in files.items():
        p = os.path.join(root, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w") as fh:
            fh.write(body)


def test_same_tree_identical_ignores_pycache(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    _mk(a, {"SKILL.md": "x", "scripts/s.py": "1"})
    _mk(b, {"SKILL.md": "x", "scripts/s.py": "1", "scripts/__pycache__/s.pyc": "junk"})
    assert _same_tree(str(a), str(b))


def test_same_tree_detects_content_diff_same_size(tmp_path):
    """Isi beda dengan ukuran sama tetap terdeteksi (bukan perbandingan stat saja)."""
    a, b = tmp_path / "a", tmp_path / "b"
    _mk(a, {"refs/r.md": "aaaa"})
    _mk(b, {"refs/r.md": "bbbb"})
    assert not _same_tree(str(a), str(b))


def test_same_tree_detects_missing_file(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    _mk(a, {"SKILL.md": "x", "references/new.md": "y"})
    _mk(b, {"SKILL.md": "x"})
    assert not _same_tree(str(a), str(b))


def test_skill_names_skips_own_namespace(tmp_path):
    _mk(tmp_path, {"evidence-normalizer/SKILL.md": "x",
                   "super-dev-builders/evidence-normalizer/SKILL.md": "x"})
    names = _skill_names(str(tmp_path))
    assert names == {"evidence-normalizer": str(tmp_path / "evidence-normalizer")}
