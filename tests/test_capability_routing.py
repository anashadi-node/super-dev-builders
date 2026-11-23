"""Security acceptance tests for the C1-03 capability execution boundary."""
from __future__ import annotations

import base64
import copy
import datetime as dt
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from dataclasses import replace
from pathlib import Path

import pytest
import yaml

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


def _keypair(state: Path) -> Path:
    """Synthetic Ed25519 keypair in the trust state dir (never in the repo, never in a prompt)."""
    state.mkdir(parents=True, exist_ok=True)
    state.chmod(0o700)
    private = state / "approval_key.pem"
    subprocess.run(["openssl", "genpkey", "-algorithm", "ED25519", "-out", str(private)],
                   check=True, capture_output=True)
    private.chmod(0o600)
    public = state / "approval_pubkey.pem"
    subprocess.run(["openssl", "pkey", "-in", str(private), "-pubout", "-out", str(public)],
                   check=True, capture_output=True)
    public.chmod(0o600)
    return private


def _sign(state: Path, record: dict) -> str:
    message = state / f"message-{uuid.uuid4().hex}"
    signature = state / f"signature-{uuid.uuid4().hex}"
    message.write_bytes(trust.approval_canonical(record))
    subprocess.run(
        ["openssl", "pkeyutl", "-sign", "-rawin", "-inkey", str(state / "approval_key.pem"),
         "-in", str(message), "-out", str(signature)],
        check=True, capture_output=True,
    )
    blob = signature.read_bytes()
    message.unlink()
    signature.unlink()
    return base64.b64encode(blob).decode("ascii")


def _approval_record(
    task: router.TaskPack,
    *,
    approval_ref: str = "C1-03-TEST-APPROVAL",
    roots: tuple[str, ...] = (),
    issued: str = "2026-11-21T00:00:00Z",
    expires: str = "2026-12-20T00:00:00Z",
    nonce: str | None = None,
    source_revision: str = "",
    execution_instance: str = "",
    issuer: str = "SDB-OWNER-SESSION-2026-11-21",
    scope_digest: str | None = None,
) -> dict:
    # Random per approval: a fixture constant made every run's nonce digest identical (D6 #5).
    nonce = nonce or f"c103-{uuid.uuid4().hex}"
    return {
        "approval_ref": approval_ref,
        "task_digest": task.digest(),
        "capability_id": task.capability_id,
        "lane": task.lane,
        "allowed_write_roots": list(roots),
        "nonproduction": True,
        "issuer": issuer,
        "issued_at": issued,
        "expires_at": expires,
        "nonce": nonce,
        "source_revision": source_revision,
        "execution_instance": execution_instance,
        "scope_digest": scope_digest or trust.approval_scope_digest(
            task.capability_id, task.lane, task.digest(), roots
        ),
        "issuer_key_id": "test-key-1",
        "signature": "",
    }


def _write_approval(state: Path, record: dict, *, sign: bool = True) -> Path:
    record = dict(record)
    record["signature"] = _sign(state, record) if sign else ""
    path = trust.approval_record_path(state, record["approval_ref"])
    path.parent.mkdir(mode=0o700, exist_ok=True)
    path.parent.chmod(0o700)
    path.write_text(yaml.safe_dump(record, sort_keys=True), encoding="utf-8")
    path.chmod(0o600)
    return path


