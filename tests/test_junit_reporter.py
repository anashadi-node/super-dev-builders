"""C1-08 — hitungan JUnit deterministik berbasis elemen testcase nyata."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import sdb_junit_reporter as reporter

REVISION = "a" * 40
NOW = dt.datetime(2026, 11, 22, 1, 0, tzinfo=dt.timezone.utc)


def _write_xml(path: Path, cases: str, *, tests: int | None = None) -> Path:
    summary = f' tests="{tests}"' if tests is not None else ""
    path.write_text(
        f'<?xml version="1.0"?><testsuites{summary}>'
        f'<testsuite name="pytest"{summary}>{cases}</testsuite></testsuites>',
        encoding="utf-8",
    )
    stamp = NOW.timestamp()
    os.utime(path, (stamp, stamp))
    return path


def _report(path: Path, **overrides):
    kwargs = {
        "command": ".venv/bin/python -m pytest tests skills integrations -q",
        "exit_code": 0,
        "run_id": "c1-08-focused",
        "revision": REVISION,
        "expected_revision": REVISION,
        "max_age_seconds": 300,
        "now": NOW,
    }
    kwargs.update(overrides)
    return reporter.build_report(path, **kwargs)


def test_T11_counts_testcase_elements_not_inflated_summary_attribute(tmp_path: Path) -> None:
    cases = "".join(f'<testcase classname="c" name="t{i}" />' for i in range(1040))
    result = _report(_write_xml(tmp_path / "junit.xml", cases, tests=1043))

    assert result["counts"] == {
        "collected": 1040,
        "executed": 1040,
        "passed": 1040,
        "failed": 0,
        "errors": 0,
        "skipped": 0,
    }
    assert result["xml_summary_tests"] == 1043
    assert result["status"] == "METRICS_VALID"
    expected_command = ".venv/bin/python -m pytest tests skills integrations -q"
    assert {
        key: result["binding"][key]
        for key in ("command_sha256", "exit_code", "run_id", "revision")
    } == {
        "command_sha256": hashlib.sha256(expected_command.encode()).hexdigest(),
        "exit_code": 0,
        "run_id": "c1-08-focused",
        "revision": REVISION,
    }
    assert expected_command not in str(result)
    assert len(result["binding"]["sha256"]) == 64
    assert result["assurance"] == {
        "level": "CALLER_ATTESTED",
        "command_causality": "NOT_INDEPENDENTLY_VERIFIED",
        "suite_completeness": "NOT_INDEPENDENTLY_VERIFIED",
        "acceptance_authority": "INFORMATIONAL_ONLY",
    }


def test_failed_error_and_skipped_are_separate_and_executed_excludes_skip(tmp_path: Path) -> None:
    cases = (
        '<testcase name="pass" />'
        '<testcase name="fail"><failure /></testcase>'
        '<testcase name="error"><error /></testcase>'
        '<testcase name="skip"><skipped /></testcase>'
    )
    result = _report(_write_xml(tmp_path / "junit.xml", cases, tests=99), exit_code=1)

    assert result["counts"] == {
        "collected": 4,
        "executed": 3,
        "passed": 1,
        "failed": 1,
        "errors": 1,
        "skipped": 1,
    }
    assert result["status"] == "TEST_FAILURE"


@pytest.mark.parametrize(
    "content,code",
    [("<testsuite>", "xml_malformed"), ("", "xml_empty")],
)
def test_malformed_and_empty_xml_are_rejected(tmp_path: Path, content: str, code: str) -> None:
    path = tmp_path / "junit.xml"
    path.write_text(content, encoding="utf-8")
    os.utime(path, (NOW.timestamp(), NOW.timestamp()))

    with pytest.raises(reporter.ReportError) as exc:
        _report(path)
    assert exc.value.code == code


def test_zero_testcases_is_rejected(tmp_path: Path) -> None:
    path = _write_xml(tmp_path / "junit.xml", "", tests=0)
    with pytest.raises(reporter.ReportError) as exc:
        _report(path)
    assert exc.value.code == "no_testcases"


def test_non_junit_xml_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "not-junit.xml"
    path.write_text("<html><body><testcase name='looks-valid'/></body></html>", encoding="utf-8")
    with pytest.raises(reporter.ReportError, match="root JUnit"):
        _report(path)


def test_testcase_outside_testsuite_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "invalid-junit.xml"
    path.write_text(
        "<testsuites><testsuite name='empty'/><testcase name='misplaced'/></testsuites>",
        encoding="utf-8",
    )
    os.utime(path, (NOW.timestamp(), NOW.timestamp()))

    with pytest.raises(reporter.ReportError) as exc:
        _report(path)
    assert exc.value.code == "xml_structure_invalid"


def test_metrics_do_not_claim_command_causality_or_suite_completeness(tmp_path: Path) -> None:
    path = _write_xml(tmp_path / "one-case.xml", '<testcase name="only" />', tests=1)

    result = _report(path, command="claimed full suite")

    assert result["status"] == "METRICS_VALID"
    assert result["counts"]["collected"] == 1
    assert result["assurance"]["command_causality"] == "NOT_INDEPENDENTLY_VERIFIED"
    assert result["assurance"]["suite_completeness"] == "NOT_INDEPENDENTLY_VERIFIED"
    assert result["assurance"]["acceptance_authority"] == "INFORMATIONAL_ONLY"


def test_stale_report_is_rejected(tmp_path: Path) -> None:
    path = _write_xml(tmp_path / "junit.xml", '<testcase name="ok" />', tests=1)
    stale = (NOW - dt.timedelta(seconds=301)).timestamp()
    os.utime(path, (stale, stale))

    with pytest.raises(reporter.ReportError) as exc:
        _report(path)
    assert exc.value.code == "report_stale"


def test_wrong_revision_is_rejected(tmp_path: Path) -> None:
    path = _write_xml(tmp_path / "junit.xml", '<testcase name="ok" />', tests=1)
    with pytest.raises(reporter.ReportError) as exc:
        _report(path, revision="b" * 40)
    assert exc.value.code == "revision_mismatch"


def test_failed_command_never_reports_pass(tmp_path: Path) -> None:
    path = _write_xml(tmp_path / "junit.xml", '<testcase name="ok" />', tests=1)
    result = _report(path, exit_code=2)
    assert result["status"] == "TEST_FAILURE"
    assert result["binding"]["exit_code"] == 2


@pytest.mark.parametrize("field,value", [("command", ""), ("run_id", ""), ("revision", "HEAD")])
def test_binding_metadata_is_mandatory_and_strict(tmp_path: Path, field: str, value: str) -> None:
    path = _write_xml(tmp_path / "junit.xml", '<testcase name="ok" />', tests=1)
    with pytest.raises(reporter.ReportError):
        _report(path, **{field: value})


def test_repo_binding_detects_untracked_even_when_git_config_hides_it(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@example.invalid"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "SDB Test"], check=True)
    tracked = repo / "tracked.txt"
    tracked.write_text("tracked\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "tracked.txt"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "fixture"], check=True)
    revision = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    subprocess.run(
        ["git", "-C", str(repo), "config", "status.showUntrackedFiles", "no"], check=True
    )
    (repo / "hidden.py").write_text("raise RuntimeError\n", encoding="utf-8")

    with pytest.raises(reporter.ReportError) as exc:
        reporter._verify_repo_binding(repo, revision)
    assert exc.value.code == "working_tree_dirty"

def test_namespaced_xml_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "ns.xml"
    path.write_bytes(
        b'<evil:testsuites xmlns:evil="urn:evil"><evil:testsuite name="s">'
        b'<evil:testcase name="t"/></evil:testsuite></evil:testsuites>'
    )
    os.utime(path, (NOW.timestamp(), NOW.timestamp()))

    with pytest.raises(reporter.ReportError) as exc:
        _report(path)
    assert exc.value.code == "xml_namespace_invalid"


def test_utf16_doctype_entity_is_rejected(tmp_path: Path) -> None:
    body = (
        '<?xml version="1.0" encoding="UTF-16"?>'
        '<!DOCTYPE testsuites [<!ENTITY boom "AAAAAAAAAA">]>'
        '<testsuites><testsuite name="s"><testcase name="&boom;"/></testsuite></testsuites>'
    )
    path = tmp_path / "utf16.xml"
    path.write_bytes(body.encode("utf-16"))
    os.utime(path, (NOW.timestamp(), NOW.timestamp()))

    with pytest.raises(reporter.ReportError) as exc:
        _report(path)
    assert exc.value.code == "xml_unsafe"


def test_missing_revision_is_cleanly_rejected(tmp_path: Path) -> None:
    path = _write_xml(tmp_path / "junit.xml", '<testcase name="ok" />', tests=1)
    with pytest.raises(reporter.ReportError) as exc:
        _report(path, revision=None)
    assert exc.value.code == "revision_invalid"


def test_from_env_missing_revision_returns_rejected_json(tmp_path, monkeypatch, capsys) -> None:
    path = _write_xml(tmp_path / "junit.xml", '<testcase name="ok" />', tests=1)
    monkeypatch.setattr(reporter, "_verify_repo_binding", lambda *_a, **_k: None)
    monkeypatch.setenv("JUNIT_XML", str(path))
    monkeypatch.setenv("TEST_COMMAND", "probe")
    monkeypatch.setenv("TEST_EXIT_CODE", "0")
    monkeypatch.setenv("TEST_RUN_ID", "probe-env")
    monkeypatch.delenv("TEST_REVISION", raising=False)

    code = reporter.main([
        "--from-env", "--expected-revision", REVISION,
        "--require-clean-repo", str(tmp_path),
    ])
    payload = json.loads(capsys.readouterr().out)
    assert code == 2
    assert payload["status"] == "REJECTED"
    assert payload["error"] == "revision_invalid"


def test_nested_outcome_cannot_be_counted_as_passed(tmp_path: Path) -> None:
    path = tmp_path / "nested.xml"
    path.write_text(
        "<testsuites><testsuite name='s'><testcase name='t'>"
        "<wrapper><failure message='FAIL'/></wrapper></testcase></testsuite></testsuites>",
        encoding="utf-8",
    )
    os.utime(path, (NOW.timestamp(), NOW.timestamp()))

    with pytest.raises(reporter.ReportError) as exc:
        _report(path)
    assert exc.value.code == "testcase_outcome_invalid"


def test_malformed_summary_does_not_veto_real_testcase_counts(tmp_path: Path) -> None:
    path = tmp_path / "summary.xml"
    path.write_text(
        "<testsuites tests='abc'><testsuite name='s' tests='abc'>"
        "<testcase name='t'/></testsuite></testsuites>",
        encoding="utf-8",
    )
    os.utime(path, (NOW.timestamp(), NOW.timestamp()))

    result = _report(path)
    assert result["status"] == "METRICS_VALID"
    assert result["counts"]["collected"] == 1
    assert result["xml_summary_tests"] is None
    assert result["xml_summary_warning"] == "xml_summary_invalid"
    assert result["xml_summary_matches_counts"] is None

