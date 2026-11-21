"""Security acceptance tests for the C1-03 capability execution boundary."""
from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
import subprocess
import sys
import time
from dataclasses import replace
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

import sdb_capability_router as router
import sdb_capability_trust as trust

TASK_RAW = {
    "schema": router.TASK_SCHEMA,
    "capability_id": "BE-SP-03",
    "lane": "backend",
    "goal": "Validate the approved API contract without production data.",
    "requested_write_paths": [],
}


@pytest.fixture()
def registry() -> router.RoutingRegistry:
    return router.RoutingRegistry.from_mapping(router.load_registry_mapping(REPO))


@pytest.fixture()
def pack() -> router.TaskPack:
    return router.TaskPack.from_mapping(TASK_RAW)


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=repo, check=True, text=True, capture_output=True
    )
    return proc.stdout.strip()


def _approval_yaml(
    task: router.TaskPack,
    *,
    approval_ref: str = "C1-03-TEST-APPROVAL",
    roots: tuple[str, ...] = (),
    issued: str = "2026-11-21T00:00:00Z",
    expires: str = "2026-12-20T00:00:00Z",
    nonce: str = "c103-test-nonce-0001",
) -> str:
    roots_yaml = "[" + ", ".join(roots) + "]"
    return f"""schema: sdb.capability.execution-approvals/1
records:
  - approval_ref: {approval_ref}
    task_digest: {task.digest()}
    capability_id: {task.capability_id}
    lane: {task.lane}
    allowed_write_roots: {roots_yaml}
    nonproduction: true
    issuer: SDB-OWNER-SESSION-2026-11-21
    issued_at: {issued}
    expires_at: {expires}
    nonce: {nonce}
"""


def _trusted_repo(
    tmp_path: Path,
    task: router.TaskPack,
    *,
    roots: tuple[str, ...] = (),
    issued: str = "2026-11-21T00:00:00Z",
    expires: str = "2026-12-20T00:00:00Z",
    nonce: str = "c103-test-nonce-0001",
) -> Path:
    repo = tmp_path / "repo"
    (repo / "registry").mkdir(parents=True)
    (repo / "scripts").mkdir()
    (repo / "runs" / "capability").mkdir(parents=True)
    (repo / "registry" / "capability_pilot.yaml").write_bytes(
        (REPO / "registry" / "capability_pilot.yaml").read_bytes()
    )
    (repo / "registry" / "capability_execution_approvals.yaml").write_text(
        _approval_yaml(task, roots=roots, issued=issued, expires=expires, nonce=nonce),
        encoding="utf-8",
    )
    (repo / "scripts" / "sdb_capability_router.py").write_text(
        "# protected implementation fixture\n", encoding="utf-8"
    )
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "Capability Test")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "trusted fixture")
    return repo


