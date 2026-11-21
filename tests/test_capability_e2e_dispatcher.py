"""C1-06: one synthetic task executed end-to-end through the real dispatcher entrypoint.

Every test here drives ``sdb_capability_router.main()`` — the same function the CLI
calls — instead of calling ``execute()`` directly. Only the executor substitution seam
(``ControlledHermesAdapter.for_test``) is used, so no live Hermes process, model call,
credential file, or network transport is involved.
"""
from __future__ import annotations

import contextlib
import copy
import datetime as dt
import io
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import sdb_capability_evidence as evidence_mod
import sdb_capability_router as router
import test_capability_routing as harness

APPROVAL_REF = "C1-03-TEST-APPROVAL"

TASK = {
    "schema": router.TASK_SCHEMA,
    "capability_id": "BE-SP-03",
    "lane": "backend",
    "goal": "Validate the approved API contract without production data.",
    "requested_write_paths": [],
}


def _scratch(
    tmp_path: Path, task: dict | None = None, *, roots: tuple[str, ...] = ("artifacts/capability",),
    state: Path | None = None,
) -> tuple[Path, Path]:
    """Trusted scratch repo + the task file the dispatcher will read."""
    pack = router.TaskPack.from_mapping(task or TASK)
    repo = harness._trusted_repo(tmp_path, pack, roots=roots, state=state)
    task_file = repo / "task.json"
    task_file.write_text(json.dumps(task or TASK), encoding="utf-8")
    return repo, task_file


def _dispatch(repo: Path, task_file: Path, approval_ref: str, adapter: router.ControlledHermesAdapter) -> dict:
    """Call the real dispatcher entrypoint with only the executor seam substituted."""
    calls = {"production": 0}

    def _production(cls):
        calls["production"] += 1
        return adapter

    original_root = router.sdb_common.REPO_ROOT
    original_production = router.ControlledHermesAdapter.production.__func__
    out, err = io.StringIO(), io.StringIO()
    router.sdb_common.REPO_ROOT = str(repo)
    router.ControlledHermesAdapter.production = classmethod(_production)
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = router.main(["--task", str(task_file), "--approval-ref", approval_ref])
    finally:
        router.sdb_common.REPO_ROOT = original_root
        router.ControlledHermesAdapter.production = classmethod(original_production)
    return {
        "code": code,
        "repo": repo,
        "calls": calls,
        "adapter": adapter,
        "stdout": out.getvalue(),
        "stderr": err.getvalue(),
    }


def run_dispatcher(
    tmp_path: Path,
    *,
    task: dict | None = None,
    approval_ref: str = APPROVAL_REF,
    mode: str = "valid",
    side_effect: str | None = None,
    roots: tuple[str, ...] = ("artifacts/capability",),
    state: Path | None = None,
) -> dict:
    """Invoke the real dispatcher entrypoint against a synthetic trusted repo."""
    repo, task_file = _scratch(tmp_path, task, roots=roots, state=state)
    adapter = harness._adapter(tmp_path, mode=mode, side_effect=side_effect)
    return _dispatch(repo, task_file, approval_ref, adapter)


@pytest.fixture()
def dispatched(tmp_path: Path) -> dict:
    return run_dispatcher(tmp_path)


