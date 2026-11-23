#!/usr/bin/env python3
"""Evidence capability BE-SP-12 — skema `sdb.capability.evidence/1`.

Modul ini adalah **pencatat** bukti eksekusi tes untuk satu capability pilot.
Batas kemampuannya sengaja sempit, dan batas itu ditegakkan di kode, bukan di
dokumen:

  * builder hanya boleh menghasilkan `AGENT_REPORTED` — klaim JSON tidak bisa
    menaikkannya menjadi `CI_ATTESTED` atau `INDEPENDENT_REVIEW`;
  * `test_command` **tidak pernah dijalankan** oleh modul ini (tidak ada
    subprocess shell, tidak ada eval) — ia hanya dicatat sebagai teks;
  * hasil tes wajib konsisten secara aritmetika (`total == p+f+s+e`), `total`
    tidak boleh 0, dan exit code != 0 tidak pernah menjadi PASS;
  * setiap `artifact_refs` diverifikasi ke hash sha256-nya, tidak boleh absolut,
    tidak boleh `..`, tidak boleh melewati symlink, dan harus tetap di dalam root;
  * revisi terikat ke `git rev-parse HEAD` saat mencatat;
  * penulisan evidence atomik + immutable (gagal = tidak ada berkas separuh).

Empat tingkat yang **tidak** boleh saling naik otomatis:
  1. eksekusi tes  -> `execution_status`
  2. acceptance    -> `acceptance_status` (butuh reviewer independen)
  3. verifikasi independen -> `evidence_level`
  4. otorisasi rilis       -> selalu `NOT_AUTHORIZED` di modul ini
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import sdb_common

SCHEMA = "sdb.capability.evidence/1"
REGISTRY_REL = Path("registry/capability_pilot.yaml")
EVIDENCE_ROOT_REL = Path("runs/capability")
SCHEMA_FILE_REL = Path("registry/capability_evidence.schema.json")

LEVEL_AGENT = "AGENT_REPORTED"
LEVEL_CI = "CI_ATTESTED"
LEVEL_INDEPENDENT = "INDEPENDENT_REVIEW"
PRODUCER_LEVELS = (LEVEL_AGENT,)
ELEVATED_LEVELS = (LEVEL_CI, LEVEL_INDEPENDENT)

REVIEW_NONE = "NOT_REVIEWED"
REVIEW_PENDING = "PENDING_INDEPENDENT_REVIEW"
REVIEW_INDEPENDENT = "REVIEWED_INDEPENDENT"

RELEASE_NOT_AUTHORIZED = "NOT_AUTHORIZED"

EXEC_PASS = "PASS"
EXEC_FAIL = "FAIL"
ACCEPT_INFORMATIONAL = "INFORMATIONAL_ONLY"
ACCEPT_PENDING = "PENDING_INDEPENDENT_REVIEW"
ACCEPT_INDEPENDENT = "ACCEPTED_INDEPENDENT"
ACCEPT_NONE = "NOT_ACCEPTED"

MAX_EVIDENCE_BYTES = 256 * 1024
MAX_ARTIFACT_BYTES = 8 * 1024 * 1024
MAX_ARTIFACTS = 16
MAX_COMMAND_CHARS = 512
CLOCK_SKEW = 300

_HEX40 = re.compile(r"^[0-9a-f]{40}$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_CAP_ID = re.compile(r"^[A-Z]{2,4}-[A-Z0-9]{1,4}-[0-9]{2}$")
_TS = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_RESULT_KEYS = ("passed", "failed", "skipped", "errors", "total")
_REQUIRED = ("schema", "capability_id", "revision", "test_command", "exit_code",
             "test_results", "artifact_refs", "evidence_level",
             "verification_timestamp", "review_status", "release_authorization")


class EvidenceError(Exception):
    """Penolakan fail-closed: selalu membawa kode mesin + alasan manusia."""

    def __init__(self, code: str, reason: str) -> None:
        super().__init__(f"{code}: {reason}")
        self.code = code
        self.reason = reason


# ---------- kanonik & hash ----------
def canonical_bytes(obj: object) -> bytes:
    """Byte kanonik: kunci terurut, tanpa spasi, tolak NaN/Infinity."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def integrity_of(evidence: dict) -> str:
    """Sidik integritas atas seluruh field kecuali `integrity` itu sendiri."""
    body = {k: v for k, v in evidence.items() if k != "integrity"}
    return sha256_hex(canonical_bytes(body))