def _fake_executor(
    tmp_path: Path,
    *,
    mode: str = "valid",
    side_effect: str | None = None,
) -> Path:
    path = tmp_path / f"fake-hermes-{mode}"
    script = f"""#!/usr/bin/python3
import hashlib, json, subprocess, sys, time
prompt = json.loads(sys.stdin.read())
mode = {mode!r}
side_effect = {side_effect!r}
if mode == 'empty':
    raise SystemExit(0)
if mode == 'arbitrary':
    print('not-json')
    raise SystemExit(0)
if mode == 'oversize':
    sys.stdout.write('x' * 200000)
    sys.stdout.flush()
    time.sleep(5)
if mode == 'timeout-descendant':
    subprocess.Popen(['/usr/bin/python3', '-c', "import time; time.sleep(.35); open(" + repr(side_effect) + ", 'w').write('escaped')"])
    time.sleep(5)
if mode == 'write-probe':
    try:
        open(side_effect, 'w').write('escape')
        raise SystemExit(9)
    except OSError:
        pass
if mode == 'isolation-probe':
    import os, socket
    spec = json.loads(side_effect)
    leaks = [item for item in spec['probes'] if os.path.lexists(item)]
    for item in ('/run', '/var/run', '/root', '/mnt', '/media', '/srv', '/opt', '/var'):
        if os.path.lexists(item) and os.listdir(item):
            leaks.append(item)
    allowed = [os.path.realpath(item) for item in spec['allowed']]
    def walk(directory):
        for name in os.listdir(directory):
            full = os.path.join(directory, name)
            if full in allowed:
                continue
            if any(item.startswith(full + os.sep) for item in allowed):
                walk(full)
            else:
                leaks.append(full)
    walk(os.environ['HOME'])
    for sock_path in spec['probes']:
        try:
            client = socket.socket(socket.AF_UNIX)
            client.connect(sock_path)
            leaks.append('connect:' + sock_path)
        except OSError:
            pass
    if leaks:
        sys.stderr.write(repr(leaks))
        raise SystemExit(9)
if mode == 'mutate-protected':
    open(side_effect, 'w').write('# changed during execution\\n')
response = hashlib.sha256(
    (prompt['challenge_nonce'] + '/' + prompt['capability_id'] + '/' + prompt['task_digest']).encode()
).hexdigest()
result = {{
    'schema': 'sdb.capability.result/1',
    'capability_id': prompt['capability_id'],
    'verdict': 'PASS_VERIFIED_SUBSCOPE',
    'challenge_response': response,
}}
if mode == 'forged':
    result['challenge_response'] = '0' * 64
if mode == 'wrong-capability':
    result['capability_id'] = 'BE-SP-12'
if mode == 'bad-verdict':
    result['verdict'] = 'INTEGRATED_VERIFIED'
if mode == 'extra-field':
    result['tests_passed'] = 999
print(json.dumps(result, separators=(',', ':')))
"""
    path.write_text(script, encoding="utf-8")
    path.chmod(0o700)
    return path


def _adapter(tmp_path: Path, *, mode: str = "valid", side_effect: str | None = None, **kw):
    return router.ControlledHermesAdapter.for_test(
        _fake_executor(tmp_path, mode=mode, side_effect=side_effect), **kw
    )


def _approval(
    repo: Path,
    task: router.TaskPack,
    *,
    now: dt.datetime | None = None,
) -> router.ApprovalRecord:
    return router.load_trusted_approval(
        repo,
        "C1-03-TEST-APPROVAL",
        task,
        now=now or dt.datetime(2026, 11, 21, 12, tzinfo=dt.timezone.utc),
    )


def test_registry_is_exact_12_frontend_and_14_backend(registry: router.RoutingRegistry) -> None:
    assert registry.lanes["frontend"].capability_ids == tuple(
        f"FE-SP-{number:02d}" for number in range(1, 13)
    )
    assert registry.lanes["backend"].capability_ids == tuple(
        f"BE-SP-{number:02d}" for number in range(1, 15)
    )


def test_registry_rejects_13_frontend_13_backend_split() -> None:
    raw = copy.deepcopy(router.load_registry_mapping(REPO))
    raw["routing"]["lanes"]["frontend"]["capability_ids"].append("FE-SP-13")
    raw["routing"]["lanes"]["backend"]["capability_ids"].remove("BE-SP-14")
    with pytest.raises(router.RoutingError, match="registry_ids_invalid"):
        router.RoutingRegistry.from_mapping(raw)


def test_task_digest_is_canonical_and_sensitive(pack: router.TaskPack) -> None:
    assert pack.digest() == "6bcb0492d7927db8723e0ac5f5bc6c63752c5717940feb03f46a0495df2348d7"
    assert replace(pack, goal=pack.goal + " altered").digest() != pack.digest()


def test_cli_has_approval_ref_not_caller_authorization_file() -> None:
    parser = router.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["--task", "task.json", "--authorization", "forged.json"])
    with pytest.raises(SystemExit):
        parser.parse_args(
            ["--task", "task.json", "--approval-ref", "x", "--no-record-evidence"]
        )


def test_trusted_approval_is_loaded_from_committed_store(tmp_path: Path, pack: router.TaskPack) -> None:
    repo = _trusted_repo(tmp_path, pack)
    approval = _approval(repo, pack)
    assert approval.task_digest == pack.digest()
    assert approval.issuer == "SDB-OWNER-SESSION-2026-11-21"
    assert approval.nonproduction is True