def test_dispatcher_runs_synthetic_task_end_to_end(dispatched: dict) -> None:
    assert dispatched["code"] == 0, dispatched["stderr"]
    output = json.loads(dispatched["stdout"])

    # 1-3: task pack accepted; capability, authorized executor and profile resolved by registry.
    assert output["schema"] == "sdb.capability.router-output/1"
    assert output["capability_id"] == "BE-SP-03"
    assert dispatched["calls"]["production"] == 1
    assert dispatched["adapter"]._test_only is True

    # 4-6: controlled adapter invoked; real child exit code captured.
    repo = dispatched["repo"]
    artifacts = sorted((repo / "runs" / "capability").glob("*.invocation.json"))
    assert len(artifacts) == 1
    invocation = json.loads(artifacts[0].read_text())
    assert invocation["exit_code"] == 0
    assert invocation["status"] == "PASS_VERIFIED_SUBSCOPE"
    assert invocation["verified_result"] is True

    # 7-8: execution artifact + BE-SP-12 contract evidence produced and self-validated.
    assert output["verdict"] == "INTEGRATION_TESTED_NONPRODUCTION"
    evidence_path = Path(output["evidence"]["evidence_path"])
    payload = json.loads(evidence_path.read_text())
    assert payload["schema"] == evidence_mod.SCHEMA
    assert payload["exit_code"] == 0
    assert payload["test_results"] == {"passed": 1, "failed": 0, "skipped": 0, "errors": 0, "total": 1}
    # D8 #2 / C1-06 Step 3: counts come from the executed JUnit report, not from the handshake.
    assert payload["test_command"] == "junit:artifacts/capability/junit.xml"
    verdict = evidence_mod.validate_payload(
        payload, repo=repo, now=dt.datetime.now(dt.timezone.utc)
    )
    assert verdict["execution_status"] == "PASS"
    assert verdict["acceptance_status"] == "INFORMATIONAL_ONLY"
    assert verdict["release_authorization"] == "NOT_AUTHORIZED"

    # No host secret material and no raw executor output can reach the persisted artifacts.
    assert "stdout" not in payload and "stderr" not in payload
    for blob in (artifacts[0].read_text(), evidence_path.read_text()):
        assert "challenge_nonce" not in blob


def test_dispatcher_failure_cannot_report_pass(tmp_path: Path) -> None:
    result = run_dispatcher(tmp_path, mode="forged")
    out = json.loads(result["stdout"])
    assert result["code"] == 1
    assert out["verdict"] == "FAIL"
    payload = json.loads(Path(out["evidence"]["evidence_path"]).read_text())
    assert payload["test_results"] == {"passed": 0, "failed": 1, "skipped": 0, "errors": 0, "total": 1}
    assert payload["test_command"] == "junit:artifacts/capability/junit.xml"
    assert payload["exit_code"] != 0
    assert len(payload["integrity"]) == 64
    # The BE-SP-12 validator must agree: FAIL evidence can never validate as PASS.
    # Note exit_code is the process code (0) while test_results carry the real verdict.
    verdict = evidence_mod.validate_payload(
        payload, repo=result["repo"], now=dt.datetime.now(dt.timezone.utc)
    )
    assert verdict["execution_status"] == "FAIL"
    assert verdict["acceptance_status"] != "PASS"


def test_dispatcher_refuses_untracked_authorization(tmp_path: Path) -> None:
    result = run_dispatcher(tmp_path, approval_ref="C1-03-NOT-IN-STORE")
    assert result["code"] == 2
    assert result["stdout"] == ""
    assert "approval" in result["stderr"]
    assert list((result["repo"] / "runs" / "capability").iterdir()) == []


def test_task_cannot_expand_permissions_beyond_approval(tmp_path: Path) -> None:
    escalated = copy.deepcopy(TASK) | {"requested_write_paths": ["scripts/sdb_capability_router.py"]}
    result = run_dispatcher(tmp_path, task=escalated)
    assert result["code"] == 2
    # Name the control that refused: scope mismatch, not a generic failure.
    assert "approval_scope_mismatch" in result["stderr"]
    protected = result["repo"] / "scripts" / "sdb_capability_router.py"
    assert protected.read_text() == "# protected implementation fixture\n"
    assert list((result["repo"] / "runs" / "capability").iterdir()) == []


def test_single_use_approval_cannot_be_replayed(tmp_path: Path) -> None:
    first = run_dispatcher(tmp_path)
    assert first["code"] == 0, first["stderr"]

    repo = first["repo"]
    second = _dispatch(repo, repo / "task.json", APPROVAL_REF, harness._adapter(tmp_path))
    assert second["code"] == 2
    assert "replay" in second["stderr"]
    assert len(list((repo / "runs" / "capability").glob("*.evidence.json"))) == 1