def _trusted_repo(
    tmp_path: Path,
    task: router.TaskPack,
    *,
    roots: tuple[str, ...] = (),
    issued: str = "2026-11-21T00:00:00Z",
    expires: str = "2026-12-20T00:00:00Z",
    nonce: str | None = None,
    source_revision: str | None = None,
    execution_instance: str | None = None,
    issuer: str = "SDB-OWNER-SESSION-2026-11-21",
    sign: bool = True,
    state: Path | None = None,
    mutate=None,
) -> Path:
    repo = tmp_path / "repo"
    (repo / "registry").mkdir(parents=True)
    (repo / "scripts").mkdir()
    (repo / "runs" / "capability").mkdir(parents=True)
    (repo / "artifacts" / "capability").mkdir(parents=True)
    (repo / "registry" / "capability_pilot.yaml").write_bytes(
        (REPO / "registry" / "capability_pilot.yaml").read_bytes()
    )
    (repo / "scripts" / "sdb_capability_router.py").write_text(
        "# protected implementation fixture\n", encoding="utf-8"
    )
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "Capability Test")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "trusted fixture")
    state_dir = state or (tmp_path / "state")
    _keypair(state_dir)
    # D8 HIGH: the verification key must be pinned out-of-band; approvals name its fingerprint.
    pin = hashlib.sha256((state_dir / "approval_pubkey.pem").read_bytes()).hexdigest()
    os.environ["SDB_APPROVAL_PUBKEY_SHA256"] = pin
    instance = trust.instance_id(state_dir, create=True)
    head = _git(repo, "rev-parse", "HEAD")
    record = _approval_record(
        task, roots=roots, issued=issued, expires=expires, nonce=nonce,
        source_revision=source_revision if source_revision is not None else head,
        execution_instance=execution_instance if execution_instance is not None else instance,
        issuer=issuer,
    )
    record["issuer_key_id"] = f"sha256:{pin}"
    if mutate is not None:
        record = mutate(record)
    _write_approval(state_dir, record, sign=sign)
    os.environ["SDB_APPROVAL_STATE_HOME"] = str(state_dir)
    return repo


