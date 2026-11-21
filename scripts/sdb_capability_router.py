#!/usr/bin/env python3
"""Fail-closed C1 capability routing and nonproduction execution boundary."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import secrets
import selectors
import signal
import stat
import subprocess
import sys
import time
from contextlib import ExitStack
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

import sdb_capability_evidence
import sdb_common
from sdb_capability_trust import (
    ApprovalRecord,
    RevisionBinding,
    RoutingError,
    RoutingRegistry,
    TaskPack,
    canonical_bytes,
    capture_revision_binding,
    consume_approval,
    fail,
    load_routing_registry,
    load_trusted_approval,
    open_directory_nofollow,
    secure_write,
    sha256,
    strict_keys,
)
from sdb_capability_trust import load_registry_mapping as load_registry_mapping

TASK_SCHEMA = "sdb.capability.task/1"
RESULT_SCHEMA = "sdb.capability.result/1"
APPROVAL_SCHEMA = "sdb.capability.execution-approvals/1"
EVIDENCE_SCHEMA = "sdb.capability.evidence/1"
HERMES_EXECUTABLE = Path("/home/anashadi/.local/bin/hermes")
HERMES_SHA256 = "ce029ccc2679fb234364effdc67971c01ea4b8920866793282b53b61c9a57e2f"
# The pinned launcher is a 2-line sh stub; the real entrypoint it execs is pinned too (H-1).
HERMES_INNER_EXECUTABLE = Path("/home/anashadi/.hermes/hermes-agent/.hermes/bin/hermes")
HERMES_INNER_SHA256 = "08bf3a4bade11a1af7d8a7ce2056aaad81d479343c039ac6ab545732c523a5c2"
HERMES_RUNTIME_DIRS = (
    Path("/home/anashadi/.hermes/hermes-agent"),
    Path("/home/anashadi/.hermes/tools"),
)
SANDBOX_SYSTEM_DIRS = ("/usr", "/bin", "/sbin", "/lib", "/lib32", "/lib64", "/libx32")
SANDBOX_ETC_ENTRIES = (
    "alternatives", "ca-certificates", "ca-certificates.conf", "group", "host.conf", "hosts",
    "ld.so.cache", "ld.so.conf", "ld.so.conf.d", "localtime", "nsswitch.conf", "os-release",
    "passwd", "ssl",
)
RUNTIME_SECRET_FILES = (".env", ".envrc")
MAX_PROMPT_BYTES = 48 * 1024  # below the 64 KiB pipe buffer: stdin write never blocks
BWRAP_EXECUTABLE = Path("/usr/bin/bwrap")
HERMES_PROFILE_ROOT = Path("/home/anashadi/.hermes/profiles")
MAX_OUTPUT_BYTES = 1024 * 1024
MAX_EXCERPT_BYTES = 2048
DEFAULT_TIMEOUT_SECONDS = 300.0
ALLOWED_EXECUTOR_VERDICTS = frozenset({"PASS_VERIFIED_SUBSCOPE", "BLOCKED", "FAIL"})
PUBLIC_VERDICTS = frozenset(
    {"PASS_VERIFIED_SUBSCOPE", "INTEGRATION_TESTED_NONPRODUCTION", "BLOCKED", "FAIL"}
)


@dataclass(frozen=True)
class ControlledHermesAdapter:
    """Pinned production executor with a programmatic test-only substitution seam."""

    _executable: Path
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    max_output_bytes: int = MAX_OUTPUT_BYTES
    _test_only: bool = field(default=False, repr=False)

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        raise TypeError("use ControlledHermesAdapter.production() or .for_test()")

    @classmethod
    def production(cls) -> "ControlledHermesAdapter":
        instance = object.__new__(cls)
        object.__setattr__(instance, "_executable", HERMES_EXECUTABLE)
        object.__setattr__(instance, "timeout_seconds", DEFAULT_TIMEOUT_SECONDS)
        object.__setattr__(instance, "max_output_bytes", MAX_OUTPUT_BYTES)
        object.__setattr__(instance, "_test_only", False)
        return instance

    @classmethod
    def for_test(
        cls,
        executable: Path,
        *,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        max_output_bytes: int = MAX_OUTPUT_BYTES,
    ) -> "ControlledHermesAdapter":
        instance = object.__new__(cls)
        object.__setattr__(instance, "_executable", Path(executable))
        object.__setattr__(instance, "timeout_seconds", float(timeout_seconds))
        object.__setattr__(instance, "max_output_bytes", int(max_output_bytes))
        object.__setattr__(instance, "_test_only", True)
        return instance


@dataclass(frozen=True)
class ExecutionResult:
    task: TaskPack
    approval: ApprovalRecord
    status: str
    failure_code: str | None
    exit_code: int
    verified_result: bool
    result_schema: str | None
    argv: tuple[str, ...]
    sandbox_argv: tuple[str, ...]
    stdout_sha256: str
    stderr_sha256: str
    stdout_excerpt: str
    stderr_excerpt: str
    output_bytes: int
    started_at: str
    finished_at: str
    revision_binding_before: RevisionBinding
    revision_binding_after: RevisionBinding


def _verify_bwrap() -> None:
    try:
        info = BWRAP_EXECUTABLE.lstat()
    except OSError as exc:
        raise fail("sandbox_untrusted", str(exc)) from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise fail("sandbox_untrusted", "bwrap must be a regular non-symlink")
    if info.st_uid != 0 or stat.S_IMODE(info.st_mode) != 0o755:
        raise fail("sandbox_untrusted", "bwrap must be root-owned mode 0755")


def _verify_executor(path: Path, *, production: bool, expected_sha256: str = HERMES_SHA256) -> int:
    try:
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
            raise fail("executor_untrusted", f"{path} must be a regular non-symlink")
        if info.st_mode & 0o022:
            raise fail("executor_untrusted", f"{path} is group/world mutable")
        if production and (info.st_uid != 1000 or stat.S_IMODE(info.st_mode) != 0o755):
            raise fail("executor_untrusted", "Hermes owner/mode differs from pinned expectation")
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        opened = os.fstat(fd)
        if (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino):
            os.close(fd)
            raise fail("executor_untrusted", "executor changed while opening")
        digest = hashlib.sha256()
        while chunk := os.read(fd, 1024 * 1024):
            digest.update(chunk)
        after = os.fstat(fd)
        if (
            (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
            != (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns)
        ):
            os.close(fd)
            raise fail("executor_untrusted", "executor changed while hashing")
        if production and digest.hexdigest() != expected_sha256:
            os.close(fd)
            raise fail("executor_untrusted", "Hermes digest differs from pinned digest")
        os.lseek(fd, 0, os.SEEK_SET)
        return fd
    except OSError as exc:
        raise fail("executor_untrusted", f"{path}: {exc}") from exc


def _sandbox_base(*, production: bool, profile_dir: Path) -> list[str]:
    """Allowlist root: start from an empty tmpfs and mount only what the child needs.

    No `/run`, `/var/run`, `/home`, `/root`, other profiles or `~/.ssh`: host unix sockets
    (docker, dbus, systemd-user) and credentials are simply not present in the mount namespace.
    """
    argv = [
        str(BWRAP_EXECUTABLE), "--unshare-all", "--share-net", "--die-with-parent", "--new-session",
    ]
    for name in SANDBOX_SYSTEM_DIRS:
        host = Path(name)
        if host.is_symlink():
            argv += ["--symlink", os.readlink(host), name]
        elif host.is_dir():
            argv += ["--ro-bind", name, name]
    for name in SANDBOX_ETC_ENTRIES:
        host = Path("/etc") / name
        if host.exists():
            argv += ["--ro-bind", str(host), str(host)]
    resolv = Path("/etc/resolv.conf")
    if resolv.exists():
        argv += ["--ro-bind", str(resolv.resolve(strict=True)), str(resolv)]
    argv += ["--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp"]
    if production:
        for runtime in HERMES_RUNTIME_DIRS:
            if runtime.is_dir():
                argv += ["--ro-bind", str(runtime), str(runtime)]
                for secret_name in RUNTIME_SECRET_FILES:  # shadow credential files with /dev/null
                    if (runtime / secret_name).is_file():
                        argv += ["--ro-bind", "/dev/null", str(runtime / secret_name)]
    home = Path.home() if not production else Path(HERMES_PROFILE_ROOT).parents[1]
    argv += [
        "--clearenv", "--setenv", "HOME", str(home),
        "--setenv", "PATH", "/usr/bin:/bin", "--setenv", "LANG", "C.UTF-8",
        "--setenv", "LC_ALL", "C.UTF-8",
        "--overlay-src", str(profile_dir), "--tmp-overlay", str(profile_dir),
    ]
    return argv


def _profile(registry: RoutingRegistry, task: TaskPack) -> str:
    route = registry.validate_task(task)
    expected = "cc-builder" if task.lane == "backend" else "cc-frontend"
    if route.profile != expected:
        raise fail("profile_invalid", f"{task.lane} must use {expected}")
    return expected


def _open_roots(repo: Path, approval: ApprovalRecord) -> list[tuple[str, int]]:
    roots: list[tuple[str, int]] = []
    try:
        for relative in approval.allowed_write_roots:
            roots.append((relative, open_directory_nofollow(repo, relative)))
        return roots
    except Exception:
        for _, fd in roots:
            os.close(fd)
        raise


def _timestamp() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _excerpt(data: bytes) -> str:
    """Never persist raw executor output: denylist redaction cannot be made complete.

    Only the length and digest are retained; the digest fields carry the evidence.
    """
    return f"[WITHHELD bytes={len(data)} sha256={sha256(data)}]"


def _kill_group(process: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def _run_streaming(
    command: Sequence[str], prompt: bytes, *, pass_fds: Sequence[int],
    timeout_seconds: float, max_output_bytes: int,
) -> tuple[int, bytes, bytes, str | None]:
    if len(prompt) > MAX_PROMPT_BYTES:
        raise fail("prompt_too_large", f"{len(prompt)} > {MAX_PROMPT_BYTES} bytes")
    process = subprocess.Popen(
        list(command), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"},
        pass_fds=tuple(pass_fds), start_new_session=True,
    )
    assert process.stdin is not None and process.stdout is not None and process.stderr is not None
    try:
        process.stdin.write(prompt)
        process.stdin.close()
    except BrokenPipeError:
        pass
    for stream in (process.stdout, process.stderr):
        os.set_blocking(stream.fileno(), False)
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ, "stdout")
    selector.register(process.stderr, selectors.EVENT_READ, "stderr")
    output = {"stdout": bytearray(), "stderr": bytearray()}
    total = 0
    failure: str | None = None
    deadline = time.monotonic() + timeout_seconds
    while selector.get_map():
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            failure = "execution_timeout"
            _kill_group(process)
            break
        for key, _ in selector.select(min(remaining, 0.05)):
            try:
                chunk = os.read(key.fd, 65536)
            except BlockingIOError:
                continue
            if not chunk:
                selector.unregister(key.fileobj)
                continue
            room = max_output_bytes - total
            if room:
                kept = chunk[:room]
                output[key.data].extend(kept)
                total += len(kept)
            if len(chunk) > room:
                failure = "execution_output_limit"
                _kill_group(process)
                break
        if failure:
            break
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        _kill_group(process)
        process.wait(timeout=2)
    return process.returncode, bytes(output["stdout"]), bytes(output["stderr"]), failure


def _validate_result(stdout: bytes, task: TaskPack, challenge: str) -> tuple[bool, str | None, str | None]:
    try:
        def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
            value: dict[str, Any] = {}
            for key, item in pairs:
                if key in value:
                    raise ValueError(f"duplicate result key: {key}")
                value[key] = item
            return value

        raw = json.loads(stdout.decode("utf-8"), object_pairs_hook=reject_duplicates)
        if not isinstance(raw, Mapping):
            raise ValueError("result must be an object")
        strict_keys(raw, {"schema", "capability_id", "verdict", "challenge_response"}, "result")
        if raw.get("schema") != RESULT_SCHEMA or raw.get("capability_id") != task.capability_id:
            raise ValueError("schema or capability mismatch")
        verdict = raw.get("verdict")
        if verdict not in ALLOWED_EXECUTOR_VERDICTS:
            raise ValueError("verdict not allowlisted")
        response = raw.get("challenge_response")
        if not isinstance(response, str) or not re.fullmatch(r"[0-9a-f]{64}", response):
            raise ValueError("challenge response must be lowercase sha256")
        expected = sha256(f"{challenge}/{task.capability_id}/{task.digest()}".encode())
        if not secrets.compare_digest(response, expected):
            raise ValueError("challenge mismatch")
        return True, str(verdict), RESULT_SCHEMA
    except (UnicodeDecodeError, json.JSONDecodeError, RoutingError, TypeError, ValueError):
        return False, None, None


def execute(
    task: TaskPack, approval: ApprovalRecord, registry: RoutingRegistry,
    repo: Path, adapter: ControlledHermesAdapter,
) -> ExecutionResult:
    """Consume authorization, execute inside bwrap, then verify result and revision."""
    repo = repo.resolve(strict=True)
    if (approval.task_digest != task.digest() or approval.capability_id != task.capability_id
            or approval.lane != task.lane or not approval.nonproduction):
        raise fail("approval_task_mismatch", "approval no longer matches the task")
    profile = _profile(registry, task)
    _verify_bwrap()
    active_profile_dir = HERMES_PROFILE_ROOT / profile
    if not active_profile_dir.is_dir() or active_profile_dir.is_symlink():
        raise fail("profile_invalid", f"untrusted Hermes profile directory: {active_profile_dir}")
    challenge = secrets.token_hex(32)
    prompt = canonical_bytes({
        "schema": TASK_SCHEMA, "capability_id": task.capability_id, "lane": task.lane,
        "goal": task.goal, "requested_write_paths": list(task.requested_write_paths),
        "task_digest": task.digest(), "challenge_nonce": challenge,
        "required_result_schema": RESULT_SCHEMA,
        "network_policy": "Hermes LLM transport only; request no arbitrary tools",
    })
    if len(prompt) > MAX_PROMPT_BYTES:
        raise fail("prompt_too_large", f"{len(prompt)} > {MAX_PROMPT_BYTES} bytes")
    hermes_args = (
        "-p", profile, "chat", "--query-file", "-", "--oneshot", "--quiet",
        "--format", "text", "--source", "tool", "--run-budget", "30",
    )
    with ExitStack() as stack:
        executor_fd = _verify_executor(adapter._executable, production=not adapter._test_only)
        stack.callback(os.close, executor_fd)
        if not adapter._test_only:
            inner_fd = _verify_executor(
                HERMES_INNER_EXECUTABLE, production=True, expected_sha256=HERMES_INNER_SHA256,
            )
            os.close(inner_fd)
        repo_fd = open_directory_nofollow(repo)
        stack.callback(os.close, repo_fd)
        roots = _open_roots(repo, approval)
        for _, fd in roots:
            stack.callback(os.close, fd)
        sandbox = _sandbox_base(production=not adapter._test_only, profile_dir=active_profile_dir)
        sandbox += [
            "--ro-bind-fd", str(repo_fd), str(repo),
            "--tmpfs", str(repo / ".git"), "--remount-ro", str(repo / ".git"),
        ]
        for relative, fd in roots:
            sandbox += ["--bind-fd", str(fd), str(repo / relative)]
        sandbox += [
            "--chdir", str(repo), "--", f"/proc/self/fd/{executor_fd}", *hermes_args,
        ]
        # Validation is complete: only now burn the single-use approval (L-1).
        consume_approval(approval, repo / ".git" / "sdb-capability-approval-replay")
        before = capture_revision_binding(repo)
        started = _timestamp()
        exit_code, stdout, stderr, process_failure = _run_streaming(
            sandbox, prompt, pass_fds=[repo_fd, executor_fd, *(fd for _, fd in roots)],
            timeout_seconds=adapter.timeout_seconds, max_output_bytes=adapter.max_output_bytes,
        )
    finished = _timestamp()
    after = capture_revision_binding(repo)
    verified, executor_verdict, result_schema = _validate_result(stdout, task, challenge)
    failure_code = process_failure
    if failure_code is None and exit_code != 0:
        failure_code = "execution_nonzero"
    if failure_code is None and not verified:
        failure_code = "result_contract_invalid"
    if failure_code is None and before.canonical() != after.canonical():
        failure_code = "revision_binding_changed"
    status = "FAIL" if failure_code else (executor_verdict or "FAIL")
    if status not in PUBLIC_VERDICTS:
        status, failure_code = "FAIL", failure_code or "result_contract_invalid"
    return ExecutionResult(
        task, approval, status, failure_code, exit_code, verified and failure_code is None,
        result_schema, hermes_args, tuple(sandbox), sha256(stdout), sha256(stderr),
        _excerpt(stdout), _excerpt(stderr), len(stdout) + len(stderr), started, finished, before, after,
    )


def _evidence_exit_code(code: int) -> int:
    """Map a Popen return code (negative = killed by signal) into 0..255 without hiding failure."""
    return min(255, 128 - code) if code < 0 else min(255, code)


def _json_bytes(value: Mapping[str, Any]) -> bytes:
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, indent=2) + "\n").encode()


def _artifact_payload(result: ExecutionResult) -> dict[str, Any]:
    return {
        "schema": "sdb.capability.invocation/1", "capability_id": result.task.capability_id,
        "task_digest": result.task.digest(), "approval_ref": result.approval.approval_ref,
        "status": result.status, "failure_code": result.failure_code, "exit_code": result.exit_code,
        "verified_result": result.verified_result, "result_schema": result.result_schema,
        "stdout_sha256": result.stdout_sha256, "stderr_sha256": result.stderr_sha256,
        "stdout_excerpt": result.stdout_excerpt, "stderr_excerpt": result.stderr_excerpt,
        "output_bytes": result.output_bytes, "started_at": result.started_at,
        "finished_at": result.finished_at,
        "revision_before": result.revision_binding_before.canonical(),
        "revision_after": result.revision_binding_after.canonical(),
    }


def write_invocation_artifact(result: ExecutionResult, repo: Path) -> tuple[str, str]:
    stamp = result.started_at.replace(":", "").replace("-", "")
    relative = f"runs/capability/{stamp}-{result.task.capability_id}-{secrets.token_hex(6)}.invocation.json"
    data = _json_bytes(_artifact_payload(result))
    secure_write(repo, relative, data)
    return relative, sha256(data)


def _write_evidence(
    result: ExecutionResult, repo: Path, *, positive_only: bool,
) -> dict[str, Any]:
    positive = result.verified_result and result.status == "PASS_VERIFIED_SUBSCOPE"
    if positive_only and not positive:
        raise fail("evidence_result_unverified", "positive evidence requires independently verified PASS")
    artifact_path, artifact_digest = write_invocation_artifact(result, repo)
    evidence_verdict = "INTEGRATION_TESTED_NONPRODUCTION" if positive else (
        "BLOCKED" if result.status == "BLOCKED" else "FAIL"
    )
    payload = {
        "schema": EVIDENCE_SCHEMA,
        "capability_id": result.task.capability_id,
        "revision": result.revision_binding_before.head,
        "test_command": "C1 controlled Hermes nonproduction challenge",
        "exit_code": _evidence_exit_code(result.exit_code),
        "test_results": {
            "passed": 1 if positive else 0,
            "failed": 0 if positive else 1,
            "skipped": 0,
            "errors": 0,
            "total": 1,
        },
        "artifact_refs": [{"path": artifact_path, "sha256": artifact_digest}],
        "evidence_level": "AGENT_REPORTED",
        "verification_timestamp": result.finished_at,
        "review_status": "NOT_REVIEWED",
        "release_authorization": "NOT_AUTHORIZED",
    }
    payload["integrity"] = sha256(canonical_bytes(payload))
    try:
        sdb_capability_evidence.validate_payload(
            payload,
            repo=repo,
            head=result.revision_binding_before.head,
            now=dt.datetime.now(dt.timezone.utc),
        )
    except sdb_capability_evidence.EvidenceError as exc:
        raise fail("evidence_validation_failed", str(exc)) from exc
    stamp = result.finished_at.replace(":", "").replace("-", "")
    relative = f"runs/capability/{stamp}-{result.task.capability_id}-{secrets.token_hex(6)}.evidence.json"
    data = _json_bytes(payload)
    secure_write(repo, relative, data)
    return {
        "execution_status": "PASS" if positive else "FAIL",
        "acceptance_status": "INFORMATIONAL_ONLY",
        "router_verdict": evidence_verdict,
        "evidence_path": str(repo / relative),
        "evidence_sha256": sha256(data),
    }


def record_execution_evidence(result: ExecutionResult, repo: Path) -> dict[str, Any]:
    return _write_evidence(result, repo, positive_only=True)


def finish_public_execution(result: ExecutionResult, repo: Path) -> dict[str, Any]:
    evidence = _write_evidence(result, repo, positive_only=False)
    return {
        "schema": "sdb.capability.router-output/1",
        "capability_id": result.task.capability_id,
        "verdict": evidence["router_verdict"],
        "evidence": evidence,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", required=True, type=Path)
    parser.add_argument("--approval-ref", required=True)
    return parser


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise fail("task_load_failed", str(exc)) from exc


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        repo = Path(sdb_common.REPO_ROOT).resolve(strict=True)
        task = TaskPack.from_mapping(_load_json(args.task))
        registry = load_routing_registry(repo)
        approval = load_trusted_approval(repo, args.approval_ref, task)
        result = execute(task, approval, registry, repo, ControlledHermesAdapter.production())
        output = finish_public_execution(result, repo)
        print(json.dumps(output, indent=2))
        return 0 if output["verdict"] == "INTEGRATION_TESTED_NONPRODUCTION" else 1
    except (RoutingError, OSError) as exc:
        print(f"capability router refused execution: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