def _invocation_path(repo: Path) -> Path:
    found = list((repo / "runs" / "capability").glob("*.invocation.json"))
    assert len(found) == 1, found
    return found[0]


def _invocation(repo: Path) -> dict:
    return json.loads(_invocation_path(repo).read_text())


def _profile_secrets() -> list[str]:
    """Real credential files that live in the routed profile directory (if any)."""
    profile = router.HERMES_PROFILE_ROOT / "cc-builder"
    paths = [str(profile / name) for name in router.PROFILE_SECRET_FILES if (profile / name).is_file()]
    paths += [str(profile / name) for name in router.PROFILE_PRIVATE_FILES if (profile / name).is_file()]
    paths += [str(profile / name) for name in router.PROFILE_PRIVATE_DIRS if (profile / name).is_dir()]
    return paths


def test_dispatcher_refuses_invalid_task_pack(tmp_path: Path) -> None:
    # Criterion 1 (negative half): an invalid Task Pack never reaches routing.
    broken = copy.deepcopy(TASK) | {"goal": "x" * 5000}  # limit is 4096
    repo, task_file = _scratch(tmp_path, None)  # valid repo, then corrupt the task file
    task_file.write_text(json.dumps(broken))
    result = _dispatch(repo, task_file, APPROVAL_REF, harness._adapter(tmp_path))
    assert result["code"] == 2
    assert result["stdout"] == ""
    assert "task_goal_too_long" in result["stderr"]
    assert list((result["repo"] / "runs" / "capability").iterdir()) == []


def test_dispatcher_refuses_unregistered_capability(tmp_path: Path) -> None:
    # Criterion 2: selection is enforced by the registry, not echoed from the task.
    unknown = copy.deepcopy(TASK) | {"capability_id": "BE-SP-99"}
    # Approval matches the requested task, so the only thing that can refuse it is the registry.
    repo = harness._trusted_repo(tmp_path, router.TaskPack.from_mapping(unknown))
    task_file = repo / "task.json"
    task_file.write_text(json.dumps(unknown))
    result = _dispatch(repo, task_file, APPROVAL_REF, harness._adapter(tmp_path))
    assert result["code"] == 2
    assert "task_route_invalid" in result["stderr"]
    assert list((result["repo"] / "runs" / "capability").iterdir()) == []


def test_nonzero_executor_exit_is_captured_and_fails(tmp_path: Path) -> None:
    # Criterion 6: a real non-zero exit code is recorded verbatim, and it cannot pass.
    result = run_dispatcher(tmp_path, mode="nonzero")
    assert result["code"] == 1
    output = json.loads(result["stdout"])
    assert output["evidence"]["execution_status"] == "FAIL"
    invocation = _invocation(result["repo"])
    assert invocation["exit_code"] == 7
    assert invocation["status"] == "FAIL"
    payload = json.loads(Path(output["evidence"]["evidence_path"]).read_text())
    assert payload["exit_code"] == 7


def test_sandbox_write_escape_is_denied_through_dispatcher(tmp_path: Path) -> None:
    # Criterion 5: inside the sandbox only approval.allowed_write_roots are writable, so a
    # write into the read-only repo tree must fail. (Paths outside the bind set resolve to
    # bwrap's ephemeral root tmpfs, which is why the probe targets a real host path instead.)
    repo, task_file = _scratch(tmp_path, None)
    escape = repo / "scripts" / "c1-06-escape.txt"
    assert not escape.exists()
    result = _dispatch(
        repo, task_file, APPROVAL_REF, harness._adapter(tmp_path, mode="write-probe", side_effect=str(escape))
    )
    assert result["code"] == 0, result["stderr"]
    assert not escape.exists()
    invocation = _invocation(result["repo"])
    assert invocation["routing"]["network_policy"] == "isolated"
    assert invocation["routing"]["executor_kind"] == "test_only"