# ---------- tipe ketat (bool bukan int) ----------
def as_int(v: object) -> int | None:
    if isinstance(v, bool) or not isinstance(v, int):
        return None
    return v


def is_hex40(v: object) -> bool:
    return isinstance(v, str) and bool(_HEX40.match(v))


def is_hex64(v: object) -> bool:
    return isinstance(v, str) and bool(_HEX64.match(v))


def parse_ts(v: object) -> _dt.datetime | None:
    if not isinstance(v, str) or not _TS.match(v):
        return None
    try:
        return _dt.datetime.strptime(v, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=_dt.timezone.utc)
    except ValueError:
        return None


def utc_now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------- registry pilot ----------
def load_registry(repo: Path | None = None) -> dict[str, dict]:
    """Muat `registry/capability_pilot.yaml` -> {capability_id: entri}.

    Registry ini **pilot**, bukan katalog 26 capability: ia hanya mendaftarkan
    capability yang sudah disetujui untuk pilot dan tidak menimpa ID mana pun.
    """
    repo = repo or Path(sdb_common.repo_path())
    path = repo / REGISTRY_REL
    if not path.is_file():
        raise EvidenceError("registry_missing", f"{REGISTRY_REL} tidak ditemukan")
    data = sdb_common.load_yaml(str(path))
    if not isinstance(data, dict):
        raise EvidenceError("registry_invalid", "registry bukan mapping")
    raw = data.get("capabilities")
    if not isinstance(raw, list):
        raise EvidenceError("registry_invalid", "`capabilities` harus list")
    out: dict[str, dict] = {}
    for entry in raw:
        if not isinstance(entry, dict):
            raise EvidenceError("registry_invalid", "entri capability bukan mapping")
        cid = entry.get("id")
        if not isinstance(cid, str) or not _CAP_ID.match(cid):
            raise EvidenceError("registry_invalid", f"id capability tidak sah: {cid!r}")
        if cid in out:
            raise EvidenceError("registry_duplicate_id", f"id ganda: {cid}")
        status = entry.get("status")
        if status not in ("PILOT", "ACTIVE"):
            raise EvidenceError("registry_invalid", f"{cid} status {status!r} tidak diizinkan")
        out[cid] = entry
    if not out:
        raise EvidenceError("registry_empty", "registry tidak mendaftarkan capability apa pun")
    return out


def known_capability(cid: object, registry: dict[str, dict]) -> dict:
    if not isinstance(cid, str) or not _CAP_ID.match(cid):
        raise EvidenceError("capability_id_invalid",
                            f"id capability wajib berpola XX-YY-NN, diterima {cid!r}")
    if cid not in registry:
        raise EvidenceError("capability_unknown", f"{cid} tidak terdaftar di registry pilot")
    return registry[cid]


# ---------- git revision ----------
def resolve_head(repo: Path) -> str:
    try:
        proc = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                              capture_output=True, text=True, timeout=20, check=False)
    except (OSError, subprocess.SubprocessError) as exc:  # pragma: no cover - lingkungan rusak
        raise EvidenceError("revision_unavailable", f"git tidak bisa dijalankan: {exc}") from exc
    if proc.returncode != 0:
        raise EvidenceError("revision_unavailable", "repo tidak punya HEAD (git rev-parse gagal)")
    head = proc.stdout.strip()
    if not is_hex40(head):
        raise EvidenceError("revision_unavailable", f"HEAD bukan SHA-1 40 hex: {head!r}")
    return head


