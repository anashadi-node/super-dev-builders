#!/usr/bin/env python3
"""Laporkan hitungan JUnit dari artefak yang sudah ada; tidak menjalankan tes."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import xml.etree.ElementTree as ET
import xml.parsers.expat
from pathlib import Path

_SHA1 = re.compile(r"^[0-9a-f]{40}$")
MAX_XML_BYTES = 16 * 1024 * 1024


class ReportError(ValueError):
    """Input laporan tidak dapat dipercaya."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _required_text(value: object, field: str, *, maximum: int = 512) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ReportError(f"{field}_invalid", f"{field} wajib teks 1..{maximum} karakter")
    if any(char in value for char in ("\x00", "\n", "\r")):
        raise ReportError(f"{field}_invalid", f"{field} tidak boleh multi-baris/NUL")
    return value


def _local_name(element: ET.Element) -> str:
    return element.tag.rsplit("}", 1)[-1]


def _summary_tests(root: ET.Element) -> tuple[int | None, str | None]:
    """Atribut ringkasan non-otoritatif: rusak → None + penanda, bukan kegagalan laporan."""
    raw = root.attrib.get("tests")
    if raw is None:
        suites = [element for element in root.iter() if _local_name(element) == "testsuite"]
        if len(suites) == 1:
            raw = suites[0].attrib.get("tests")
    if raw is None:
        return None, None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None, "xml_summary_invalid"
    if value < 0:
        return None, "xml_summary_negative"
    return value, None


