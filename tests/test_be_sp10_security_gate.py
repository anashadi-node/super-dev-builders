"""C1-08 — BE-SP-10 fail-closed security gate."""
from __future__ import annotations

import hashlib
import inspect
import json
import random
import shutil
import string
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import sdb_security_gate as gate

REVISION = "a" * 40
REGISTRY = {
    "BE-SP-10": {
        "id": "BE-SP-10",
        "status": "PILOT",
        "security_gate": {
            "scanner": "gitleaks",
            "config": ".gitleaks.toml",
            "allowed_scopes": ["."],
        },
    }
}


def _repo(tmp_path: Path, config: str = 'title = "test"\n') -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".gitleaks.toml").write_text(config, encoding="utf-8")
    (repo / "sample.txt").write_text("clean fixture\n", encoding="utf-8")
    return repo


def _scanner(tmp_path: Path, mode: str) -> Path:
    script = tmp_path / f"scanner-{mode}.py"
    scripts = {
        "clean": "report.write_text('[]')\nsys.exit(0)",
        "finding": (
            "report.write_text(json.dumps([{"
            "'RuleID':'synthetic-rule','Description':'synthetic finding',"
            "'File':'sample.txt','StartLine':1,'EndLine':1,"
            "'Fingerprint':'fp:1','Secret':'MUST_NOT_LEAK','Match':'MUST_NOT_LEAK'}]))\n"
            "sys.exit(1)"
        ),
        "crash": "sys.exit(3)",
        "malformed": "report.write_text('{bad json')\nsys.exit(1)",
        "missing": "sys.exit(0)",
        "timeout": "time.sleep(2)\nreport.write_text('[]')\nsys.exit(0)",
    }
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import json, pathlib, sys, time\n"
        "args = sys.argv[1:]\n"
        "report = pathlib.Path(args[args.index('--report-path') + 1])\n"
        + scripts[mode]
        + "\n",
        encoding="utf-8",
    )
    script.chmod(0o700)
    return script


def _head(repo: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()


def _ensure_repo(repo: Path) -> str:
    """Fixture harus repo git nyata: trust root gate dibaca dari blob revision.

    Bila repo sudah punya commit, HEAD dipakai apa adanya (tidak commit ulang)
    agar fixture 'dirty tree' tetap dirty.
    """
    if (repo / ".git").is_dir():
        return _head(repo)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "SDB Test"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "sdb@test.invalid"], check=True)
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "fixture"], check=True)
    return _head(repo)


def _run(repo: Path, scanner: Path | str, **overrides):
    fixture_revision = _ensure_repo(repo)
    kwargs = {
        "repo": repo,
        "capability_id": "BE-SP-10",
        "scope": ".",
        "revision": fixture_revision,
        "expected_revision": fixture_revision,
        "scanner": str(scanner),
        "timeout_seconds": 1.0,
        "registry": REGISTRY,
        "require_clean": False,
    }
    kwargs.update(overrides)
    return gate._run_gate(**kwargs)


def test_T1_clean_synthetic_fixture_passes(tmp_path: Path) -> None:
    result = _run(_repo(tmp_path), _scanner(tmp_path, "clean"))
    assert result["status"] == "PASS", result
    assert result["execution"]["status"] == "SUCCESS"
    assert result["findings"] == []
    assert result["capability_evidence"]["execution_status"] == "PASS"


def test_T2_synthetic_secret_finding_is_a_failure_and_redacted(tmp_path: Path) -> None:
    result = _run(_repo(tmp_path), _scanner(tmp_path, "finding"))
    encoded = json.dumps(result)
    assert result["status"] == "FAIL"
    assert result["execution"]["status"] == "SUCCESS"
    assert len(result["findings"]) == 1
    assert "MUST_NOT_LEAK" not in encoded
    assert "Secret" not in result["findings"][0]
    assert "Match" not in result["findings"][0]


def test_T2b_untrusted_text_fields_cannot_echo_secret_material() -> None:
    raw = [{
        "RuleID": "generic-api-key",
        "File": "sample.txt",
        "StartLine": 1,
        "EndLine": 1,
        "Description": "SECRET_SENTINEL",
        "Fingerprint": "SECRET_SENTINEL",
        "Secret": "SECRET_SENTINEL",
        "Match": "SECRET_SENTINEL",
    }]
    assert "SECRET_SENTINEL" not in json.dumps(gate._normalize_findings(raw))