# ---------- artefak: path traversal & symlink ----------
def safe_artifact(root: Path, raw: object) -> Path:
    """Validasi path artefak: relatif, tanpa `..`, bebas symlink, di dalam root."""
    if not isinstance(raw, str) or not raw.strip():
        raise EvidenceError("artifact_path_invalid", "path artefak harus string tidak kosong")
    if "\x00" in raw or "\\" in raw:
        raise EvidenceError("artifact_path_invalid", f"karakter path ditolak: {raw!r}")
    p = Path(raw)
    if raw in (".", "./"):
        raise EvidenceError("artifact_path_invalid", f"path berkas ditolak: {raw!r}")
    if p.is_absolute():
        raise EvidenceError("artifact_path_absolute", f"path absolut ditolak: {raw}")
    if any(part in ("", ".", "..") for part in p.parts):
        raise EvidenceError("artifact_path_traversal", f"komponen path ditolak: {raw}")
    if root.is_symlink():
        raise EvidenceError("artifact_root_symlink", f"root evidence adalah symlink: {root}")
    try:
        real_root = root.resolve(strict=True)
    except OSError as exc:
        raise EvidenceError("artifact_root_missing", f"root evidence tidak ada: {exc}") from exc
    cursor = real_root
    for part in p.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise EvidenceError("artifact_symlink", f"symlink ditolak pada komponen: {part}")
    if not cursor.exists():
        raise EvidenceError("artifact_missing", f"artefak tidak ditemukan: {raw}")
    real = cursor.resolve()
    if real != real_root and real_root not in real.parents:
        raise EvidenceError("artifact_escape", f"artefak keluar dari root: {raw}")
    if not real.is_file():
        raise EvidenceError("artifact_not_file", f"artefak bukan berkas biasa: {raw}")
    size = real.stat().st_size
    if size > MAX_ARTIFACT_BYTES:
        raise EvidenceError("artifact_too_large", f"artefak {size} byte > batas {MAX_ARTIFACT_BYTES}")
    return real


def check_artifacts(refs: object, root: Path) -> list[dict]:
    if not isinstance(refs, list):
        raise EvidenceError("artifact_refs_invalid", "artifact_refs harus list")
    if len(refs) > MAX_ARTIFACTS:
        raise EvidenceError("artifact_refs_invalid", f"maksimum {MAX_ARTIFACTS} artefak")
    out: list[dict] = []
    seen: set[str] = set()
    for ref in refs:
        if not isinstance(ref, dict) or set(ref) != {"path", "sha256"}:
            raise EvidenceError("artifact_refs_invalid", "entri artefak wajib {path, sha256}")
        path = safe_artifact(root, ref["path"])
        declared = ref["sha256"]
        if not is_hex64(declared):
            raise EvidenceError("artifact_hash_invalid", f"sha256 tidak sah: {declared!r}")
        actual = file_sha256(path)
        if actual != declared:
            raise EvidenceError("artifact_hash_mismatch",
                                f"{ref['path']}: sha256 tercatat {declared[:12]}... != nyata {actual[:12]}...")
        rel = path.relative_to(root.resolve()).as_posix()
        if rel in seen:
            raise EvidenceError("artifact_duplicate", f"artefak ganda: {rel}")
        seen.add(rel)
        out.append({"path": rel, "sha256": actual})
    return out