def _read_artifact(path: Path, limit: int) -> tuple[bytes, float]:
    """Baca artefak sekali lewat satu FD.

    Ukuran, isi, dan mtime diambil dari objek berkas yang sama sehingga hash,
    parse, dan umur laporan tidak dapat merujuk ke dua objek berbeda (TOCTOU).
    """
    try:
        handle = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError as exc:
        raise ReportError("xml_missing", f"JUnit tidak dapat dibaca: {exc}") from exc
    try:
        info = os.fstat(handle)
        if not stat.S_ISREG(info.st_mode):
            raise ReportError("xml_missing", "JUnit bukan berkas biasa")
        if info.st_size == 0:
            raise ReportError("xml_empty", "JUnit kosong")
        if info.st_size > limit:
            raise ReportError("xml_too_large", f"JUnit melebihi {limit} byte")
        chunks: list[bytes] = []
        remaining = limit + 1
        while remaining > 0:
            chunk = os.read(handle, min(1024 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        modified_at = info.st_mtime
    except OSError as exc:
        raise ReportError("xml_unreadable", f"JUnit tidak dapat dibaca: {exc}") from exc
    finally:
        os.close(handle)
    if not raw:
        raise ReportError("xml_empty", "JUnit kosong")
    if len(raw) > limit:
        raise ReportError("xml_too_large", f"JUnit melebihi {limit} byte")
    return raw, modified_at


def _assert_no_doctype(raw: bytes) -> None:
    """Tolak DTD/entity apa pun, termasuk dokumen UTF-16 yang lolos scan byte ASCII."""
    class _Rejected(Exception):
        pass

    def reject(*_args: object, **_kwargs: object) -> None:
        raise _Rejected

    def reject_external(*_args: object, **_kwargs: object) -> int:
        raise _Rejected

    parser = xml.parsers.expat.ParserCreate()
    parser.StartDoctypeDeclHandler = reject
    parser.EntityDeclHandler = reject
    parser.ExternalEntityRefHandler = reject_external
    try:
        parser.Parse(raw, True)
    except _Rejected:
        raise ReportError("xml_unsafe", "DTD/entity pada JUnit ditolak") from None
    except xml.parsers.expat.ExpatError:
        # ET.fromstring di bawah memberi kode xml_malformed yang kanonik.
        return


def _assert_plain_xml(root: ET.Element) -> None:
    """Namespace dibuang ET oleh _local_name, jadi tolak elemen bertnamespace sebelum dihitung."""
    if any(isinstance(node.tag, str) and "}" in node.tag for node in root.iter()):
        raise ReportError("xml_namespace_invalid", "elemen JUnit bertnamespace ditolak")


def _parse_xml(path: Path) -> tuple[ET.Element, bytes, float]:
    raw, modified_at = _read_artifact(path, MAX_XML_BYTES)
    upper = raw.upper()
    if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
        raise ReportError("xml_unsafe", "DTD/entity pada JUnit ditolak")
    _assert_no_doctype(raw)
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise ReportError("xml_malformed", f"JUnit malformed: {exc}") from exc
    _assert_plain_xml(root)
    return root, raw, modified_at


def build_report(
    path: Path,
    *,
    command: str,
    exit_code: int,
    run_id: str,
    revision: str,
    expected_revision: str,
    max_age_seconds: int,
    now: dt.datetime | None = None,
) -> dict:
    """Bangun laporan terikat run/revisi dari satu artefak JUnit."""
    path = Path(path)
    command = _required_text(command, "command")
    run_id = _required_text(run_id, "run_id", maximum=128)
    if isinstance(exit_code, bool) or not isinstance(exit_code, int) or not 0 <= exit_code <= 255:
        raise ReportError("exit_code_invalid", "exit_code wajib integer 0..255")
    if not isinstance(revision, str) or not _SHA1.fullmatch(revision):
        raise ReportError("revision_invalid", "revision wajib SHA-1 penuh 40 hex")
    if not isinstance(expected_revision, str) or not _SHA1.fullmatch(expected_revision):
        raise ReportError("expected_revision_invalid", "expected_revision wajib SHA-1 penuh 40 hex")
    if revision != expected_revision:
        raise ReportError("revision_mismatch", "revision laporan tidak sama dengan revision yang diverifikasi")
    if isinstance(max_age_seconds, bool) or not isinstance(max_age_seconds, int) or max_age_seconds <= 0:
        raise ReportError("max_age_invalid", "max_age_seconds wajib integer positif")

    root, raw, modified_at = _parse_xml(path)
    root_name = _local_name(root)
    if root_name not in {"testsuite", "testsuites"}:
        raise ReportError("xml_not_junit", "root JUnit wajib testsuite atau testsuites")
    suites = [element for element in root.iter() if _local_name(element) == "testsuite"]
    if not suites:
        raise ReportError("xml_structure_invalid", "JUnit wajib memuat elemen testsuite")
    current = now or dt.datetime.now(dt.timezone.utc)
    if current.tzinfo is None:
        raise ReportError("now_invalid", "now wajib timezone-aware")
    modified = dt.datetime.fromtimestamp(modified_at, tz=dt.timezone.utc)
    age = (current.astimezone(dt.timezone.utc) - modified).total_seconds()
    if age < -5:
        raise ReportError("report_from_future", "mtime JUnit berada di masa depan")
    if age > max_age_seconds:
        raise ReportError("report_stale", f"umur JUnit {age:.0f}s > batas {max_age_seconds}s")

    cases: list[ET.Element] = []
    for parent in root.iter():
        for child in parent:
            if _local_name(child) != "testcase":
                continue
            if _local_name(parent) != "testsuite":
                raise ReportError(
                    "xml_structure_invalid", "testcase JUnit wajib menjadi anak langsung testsuite"
                )
            cases.append(child)
    if not cases:
        raise ReportError("no_testcases", "JUnit tidak memuat elemen testcase")

    counts = {"passed": 0, "failed": 0, "errors": 0, "skipped": 0}
    outcome_keys = {"failure": "failed", "error": "errors", "skipped": "skipped"}
    for case in cases:
        children = list(case)
        outcomes = [_local_name(child) for child in children if _local_name(child) in outcome_keys]
        if len(outcomes) > 1:
            raise ReportError("testcase_outcome_invalid", "satu testcase memiliki beberapa outcome")
        for child in children:
            if _local_name(child) in outcome_keys:
                continue
            if any(_local_name(node) in outcome_keys for node in child.iter()):
                raise ReportError("testcase_outcome_invalid", "outcome JUnit bersarang ditolak")
        key = outcome_keys[outcomes[0]] if outcomes else "passed"
        counts[key] += 1
    collected = len(cases)
    executed = collected - counts["skipped"]
    summary_tests, summary_warning = _summary_tests(root)
    status = "METRICS_VALID"
    if exit_code != 0 or counts["failed"] or counts["errors"] or executed == 0:
        status = "TEST_FAILURE"

    command_sha256 = hashlib.sha256(command.encode()).hexdigest()
    artifact_sha256 = hashlib.sha256(raw).hexdigest()
    binding_payload = json.dumps(
        {
            "artifact_sha256": artifact_sha256,
            "command_sha256": command_sha256,
            "exit_code": exit_code,
            "revision": revision,
            "run_id": run_id,
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return {
        "schema": "sdb.junit-report/1",
        "status": status,
        "assurance": {
            "level": "CALLER_ATTESTED",
            "command_causality": "NOT_INDEPENDENTLY_VERIFIED",
            "suite_completeness": "NOT_INDEPENDENTLY_VERIFIED",
            "acceptance_authority": "INFORMATIONAL_ONLY",
        },
        "binding": {
            "command_sha256": command_sha256,
            "exit_code": exit_code,
            "run_id": run_id,
            "revision": revision,
            "sha256": hashlib.sha256(binding_payload).hexdigest(),
        },
        "counts": {
            "collected": collected,
            "executed": executed,
            **counts,
        },
        "xml_summary_tests": summary_tests,
        "xml_summary_warning": summary_warning,
        "xml_summary_matches_counts": (
            summary_tests == collected if summary_tests is not None else None
        ),
        "artifact": {
            "path": str(path),
            "sha256": artifact_sha256,
            "modified_at": modified.isoformat().replace("+00:00", "Z"),
            "age_seconds": int(max(age, 0)),
        },
    }


def _verify_repo_binding(repo: Path, expected_revision: str) -> None:
    try:
        head = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=20, check=False,
        )
        status = subprocess.run(
            [
                "git", "-C", str(repo), "status", "--porcelain=v1",
                "--untracked-files=all", "--ignore-submodules=none",
            ],
            capture_output=True, text=True, timeout=20, check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ReportError("repo_check_failed", "repository tidak dapat diverifikasi") from exc
    if head.returncode != 0 or status.returncode != 0:
        raise ReportError("repo_check_failed", "repository tidak dapat diverifikasi")
    if head.stdout.strip() != expected_revision:
        raise ReportError("revision_mismatch", "HEAD repository tidak sama dengan revision laporan")
    if status.stdout:
        raise ReportError("working_tree_dirty", "working tree berubah; laporan tidak terikat snapshot bersih")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("junit_xml", type=Path, nargs="?")
    parser.add_argument("--from-env", action="store_true")
    parser.add_argument("--command")
    parser.add_argument("--exit-code", type=int)
    parser.add_argument("--run-id")
    parser.add_argument("--revision")
    parser.add_argument("--expected-revision", required=True)
    parser.add_argument("--require-clean-repo", type=Path, required=True)
    parser.add_argument("--max-age-seconds", type=int, default=3600)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.from_env:
        args.junit_xml = Path(os.environ.get("JUNIT_XML", ""))
        args.command = os.environ.get("TEST_COMMAND")
        raw_exit = os.environ.get("TEST_EXIT_CODE", "")
        try:
            args.exit_code = int(raw_exit)
        except ValueError:
            args.exit_code = -1
        args.run_id = os.environ.get("TEST_RUN_ID")
        args.revision = os.environ.get("TEST_REVISION")
    elif any(value is None for value in (
        args.junit_xml, args.command, args.exit_code, args.run_id, args.revision
    )):
        parser.error("junit_xml, --command, --exit-code, --run-id, dan --revision wajib")
    try:
        if args.require_clean_repo is not None:
            _verify_repo_binding(args.require_clean_repo.resolve(), args.expected_revision)
        result = build_report(
            args.junit_xml,
            command=args.command,
            exit_code=args.exit_code,
            run_id=args.run_id,
            revision=args.revision,
            expected_revision=args.expected_revision,
            max_age_seconds=args.max_age_seconds,
        )
    except ReportError as exc:
        print(json.dumps({"schema": "sdb.junit-report/1", "status": "REJECTED", "error": exc.code,
                          "message": str(exc)}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "METRICS_VALID" else 1


if __name__ == "__main__":
    sys.exit(main())