def test_public_callable_has_no_trust_root_override_parameters() -> None:
    parameters = set(inspect.signature(gate.run_gate).parameters)
    assert parameters.isdisjoint({"registry", "scanner", "require_clean"})


def test_clean_guard_detects_untracked_when_git_config_hides_it(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@example.invalid"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "SDB Test"], check=True)
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
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

    result = _run(
        repo,
        _scanner(tmp_path, "clean"),
        revision=revision,
        expected_revision=revision,
        require_clean=True,
    )
    assert result["status"] == "ERROR"
    assert result["execution"]["errors"][0]["code"] == "working_tree_dirty"


def test_T3_missing_scanner_fails_closed(tmp_path: Path) -> None:
    result = _run(_repo(tmp_path), tmp_path / "missing-gitleaks")
    assert result["status"] == "ERROR"
    assert result["execution"]["errors"][0]["code"] == "scanner_missing"


@pytest.mark.parametrize(
    "mode,code",
    [
        ("crash", "scanner_failed"),
        ("timeout", "scanner_timeout"),
        ("missing", "scanner_result_missing"),
    ],
)
def test_T4_scanner_crash_timeout_or_missing_result_fails_closed(tmp_path: Path, mode: str, code: str) -> None:
    result = _run(
        _repo(tmp_path),
        _scanner(tmp_path, mode),
        timeout_seconds=0.05 if mode == "timeout" else 1.0,
    )
    assert result["status"] == "ERROR"
    assert result["execution"]["errors"][0]["code"] == code


def test_T5_invalid_configuration_fails_closed_before_scan(tmp_path: Path) -> None:
    result = _run(_repo(tmp_path, config="[broken\n"), _scanner(tmp_path, "clean"))
    assert result["status"] == "ERROR"
    assert result["execution"]["errors"][0]["code"] == "config_invalid"


def test_T6_gate_does_not_suppress_new_finding_with_historical_config(tmp_path: Path) -> None:
    config = 'title = "historical exceptions retained"\n[[allowlists]]\ndescription = "old path only"\npaths = ["old.txt"]\n'
    result = _run(_repo(tmp_path, config=config), _scanner(tmp_path, "finding"))
    assert result["status"] == "FAIL"
    assert result["findings"][0]["file"] == "sample.txt"


def test_config_symlink_is_rejected(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    target = repo / "real-config.toml"
    (repo / ".gitleaks.toml").unlink()
    target.write_text('title = "test"\n', encoding="utf-8")
    (repo / ".gitleaks.toml").symlink_to(target.name)
    result = _run(repo, _scanner(tmp_path, "clean"))
    assert result["status"] == "ERROR"
    assert result["execution"]["errors"][0]["code"] == "config_symlink"


def test_config_content_comes_from_bound_revision_not_working_tree(tmp_path: Path) -> None:
    committed = 'title = "committed configuration"\n'
    repo = _repo(tmp_path, config=committed)
    revision = _ensure_repo(repo)
    (repo / ".gitleaks.toml").write_text(
        'title = "working tree rewrite"\n[[allowlists]]\ndescription = "suppress"\npaths = ["sample.txt"]\n',
        encoding="utf-8",
    )
    result = _run(
        repo,
        _scanner(tmp_path, "finding"),
        revision=revision,
        expected_revision=revision,
        require_clean=False,
    )
    assert result["status"] == "FAIL", result
    assert result["execution"]["config_sha256"] == hashlib.sha256(committed.encode()).hexdigest()


def test_registry_trust_root_comes_from_bound_revision_not_working_tree(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    source = Path(__file__).resolve().parents[1] / "registry" / "capability_pilot.yaml"
    registry_dir = repo / "registry"
    registry_dir.mkdir()
    registry_dir.joinpath("capability_pilot.yaml").write_text(
        source.read_text(encoding="utf-8"), encoding="utf-8"
    )
    revision = _ensure_repo(repo)
    registry_dir.joinpath("capability_pilot.yaml").write_text("BE-SP-10: {broken\n", encoding="utf-8")
    result = _run(
        repo,
        _scanner(tmp_path, "clean"),
        revision=revision,
        expected_revision=revision,
        registry=None,
    )
    assert result["status"] == "PASS", result


def test_registry_blob_missing_fails_closed(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    revision = _ensure_repo(repo)
    result = _run(
        repo,
        _scanner(tmp_path, "clean"),
        revision=revision,
        expected_revision=revision,
        registry=None,
    )
    assert result["status"] == "ERROR"
    assert result["execution"]["errors"][0]["code"] == "registry_missing"


def test_T7_malformed_scanner_output_is_execution_error(tmp_path: Path) -> None:
    result = _run(_repo(tmp_path), _scanner(tmp_path, "malformed"))
    assert result["status"] == "ERROR"
    assert result["execution"]["errors"][0]["code"] == "scanner_output_invalid"
    assert result["findings"] == []


def test_T8_wrong_source_revision_is_rejected_before_scan(tmp_path: Path) -> None:
    result = _run(
        _repo(tmp_path), _scanner(tmp_path, "clean"), revision="b" * 40
    )
    assert result["status"] == "ERROR"
    assert result["execution"]["errors"][0]["code"] == "revision_mismatch"


def test_T9_builder_cannot_self_attest_independent_acceptance(tmp_path: Path) -> None:
    result = _run(_repo(tmp_path), _scanner(tmp_path, "clean"))
    evidence = result["capability_evidence"]
    assert evidence["evidence_level"] == "AGENT_REPORTED"
    assert evidence["review_status"] == "NOT_REVIEWED"
    assert evidence["acceptance_status"] == "INFORMATIONAL_ONLY"
    assert evidence["release_authorization"] == "NOT_AUTHORIZED"


def test_T10_BE_SP12_and_BE_SP03_registry_entries_remain_intact() -> None:
    repo = Path(__file__).resolve().parents[1]
    data = gate.evidence.load_registry(repo)
    assert data["BE-SP-12"]["implementation_status"] == "PILOT_VERIFIED_SUBSCOPE"
    assert data["BE-SP-03"]["implementation_status"] == "PILOT_VERIFIED_SUBSCOPE"


def test_T12_existing_approved_capability_matrix_is_unchanged() -> None:
    repo = Path(__file__).resolve().parents[1]
    raw = (repo / "registry" / "capability_pilot.yaml").read_text(encoding="utf-8")
    assert "BE-SP-01, BE-SP-02, BE-SP-03, BE-SP-04, BE-SP-05, BE-SP-06, BE-SP-07" in raw
    assert "BE-SP-08, BE-SP-09, BE-SP-10, BE-SP-11, BE-SP-12, BE-SP-13, BE-SP-14" in raw


def _commit_fixture(source: Path) -> str:
    subprocess.run(["git", "init", "-q", str(source)], check=True)
    subprocess.run(["git", "-C", str(source), "config", "user.name", "SDB Test"], check=True)
    subprocess.run(["git", "-C", str(source), "config", "user.email", "sdb@test.invalid"], check=True)
    subprocess.run(["git", "-C", str(source), "add", "."], check=True)
    subprocess.run(["git", "-C", str(source), "commit", "-qm", "fixture"], check=True)
    return subprocess.run(
        ["git", "-C", str(source), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()


@pytest.mark.skipif(shutil.which("gitleaks") is None, reason="gitleaks tidak tersedia")
def test_real_supported_gitleaks_configuration_accepts_clean_fixture(tmp_path: Path) -> None:
    source = _repo(tmp_path, (Path(__file__).resolve().parents[1] / ".gitleaks.toml").read_text())
    revision = _commit_fixture(source)
    result = _run(
        source,
        shutil.which("gitleaks") or "gitleaks",
        timeout_seconds=20,
        revision=revision,
        expected_revision=revision,
    )
    assert result["status"] == "PASS", result


@pytest.mark.skipif(shutil.which("gitleaks") is None, reason="gitleaks tidak tersedia")
def test_real_supported_gitleaks_configuration_detects_new_fixture(tmp_path: Path) -> None:
    source = _repo(tmp_path, (Path(__file__).resolve().parents[1] / ".gitleaks.toml").read_text())
    acak = random.Random(20261122)
    alfabet = string.ascii_letters + string.digits
    synthetic_value = "".join(acak.choice(alfabet) for _ in range(36))
    (source / "fresh-secret.txt").write_text(
        f'api_key = "{synthetic_value}"\n', encoding="utf-8"
    )
    revision = _commit_fixture(source)
    result = _run(
        source,
        shutil.which("gitleaks") or "gitleaks",
        timeout_seconds=20,
        revision=revision,
        expected_revision=revision,
    )
    assert result["status"] == "FAIL", result
    assert len(result["findings"]) >= 1
    for finding in result["findings"]:
        assert finding["rule_id"]
        assert finding["file"]
        assert "Secret" not in finding
        assert "Match" not in finding


def test_scanner_provenance_pin_missing_is_fail_closed(tmp_path: Path) -> None:
    """scanner=None harus memakai pin registry; tanpa pin → ERROR (tidak diam-diam lolos)."""
    repo = _repo(tmp_path)
    revision = _ensure_repo(repo)
    result = gate._run_gate(
        repo=repo, capability_id="BE-SP-10", scope=".",
        revision=revision, expected_revision=revision,
        scanner=None, timeout_seconds=30.0, registry=REGISTRY, require_clean=False,
    )
    assert result["status"] == "ERROR"
    assert result["execution"]["errors"][0]["code"] == "scanner_provenance_invalid"


def test_scanner_provenance_wrong_digest_is_fail_closed(tmp_path: Path) -> None:
    """Digest salah harus menolak scanner, walaupun scanner nyata tersedia."""
    registry = json.loads(json.dumps(REGISTRY))
    registry["BE-SP-10"]["security_gate"].update(
        scanner_sha256="0" * 64, scanner_version="8.28.0",
    )
    repo = _repo(tmp_path)
    revision = _ensure_repo(repo)
    result = gate._run_gate(
        repo=repo, capability_id="BE-SP-10", scope=".",
        revision=revision, expected_revision=revision,
        scanner=None, timeout_seconds=30.0, registry=registry, require_clean=False,
    )
    assert result["status"] == "ERROR"
    assert result["execution"]["errors"][0]["code"] == "scanner_provenance_invalid"


def test_scanner_provenance_correct_pin_runs_real_gitleaks(tmp_path: Path) -> None:
    """Jalur scanner=None dengan pin sah harus benar-benar menjalankan scanner."""
    scanner_path = shutil.which("gitleaks") or ""
    if not scanner_path:
        pytest.skip("gitleaks tidak tersedia di PATH")
    version = subprocess.run(
        [scanner_path, "version"], check=True, capture_output=True, text=True,
    ).stdout.strip()
    registry = json.loads(json.dumps(REGISTRY))
    registry["BE-SP-10"]["security_gate"].update(
        scanner_sha256=hashlib.sha256(Path(scanner_path).read_bytes()).hexdigest(),
        scanner_version=version,
    )
    repo = _repo(tmp_path)
    revision = _ensure_repo(repo)
    result = gate._run_gate(
        repo=repo, capability_id="BE-SP-10", scope=".",
        revision=revision, expected_revision=revision,
        scanner=None, timeout_seconds=30.0, registry=registry, require_clean=False,
    )
    assert result["status"] == "PASS", result
    assert result["execution"]["scanner_version"] == version
    evidence = result["capability_evidence"]
    assert evidence["acceptance_status"] == "INFORMATIONAL_ONLY"
    assert evidence["release_authorization"] == "NOT_AUTHORIZED"


def test_scanner_argv_binds_revision_config_and_redaction(tmp_path: Path) -> None:
    """Argv scanner wajib mengikat revisi/history, config, redaksi, dan mode git."""
    argv_path = tmp_path / "argv.json"
    script = tmp_path / "recorder.py"
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import json, pathlib, sys\n"
        f"pathlib.Path({str(argv_path)!r}).write_text(json.dumps(sys.argv[1:]))\n"
        "report = pathlib.Path(sys.argv[sys.argv.index('--report-path') + 1])\n"
        "report.write_text('[]')\n"
        "sys.exit(0)\n",
        encoding="utf-8",
    )
    script.chmod(0o700)
    repo = _repo(tmp_path)
    revision = _ensure_repo(repo)
    result = _run(repo, script, timeout_seconds=5.0, revision=revision, expected_revision=revision)
    assert result["status"] == "PASS", result
    argv = json.loads(argv_path.read_text(encoding="utf-8"))
    assert argv[0] == "git"
    assert argv[argv.index("--log-opts") + 1] == revision
    config_arg = argv[argv.index("--config") + 1]
    assert config_arg.endswith("gitleaks.toml")
    assert "sdb-be-sp10-" in config_arg  # salinan privat, bukan path working tree
    assert "--redact=100" in argv
    assert "--no-banner" in argv
    assert argv[argv.index("--exit-code") + 1] == "1"
    command_text = result["execution"]["command"]
    assert str(tmp_path) not in command_text
    assert "[repository]" in command_text