def _fake_executor(
    tmp_path: Path,
    *,
    mode: str = "valid",
    side_effect: str | None = None,
) -> Path:
    path = tmp_path / f"fake-hermes-{mode}"
    script = f"""#!/usr/bin/python3
import hashlib, json, os, subprocess, sys, time
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
if mode != 'empty':
    try:
        os.makedirs('artifacts/capability', exist_ok=True)
        failing = 0 if mode in (
            'valid', 'mutate-protected', 'write-probe', 'isolation-probe',
            'credential-probe', 'extra-field',
        ) else 1
        with open('artifacts/capability/junit.xml', 'w') as handle:
            handle.write(
                '<testsuite name="stub" tests="1" failures="%d" errors="0" skipped="0">'
                '<testcase classname="stub" name="stub-check"/></testsuite>' % failing
            )
    except OSError:
        pass
if mode == 'nonzero':
    sys.stderr.write('stub refused the task')
    raise SystemExit(7)
if mode == 'credential-probe':
    import os, socket
    spec = json.loads(side_effect)
    leaks = []
    for item in spec['secrets']:
        try:
            if open(item).read():
                leaks.append('read:' + item)
        except OSError:
            try:
                if os.listdir(item):
                    leaks.append('list:' + item)
            except OSError:
                pass
    probe = socket.socket()
    probe.settimeout(1.5)
    try:
        probe.connect(('1.1.1.1', 443))
        leaks.append('network:open')
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


def test_trusted_approval_is_loaded_from_trust_state(tmp_path: Path, pack: router.TaskPack) -> None:
    repo = _trusted_repo(tmp_path, pack)
    approval = _approval(repo, pack)
    assert approval.task_digest == pack.digest()
    assert approval.issuer == "SDB-OWNER-SESSION-2026-11-21"
    assert approval.nonproduction is True
    assert approval.source_revision == _git(repo, "rev-parse", "HEAD")
    assert approval.execution_instance.startswith("inst-")
    state = trust.approval_state_dir()
    assert approval.issuer_key_id == f"sha256:{hashlib.sha256((state / 'approval_pubkey.pem').read_bytes()).hexdigest()}"


def test_forged_unknown_approval_is_rejected(tmp_path: Path, pack: router.TaskPack) -> None:
    repo = _trusted_repo(tmp_path, pack)
    with pytest.raises(router.RoutingError, match="approval_record_missing"):
        router.load_trusted_approval(repo, "CALLER-SAYS-APPROVED", pack)


def test_modified_approval_record_is_rejected(tmp_path: Path, pack: router.TaskPack) -> None:
    """T6: any edit to the signed record breaks the signature, not just the store hash."""
    repo = _trusted_repo(tmp_path, pack)
    path = trust.approval_record_path(trust.approval_state_dir(), "C1-03-TEST-APPROVAL")
    record = yaml.safe_load(path.read_text())
    record["expires_at"] = "2099-12-20T00:00:00Z"
    path.write_text(yaml.safe_dump(record, sort_keys=True), encoding="utf-8")
    with pytest.raises(router.RoutingError, match="approval_signature_invalid"):
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
    """T2: one-time use is enforced by machine-local state."""
    repo = _trusted_repo(tmp_path, pack)
    approval = _approval(repo, pack)
    state = trust.approval_state_dir()
    router.consume_approval(approval, state)
    with pytest.raises(router.RoutingError, match="approval_replayed"):
        router.consume_approval(approval, state)


def test_replay_state_inside_the_working_copy_is_refused(tmp_path: Path, pack: router.TaskPack) -> None:
    """A clone must not be able to host its own replay ledger (fail-closed)."""
    repo = _trusted_repo(tmp_path, pack)
    approval = _approval(repo, pack)
    with pytest.raises(router.RoutingError, match="trust_state_missing"):
        router.consume_approval(approval, repo / "runs" / "capability" / "approval-replay")
    assert not (repo / "runs" / "capability" / "approval-replay").exists()


def test_symlinked_replay_parent_is_rejected_before_write(tmp_path: Path, pack: router.TaskPack) -> None:
    repo = _trusted_repo(tmp_path, pack)
    approval = _approval(repo, pack)
    outside = tmp_path / "outside"
    outside.mkdir()
    state = trust.approval_state_dir()
    (state / "approval-replay").symlink_to(outside)
    with pytest.raises(router.RoutingError, match="trust_state_corrupted"):
        router.consume_approval(approval, state)
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
    # Test-only executor: net namespace stays unshared, so "offline" is enforced, not advisory.
    assert "--unshare-all" in sandbox and "--unshare-net" in sandbox
    assert "--share-net" not in sandbox
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
    monkeypatch.setattr(router, "FORBIDDEN_ROOT_HEADS", frozenset())
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
    repo = _trusted_repo(tmp_path, pack, roots=("artifacts/capability",))
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
    repo = _trusted_repo(tmp_path, pack, roots=("artifacts/capability",))
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
    repo = _trusted_repo(tmp_path, pack, roots=("artifacts/capability",))
    result = router.execute(
        pack, _approval(repo, pack), registry, repo, _adapter(tmp_path, mode="forged")
    )
    with pytest.raises(router.RoutingError, match="evidence_result_unverified"):
        router.record_execution_evidence(result, repo)

    output = router.finish_public_execution(result, repo)
    assert output["verdict"] == "FAIL"
    payload = json.loads(Path(output["evidence"]["evidence_path"]).read_text())
    # Counts come from the JUnit report the run produced, never from the verdict.
    assert payload["test_results"] == {
        "passed": 0, "failed": 1, "skipped": 0, "errors": 0, "total": 1
    }
    assert payload["test_command"] == "junit:artifacts/capability/junit.xml"
    assert output["evidence"]["execution_status"] == "FAIL"
    assert len(payload["integrity"]) == 64


def test_public_flow_fails_when_mandatory_evidence_write_fails(
    tmp_path: Path, pack: router.TaskPack, registry: router.RoutingRegistry
) -> None:
    repo = _trusted_repo(tmp_path, pack, roots=("artifacts/capability",))
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
        ("Authorization: Bearer " + marker).encode(),
        ('{"api' + '_key": "' + marker + '"}').encode(),
        ("cookie: " + marker).encode(),
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
    path = trust.approval_record_path(trust.approval_state_dir(), "C1-03-TEST-APPROVAL")
    path.write_text(
        path.read_text().replace(
            "nonproduction: true\n", "nonproduction: true\nnonproduction: true\n"
        ),
        encoding="utf-8",
    )
    with pytest.raises(router.RoutingError, match="yaml_duplicate_key"):
        _approval(repo, pack)


def test_approval_rejects_alias_excessive_ttl_and_protected_roots(
    tmp_path: Path, pack: router.TaskPack
) -> None:
    (tmp_path / "a").mkdir()
    with pytest.raises(router.RoutingError, match="approval_time_invalid"):
        _approval(_trusted_repo(tmp_path / "a", pack, expires="9999-01-01T00:00:00Z"), pack)
    for root in sorted(trust.FORBIDDEN_ROOT_HEADS):
        sub = tmp_path / f"r-{root}"
        sub.mkdir()
        with pytest.raises(router.RoutingError, match="approval_roots_invalid"):
            _approval(_trusted_repo(sub, pack, roots=(root,)), pack)


def test_execute_rechecks_forbidden_write_roots(tmp_path: Path, pack: router.TaskPack) -> None:
    """Defence in depth: a tampered ApprovalRecord cannot widen writes at execute() time."""
    repo = _trusted_repo(tmp_path, pack)
    approval = replace(_approval(repo, pack), allowed_write_roots=("tests",))
    with pytest.raises(router.RoutingError, match="approval_roots_invalid"):
        router.execute(
            task=pack,
            approval=approval,
            registry=trust.load_routing_registry(repo),
            repo=repo,
            adapter=router.ControlledHermesAdapter.for_test(REPO / "tests" / "noop.sh"),
        )


@pytest.mark.parametrize("flag", ["--assume-unchanged", "--skip-worktree"])
def test_index_flags_cannot_hide_a_modified_approval_record(
    tmp_path: Path, pack: router.TaskPack, flag: str
) -> None:
    """Approvals are not in the working copy, so index tricks cannot launder a tampered record."""
    repo = _trusted_repo(tmp_path, pack)
    state = trust.approval_state_dir()
    assert repo.resolve() not in state.resolve().parents
    path = trust.approval_record_path(state, "C1-03-TEST-APPROVAL")
    path.write_text(path.read_text().replace("SDB-OWNER-SESSION", "ATTACKER-SESSION"), encoding="utf-8")
    _git(repo, "update-index", flag, "registry/capability_pilot.yaml")
    with pytest.raises(router.RoutingError, match="approval_signature_invalid"):
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


def test_production_sandbox_shares_net_and_binds_runtime_dirs() -> None:
    """D8 #1: the production branch of _sandbox_base must actually be built by a test."""
    profile = router.HERMES_PROFILE_ROOT / "cc-builder"
    argv = router._sandbox_base(production=True, profile_dir=profile)
    assert "--share-net" in argv
    assert "--unshare-net" not in argv
    for runtime in router.HERMES_RUNTIME_DIRS:
        if runtime.is_dir():
            triple = ["--ro-bind", str(runtime), str(runtime)]
            assert any(argv[i:i + 3] == triple for i in range(len(argv) - 2)), runtime


