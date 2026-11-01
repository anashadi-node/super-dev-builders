"""Tautan Intake -> runner: brief jadi konteks tahap tanpa salin-tempel.

Yang diuji adalah perilaku nyata `workflow_run.py --intake`: file yang ditulis,
provenance yang jujur, tidak menimpa artefak yang sudah ada, dan penolakan id
yang mencoba keluar dari folder intake.
"""
import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import intake_lib  # noqa: E402
import workflow_run  # noqa: E402

IID = "20261101-094618-df1e92"
TARGET = "demo-target"
BRIEF = "# Brief — buat ulang dashboard\n\nButuh: login, tabel, filter.\n"


@pytest.fixture()
def env(tmp_path, monkeypatch):
    intake_root = tmp_path / "intake"
    d = intake_root / IID
    (d / "files").mkdir(parents=True)
    (d / "files" / "lampiran.md").write_text("isi lampiran\n", encoding="utf-8")
    (d / "brief.md").write_text(BRIEF, encoding="utf-8")
    (d / "meta.json").write_text(json.dumps({
        "id": IID, "scen": "A", "scen_title": "Clone / Reverse Engineering",
        "stage": "01A", "target": "", "created": "2026-11-01 09:46:18",
        "text": "buat ulang dashboard", "links": ["https://example.com/acuan"],
        "files": [{"name": "lampiran.md", "stored": "lampiran.md", "size": 13,
                   "sha256": "abc123def4567890", "type": "text/markdown"}],
    }), encoding="utf-8")

    repo = tmp_path / "repo"
    (repo / "runs" / TARGET).mkdir(parents=True)
    monkeypatch.setenv("SDB_INTAKE_ROOT", str(intake_root))
    return repo, intake_root


def test_list_intakes(env, capsys):
    repo, _root = env
    assert workflow_run.main(["--list-intakes"]) == 0
    out = capsys.readouterr().out
    assert IID in out and "scen=A" in out


def test_bind_menulis_kartu_konteks(env):
    repo, _root = env
    rc = workflow_run.main([TARGET, "--intake", IID, "--root", str(repo)])
    assert rc == 0

    doc = repo / "runs" / TARGET / "docs" / f"intake-{IID}.md"
    assert doc.is_file()
    txt = doc.read_text()
    assert BRIEF.strip() in txt                      # brief verbatim
    assert "BELUM diverifikasi" in txt               # provenance jujur
    assert str(_root / IID / "files" / "lampiran.md") in txt   # path absolut
    assert "https://example.com/acuan" in txt

    ctx = (repo / "runs" / TARGET / "CONTEXT.md").read_text()
    assert IID in ctx and f"docs/intake-{IID}.md" in ctx


def test_bind_idempoten_tidak_menumpuk(env):
    repo, _root = env
    workflow_run.main([TARGET, "--intake", IID, "--root", str(repo)])
    workflow_run.main([TARGET, "--intake", IID, "--root", str(repo)])
    ctx = (repo / "runs" / TARGET / "CONTEXT.md").read_text()
    assert ctx.count("## Intake terbaru") == 1
    assert ctx.count("<!-- intake:begin -->") == 1


def test_as_01_mengisi_requirements(env):
    repo, _root = env
    assert workflow_run.main([TARGET, "--intake", IID, "--as", "01", "--root", str(repo)]) == 0
    req = repo / "runs" / TARGET / "requirements.md"
    assert req.is_file()
    body = req.read_text()
    assert body.startswith("<!-- dibuat otomatis dari intake")
    assert "BELUM ditinjau manusia" in body
    assert BRIEF.strip() in body


def test_as_01_tidak_menimpa_requirements_yang_sudah_ada(env):
    repo, _root = env
    req = repo / "runs" / TARGET / "requirements.md"
    req.write_text("# Requirements asli dari manusia\n", encoding="utf-8")
    workflow_run.main([TARGET, "--intake", IID, "--as", "01", "--root", str(repo)])
    assert req.read_text() == "# Requirements asli dari manusia\n"


def test_as_tahap_lain_ditolak(env):
    repo, _root = env
    with pytest.raises(SystemExit) as exc:
        workflow_run.main([TARGET, "--intake", IID, "--as", "07", "--root", str(repo)])
    assert exc.value.code == 2


def test_id_tidak_dikenal_exit_2(env, capsys):
    repo, _root = env
    assert workflow_run.main([TARGET, "--intake", "20200101-000000-abcdef", "--root", str(repo)]) == 2
    assert "tidak ada" in capsys.readouterr().err


def test_id_traversal_ditolak(env):
    repo, _root = env
    with pytest.raises(ValueError):
        intake_lib.load("../../etc/passwd")
    assert workflow_run.main([TARGET, "--intake", "../../etc/passwd", "--root", str(repo)]) == 2


def test_intake_tanpa_target_exit_2(env):
    repo, _root = env
    assert workflow_run.main(["tidak-ada-target", "--intake", IID, "--root", str(repo)]) == 2


def test_latest_memilih_terbaru(env):
    root = intake_lib.root()
    newer = root / "20261102-101010-bbbbbb"
    (newer / "files").mkdir(parents=True)
    (newer / "meta.json").write_text(json.dumps({"scen": "B", "text": "baru"}), encoding="utf-8")
    (newer / "brief.md").write_text("# baru\n", encoding="utf-8")
    assert intake_lib.latest() == "20261102-101010-bbbbbb"
