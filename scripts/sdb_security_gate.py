#!/usr/bin/env python3
"""BE-SP-10: gate Gitleaks fail-closed dengan evidence BE-SP-12."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

import sdb_capability_evidence as evidence
import tomllib

SCHEMA = "sdb.security-gate/1"
CAPABILITY_ID = "BE-SP-10"
MAX_REPORT_BYTES = 8 * 1024 * 1024
MAX_FINDINGS = 10_000
_RULE_ID = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


def _error_result(capability_id: str, scope: str, revision: str, code: str, message: str) -> dict:
    return {
        "schema": SCHEMA,
        "capability_id": capability_id,
        "scope": scope,
        "source_revision": revision,
        "status": "ERROR",
        "execution": {
            "status": "ERROR",
            "scanner_exit_code": None,
            "errors": [{"code": code, "message": message}],
        },
        "findings": [],
    }


def _with_evidence(
    result: dict,
    *,
    repo: Path,
    registry: dict[str, dict],
    command: str,
    exit_code: int,
    passed: int,
    failed: int,
    errors: int,
    head: str,
) -> dict:
    result["execution"]["command"] = command
    payload = {
        "schema": evidence.SCHEMA,
        "capability_id": result["capability_id"],
        "revision": result["source_revision"],
        "test_command": command,
        "exit_code": exit_code,
        "test_results": {
            "passed": passed,
            "failed": failed,
            "skipped": 0,
            "errors": errors,
            "total": passed + failed + errors,
        },
        "artifact_refs": [],
        "evidence_level": evidence.LEVEL_AGENT,
        "verification_timestamp": evidence.utc_now_iso(),
        "review_status": evidence.REVIEW_NONE,
        "release_authorization": evidence.RELEASE_NOT_AUTHORIZED,
    }
    try:
        result["capability_evidence"] = evidence.validate_payload(
            payload,
            repo=repo,
            head=head,
            now=dt.datetime.now(dt.timezone.utc),
            registry=registry,
        )
    except evidence.EvidenceError as exc:
        return _error_result(
            result["capability_id"],
            result["scope"],
            result["source_revision"],
            "evidence_rejected",
            f"BE-SP-12 menolak evidence: {exc.code}",
        )
    return result


def _resolve_scanner(raw: str) -> str | None:
    """Kanonikalisasi scanner ke path absolut regular+executable.

    `shutil.which` dapat mengembalikan path relatif terhadap CWD, sedangkan scan
    berjalan dengan `cwd=repo`; karena itu path di-resolve sekali, di sini, dan
    semua langkah berikutnya memakai path absolut hasil resolve.
    """
    if os.sep in raw or (os.altsep and os.altsep in raw):
        candidate = Path(raw)
    else:
        found = shutil.which(raw)
        if not found:
            return None
        candidate = Path(found)
    try:
        resolved = candidate.resolve(strict=True)
        info = resolved.stat()
    except OSError:
        return None
    if not stat.S_ISREG(info.st_mode) or not os.access(resolved, os.X_OK):
        return None
    return str(resolved)


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_bounded(path: Path, limit: int) -> bytes:
    """Baca berkas regular lewat satu FD: ukuran dari fstat, isi dari objek yang sama."""
    handle = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        info = os.fstat(handle)
        if not stat.S_ISREG(info.st_mode):
            raise OSError("bukan berkas regular")
        if info.st_size > limit:
            raise OSError("berkas melebihi batas")
        chunks: list[bytes] = []
        remaining = limit + 1
        while remaining > 0:
            chunk = os.read(handle, min(1024 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b"".join(chunks)
    finally:
        os.close(handle)
    if len(data) > limit:
        raise OSError("berkas tumbuh melewati batas")
    return data


def _git_blob(repo: Path, revision: str, relative: str) -> bytes:
    """Ambil isi blob pada revision yang diverifikasi, bukan dari working tree."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), "show", f"{revision}:{relative}"],
            capture_output=True, timeout=30, check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise OSError(f"blob {relative} tidak dapat dibaca") from exc
    if proc.returncode != 0:
        raise OSError(f"blob {relative} tidak tersedia pada revision")
    return proc.stdout


def _load_registry_at(repo: Path, revision: str) -> dict[str, dict]:
    """Trust root registry wajib berasal dari blob revision terikat.

    Isi blob ditulis ke direktori privat agar validasi tetap memakai
    `evidence.load_registry` yang sama (tanpa validator paralel).
    """
    raw = _git_blob(repo, revision, evidence.REGISTRY_REL.as_posix())
    with tempfile.TemporaryDirectory(prefix="sdb-be-sp10-registry-") as temp_dir:
        path = Path(temp_dir) / evidence.REGISTRY_REL
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        return evidence.load_registry(Path(temp_dir))