def test_forged_unknown_approval_is_rejected(tmp_path: Path, pack: router.TaskPack) -> None:
    repo = _trusted_repo(tmp_path, pack)
    with pytest.raises(router.RoutingError, match="approval_unknown"):
        router.load_trusted_approval(repo, "CALLER-SAYS-APPROVED", pack)


def test_modified_approval_store_is_rejected(tmp_path: Path, pack: router.TaskPack) -> None:
    repo = _trusted_repo(tmp_path, pack)
    path = repo / "registry" / "capability_execution_approvals.yaml"
    path.write_text(path.read_text() + "# caller alteration\n", encoding="utf-8")
    with pytest.raises(router.RoutingError, match="approval_store_modified"):
        router.load_trusted_approval(repo, "C1-03-TEST-APPROVAL", pack)


def test_expired_approval_is_rejected(tmp_path: Path, pack: router.TaskPack) -> None:
    repo = _trusted_repo(tmp_path, pack, expires="2026-11-21T01:00:00Z")
    with pytest.raises(router.RoutingError, match="approval_expired"):
        _approval(repo, pack)


def test_approval_for_wrong_task_is_rejected(tmp_path: Path, pack: router.TaskPack) -> None:
    repo = _trusted_repo(tmp_path, pack)
    changed = replace(pack, goal="different approved operation")
    with pytest.raises(router.RoutingError, match="approval_task_mismatch"):
        _approval(repo, changed)


def test_replayed_approval_is_rejected(tmp_path: Path, pack: router.TaskPack) -> None:
    repo = _trusted_repo(tmp_path, pack)
    approval = _approval(repo, pack)
    replay = repo / "runs" / "capability" / "approval-replay"
    router.consume_approval(approval, replay)
    with pytest.raises(router.RoutingError, match="approval_replayed"):
        router.consume_approval(approval, replay)


def test_symlinked_replay_parent_is_rejected_before_write(tmp_path: Path, pack: router.TaskPack) -> None:
    repo = _trusted_repo(tmp_path, pack)
    approval = _approval(repo, pack)
    outside = tmp_path / "outside"
    outside.mkdir()
    (repo / "runs" / "capability" / "approval-replay").symlink_to(outside)
    with pytest.raises(router.RoutingError, match="secure_path_symlink"):
        router.consume_approval(approval, repo / "runs" / "capability" / "approval-replay")
    assert list(outside.iterdir()) == []


def test_sandbox_denies_repo_write_outside_approved_roots(
    tmp_path: Path, pack: router.TaskPack, registry: router.RoutingRegistry
) -> None:
    repo = _trusted_repo(tmp_path, pack)
    approval = _approval(repo, pack)
    escaped = repo / "escape.txt"
    result = router.execute(
        pack, approval, registry, repo,
        _adapter(tmp_path, mode="write-probe", side_effect=str(escaped)),
    )
    assert result.status == "PASS_VERIFIED_SUBSCOPE", (
        result.failure_code, result.exit_code, result.stderr_excerpt, result.stdout_excerpt
    )
    assert result.verified_result is True
    assert not escaped.exists()
    assert "--ro-bind-fd" in result.sandbox_argv
    assert "--bind-fd" not in result.sandbox_argv


def test_sandbox_hides_git_even_when_another_root_is_writable(
    tmp_path: Path, registry: router.RoutingRegistry
) -> None:
    task = router.TaskPack.from_mapping(
        TASK_RAW | {"requested_write_paths": ["approved/output.txt"]}
    )
    repo = _trusted_repo(tmp_path, task, roots=("approved",))
    (repo / "approved").mkdir()
    target = repo / ".git" / "executor-escape"
    result = router.execute(
        task,
        _approval(repo, task),
        registry,
        repo,
        _adapter(tmp_path, mode="write-probe", side_effect=str(target)),
    )
    assert result.status == "PASS_VERIFIED_SUBSCOPE"
    assert not target.exists()
    assert "--tmpfs" in result.sandbox_argv
    assert "--remount-ro" in result.sandbox_argv