def test_routing_inconsistent_when_sandbox_net_flags_disagree(
    tmp_path: Path, pack: router.TaskPack, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D8 #7: the recorded network policy is checked against the argv, not re-derived from it."""
    repo = _trusted_repo(tmp_path, pack)
    real = router._sandbox_base
    monkeypatch.setattr(
        router, "_sandbox_base",
        lambda *, production, profile_dir: [
            *real(production=production, profile_dir=profile_dir), "--share-net",
        ],
    )
    with pytest.raises(router.RoutingError, match="routing_inconsistent"):
        router.execute(
            task=pack,
            approval=_approval(repo, pack),
            registry=trust.load_routing_registry(repo),
            repo=repo,
            adapter=_adapter(tmp_path),
        )


def test_verify_executor_pins_digest_in_both_directions(tmp_path: Path) -> None:
    """D6 #3 / D8 #1: prove the positive pin path, not only that /bin/true is refused."""
    if os.getuid() != 1000:
        pytest.skip("pinned owner expectation is uid 1000")
    copy = tmp_path / "hermes-copy"
    copy.write_bytes(Path("/bin/true").read_bytes())
    copy.chmod(0o755)
    digest = hashlib.sha256(copy.read_bytes()).hexdigest()
    fd = router._verify_executor(copy, production=True, expected_sha256=digest)
    try:
        assert os.fstat(fd).st_size == copy.stat().st_size
    finally:
        os.close(fd)
    with pytest.raises(router.RoutingError, match="digest differs"):
        router._verify_executor(copy, production=True, expected_sha256="0" * 64)


# ---------------------------------------------------------------------------
# C1-06 security acceptance (T1-T12): replay, binding, trust state, evidence.
# ---------------------------------------------------------------------------


def test_t1_valid_synthetic_approval_is_accepted_exactly_once(tmp_path: Path, pack: router.TaskPack) -> None:
    repo = _trusted_repo(tmp_path, pack)
    approval = _approval(repo, pack)
    state = trust.approval_state_dir()
    marker = router.consume_approval(approval, state)
    assert marker.exists()
    assert marker.stat().st_mode & 0o077 == 0
    with pytest.raises(router.RoutingError, match="approval_replayed"):
        router.consume_approval(approval, state)


def test_t3_cross_clone_replay_is_rejected(tmp_path: Path, pack: router.TaskPack) -> None:
    """Same signed approval presented from a second working copy of the repo."""
    repo = _trusted_repo(tmp_path, pack)
    approval = _approval(repo, pack)
    state = trust.approval_state_dir()
    router.consume_approval(approval, state)
    clone = tmp_path / "clone"
    shutil.copytree(repo, clone)
    assert _git(clone, "rev-parse", "HEAD") == _git(repo, "rev-parse", "HEAD")
    with pytest.raises(router.RoutingError, match="approval_replayed"):
        router.consume_approval(_approval(clone, pack), state)


def test_t4_approval_for_another_execution_instance_is_rejected(
    tmp_path: Path, pack: router.TaskPack
) -> None:
    other = tmp_path / "other-state"
    other.mkdir()
    other.chmod(0o700)
    _keypair(other)
    foreign = trust.instance_id(other, create=True)
    repo = _trusted_repo(tmp_path, pack, execution_instance=foreign)
    with pytest.raises(router.RoutingError, match="approval_instance_mismatch"):
        _approval(repo, pack)


def test_t5_wrong_source_revision_is_rejected(tmp_path: Path, pack: router.TaskPack) -> None:
    repo = _trusted_repo(tmp_path, pack, source_revision="0" * 40)
    with pytest.raises(router.RoutingError, match="approval_revision_mismatch"):
        _approval(repo, pack)


def test_t5_signed_scope_must_match_authorized_roots(tmp_path: Path, pack: router.TaskPack) -> None:
    repo = _trusted_repo(
        tmp_path, pack, roots=("approved",),
        mutate=lambda record: {**record, "allowed_write_roots": ["elsewhere"]},
    )
    with pytest.raises(router.RoutingError, match="approval_scope_digest_mismatch"):
        _approval(repo, pack)


def test_t8_not_yet_valid_approval_is_rejected(tmp_path: Path, pack: router.TaskPack) -> None:
    repo = _trusted_repo(
        tmp_path, pack, issued="2099-01-01T00:00:00Z", expires="2099-01-02T00:00:00Z"
    )
    with pytest.raises(router.RoutingError, match="approval_not_yet_valid"):
        _approval(repo, pack)


def test_t7_untrusted_issuer_is_rejected(tmp_path: Path, pack: router.TaskPack) -> None:
    repo = _trusted_repo(tmp_path, pack, issuer="ATTACKER-SESSION-2026-11-21")
    with pytest.raises(router.RoutingError, match="approval_issuer_untrusted"):
        _approval(repo, pack)


def test_t7_unsigned_approval_is_rejected(tmp_path: Path, pack: router.TaskPack) -> None:
    repo = _trusted_repo(tmp_path, pack, sign=False)
    with pytest.raises(router.RoutingError, match="approval_unsigned"):
        _approval(repo, pack)


def test_t7_swapped_verification_key_is_rejected(tmp_path: Path, pack: router.TaskPack) -> None:
    """A same-UID writer that replaces the key cannot pass: the fingerprint is pinned (D8 #1)."""
    repo = _trusted_repo(tmp_path, pack)
    state = trust.approval_state_dir()
    rogue = tmp_path / "rogue-state"
    _keypair(rogue)
    (state / "approval_pubkey.pem").write_bytes((rogue / "approval_pubkey.pem").read_bytes())
    with pytest.raises(router.RoutingError, match="trust_anchor_mismatch"):
        _approval(repo, pack)


def test_t7_signature_from_an_untrusted_key_is_rejected(
    tmp_path: Path, pack: router.TaskPack, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Even with the rogue key pinned, a record signed by the old key fails verification."""
    repo = _trusted_repo(tmp_path, pack)
    state = trust.approval_state_dir()
    rogue = tmp_path / "rogue-state"
    _keypair(rogue)
    (state / "approval_pubkey.pem").write_bytes((rogue / "approval_pubkey.pem").read_bytes())
    monkeypatch.setenv(
        "SDB_APPROVAL_PUBKEY_SHA256",
        hashlib.sha256((rogue / "approval_pubkey.pem").read_bytes()).hexdigest(),
    )
    with pytest.raises(router.RoutingError, match="approval_signature_invalid"):
        _approval(repo, pack)


def test_committed_approval_store_is_not_an_authority(tmp_path: Path, pack: router.TaskPack) -> None:
    """D6 BLOCKER-2: the registry record with this ref exists in Git but must never be read."""
    _trusted_repo(tmp_path, pack)
    root = Path(__file__).resolve().parents[1]
    assert (root / "registry" / "capability_execution_approvals.yaml").is_file()
    # The committed record exists in Git, yet it is not loadable: state dir has no such record.
    with pytest.raises(router.RoutingError, match="approval_record_missing"):
        router.load_trusted_approval(root, "C1-03-D6D8-NONPROD-20261121", pack)


def test_unpinned_verification_key_fails_closed(
    tmp_path: Path, pack: router.TaskPack, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _trusted_repo(tmp_path, pack)
    monkeypatch.delenv("SDB_APPROVAL_PUBKEY_SHA256", raising=False)
    with pytest.raises(router.RoutingError, match="trust_anchor_missing"):
        _approval(repo, pack)


def test_record_bound_to_another_key_id_is_rejected(tmp_path: Path, pack: router.TaskPack) -> None:
    repo = _trusted_repo(
        tmp_path, pack, mutate=lambda r: {**r, "issuer_key_id": "sha256:" + "0" * 64}
    )
    with pytest.raises(router.RoutingError, match="approval_issuer_key_mismatch"):
        _approval(repo, pack)


def test_trust_state_inside_the_working_copy_is_refused(tmp_path: Path, pack: router.TaskPack) -> None:
    repo = tmp_path / "repo"
    _trusted_repo(tmp_path, pack, state=repo / "state")
    with pytest.raises(router.RoutingError, match="trust_state_untrusted"):
        router.load_trusted_approval(repo, "C1-03-TEST-APPROVAL", pack)


def test_t9_missing_trust_state_fails_closed(
    tmp_path: Path, pack: router.TaskPack, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _trusted_repo(tmp_path, pack)
    monkeypatch.setenv("SDB_APPROVAL_STATE_HOME", str(tmp_path / "absent-state"))
    with pytest.raises(router.RoutingError, match="trust_state_missing"):
        _approval(repo, pack)


def test_t9_corrupted_instance_state_fails_closed(tmp_path: Path, pack: router.TaskPack) -> None:
    repo = _trusted_repo(tmp_path, pack)
    (trust.approval_state_dir() / "instance.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(router.RoutingError, match="trust_state_corrupted"):
        _approval(repo, pack)


def test_t9_group_readable_state_dir_is_untrusted(tmp_path: Path, pack: router.TaskPack) -> None:
    repo = _trusted_repo(tmp_path, pack)
    trust.approval_state_dir().chmod(0o755)
    with pytest.raises(router.RoutingError, match="trust_state_untrusted"):
        _approval(repo, pack)


def test_t9_missing_verification_key_fails_closed(tmp_path: Path, pack: router.TaskPack) -> None:
    repo = _trusted_repo(tmp_path, pack)
    (trust.approval_state_dir() / "approval_pubkey.pem").unlink()
    with pytest.raises(router.RoutingError, match="trust_anchor_missing"):
        _approval(repo, pack)


def test_t10_executor_pass_is_refused_when_the_test_report_contradicts_it(
    tmp_path: Path, pack: router.TaskPack, registry: router.RoutingRegistry
) -> None:
    """The stub returns a correct challenge and PASS while its own JUnit report records a failure."""
    repo = _trusted_repo(tmp_path, pack, roots=("artifacts/capability",))
    result = router.execute(
        pack, _approval(repo, pack), registry, repo, _adapter(tmp_path, mode="contradict")
    )
    assert result.status == "PASS_VERIFIED_SUBSCOPE"
    with pytest.raises(router.RoutingError, match="evidence_result_unverified"):
        router.record_execution_evidence(result, repo)


def test_t10_no_junit_report_means_no_evidence(tmp_path: Path, pack: router.TaskPack, registry: router.RoutingRegistry) -> None:
    """A handshake alone is not evidence: without an executed report nothing is recorded."""
    repo = _trusted_repo(tmp_path, pack, roots=("artifacts/capability",))
    result = router.execute(pack, _approval(repo, pack), registry, repo, _adapter(tmp_path))
    (repo / router.JUNIT_RELATIVE).unlink()
    with pytest.raises(router.RoutingError, match="evidence_no_tests"):
        router.record_execution_evidence(result, repo)


def _shim_openssl(directory: Path, *, marker: Path | None = None) -> Path:
    """A PATH shim that claims success for every signature (D8 attack #3)."""
    directory.mkdir(parents=True, exist_ok=True)
    shim = directory / "openssl"
    body = "#!/bin/sh\n" + (f"touch {marker}\n" if marker else "") + "exit 0\n"
    shim.write_text(body, encoding="utf-8")
    shim.chmod(0o755)
    return shim


def test_sec01_path_shim_cannot_forge_an_approval_signature(
    tmp_path: Path, pack: router.TaskPack, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A fake `openssl` earlier in PATH must never be consulted, let alone accept a forgery."""
    repo = _trusted_repo(tmp_path, pack)
    marker = tmp_path / "shim-ran"
    _shim_openssl(tmp_path / "shim", marker=marker)
    monkeypatch.setenv("PATH", f"{tmp_path / 'shim'}:{os.environ['PATH']}")
    record = _approval_record(
        pack,
        source_revision=_git(repo, "rev-parse", "HEAD"),
        execution_instance=trust.instance_id(trust.approval_state_dir()),
    )
    record["signature"] = base64.b64encode(b"\x00" * 64).decode("ascii")
    with pytest.raises(router.RoutingError, match="approval_signature_invalid"):
        trust.verify_approval_signature(record, state_dir=trust.approval_state_dir())
    assert not marker.exists(), "the PATH shim was executed"


def test_sec01_env_cannot_select_the_verifier(
    tmp_path: Path, pack: router.TaskPack, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D8 HIGH: pointing SDB_OPENSSL_BIN at another root-owned binary must not help."""
    repo = _trusted_repo(tmp_path, pack)
    monkeypatch.setenv("SDB_OPENSSL_BIN", "/bin/true")
    record = _approval_record(
        pack,
        source_revision=_git(repo, "rev-parse", "HEAD"),
        execution_instance=trust.instance_id(trust.approval_state_dir()),
    )
    record["signature"] = base64.b64encode(b"\x00" * 64).decode("ascii")
    with pytest.raises(router.RoutingError, match="approval_signature_invalid"):
        trust.verify_approval_signature(record, state_dir=trust.approval_state_dir())


def test_sec01_pin_cannot_endorse_a_substituted_binary(
    tmp_path: Path, pack: router.TaskPack, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A digest taken from the same env as the override cannot legitimise another binary."""
    repo = _trusted_repo(tmp_path, pack)
    substitute = Path("/bin/true")
    monkeypatch.setenv("SDB_OPENSSL_BIN", str(substitute))
    monkeypatch.setenv("SDB_OPENSSL_SHA256", hashlib.sha256(substitute.read_bytes()).hexdigest())
    record = _approval_record(
        pack,
        source_revision=_git(repo, "rev-parse", "HEAD"),
        execution_instance=trust.instance_id(trust.approval_state_dir()),
    )
    record["signature"] = base64.b64encode(b"\x00" * 64).decode("ascii")
    with pytest.raises(router.RoutingError, match="trust_verifier_mismatch"):
        trust.verify_approval_signature(record, state_dir=trust.approval_state_dir())


def test_sec01_verifier_pin_mismatch_fails_closed(
    tmp_path: Path, pack: router.TaskPack, monkeypatch: pytest.MonkeyPatch
) -> None:
    _trusted_repo(tmp_path, pack)
    monkeypatch.setenv("SDB_OPENSSL_SHA256", "0" * 64)
    with pytest.raises(router.RoutingError, match="trust_verifier_mismatch"):
        trust.open_trusted_verifier()


def test_sec01_system_verifier_is_accepted() -> None:
    """The default candidate set resolves to a real root-owned binary on this host."""
    fd, path, digest = trust.open_trusted_verifier()
    try:
        info = os.fstat(fd)
        assert info.st_uid == 0 and not info.st_mode & 0o022
        assert len(digest) == 64 and path.is_absolute()
    finally:
        os.close(fd)


def test_sec02_execute_refuses_a_revision_that_changed_after_approval(
    tmp_path: Path, pack: router.TaskPack, registry: router.RoutingRegistry
) -> None:
    """D8 attack #13: approving HEAD A must not authorize execution of HEAD B."""
    repo = _trusted_repo(tmp_path, pack)
    approval = _approval(repo, pack)
    _git(repo, "commit", "-q", "--allow-empty", "-m", "unapproved drift")
    assert _git(repo, "rev-parse", "HEAD") != approval.source_revision
    with pytest.raises(router.RoutingError, match="source_revision_changed"):
        router.execute(pack, approval, registry, repo, _adapter(tmp_path))


def test_sec02_revision_mismatch_does_not_burn_the_approval(
    tmp_path: Path, pack: router.TaskPack, registry: router.RoutingRegistry
) -> None:
    """The pre-flight refusal happens before the single-use marker is written."""
    repo = _trusted_repo(tmp_path, pack)
    approval = _approval(repo, pack)
    _git(repo, "commit", "-q", "--allow-empty", "-m", "unapproved drift")
    with pytest.raises(router.RoutingError, match="source_revision_changed"):
        router.execute(pack, approval, registry, repo, _adapter(tmp_path))
    assert not trust.replay_marker_path(approval, trust.approval_state_dir()).exists()


def test_sec02_dirty_worktree_is_refused(
    tmp_path: Path, pack: router.TaskPack, registry: router.RoutingRegistry
) -> None:
    """D8 HIGH: HEAD alone is a label — an uncommitted edit must not execute."""
    repo = _trusted_repo(tmp_path, pack)
    approval = _approval(repo, pack)
    target = repo / "scripts" / "sdb_capability_router.py"
    target.write_text(target.read_text(encoding="utf-8") + "\n# unapproved edit\n",
                      encoding="utf-8")
    with pytest.raises(router.RoutingError, match="source_revision_dirty"):
        router.execute(pack, approval, registry, repo, _adapter(tmp_path))
    assert not trust.replay_marker_path(approval, trust.approval_state_dir()).exists()


def test_sec02_untracked_executor_input_is_refused(
    tmp_path: Path, pack: router.TaskPack, registry: router.RoutingRegistry
) -> None:
    """An untracked tests/conftest.py can rewrite the verdict without touching HEAD."""
    repo = _trusted_repo(tmp_path, pack)
    approval = _approval(repo, pack)
    (repo / "tests").mkdir()
    (repo / "tests" / "conftest.py").write_text("import pytest\n", encoding="utf-8")
    with pytest.raises(router.RoutingError, match="source_revision_dirty"):
        router.execute(pack, approval, registry, repo, _adapter(tmp_path))


def test_sec02_late_revision_change_is_refused_before_launch(
    tmp_path: Path, pack: router.TaskPack, registry: router.RoutingRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The second check fires even when the pre-flight check saw the approved revision."""
    repo = _trusted_repo(tmp_path, pack)
    approval = _approval(repo, pack)
    real = router.capture_revision_binding

    def drifting(path: Path):
        binding = real(path)
        return trust.RevisionBinding("f" * 40, binding.files)

    monkeypatch.setattr(router, "capture_revision_binding", drifting)
    with pytest.raises(router.RoutingError, match="source_revision_changed"):
        router.execute(pack, approval, registry, repo, _adapter(tmp_path))