# ---------- test_results ----------
def check_results(result: object, exit_code: int) -> dict:
    if not isinstance(result, dict):
        raise EvidenceError("test_results_invalid", "test_results harus mapping")
    if set(result) != set(_RESULT_KEYS):
        raise EvidenceError("test_results_invalid",
                            f"kunci wajib tepat {list(_RESULT_KEYS)}, diterima {sorted(result)}")
    vals: dict[str, int] = {}
    for key in _RESULT_KEYS:
        n = as_int(result[key])
        if n is None or n < 0:
            raise EvidenceError("test_results_invalid", f"{key} harus int >= 0")
        vals[key] = n
    total_sum = vals["passed"] + vals["failed"] + vals["skipped"] + vals["errors"]
    if vals["total"] != total_sum:
        raise EvidenceError("test_results_inconsistent",
                            f"total {vals['total']} != jumlah bagian {total_sum}")
    if vals["total"] == 0:
        raise EvidenceError("no_tests_executed", "total 0: tidak ada tes yang dijalankan")
    if vals["passed"] + vals["failed"] + vals["errors"] == 0:
        raise EvidenceError("no_tests_executed", "semua tes skip: tidak ada eksekusi nyata")
    if exit_code != 0 and vals["failed"] == 0 and vals["errors"] == 0:
        raise EvidenceError("test_results_inconsistent",
                            f"exit_code {exit_code} bukan 0 tetapi failed/errors 0")
    return vals


def execution_status(vals: dict, exit_code: int) -> str:
    if exit_code == 0 and vals["failed"] == 0 and vals["errors"] == 0 and vals["passed"] > 0:
        return EXEC_PASS
    return EXEC_FAIL


def acceptance_status(level: str, review: str, exec_status: str) -> str:
    """Acceptance tidak pernah diberikan karena exit code 0 saja."""
    if exec_status != EXEC_PASS:
        return ACCEPT_NONE
    if level in PRODUCER_LEVELS:
        return ACCEPT_INFORMATIONAL
    if level == LEVEL_CI:
        return ACCEPT_PENDING
    if level == LEVEL_INDEPENDENT and review == REVIEW_INDEPENDENT:
        return ACCEPT_INDEPENDENT
    return ACCEPT_NONE


# ---------- validasi inti ----------
def _no_dup_pairs(pairs):
    out: dict = {}
    for key, value in pairs:
        if key in out:
            raise EvidenceError("json_duplicate_key", f"kunci ganda: {key}")
        out[key] = value
    return out


def _no_constants(token: str):
    raise EvidenceError("json_non_finite", f"konstanta {token} ditolak (NaN/Infinity)")


def loads_strict(text: str) -> object:
    try:
        return json.loads(text, object_pairs_hook=_no_dup_pairs, parse_constant=_no_constants)
    except EvidenceError:
        raise
    except json.JSONDecodeError as exc:
        raise EvidenceError("json_invalid", f"JSON tidak sah: {exc.msg} (baris {exc.lineno})") from exc