def test_sandbox_allows_only_preopened_approved_directory(
    tmp_path: Path, registry: router.RoutingRegistry
) -> None:
    task = router.TaskPack.from_mapping(
        TASK_RAW | {"requested_write_paths": ["approved/output.txt"]}
    )
    repo = _trusted_repo(tmp_path, task, roots=("approved",))
    (repo / "approved").mkdir()
    approval = _approval(repo, task)
    target = repo / "approved" / "output.txt"
    result = router.execute(
        task, approval, registry, repo,
        _adapter(tmp_path, mode="mutate-protected", side_effect=str(target)),
    )
    assert result.verified_result is True
    assert target.read_text() == "# changed during execution\n"
    assert "--bind-fd" in result.sandbox_argv


@pytest.mark.parametrize(
    "mode", ["empty", "arbitrary", "forged", "wrong-capability", "bad-verdict", "extra-field"]
)
def test_result_contract_rejects_invalid_output(
    tmp_path: Path, pack: router.TaskPack, registry: router.RoutingRegistry, mode: str
) -> None:
    repo = _trusted_repo(tmp_path, pack)
    result = router.execute(pack, _approval(repo, pack), registry, repo, _adapter(tmp_path, mode=mode))
    assert result.verified_result is False
    assert result.status == "FAIL"
    assert result.failure_code == "result_contract_invalid"


def test_hermes_argv_and_prompt_contract_are_fixed(
    tmp_path: Path, pack: router.TaskPack, registry: router.RoutingRegistry
) -> None:
    repo = _trusted_repo(tmp_path, pack)
    result = router.execute(pack, _approval(repo, pack), registry, repo, _adapter(tmp_path))
    assert result.argv == (
        "-p", "cc-builder", "chat", "--query-file", "-", "--oneshot", "--quiet",
        "--format", "text", "--source", "tool", "--run-budget", "30",
    )
    assert result.status == "PASS_VERIFIED_SUBSCOPE"
    assert result.verified_result is True
    assert result.result_schema == router.RESULT_SCHEMA
    sandbox = result.sandbox_argv
    assert "--unshare-all" in sandbox and "--share-net" in sandbox
    assert "--clearenv" in sandbox and "--new-session" in sandbox
    assert "--yolo" not in sandbox
    assert sandbox.count("--tmp-overlay") == 1
    overlay_index = sandbox.index("--tmp-overlay")
    assert sandbox[overlay_index + 1] == str(router.HERMES_PROFILE_ROOT / "cc-builder")


