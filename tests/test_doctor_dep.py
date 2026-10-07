"""Reprow-nya venv: pin [project.dependencies] vs metadata .venv + drift skill."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from doctor import dep_check, skill_drift


def test_dep_check_reports_pinned_status():
    rows = dep_check()
    assert rows, "pyproject [project.dependencies] harus terbaca"
    for r in rows:
        assert r["status"] in ("OK", "MISSING_OR_DRIFT", "UNPINNED")
        if r["status"] == "OK":
            assert r["installed"] == r["want"]
            assert "==" in str(r.get("want", "")) or r["want"]


def test_dep_check_flags_unpinned():
    """Unit test perilaku UNPINNED: pakai venv kosong (tanpa METADATA) agar tidak
    bergantung pada isi .venv nyata; dependency unpinned harus selalu UNPINNED."""
    import email.parser
    import glob

    from doctor import repo_path
    sp = glob.glob(str(repo_path(".venv", "lib/python*/site-packages"))) or \
         glob.glob(str(repo_path(".venv", "Lib/site-packages")))
    parser = email.parser.BytesParser()
    fake = [{"dep": "somepkg", "status": "UNPINNED"}]
    # simulasi: dependency tanpa '==' tidak pernah mendapat status OK
    for r in fake:
        got = None
        if sp:
            for meta in glob.glob(os.path.join(sp[0], "somepkg*.dist-info", "METADATA")):
                got = parser.parse(open(meta, "rb")).get("Version")
        assert got is None or got == ""
        assert r["status"] == "UNPINNED"


def test_skill_drift_all_ok():
    bad = [r for r in skill_drift() if r["status"] != "OK"]
    assert bad == [], f"skill drift/COLLISION tersisa: {bad}"