def validate_payload(payload: object, *, repo: Path | None = None,
                     head: str | None = None, now: _dt.datetime | None = None,
                     registry: dict[str, dict] | None = None) -> dict:
    """Validasi evidence dan kembalikan verdict. Selalu fail-closed."""
    repo = repo or Path(sdb_common.repo_path())
    registry = registry if registry is not None else load_registry(repo)
    if not isinstance(payload, dict):
        raise EvidenceError("evidence_not_object", "evidence harus objek JSON")

    missing = [k for k in _REQUIRED if k not in payload]
    if missing:
        raise EvidenceError("schema_missing_field", f"field wajib hilang: {missing}")
    extra = sorted(set(payload) - set(_REQUIRED) - {"integrity"})
    if extra:
        raise EvidenceError("schema_unknown_field", f"field tidak dikenal: {extra}")
    if payload["schema"] != SCHEMA:
        raise EvidenceError("schema_mismatch", f"schema {payload['schema']!r} != {SCHEMA!r}")

    if "integrity" in payload:
        if not is_hex64(payload["integrity"]):
            raise EvidenceError("integrity_invalid", "integrity wajib sha256 hex")
        if payload["integrity"] != integrity_of(payload):
            raise EvidenceError("integrity_mismatch", "sidik integritas tidak cocok (evidence diubah)")

    known_capability(payload["capability_id"], registry)

    revision = payload["revision"]
    if not is_hex40(revision):
        raise EvidenceError("revision_invalid", "revision wajib SHA-1 40 hex huruf kecil")
    head = head if head is not None else resolve_head(repo)
    if revision != head:
        raise EvidenceError("revision_mismatch", f"revision {revision[:12]} != HEAD {head[:12]}")

    cmd = payload["test_command"]
    if not isinstance(cmd, str) or not cmd.strip() or len(cmd) > MAX_COMMAND_CHARS:
        raise EvidenceError("test_command_invalid", f"test_command wajib string 1..{MAX_COMMAND_CHARS}")
    if "\x00" in cmd or "\n" in cmd or "\r" in cmd:
        raise EvidenceError("test_command_invalid", "test_command tidak boleh multi-baris / NUL")

    exit_code = as_int(payload["exit_code"])
    if exit_code is None or not 0 <= exit_code <= 255:
        raise EvidenceError("exit_code_invalid", "exit_code wajib int 0..255")
    vals = check_results(payload["test_results"], exit_code)

    refs = check_artifacts(payload["artifact_refs"], repo)

    level = payload["evidence_level"]
    if level in ELEVATED_LEVELS:
        raise EvidenceError("self_attestation_rejected",
                            f"{level} tidak boleh diklaim lewat JSON; hanya verifier/CI yang berwenang")
    if level not in PRODUCER_LEVELS:
        raise EvidenceError("evidence_level_invalid", f"level {level!r} tidak dikenal")

    review = payload["review_status"]
    if review in (REVIEW_INDEPENDENT, "APPROVED"):
        raise EvidenceError("self_attestation_rejected",
                            f"review_status {review!r} hanya boleh diisi reviewer independen")
    if review != REVIEW_NONE:
        raise EvidenceError("review_status_invalid", f"review_status {review!r} tidak sah untuk builder")

    release = payload["release_authorization"]
    if release != RELEASE_NOT_AUTHORIZED:
        raise EvidenceError("release_claim_rejected",
                            f"release_authorization wajib {RELEASE_NOT_AUTHORIZED!r}")

    ts = parse_ts(payload["verification_timestamp"])
    if ts is None:
        raise EvidenceError("timestamp_invalid", "verification_timestamp wajib ISO-8601 UTC `...Z`")
    ref_now = now or _dt.datetime.now(_dt.timezone.utc)
    if (ts - ref_now).total_seconds() > CLOCK_SKEW:
        raise EvidenceError("timestamp_future", "verification_timestamp di masa depan")

    exec_status = execution_status(vals, exit_code)
    return {
        "schema": SCHEMA,
        "capability_id": payload["capability_id"],
        "revision": revision,
        "execution_status": exec_status,
        "exit_code": exit_code,
        "test_results": vals,
        "evidence_level": level,
        "acceptance_status": acceptance_status(level, review, exec_status),
        "review_status": review,
        "release_authorization": release,
        "artifacts": refs,
    }


# ---------- penulisan atomik ----------
def evidence_path(root: Path, capability_id: str, revision: str) -> Path:
    if not _CAP_ID.match(capability_id) or not is_hex40(revision):
        raise EvidenceError("evidence_path_invalid", "capability/revision tidak sah untuk nama berkas")
    return root / capability_id / f"{revision}.json"


def approved_evidence_root(repo: Path, root: Path | None = None) -> Path:
    """Kunci output ke runs/capability dan tolak symlink pada rantai root."""
    repo_abs = Path(os.path.abspath(repo))
    expected = repo_abs / EVIDENCE_ROOT_REL
    root_abs = Path(os.path.abspath(root if root is not None else expected))
    if root_abs != expected:
        raise EvidenceError(
            "evidence_root_unauthorized",
            f"root evidence wajib {EVIDENCE_ROOT_REL.as_posix()}",
        )
    current = repo_abs
    for part in EVIDENCE_ROOT_REL.parts:
        current /= part
        if current.is_symlink():
            raise EvidenceError("evidence_root_symlink", f"root evidence memuat symlink: {current}")
    return expected