def test_test_only_executor_is_offline_and_credential_blind(tmp_path: Path) -> None:
    # D8 F1/F2: inside the sandbox the executor must neither read profile credentials nor reach the net.
    secrets = _profile_secrets()
    probe = json.dumps({"secrets": secrets})
    result = run_dispatcher(tmp_path, mode="credential-probe", side_effect=probe)
    assert result["code"] == 0, f"leaks: {result['stderr']}"
    assert json.loads(result["stdout"])["evidence"]["execution_status"] == "PASS"


def test_invocation_records_non_secret_routing_metadata(tmp_path: Path) -> None:
    # Criterion 11: routing is diagnosable from persisted, non-replayable metadata.
    result = run_dispatcher(tmp_path)
    assert result["code"] == 0, result["stderr"]
    routing = _invocation(result["repo"])["routing"]
    assert routing["profile"] == "cc-builder"
    assert routing["executor_kind"] == "test_only"
    assert routing["network_policy"] == "isolated"
    assert len(routing["approval_nonce_sha256"]) == 64
    approval = router.load_trusted_approval(
        result["repo"], APPROVAL_REF, router.TaskPack.from_mapping(TASK)
    )
    text = _invocation_path(result["repo"]).read_text()
    assert approval.nonce not in text
    assert "challenge_nonce" not in text


def test_production_adapter_stays_pinned(tmp_path: Path) -> None:
    # D8 F4: the substitution seam must not hide a production-path regression.
    production = router.ControlledHermesAdapter.production()
    assert production._test_only is False
    assert production._executable == router.HERMES_EXECUTABLE
    assert harness._adapter(tmp_path)._test_only is True
    with pytest.raises(router.RoutingError) as refused:
        router._verify_executor(Path("/bin/true"), production=True)
    assert "executor_untrusted" in str(refused.value)


def test_dispatcher_does_not_touch_credentials_or_live_hermes(dispatched: dict) -> None:
    repo = dispatched["repo"]
    artifacts = list((repo / "runs" / "capability").glob("*"))
    assert artifacts, "execution must leave an audit trail"
    real_hermes = router.HERMES_EXECUTABLE
    assert real_hermes.exists()
    # The stub path is the only executor that ran: the pinned binary is never opened for exec.
    assert dispatched["adapter"]._executable != real_hermes
    for path in artifacts:
        text = path.read_text()
        assert "challenge_nonce" not in text
        assert str(real_hermes) not in text


def test_stale_junit_report_cannot_become_evidence(tmp_path: Path) -> None:
    """D8: a green report planted before the run must not survive into this run's evidence."""
    repo, task_file = _scratch(tmp_path)
    planted = repo / "artifacts" / "capability" / "junit.xml"
    planted.write_text(
        '<testsuite name="planted" tests="1" failures="0" errors="0" skipped="0">'
        '<testcase classname="planted" name="planted-check"/></testsuite>',
        encoding="utf-8",
    )
    adapter = harness._adapter(tmp_path, mode="empty")
    result = _dispatch(repo, task_file, APPROVAL_REF, adapter)
    assert result["code"] != 0
    assert "evidence_no_tests" in result["stderr"] or "result_contract_invalid" in result["stderr"]
    assert not list((repo / "runs" / "capability").glob("*.evidence.json"))


def test_main_is_the_wired_entrypoint() -> None:
    """Guard: the E2E tests are only meaningful while main() stays the wired path."""
    with pytest.raises(SystemExit), contextlib.redirect_stdout(io.StringIO()):
        router.main(["--help"])


def test_smoke_helper_matches_shipped_contracts() -> None:
    assert harness.TASK_RAW["schema"] == router.TASK_SCHEMA
    assert shutil.which("bwrap") == str(router.BWRAP_EXECUTABLE)
    assert subprocess.run(["git", "--version"], capture_output=True).returncode == 0