def _load_config(repo: Path, raw: str, revision: str) -> tuple[bytes | None, str | None]:
    """Validasi bentuk path di working tree, lalu ambil isi config dari blob revision."""
    relative = Path(raw)
    if relative.is_absolute() or ".." in relative.parts:
        return None, "config_invalid"
    current = repo
    try:
        for part in relative.parts:
            current /= part
            if current.is_symlink():
                return None, "config_symlink"
        if not current.is_file():
            return None, "config_missing"
        data = _git_blob(repo, revision, relative.as_posix())
    except OSError:
        return None, "config_missing"
    try:
        parsed = tomllib.loads(data.decode("utf-8"))
    except (UnicodeError, ValueError, tomllib.TOMLDecodeError):
        return None, "config_invalid"
    if not isinstance(parsed, dict) or not parsed:
        return None, "config_invalid"
    return data, None


def _normalize_findings(raw: object) -> list[dict]:
    if not isinstance(raw, list) or len(raw) > MAX_FINDINGS:
        raise ValueError("root output bukan list atau terlalu banyak findings")
    normalized: list[dict] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("entri finding bukan object")
        rule_id = item.get("RuleID")
        file_name = item.get("File")
        start = item.get("StartLine")
        end = item.get("EndLine")
        if not isinstance(rule_id, str) or not _RULE_ID.fullmatch(rule_id):
            raise ValueError("RuleID tidak sah")
        if (
            not isinstance(file_name, str)
            or not file_name
            or len(file_name) > 1024
            or Path(file_name).is_absolute()
            or ".." in Path(file_name).parts
            or any(ord(char) < 32 for char in file_name)
        ):
            raise ValueError("File tidak sah")
        if not isinstance(start, int) or isinstance(start, bool) or start < 1:
            raise ValueError("StartLine tidak sah")
        if not isinstance(end, int) or isinstance(end, bool) or end < start:
            raise ValueError("EndLine tidak sah")
        normalized.append({
            "rule_id": rule_id,
            "file": file_name,
            "start_line": start,
            "end_line": end,
        })
    return normalized