def test_revision_binding_detects_protected_file_change(
    tmp_path: Path, registry: router.RoutingRegistry, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Defense in depth: simulate a sandbox failure by lifting the approval-time root denylist.
    monkeypatch.setattr(trust, "FORBIDDEN_ROOT_HEADS", frozenset())
    task = router.TaskPack.from_mapping(
        TASK_RAW | {"requested_write_paths": ["scripts/sdb_capability_router.py"]}
    )
    repo = _trusted_repo(tmp_path, task, roots=("scripts",))
    protected = repo / "scripts" / "sdb_capability_router.py"
    result = router.execute(
        task, _approval(repo, task), registry, repo,
        _adapter(tmp_path, mode="mutate-protected", side_effect=str(protected)),
    )
    assert result.status == "FAIL"
    assert result.failure_code == "revision_binding_changed"
    assert result.revision_binding_before.files["scripts/sdb_capability_router.py"].tracked


def test_revision_binding_represents_dirty_and_untracked_files(
    tmp_path: Path, pack: router.TaskPack
) -> None:
    repo = _trusted_repo(tmp_path, pack)
    protected = repo / "scripts" / "sdb_capability_router.py"
    protected.write_text("# dirty\n", encoding="utf-8")
    untracked = repo / "scripts" / "sdb_capability_sandbox.py"
    untracked.write_text("# untracked\n", encoding="utf-8")
    binding = router.capture_revision_binding(repo)
    assert binding.files["scripts/sdb_capability_router.py"].dirty is True
    assert binding.files["scripts/sdb_capability_sandbox.py"].tracked is False
    assert binding.files["scripts/sdb_capability_sandbox.py"].sha256 == hashlib.sha256(
        b"# untracked\n"
    ).hexdigest()


def test_streaming_output_limit_kills_execution(
    tmp_path: Path, pack: router.TaskPack, registry: router.RoutingRegistry
) -> None:
    repo = _trusted_repo(tmp_path, pack)
    result = router.execute(
        pack, _approval(repo, pack), registry, repo,
        _adapter(tmp_path, mode="oversize", max_output_bytes=4096, timeout_seconds=2),
    )
    assert result.status == "FAIL"
    assert result.failure_code == "execution_output_limit"
    assert result.output_bytes <= 4096


def test_timeout_kills_descendant_process(
    tmp_path: Path, registry: router.RoutingRegistry
) -> None:
    task = router.TaskPack.from_mapping(
        TASK_RAW | {"requested_write_paths": ["approved/late.txt"]}
    )
    repo = _trusted_repo(tmp_path, task, roots=("approved",))
    (repo / "approved").mkdir()
    marker = repo / "approved" / "late.txt"
    result = router.execute(
        task, _approval(repo, task), registry, repo,
        _adapter(tmp_path, mode="timeout-descendant", side_effect=str(marker), timeout_seconds=0.08),
    )
    assert result.failure_code == "execution_timeout"
    time.sleep(0.5)
    assert not marker.exists()


def test_execution_artifact_has_only_digest_and_bounded_redacted_excerpt(
    tmp_path: Path, pack: router.TaskPack, registry: router.RoutingRegistry
) -> None:
    repo = _trusted_repo(tmp_path, pack)
    result = router.execute(pack, _approval(repo, pack), registry, repo, _adapter(tmp_path))
    artifact, _ = router.write_invocation_artifact(result, repo)
    payload = json.loads((repo / artifact).read_text())
    assert "stdout" not in payload and "stderr" not in payload
    assert len(payload["stdout_excerpt"].encode()) <= router.MAX_EXCERPT_BYTES
    assert len(payload["stdout_sha256"]) == 64


def test_evidence_symlink_parent_fails_before_any_outside_write(
    tmp_path: Path, pack: router.TaskPack, registry: router.RoutingRegistry
) -> None:
    repo = _trusted_repo(tmp_path, pack)
    result = router.execute(pack, _approval(repo, pack), registry, repo, _adapter(tmp_path))
    outside = tmp_path / "outside"
    outside.mkdir()
    capability = repo / "runs" / "capability"
    capability.rmdir()
    capability.symlink_to(outside, target_is_directory=True)
    with pytest.raises(router.RoutingError, match="secure_path_symlink"):
        router.record_execution_evidence(result, repo)
    assert list(outside.iterdir()) == []


def test_verified_result_yields_be_sp12_compatible_mandatory_evidence(
    tmp_path: Path, pack: router.TaskPack, registry: router.RoutingRegistry
) -> None:
    repo = _trusted_repo(tmp_path, pack)
    result = router.execute(pack, _approval(repo, pack), registry, repo, _adapter(tmp_path))
    evidence = router.record_execution_evidence(result, repo)
    assert evidence["execution_status"] == "PASS"
    assert evidence["acceptance_status"] == "INFORMATIONAL_ONLY"
    assert evidence["router_verdict"] == "INTEGRATION_TESTED_NONPRODUCTION"
    payload = json.loads(Path(evidence["evidence_path"]).read_text())
    assert payload["schema"] == "sdb.capability.evidence/1"
    assert payload["test_results"] == {
        "passed": 1, "failed": 0, "skipped": 0, "errors": 0, "total": 1
    }


def test_unverified_result_cannot_create_positive_evidence(
    tmp_path: Path, pack: router.TaskPack, registry: router.RoutingRegistry
) -> None:
    repo = _trusted_repo(tmp_path, pack)
    result = router.execute(
        pack, _approval(repo, pack), registry, repo, _adapter(tmp_path, mode="forged")
    )
    with pytest.raises(router.RoutingError, match="evidence_result_unverified"):
        router.record_execution_evidence(result, repo)

    output = router.finish_public_execution(result, repo)
    assert output["verdict"] == "FAIL"
    payload = json.loads(Path(output["evidence"]["evidence_path"]).read_text())
    assert payload["test_results"] == {
        "passed": 0, "failed": 1, "skipped": 0, "errors": 0, "total": 1
    }
    assert len(payload["integrity"]) == 64


def test_public_flow_fails_when_mandatory_evidence_write_fails(
    tmp_path: Path, pack: router.TaskPack, registry: router.RoutingRegistry
) -> None:
    repo = _trusted_repo(tmp_path, pack)
    result = router.execute(pack, _approval(repo, pack), registry, repo, _adapter(tmp_path))
    outside = tmp_path / "outside"
    outside.mkdir()
    capability = repo / "runs" / "capability"
    capability.rmdir()
    capability.symlink_to(outside, target_is_directory=True)
    with pytest.raises(router.RoutingError, match="secure_path_symlink"):
        router.finish_public_execution(result, repo)
    assert list(outside.iterdir()) == []


def test_test_executable_is_programmatic_only_and_production_path_is_pinned() -> None:
    assert router.HERMES_EXECUTABLE == Path("/home/anashadi/.local/bin/hermes")
    assert router.BWRAP_EXECUTABLE == Path("/usr/bin/bwrap")
    with pytest.raises(TypeError):
        router.ControlledHermesAdapter(executable="/tmp/caller-controlled")


def test_sandbox_hides_host_sockets_and_credentials(
    tmp_path: Path, pack: router.TaskPack, registry: router.RoutingRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import os
    import socket

    monkeypatch.setattr(router, "_excerpt", lambda data: data.decode(errors="replace"))  # leak list is diagnostics

    repo = _trusted_repo(tmp_path, pack)
    secret = tmp_path / "host-secret.env"
    secret.write_text("TOKEN=[REDACTED]\n", encoding="utf-8")
    import tempfile

    short = Path(tempfile.mkdtemp(prefix="s", dir="/tmp"))
    sock_path = short / "h.sock"
    server = socket.socket(socket.AF_UNIX)
    server.bind(str(sock_path))
    server.listen(1)
    home = Path.home()
    probes = [
        str(secret), str(sock_path), "/var/run/docker.sock", "/run/docker.sock",
        f"/run/user/{os.getuid()}/bus", f"/run/user/{os.getuid()}/systemd/private",
        str(home / ".ssh"), str(home / ".gnupg"), str(home / ".hermes" / "auth.json"),
        str(home / ".hermes" / "profiles" / "default"),
    ]
    spec = {"probes": probes, "allowed": [str(repo), str(router.HERMES_PROFILE_ROOT / "cc-builder")]}
    try:
        result = router.execute(
            pack, _approval(repo, pack), registry, repo,
            _adapter(tmp_path, mode="isolation-probe", side_effect=json.dumps(spec)),
        )
    finally:
        server.close()
        sock_path.unlink(missing_ok=True)
        short.rmdir()
    assert result.status == "PASS_VERIFIED_SUBSCOPE", (
        result.failure_code, result.exit_code, result.stderr_excerpt
    )
    assert "--ro-bind" in result.sandbox_argv
    argv = list(result.sandbox_argv)
    for index, token in enumerate(argv[:-2]):
        assert not (token == "--ro-bind" and argv[index + 1] == "/" and argv[index + 2] == "/")
    assert "/run" not in argv and "/home" not in argv


def test_excerpt_never_persists_raw_executor_output() -> None:
    # Sample strings are assembled at runtime so the repository holds no secret-shaped literals.
    marker = "S" + "ECRET" + "-" + "VALUE"
    samples = [
        f"Authorization: Bearer {marker}".encode(),
        ('{"api' + '_key": "' + marker + '"}').encode(),
        f"cookie: sid={marker}".encode(),
        f"passwd={marker}".encode(),
        b"gh" + b"p_" + b"A" * 36,
        ("-----BEGIN " + "PRIVATE KEY-----\n" + marker + "\n-----END " + "PRIVATE KEY-----").encode(),
        f"postgres://user:{marker}@host/db".encode(),
        f'password = "word {marker}"'.encode(),
    ]
    for raw in samples:
        out = router._excerpt(raw)
        assert out.startswith("[WITHHELD")
        assert marker not in out
        assert hashlib.sha256(raw).hexdigest() in out


def test_oversized_goal_is_rejected_at_the_boundary() -> None:
    with pytest.raises(router.RoutingError, match="task_goal_too_long"):
        router.TaskPack.from_mapping(TASK_RAW | {"goal": "x" * 5000})


def test_signal_exit_is_not_reported_as_success() -> None:
    assert router._evidence_exit_code(-9) == 137
    assert router._evidence_exit_code(0) == 0
    assert router._evidence_exit_code(3) == 3
    assert router._evidence_exit_code(500) == 255


def test_approval_rejects_duplicate_yaml_keys(tmp_path: Path, pack: router.TaskPack) -> None:
    repo = _trusted_repo(tmp_path, pack)
    store = repo / "registry" / "capability_execution_approvals.yaml"
    store.write_text(
        store.read_text().replace(
            "    allowed_write_roots: []\n", "    allowed_write_roots: []\n    allowed_write_roots: [approved]\n"
        ),
        encoding="utf-8",
    )
    _git(repo, "commit", "-qam", "dup key")
    with pytest.raises(router.RoutingError, match="yaml_duplicate_key"):
        _approval(repo, pack)


def test_approval_rejects_alias_excessive_ttl_and_protected_roots(
    tmp_path: Path, pack: router.TaskPack
) -> None:
    (tmp_path / "a").mkdir()
    with pytest.raises(router.RoutingError, match="approval_time_invalid"):
        _approval(_trusted_repo(tmp_path / "a", pack, expires="9999-01-01T00:00:00Z"), pack)
    for root in ("scripts", "registry", "runs"):
        sub = tmp_path / f"r-{root}"
        sub.mkdir()
        with pytest.raises(router.RoutingError, match="approval_roots_invalid"):
            _approval(_trusted_repo(sub, pack, roots=(root,)), pack)


@pytest.mark.parametrize("flag", ["--assume-unchanged", "--skip-worktree"])
def test_index_flags_cannot_hide_a_modified_approval_store(
    tmp_path: Path, pack: router.TaskPack, flag: str
) -> None:
    repo = _trusted_repo(tmp_path, pack)
    store = repo / "registry" / "capability_execution_approvals.yaml"
    store.write_text(store.read_text().replace("SDB-OWNER-SESSION", "ATTACKER-SESSION"), encoding="utf-8")
    _git(repo, "update-index", flag, "registry/capability_execution_approvals.yaml")
    with pytest.raises(router.RoutingError, match="approval_store_modified"):
        _approval(repo, pack)


def test_trust_checks_ignore_caller_git_environment(
    tmp_path: Path, pack: router.TaskPack, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _trusted_repo(tmp_path, pack)
    decoy = tmp_path / "decoy-index"
    monkeypatch.setenv("GIT_INDEX_FILE", str(decoy))
    monkeypatch.setenv("GIT_DIR", str(tmp_path / "nonexistent.git"))
    assert _approval(repo, pack).approval_ref == "C1-03-TEST-APPROVAL"
    assert not decoy.exists()


def test_production_executor_pins_inner_hermes_entrypoint() -> None:
    assert router.HERMES_INNER_SHA256 and len(router.HERMES_INNER_SHA256) == 64
    assert router.HERMES_INNER_EXECUTABLE.is_absolute()


def test_production_sandbox_shadows_runtime_credential_files() -> None:
    profile = router.HERMES_PROFILE_ROOT / "cc-builder"
    if not profile.is_dir() or not router.HERMES_RUNTIME_DIRS[0].is_dir():
        pytest.skip("Hermes runtime not installed on this host")
    argv = router._sandbox_base(production=True, profile_dir=profile)
    env_file = router.HERMES_RUNTIME_DIRS[0] / ".env"
    if not env_file.is_file():
        pytest.skip("no runtime .env on this host")
    probe = subprocess.run(
        [*argv, "--", "/usr/bin/test", "-s", str(env_file)], capture_output=True, check=False
    )
    assert probe.returncode == 1  # file present but empty: real contents are shadowed
    for hidden in ("/var/run/docker.sock", f"{Path.home()}/.ssh", "/run/user"):
        gone = subprocess.run([*argv, "--", "/usr/bin/test", "-e", hidden], check=False)
        assert gone.returncode == 1, hidden


def test_strict_yaml_rejects_unhashable_keys_with_routing_error() -> None:
    with pytest.raises(router.RoutingError, match="yaml_invalid"):
        trust.strict_yaml_load(b"? [a]\n: 1\n", "probe")