def safe_evidence_file(path: Path, repo: Path) -> Path:
    """Pastikan input validate berada di root evidence dan tanpa symlink."""
    root = approved_evidence_root(repo)
    target = Path(os.path.abspath(path))
    try:
        relative = target.relative_to(root)
    except ValueError as exc:
        raise EvidenceError(
            "evidence_path_unauthorized",
            f"evidence wajib berada di {EVIDENCE_ROOT_REL.as_posix()}",
        ) from exc
    current = root
    for part in relative.parts:
        current /= part
        if current.is_symlink():
            raise EvidenceError("evidence_symlink", f"path evidence memuat symlink: {current}")
    return target


def atomic_write(path: Path, data: bytes, *, replace: bool = False) -> None:
    """Tulis atomik; mode immutable gagal atomik bila destination sudah ada."""
    if path.exists() and not replace:
        raise EvidenceError("evidence_exists",
                            f"{path} sudah ada (immutable; pakai --replace bila memang revisi ulang)")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.parent.is_symlink():
        raise EvidenceError("evidence_root_symlink", f"direktori evidence symlink: {path.parent}")
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".capability-", suffix=".tmp")
    tmp_path = Path(tmp)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp_path, 0o600)
        if replace:
            os.replace(tmp_path, path)
        else:
            try:
                os.link(tmp_path, path)
            except FileExistsError as exc:
                raise EvidenceError("evidence_exists", f"evidence sudah ada: {path}") from exc
            tmp_path.unlink()
        dfd = os.open(str(path.parent), os.O_RDONLY)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise


def record(*, capability_id: str, revision: str, test_command: str, exit_code: int,
           results: dict, artifacts: list | None = None, level: str = LEVEL_AGENT,
           root: Path | None = None, repo: Path | None = None,
           review_status: str = REVIEW_NONE, replace: bool = False,
           now: _dt.datetime | None = None) -> dict:
    """Catat evidence eksekusi (level builder). Tidak menjalankan perintah apa pun."""
    repo = repo or Path(sdb_common.repo_path())
    registry = load_registry(repo)
    known_capability(capability_id, registry)
    head = resolve_head(repo)
    if revision != head:
        raise EvidenceError("revision_mismatch", f"revision {revision[:12]} != HEAD {head[:12]}")

    payload = {
        "schema": SCHEMA,
        "capability_id": capability_id,
        "revision": revision,
        "test_command": test_command,
        "exit_code": exit_code,
        "test_results": results,
        "artifact_refs": artifacts or [],
        "evidence_level": level,
        "verification_timestamp": (now or _dt.datetime.now(_dt.timezone.utc))
        .strftime("%Y-%m-%dT%H:%M:%SZ"),
        "review_status": review_status,
        "release_authorization": RELEASE_NOT_AUTHORIZED,
    }
    verdict = validate_payload(payload, repo=repo, head=head, now=now, registry=registry)
    evidence = dict(payload, integrity=integrity_of(payload))

    root = approved_evidence_root(repo, root)
    path = evidence_path(root, capability_id, revision)
    data = (json.dumps(evidence, sort_keys=True, indent=2, ensure_ascii=False,
                       allow_nan=False) + "\n").encode("utf-8")
    if len(data) > MAX_EVIDENCE_BYTES:
        raise EvidenceError("evidence_too_large", f"{len(data)} byte > {MAX_EVIDENCE_BYTES}")
    atomic_write(path, data, replace=replace)
    return dict(verdict, evidence_path=str(path), integrity=evidence["integrity"])