def _run_gate(
    *,
    repo: Path,
    capability_id: str,
    scope: str,
    revision: str,
    expected_revision: str,
    scanner: str | None = None,
    timeout_seconds: float = 120.0,
    registry: dict[str, dict] | None = None,
    require_clean: bool = True,
) -> dict:
    """Jalankan gate terikat capability, scope, dan source revision."""
    repo = Path(repo).resolve()
    base_command = "gitleaks dir [approved-scope]"
    if not evidence.is_hex40(revision) or not evidence.is_hex40(expected_revision):
        return _error_result(capability_id, scope, revision, "revision_invalid",
                             "revision wajib SHA-1 penuh 40 hex")
    if revision != expected_revision:
        return _error_result(capability_id, scope, revision, "revision_mismatch",
                             "source revision tidak sama dengan HEAD yang diverifikasi")
    if registry is None:
        try:
            registry = _load_registry_at(repo, revision)
        except evidence.EvidenceError as exc:
            return _error_result(capability_id, scope, revision, exc.code, str(exc))
        except OSError as exc:
            return _error_result(capability_id, scope, revision, "registry_missing",
                                 f"registry tidak tersedia pada revision terikat: {exc}")
    try:
        entry = evidence.known_capability(capability_id, registry)
    except evidence.EvidenceError as exc:
        return _error_result(capability_id, scope, revision, exc.code, str(exc))
    policy = entry.get("security_gate")
    if capability_id != CAPABILITY_ID or not isinstance(policy, dict):
        return _error_result(capability_id, scope, revision, "capability_not_security_gate",
                             "capability bukan gate BE-SP-10 yang disetujui")
    if not isinstance(require_clean, bool):
        return _error_result(capability_id, scope, revision, "clean_policy_invalid",
                             "require_clean wajib boolean")
    if require_clean:
        try:
            clean_check = subprocess.run(
                [
                    "git", "-C", str(repo), "status", "--porcelain=v1",
                    "--untracked-files=all", "--ignore-submodules=none",
                ],
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return _error_result(capability_id, scope, revision, "clean_check_failed",
                                 "status working tree tidak dapat diverifikasi")
        if clean_check.returncode != 0:
            return _error_result(capability_id, scope, revision, "clean_check_failed",
                                 "status working tree tidak dapat diverifikasi")
        if clean_check.stdout:
            return _error_result(capability_id, scope, revision, "working_tree_dirty",
                                 "working tree berubah; source tidak identik dengan revision")
    allowed = policy.get("allowed_scopes")
    if not isinstance(allowed, list) or scope not in allowed:
        return _error_result(capability_id, scope, revision, "scope_not_approved",
                             "scope tidak tercantum di registry capability")
    try:
        scope_path = (repo / scope).resolve(strict=True)
        scope_path.relative_to(repo)
    except (OSError, ValueError):
        return _error_result(capability_id, scope, revision, "scope_invalid",
                             "scope hilang atau keluar dari repository")
    if not scope_path.is_dir():
        return _error_result(capability_id, scope, revision, "scope_invalid",
                             "scope gate wajib direktori")

    config_raw = policy.get("config")
    if not isinstance(config_raw, str) or not config_raw:
        return _error_result(capability_id, scope, revision, "config_invalid",
                             "path config tidak sah di registry")
    config_bytes, config_error = _load_config(repo, config_raw, revision)
    if config_error or config_bytes is None:
        return _with_evidence(
            _error_result(capability_id, scope, revision, config_error or "config_invalid",
                          "config scanner ditolak"),
            repo=repo, registry=registry, command=base_command, exit_code=2,
            passed=0, failed=0, errors=1, head=expected_revision,
        )

    scanner_name = scanner if scanner is not None else policy.get("scanner")
    if not isinstance(scanner_name, str) or not scanner_name:
        resolved = None
    else:
        resolved = _resolve_scanner(scanner_name)
    if resolved is None:
        return _with_evidence(
            _error_result(capability_id, scope, revision, "scanner_missing", "scanner mandatory tidak tersedia"),
            repo=repo, registry=registry, command=base_command, exit_code=2,
            passed=0, failed=0, errors=1, head=expected_revision,
        )
    try:
        scanner_digest = _sha256_file(Path(resolved))
    except OSError:
        scanner_digest = None
    scanner_version: str | None = None
    if not isinstance(timeout_seconds, (int, float)) or isinstance(timeout_seconds, bool) or timeout_seconds <= 0:
        return _error_result(capability_id, scope, revision, "timeout_invalid", "timeout wajib positif")

    config_digest = _sha256_bytes(config_bytes)
    with tempfile.TemporaryDirectory(prefix="sdb-be-sp10-") as temp_dir:
        private_dir = Path(temp_dir)
        report_path = private_dir / "gitleaks.json"
        scanner_copy = private_dir / "scanner"
        config_copy = private_dir / "gitleaks.toml"
        try:
            shutil.copy2(resolved, scanner_copy)
            config_copy.write_bytes(config_bytes)
            scanner_copy.chmod(0o500)
            config_copy.chmod(0o400)
            if _sha256_file(scanner_copy) != scanner_digest or _sha256_file(config_copy) != config_digest:
                raise OSError("snapshot provenance mismatch")
        except OSError:
            return _with_evidence(
                _error_result(
                    capability_id,
                    scope,
                    revision,
                    "scanner_snapshot_failed",
                    "scanner/config tidak dapat diikat ke salinan privat",
                ),
                repo=repo, registry=registry, command=base_command, exit_code=2,
                passed=0, failed=0, errors=1, head=expected_revision,
            )
        if scanner is None:
            expected_digest = policy.get("scanner_sha256")
            expected_version = policy.get("scanner_version")
            if (
                not isinstance(expected_digest, str)
                or not re.fullmatch(r"[0-9a-f]{64}", expected_digest)
                or scanner_digest != expected_digest
                or not isinstance(expected_version, str)
                or not expected_version
            ):
                return _error_result(capability_id, scope, revision, "scanner_provenance_invalid",
                                     "digest/version scanner tidak cocok registry")
            try:
                version_check = subprocess.run(
                    [str(scanner_copy), "version"],
                    capture_output=True, text=True, timeout=10, check=False,
                )
            except (OSError, subprocess.SubprocessError):
                version_check = None
            if version_check is None or version_check.returncode != 0:
                return _error_result(capability_id, scope, revision, "scanner_provenance_invalid",
                                     "versi scanner tidak dapat diverifikasi")
            scanner_version = version_check.stdout.strip()
            if scanner_version != expected_version:
                return _error_result(capability_id, scope, revision, "scanner_provenance_invalid",
                                     "versi scanner tidak cocok registry")
        command = [
            str(scanner_copy),
            "git",
            "--log-opts", revision,
            "--config", str(config_copy),
            "--report-format", "json",
            "--report-path", str(report_path),
            "--exit-code", "1",
            "--redact=100",
            "--no-banner",
            str(repo),
        ]
        command_text = shlex.join([
            Path(resolved).name,
            "git",
            "--log-opts", revision,
            "--config", config_raw,
            "--report-format", "json",
            "--report-path", "[ephemeral-report]",
            "--exit-code", "1",
            "--redact=100",
            "--no-banner",
            "[repository]",
        ])
        try:
            proc = subprocess.run(
                command,
                cwd=repo,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return _with_evidence(
                _error_result(capability_id, scope, revision, "scanner_timeout", "scanner melewati timeout"),
                repo=repo, registry=registry, command=command_text, exit_code=2,
                passed=0, failed=0, errors=1, head=expected_revision,
            )
        except OSError:
            return _with_evidence(
                _error_result(capability_id, scope, revision, "scanner_failed", "scanner gagal dijalankan"),
                repo=repo, registry=registry, command=command_text, exit_code=2,
                passed=0, failed=0, errors=1, head=expected_revision,
            )
        if proc.returncode not in (0, 1):
            return _with_evidence(
                _error_result(capability_id, scope, revision, "scanner_failed",
                              f"scanner exit {proc.returncode}; output sengaja tidak diekspos"),
                repo=repo, registry=registry, command=command_text,
                exit_code=min(max(proc.returncode, 2), 255), passed=0, failed=0, errors=1,
                head=expected_revision,
            )
        if not report_path.is_file():
            return _with_evidence(
                _error_result(capability_id, scope, revision, "scanner_result_missing", "report scanner tidak dibuat"),
                repo=repo, registry=registry, command=command_text, exit_code=2,
                passed=0, failed=0, errors=1, head=expected_revision,
            )
        try:
            findings = _normalize_findings(json.loads(_read_bounded(report_path, MAX_REPORT_BYTES).decode("utf-8")))
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
            return _with_evidence(
                _error_result(capability_id, scope, revision, "scanner_output_invalid", "report scanner malformed"),
                repo=repo, registry=registry, command=command_text, exit_code=2,
                passed=0, failed=0, errors=1, head=expected_revision,
            )

    if require_clean:
        try:
            post_head = evidence.resolve_head(repo)
            post_status = subprocess.run(
                [
                    "git", "-C", str(repo), "status", "--porcelain=v1",
                    "--untracked-files=all", "--ignore-submodules=none",
                ],
                capture_output=True, text=True, timeout=20, check=False,
            )
        except (OSError, subprocess.SubprocessError, evidence.EvidenceError):
            post_head = ""
            post_status = None
        if (
            post_head != expected_revision
            or post_status is None
            or post_status.returncode != 0
            or bool(post_status.stdout)
        ):
            return _error_result(capability_id, scope, revision, "source_changed_during_scan",
                                 "HEAD/working tree berubah selama scan; evidence tidak diterbitkan")
    if (proc.returncode == 0 and findings) or (proc.returncode == 1 and not findings):
        return _with_evidence(
            _error_result(capability_id, scope, revision, "scanner_result_inconsistent",
                          "exit scanner tidak konsisten dengan findings"),
            repo=repo, registry=registry, command=command_text, exit_code=2,
            passed=0, failed=0, errors=1, head=expected_revision,
        )
    result = {
        "schema": SCHEMA,
        "capability_id": capability_id,
        "scope": scope,
        "source_revision": revision,
        "status": "FAIL" if findings else "PASS",
        "execution": {
            "status": "SUCCESS",
            "scanner": Path(resolved).name,
            "scanner_version": scanner_version,
            "scanner_sha256": scanner_digest,
            "config_sha256": config_digest,
            "scanner_exit_code": proc.returncode,
            "errors": [],
        },
        "findings": findings,
    }
    return _with_evidence(
        result,
        repo=repo,
        registry=registry,
        command=command_text,
        exit_code=proc.returncode,
        passed=0 if findings else 1,
        failed=1 if findings else 0,
        errors=0,
        head=expected_revision,
    )


def run_gate(
    *,
    repo: Path,
    capability_id: str,
    scope: str,
    revision: str,
    timeout_seconds: float = 120.0,
) -> dict:
    """Jalankan BE-SP-10 dengan trust root hanya dari blob revision terikat."""
    repo = Path(repo).resolve()
    try:
        head = evidence.resolve_head(repo)
    except evidence.EvidenceError as exc:
        return _error_result(capability_id, scope, revision, exc.code, str(exc))
    return _run_gate(
        repo=repo,
        capability_id=capability_id,
        scope=scope,
        revision=revision,
        expected_revision=head,
        timeout_seconds=timeout_seconds,
        require_clean=True,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capability", required=True)
    parser.add_argument("--scope", default=".")
    parser.add_argument("--revision", required=True)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--timeout", type=float, default=120.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    result = run_gate(
        repo=args.repo,
        capability_id=args.capability,
        scope=args.scope,
        revision=args.revision,
        timeout_seconds=args.timeout,
    )
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "PASS" else (1 if result["status"] == "FAIL" else 2)


if __name__ == "__main__":
    sys.exit(main())
