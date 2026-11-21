#!/usr/bin/env python3
"""Trusted models, authorization, registry, revision, and safe I/O for C1-03."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any, Mapping

import sdb_common

TASK_SCHEMA = "sdb.capability.task/1"
APPROVAL_SCHEMA = "sdb.capability.execution-approvals/1"
EXPECTED_IDS = {
    "frontend": tuple(f"FE-SP-{number:02d}" for number in range(1, 13)),
    "backend": tuple(f"BE-SP-{number:02d}" for number in range(1, 15)),
}
MAX_GOAL_CHARS = 4096
MAX_REQUESTED_PATHS = 32
MAX_PATH_CHARS = 240
MAX_APPROVAL_TTL = dt.timedelta(days=31)
FORBIDDEN_ROOT_HEADS = frozenset({"scripts", "registry", "runs"})
_PROTECTED_EXACT = (
    "registry/capability_pilot.yaml",
    "registry/capability_execution_approvals.yaml",
)


class RoutingError(ValueError):
    """A fail-closed routing boundary refusal."""


def fail(code: str, message: str) -> RoutingError:
    return RoutingError(f"{code}: {message}")


def canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise fail("canonical_json_invalid", str(exc)) from exc


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def strict_keys(raw: Mapping[str, Any], expected: set[str], where: str) -> None:
    if set(raw) != expected:
        raise fail(f"{where}_fields_invalid", f"expected {sorted(expected)}, got {sorted(raw)}")


def text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise fail("field_invalid", f"{field} must be non-empty text without NUL")
    return value.strip()


def safe_relative(value: str, field: str) -> str:
    if "\\" in value:
        raise fail("path_invalid", f"{field} must use POSIX separators")
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise fail("path_invalid", f"{field} must be normalized and relative")
    if ".git" in path.parts:
        raise fail("path_invalid", ".git is never writable")
    return path.as_posix()


def parse_time(value: Any, field: str) -> dt.datetime:
    if isinstance(value, dt.datetime):
        parsed = value
    elif isinstance(value, dt.date):
        parsed = dt.datetime.combine(value, dt.time(), tzinfo=dt.timezone.utc)
    else:
        try:
            parsed = dt.datetime.fromisoformat(text(value, field).replace("Z", "+00:00"))
        except ValueError as exc:
            raise fail("approval_time_invalid", field) from exc
    if parsed.tzinfo is None:
        raise fail("approval_time_invalid", f"{field} requires timezone")
    return parsed.astimezone(dt.timezone.utc)


@dataclass(frozen=True)
class TaskPack:
    schema: str
    capability_id: str
    lane: str
    goal: str
    requested_write_paths: tuple[str, ...]

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "TaskPack":
        if not isinstance(raw, Mapping):
            raise fail("task_invalid", "task must be an object")
        strict_keys(raw, {"schema", "capability_id", "lane", "goal", "requested_write_paths"}, "task")
        if raw.get("schema") != TASK_SCHEMA:
            raise fail("task_schema_invalid", TASK_SCHEMA)
        lane = text(raw.get("lane"), "lane")
        if lane not in EXPECTED_IDS:
            raise fail("task_lane_invalid", lane)
        paths_raw = raw.get("requested_write_paths")
        if not isinstance(paths_raw, list):
            raise fail("task_paths_invalid", "requested_write_paths must be a list")
        if len(paths_raw) > MAX_REQUESTED_PATHS:
            raise fail("task_paths_invalid", f"at most {MAX_REQUESTED_PATHS} requested paths")
        paths = tuple(safe_relative(text(item, "requested_write_paths[]"), "requested_write_paths[]") for item in paths_raw)
        if any(len(item) > MAX_PATH_CHARS for item in paths):
            raise fail("task_paths_invalid", f"path longer than {MAX_PATH_CHARS} chars")
        if len(set(paths)) != len(paths):
            raise fail("task_paths_invalid", "duplicate requested path")
        goal = text(raw.get("goal"), "goal")
        if len(goal) > MAX_GOAL_CHARS:
            raise fail("task_goal_too_long", f"goal exceeds {MAX_GOAL_CHARS} chars")
        return cls(
            TASK_SCHEMA,
            text(raw.get("capability_id"), "capability_id"),
            lane,
            goal,
            paths,
        )

    def as_mapping(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "capability_id": self.capability_id,
            "lane": self.lane,
            "goal": self.goal,
            "requested_write_paths": list(self.requested_write_paths),
        }

    def digest(self) -> str:
        return sha256(canonical_bytes(self.as_mapping()))


@dataclass(frozen=True)
class LaneRoute:
    profile: str
    capability_ids: tuple[str, ...]


@dataclass(frozen=True)
class RoutingRegistry:
    executor: str
    lanes: Mapping[str, LaneRoute]
    profiles: Mapping[str, Mapping[str, Any]]
    capabilities: Mapping[str, Mapping[str, Any]]

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "RoutingRegistry":
        try:
            routing = raw["routing"]
            lanes_raw = routing["lanes"]
            definitions = raw["capabilities"]
        except (KeyError, TypeError) as exc:
            raise fail("registry_invalid", "missing registry sections") from exc
        if routing.get("executor") != "hermes" or set(lanes_raw) != set(EXPECTED_IDS):
            raise fail("registry_ids_invalid", "unexpected executor or lanes")
        lanes: dict[str, LaneRoute] = {}
        profiles_raw = raw.get("profiles", {})
        if not isinstance(profiles_raw, Mapping):
            raise fail("registry_invalid", "profiles must be an object when present")
        profiles: dict[str, Mapping[str, Any]] = dict(profiles_raw)
        for lane_name, expected in EXPECTED_IDS.items():
            lane = lanes_raw[lane_name]
            ids = tuple(lane.get("capability_ids", ()))
            if ids != expected:
                raise fail("registry_ids_invalid", f"{lane_name} must be exactly {list(expected)}")
            profile = text(lane.get("profile"), f"{lane_name}.profile")
            profiles.setdefault(profile, MappingProxyType({"lane": lane_name}))
            lanes[lane_name] = LaneRoute(profile, ids)
        if not isinstance(definitions, list):
            raise fail("registry_invalid", "capabilities must be a list")
        capabilities = {
            item["id"]: item
            for item in definitions
            if isinstance(item, Mapping) and isinstance(item.get("id"), str)
        }
        expected_all = set(EXPECTED_IDS["frontend"]) | set(EXPECTED_IDS["backend"])
        if not set(capabilities).issubset(expected_all):
            raise fail("registry_ids_invalid", "definition outside exact lane sets")
        return cls("hermes", MappingProxyType(lanes), MappingProxyType(dict(profiles)), MappingProxyType(capabilities))

    def validate_task(self, task: TaskPack) -> LaneRoute:
        lane = self.lanes.get(task.lane)
        if lane is None or task.capability_id not in lane.capability_ids:
            raise fail("task_route_invalid", f"{task.capability_id} not in {task.lane}")
        return lane


@dataclass(frozen=True)
class ApprovalRecord:
    approval_ref: str
    task_digest: str
    capability_id: str
    lane: str
    allowed_write_roots: tuple[str, ...]
    nonproduction: bool
    issuer: str
    issued_at: dt.datetime
    expires_at: dt.datetime
    nonce: str


@dataclass(frozen=True)
class FileBinding:
    sha256: str
    tracked: bool
    dirty: bool


@dataclass(frozen=True)
class RevisionBinding:
    head: str
    files: Mapping[str, FileBinding]

    def canonical(self) -> dict[str, Any]:
        return {
            "head": self.head,
            "files": {
                name: {"sha256": item.sha256, "tracked": item.tracked, "dirty": item.dirty}
                for name, item in sorted(self.files.items())
            },
        }


def load_registry_mapping(repo: Path) -> Mapping[str, Any]:
    return sdb_common.load_yaml(str(repo / "registry" / "capability_pilot.yaml"))


def strict_yaml_load(data: bytes, where: str) -> Any:
    """PyYAML safe load that rejects duplicate keys and anchors/aliases (last-key-wins is a trap)."""
    try:
        import yaml
    except ModuleNotFoundError as exc:
        raise fail("yaml_unavailable", "PyYAML is required for trusted configuration") from exc

    class _Strict(yaml.SafeLoader):
        pass

    def construct_mapping(loader: Any, node: Any, deep: bool = False) -> dict[Any, Any]:
        seen: set[Any] = set()
        for key_node, _ in node.value:
            key = loader.construct_object(key_node, deep=True)
            if key in seen:
                raise fail("yaml_duplicate_key", f"{where}: duplicate key {key!r}")
            seen.add(key)
        return yaml.SafeLoader.construct_mapping(loader, node, deep)

    _Strict.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, construct_mapping)
    try:
        text_value = data.decode("utf-8")
        if any(isinstance(event, yaml.AliasEvent) for event in yaml.parse(text_value, Loader=yaml.SafeLoader)):
            raise fail("yaml_alias_forbidden", where)
        return yaml.load(text_value, Loader=_Strict)
    except RoutingError:
        raise
    except (UnicodeDecodeError, TypeError, yaml.YAMLError) as exc:
        raise fail("yaml_invalid", f"{where}: {exc}") from exc


def _git_env() -> dict[str, str]:
    """Clean git environment: caller GIT_DIR/GIT_INDEX_FILE/config must not steer trust checks."""
    return {
        "PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8",
        "GIT_CONFIG_NOSYSTEM": "1", "GIT_NO_REPLACE_OBJECTS": "1", "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_OPTIONAL_LOCKS": "0",
    }


def git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    process = subprocess.run(
        ["git", "-c", "core.fsmonitor=false", *args], cwd=repo, text=True, capture_output=True,
        check=False, env=_git_env(),
    )
    if check and process.returncode:
        raise fail("git_state_invalid", (process.stderr or process.stdout).strip())
    return process


def committed_blob(repo: Path, relative: str) -> bytes | None:
    process = subprocess.run(
        ["git", "-c", "core.fsmonitor=false", "show", f"HEAD:{relative}"], cwd=repo,
        capture_output=True, check=False, env=_git_env(),
    )
    return process.stdout if process.returncode == 0 else None


def file_state(repo: Path, relative: str) -> tuple[bool, bool, bytes | None]:
    """Return (tracked, dirty, committed_blob). Index flags (assume-unchanged/skip-worktree) are dirty."""
    listing = git(repo, "ls-files", "-v", "--", relative, check=False)
    line = listing.stdout.splitlines()[0] if listing.returncode == 0 and listing.stdout.strip() else ""
    tracked = bool(line)
    blob = committed_blob(repo, relative) if tracked else None
    try:
        disk = (repo / relative).read_bytes()
    except OSError:
        disk = None
    dirty = (not tracked) or line[:1] != "H" or blob is None or disk != blob
    return tracked, dirty, blob


def load_routing_registry(repo: Path) -> RoutingRegistry:
    relative = "registry/capability_pilot.yaml"
    path = repo / relative
    try:
        info = path.lstat()
    except OSError as exc:
        raise fail("registry_untrusted", str(path)) from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise fail("registry_untrusted", "registry must be a regular non-symlink")
    tracked, dirty, blob = file_state(repo, relative)
    if not tracked:
        raise fail("registry_untrusted", "registry is not tracked")
    if dirty or blob is None:
        raise fail("registry_untrusted", "registry differs from committed configuration")
    raw = strict_yaml_load(blob, relative)
    if not isinstance(raw, Mapping):
        raise fail("registry_invalid", "registry must be an object")
    return RoutingRegistry.from_mapping(raw)


def load_trusted_approval(
    repo: Path,
    approval_ref: str,
    task: TaskPack,
    *,
    now: dt.datetime | None = None,
) -> ApprovalRecord:
    relative = "registry/capability_execution_approvals.yaml"
    path = repo / relative
    try:
        info = path.lstat()
    except OSError as exc:
        raise fail("approval_store_missing", str(path)) from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise fail("approval_store_untrusted", "store must be a regular non-symlink")
    tracked, dirty, blob = file_state(repo, relative)
    if not tracked:
        raise fail("approval_store_modified", "store is not tracked")
    if dirty or blob is None:
        raise fail("approval_store_modified", "store differs from committed configuration")
    raw = strict_yaml_load(blob, relative)
    if not isinstance(raw, Mapping) or set(raw) != {"schema", "records"} or raw.get("schema") != APPROVAL_SCHEMA:
        raise fail("approval_store_invalid", APPROVAL_SCHEMA)
    records = raw.get("records")
    if not isinstance(records, list):
        raise fail("approval_store_invalid", "records must be a list")
    matches = [item for item in records if isinstance(item, Mapping) and item.get("approval_ref") == approval_ref]
    if len(matches) != 1:
        raise fail("approval_unknown", approval_ref)
    item = matches[0]
    strict_keys(
        item,
        {"approval_ref", "task_digest", "capability_id", "lane", "allowed_write_roots", "nonproduction", "issuer", "issued_at", "expires_at", "nonce"},
        "approval",
    )
    roots_raw = item.get("allowed_write_roots")
    if not isinstance(roots_raw, list):
        raise fail("approval_roots_invalid", "roots must be a list")
    roots = tuple(safe_relative(text(root, "allowed_write_roots[]"), "allowed_write_roots[]") for root in roots_raw)
    if len(set(roots)) != len(roots):
        raise fail("approval_roots_invalid", "duplicate roots")
    for root in roots:
        if PurePosixPath(root).parts[0] in FORBIDDEN_ROOT_HEADS:
            raise fail("approval_roots_invalid", f"{root} overlaps protected paths")
    issued = parse_time(item.get("issued_at"), "issued_at")
    expires = parse_time(item.get("expires_at"), "expires_at")
    current = (now or dt.datetime.now(dt.timezone.utc)).astimezone(dt.timezone.utc)
    if expires <= issued:
        raise fail("approval_time_invalid", "expiry must follow issue")
    if expires - issued > MAX_APPROVAL_TTL:
        raise fail("approval_time_invalid", f"approval lifetime exceeds {MAX_APPROVAL_TTL}")
    if current < issued:
        raise fail("approval_not_yet_valid", approval_ref)
    if current >= expires:
        raise fail("approval_expired", approval_ref)
    approval = ApprovalRecord(
        approval_ref,
        text(item.get("task_digest"), "task_digest"),
        text(item.get("capability_id"), "capability_id"),
        text(item.get("lane"), "lane"),
        roots,
        item.get("nonproduction") is True,
        text(item.get("issuer"), "issuer"),
        issued,
        expires,
        text(item.get("nonce"), "nonce"),
    )
    if approval.task_digest != task.digest() or approval.capability_id != task.capability_id or approval.lane != task.lane:
        raise fail("approval_task_mismatch", "digest, capability, or lane differs")
    if not approval.nonproduction:
        raise fail("approval_production_forbidden", "only nonproduction is supported")
    for requested in task.requested_write_paths:
        if not any(requested == root or requested.startswith(root + "/") for root in roots):
            raise fail("approval_scope_mismatch", requested)
    return approval


def open_directory_nofollow(root: Path, relative: str = "", *, create: bool = False) -> int:
    fd: int | None = None
    try:
        info = root.lstat()
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
            raise fail("secure_path_symlink", str(root))
        fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        for component in PurePosixPath(relative).parts if relative else ():
            if component in {"", ".", ".."}:
                raise fail("secure_path_invalid", relative)
            try:
                next_fd = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=fd)
            except FileNotFoundError:
                if not create:
                    raise
                os.mkdir(component, 0o700, dir_fd=fd)
                next_fd = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        return fd
    except RoutingError:
        if fd is not None:
            os.close(fd)
        raise
    except OSError as exc:
        if fd is not None:
            os.close(fd)
        code = "secure_path_symlink" if exc.errno in {20, 40} else "secure_path_open_failed"
        raise fail(code, f"{relative or root}: {exc}") from exc


def secure_write(
    repo: Path,
    relative: str,
    data: bytes,
    *,
    exclusive: bool = True,
    _allow_internal_git: bool = False,
) -> None:
    if _allow_internal_git:
        path = PurePosixPath(relative)
        expected_parent = (".git", "sdb-capability-approval-replay")
        if path.is_absolute() or path.parts[:-1] != expected_parent or not path.name:
            raise fail("secure_path_invalid", "only the internal replay directory is allowed")
        relative = path.as_posix()
    else:
        relative = safe_relative(relative, "secure write")
    relative_path = PurePosixPath(relative)
    filename = relative_path.name
    if not filename:
        raise fail("secure_path_invalid", "secure write requires a file name")
    parent = relative_path.parent.as_posix()
    if parent == ".":
        parent = ""
    parent_fd = open_directory_nofollow(repo, parent, create=True)
    temporary = f".{filename}.{os.getpid()}.{os.urandom(8).hex()}.tmp"
    created = False
    try:
        fd = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
            0o600,
            dir_fd=parent_fd,
        )
        created = True
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
            os.fchmod(handle.fileno(), 0o400)
        if exclusive:
            os.link(
                temporary,
                filename,
                src_dir_fd=parent_fd,
                dst_dir_fd=parent_fd,
                follow_symlinks=False,
            )
        else:
            os.replace(temporary, filename, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
            created = False
        os.fsync(parent_fd)
    except FileExistsError as exc:
        raise fail("approval_replayed", relative) from exc
    except OSError as exc:
        code = "secure_path_symlink" if exc.errno in {20, 40} else "secure_write_failed"
        raise fail(code, f"{relative}: {exc}") from exc
    finally:
        if created:
            try:
                os.unlink(temporary, dir_fd=parent_fd)
            except FileNotFoundError:
                pass
        os.close(parent_fd)


def consume_approval(approval: ApprovalRecord, replay_root: Path) -> None:
    replay_root = replay_root.absolute()
    internal_git = False
    if replay_root.name == "sdb-capability-approval-replay" and replay_root.parent.name == ".git":
        repo = replay_root.parents[1]
        relative_root = ".git/sdb-capability-approval-replay"
        internal_git = True
    elif replay_root.name != "approval-replay":
        raise fail("secure_path_invalid", "replay root must be a dedicated approval-replay directory")
    elif replay_root.parent.name == "capability" and replay_root.parent.parent.name == "runs":
        repo = replay_root.parents[2]
        relative_root = "runs/capability/approval-replay"
    elif replay_root.parent.name == "runs":
        repo = replay_root.parents[1]
        relative_root = "runs/approval-replay"
    else:
        raise fail("secure_path_invalid", "replay root must be below repo/runs")
    marker = sha256(f"{approval.approval_ref}\0{approval.nonce}".encode()) + ".json"
    payload = canonical_bytes({
        "approval_ref": approval.approval_ref,
        "nonce_sha256": sha256(approval.nonce.encode()),
        "task_digest": approval.task_digest,
    }) + b"\n"
    secure_write(
        repo,
        f"{relative_root}/{marker}",
        payload,
        exclusive=True,
        _allow_internal_git=internal_git,
    )


def protected_paths(repo: Path) -> tuple[str, ...]:
    names = {name for name in _PROTECTED_EXACT if (repo / name).is_file() or (repo / name).is_symlink()}
    scripts = repo / "scripts"
    if scripts.is_dir():
        for path in scripts.iterdir():
            relative = path.relative_to(repo).as_posix()
            if relative.startswith("scripts/sdb_capability") and path.is_file():
                names.add(relative)
    return tuple(sorted(names))


def capture_revision_binding(repo: Path) -> RevisionBinding:
    head = git(repo, "rev-parse", "HEAD").stdout.strip()
    files: dict[str, FileBinding] = {}
    for relative in protected_paths(repo):
        path = repo / relative
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
            raise fail("revision_binding_invalid", relative)
        tracked, dirty, _ = file_state(repo, relative)
        files[relative] = FileBinding(sha256_file(path), tracked, dirty)
    return RevisionBinding(head, MappingProxyType(files))