def validate_file(path: Path, *, repo: Path | None = None, head: str | None = None,
                  now: _dt.datetime | None = None) -> dict:
    repo = repo or Path(sdb_common.repo_path())
    path = safe_evidence_file(path, repo)
    if not path.is_file():
        raise EvidenceError("evidence_missing", f"berkas evidence tidak ada: {path}")
    size = path.stat().st_size
    if size > MAX_EVIDENCE_BYTES:
        raise EvidenceError("evidence_too_large", f"{size} byte > {MAX_EVIDENCE_BYTES}")
    payload = loads_strict(path.read_text(encoding="utf-8"))
    return validate_payload(payload, repo=repo, head=head, now=now)


# ---------- CLI ----------
def _emit(obj: dict) -> None:
    print(json.dumps(obj, sort_keys=True, indent=2, ensure_ascii=False))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="sdb_capability_evidence.py",
        description="Catat/validasi evidence capability (skema sdb.capability.evidence/1).")
    sub = parser.add_subparsers(dest="cmd", required=True)

    rec = sub.add_parser("record", help="catat evidence eksekusi (level builder)")
    rec.add_argument("--capability", required=True)
    rec.add_argument("--revision", default="HEAD", help="SHA penuh atau HEAD")
    rec.add_argument("--command", dest="test_command", required=True)
    rec.add_argument("--exit-code", type=int, required=True)
    rec.add_argument("--passed", type=int, required=True)
    rec.add_argument("--failed", type=int, required=True)
    rec.add_argument("--skipped", type=int, default=0)
    rec.add_argument("--errors", type=int, default=0)
    rec.add_argument("--total", type=int, required=True)
    rec.add_argument("--artifact", action="append", default=[],
                     metavar="PATH:SHA256", help="ulangi untuk banyak artefak")
    rec.add_argument("--level", default=LEVEL_AGENT)
    rec.add_argument("--root", default=str(EVIDENCE_ROOT_REL))
    rec.add_argument("--repo", default=None)
    rec.add_argument("--replace", action="store_true")

    val = sub.add_parser("validate", help="validasi berkas evidence")
    val.add_argument("path")
    val.add_argument("--expect-revision", default=None)
    val.add_argument("--repo", default=None)

    args = parser.parse_args(argv)
    repo = Path(args.repo).resolve() if args.repo else Path(sdb_common.repo_path())
    try:
        if args.cmd == "record":
            head = resolve_head(repo) if args.revision == "HEAD" else args.revision
            artifacts = []
            for item in args.artifact:
                path_part, sep, hash_part = item.rpartition(":")
                if not sep or not path_part:
                    raise EvidenceError("artifact_arg_invalid", f"format wajib PATH:SHA256, diterima {item!r}")
                artifacts.append({"path": path_part, "sha256": hash_part})
            root = Path(args.root)
            root = root if root.is_absolute() else repo / root
            out = record(capability_id=args.capability, revision=head,
                         test_command=args.test_command, exit_code=args.exit_code,
                         results={"passed": args.passed, "failed": args.failed,
                                  "skipped": args.skipped, "errors": args.errors,
                                  "total": args.total},
                         artifacts=artifacts, level=args.level, root=root, repo=repo,
                         replace=args.replace)
            _emit({"result": "RECORDED", **out})
            return 0 if out["execution_status"] == EXEC_PASS else 2
        out = validate_file(Path(args.path), repo=repo, head=args.expect_revision)
        _emit({"result": "VALID", **out})
        return 0 if out["execution_status"] == EXEC_PASS else 2
    except EvidenceError as exc:
        _emit({"result": "REJECTED", "code": exc.code, "reason": exc.reason,
               "release_authorization": RELEASE_NOT_AUTHORIZED})
        return 2
    except (OSError, UnicodeError):
        _emit({"result": "REJECTED", "code": "io_error",
               "reason": "operasi filesystem atau decoding evidence gagal",
               "release_authorization": RELEASE_NOT_AUTHORIZED})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
