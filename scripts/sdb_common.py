#!/usr/bin/python3
"""Shared helpers untuk scripts Super Dev Builders Ecosystem.

Stdlib-only. PyYAML dipakai bila tersedia; jika tidak, ada parser YAML-subset
internal (scripts/sdb_common.py:load_yaml) yang tervalidasi test terhadap PyYAML.

Jalankan script dengan /usr/bin/python3 (punya PyYAML) bila memungkinkan.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import re
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERMES_HOME = os.environ.get("HERMES_HOME") or os.path.expanduser("~/.hermes")
PROFILES_DIR = os.path.join(HERMES_HOME, "profiles")
SKILLS_DIR = os.path.join(HERMES_HOME, "skills")
SKILL_NAMESPACE = "super-dev-builders"

ISO = "%Y-%m-%dT%H:%M:%S%z"


def now_iso() -> str:
    return _dt.datetime.now().astimezone().strftime(ISO)


def repo_path(*parts: str) -> str:
    return os.path.join(REPO_ROOT, *parts)


# ---------------------------------------------------------------- YAML subset
def _strip_comment(line: str) -> str:
    out, quote = [], None
    for ch in line:
        if quote:
            out.append(ch)
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
            out.append(ch)
        elif ch == "#":
            break
        else:
            out.append(ch)
    return "".join(out).rstrip()


def _split_flow(text: str):
    parts, buf, depth, quote = [], [], 0, None
    for ch in text:
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = None
            continue
        if ch in "\"'":
            quote = ch
            buf.append(ch)
        elif ch in "[{":
            depth += 1
            buf.append(ch)
        elif ch in "]}":
            depth -= 1
            buf.append(ch)
        elif ch == "," and depth == 0:
            parts.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
    if "".join(buf).strip():
        parts.append("".join(buf).strip())
    return [p for p in parts if p != ""]


_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ISO_DATETIME = re.compile(
    r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:?\d{2})?$"
)


def _maybe_temporal(s: str):
    """Tiru perilaku PyYAML: '2026-10-04' -> date, ISO timestamp -> datetime."""
    try:
        if _ISO_DATE.match(s):
            return _dt.date.fromisoformat(s)
        if _ISO_DATETIME.match(s):
            return _dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    return None


def _scalar(text: str):
    s = text.strip()
    if s == "" or s in ("~", "null", "None", "NULL"):
        return None
    temporal = _maybe_temporal(s)
    if temporal is not None:
        return temporal
    if s in ("true", "True", "yes", "on"):
        return True
    if s in ("false", "False", "no", "off"):
        return False
    if s.startswith("[") and s.endswith("]"):
        return [_scalar(x) for x in _split_flow(s[1:-1])]
    if s.startswith("{") and s.endswith("}"):
        out = {}
        for part in _split_flow(s[1:-1]):
            k, _, v = part.partition(":")
            out[k.strip()] = _scalar(v)
        return out
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'":
        return s[1:-1]
    for cast in (int, float):
        try:
            return cast(s)
        except (TypeError, ValueError):
            pass
    return s


def _indent_of(line: str) -> int:
    return len(line) - len(line.lstrip())


def _balanced(text: str) -> bool:
    """True bila bracket/quote pada nilai flow sudah tertutup (untuk gabung baris lanjutan)."""
    depth, quote = 0, None
    for ch in text:
        if quote:
            if ch == quote:
                quote = None
            continue
        if ch in "\"'":
            quote = ch
        elif ch in "[{":
            depth += 1
        elif ch in "]}":
            depth -= 1
    return depth <= 0 and quote is None


def _parse_block(lines, i, indent):
    """Parse mapping atau sequence pada indent tertentu. Return (obj, next_index)."""
    if i >= len(lines):
        return None, i
    if lines[i].lstrip().startswith("- "):
        items = []
        while i < len(lines):
            raw = lines[i]
            if _indent_of(raw) < indent or not raw.lstrip().startswith("- "):
                break
            content = raw.lstrip()[2:]
            head, _, tail = content.partition(":")
            if tail and not content.startswith(("[", "{")) and not re.match(r'^["\']', content):
                while not _balanced(tail) and i + 1 < len(lines):
                    i += 1
                    tail = tail + " " + lines[i].strip()
                item = {head.strip(): _scalar(tail)}
                i += 1
                if i < len(lines) and _indent_of(lines[i]) > indent:
                    sub, i = _parse_block(lines, i, indent + 2)
                    if isinstance(sub, dict):
                        item.update(sub)
                    elif sub is not None:
                        item["_extra"] = sub
                items.append(item)
            else:
                items.append(_scalar(content))
                i += 1
        return items, i
    mapping = {}
    while i < len(lines):
        raw = lines[i]
        if _indent_of(raw) != indent:
            break
        key, sep, value = raw.strip().partition(":")
        if not sep:
            break
        key, value = key.strip(), value.strip()
        if value == "":
            if i + 1 < len(lines) and _indent_of(lines[i + 1]) > indent:
                sub, i = _parse_block(lines, i + 1, _indent_of(lines[i + 1]))
                mapping[key] = sub
            else:
                mapping[key] = None
                i += 1
        else:
            while not _balanced(value) and i + 1 < len(lines):
                i += 1
                value = value + " " + lines[i].strip()
            mapping[key] = _scalar(value)
            i += 1
    return mapping, i


def fallback_yaml_load(text: str):
    """Parser YAML-subset (mapping/sequence/scalar/inline). Bukan YAML penuh."""
    lines = []
    for raw in text.splitlines():
        if not raw.strip() or raw.strip().startswith("#"):
            continue
        cleaned = _strip_comment(raw)
        if not cleaned.strip():
            continue
        lines.append(cleaned.replace("\t", "    "))
    obj, _ = _parse_block(lines, 0, _indent_of(lines[0]) if lines else 0)
    return obj


def load_yaml(path: str):
    with open(path, "r", encoding="utf-8") as fh:
        text = fh.read()
    try:
        import yaml  # type: ignore

        return yaml.safe_load(text)
    except ModuleNotFoundError:
        return fallback_yaml_load(text)
    except Exception as exc:
        raise RuntimeError(f"YAML invalid: {path}: {exc}") from exc


def yaml_backend() -> str:
    try:
        import yaml  # type: ignore  # noqa: F401

        return "PyYAML"
    except ModuleNotFoundError:
        return "fallback-parser"


# ------------------------------------------------------------------- JSON I/O
def read_json(path: str, default=None):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def write_json(path: str, obj) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2, ensure_ascii=False)
        fh.write("\n")


# ------------------------------------------------------------------ redaction
SECRET_KEY_PATTERN = re.compile(
    r"(authorization|cookie|set-cookie|x-api-key|api[-_]?key|access[-_]?token|refresh[-_]?token|"
    r"secret|password|passwd|session|bearer|private[-_]?key)",
    re.IGNORECASE,
)
SECRET_VALUE_PATTERN = re.compile(
    r"(bearer\s+[A-Za-z0-9._\-]+|eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}|"
    r"AKIA[0-9A-Z]{16}|sk-[A-Za-z0-9]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|"
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----)",
    # Tanpa IGNORECASE, header "Authorization: Bearer ..." (huruf B kapital, bentuk
    # yang sebenarnya dikirim browser) TIDAK ketahuan — ditemukan lewat test canary
    # 2026-10-07. Aturan #3 repo: tidak ada credential yang boleh lolos ke evidence.
    re.IGNORECASE,
)
PII_PATTERNS = [
    re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}"),
    re.compile(r"\b\d{13,19}\b"),
    re.compile(r"\+?\d{9,15}\b(?=[^\d]|$)"),
]
REDACTED = "[REDACTED]"


def redact_obj(obj, key_hits=None, value_hits=None):
    """Return salinan obj dengan nilai sensitif diganti [REDACTED]."""
    key_hits = key_hits if key_hits is not None else []
    value_hits = value_hits if value_hits is not None else []
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if SECRET_KEY_PATTERN.search(str(k)):
                key_hits.append(str(k))
                out[k] = REDACTED
            else:
                out[k] = redact_obj(v, key_hits, value_hits)
        return out
    if isinstance(obj, list):
        return [redact_obj(v, key_hits, value_hits) for v in obj]
    if isinstance(obj, str):
        s = obj
        if SECRET_VALUE_PATTERN.search(s):
            value_hits.append("secret-value")
            return REDACTED
        for pat in PII_PATTERNS:
            if pat.search(s):
                value_hits.append("pii")
                s = pat.sub(REDACTED, s)
        return s
    return obj


def scan_for_secrets(obj, path="$"):
    """Yield lokasi yang masih mengandung pola rahasia (untuk lint)."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if SECRET_KEY_PATTERN.search(str(k)) and not (isinstance(v, str) and v == REDACTED):
                yield f"{path}.{k}"
            yield from scan_for_secrets(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for idx, v in enumerate(obj):
            yield from scan_for_secrets(v, f"{path}[{idx}]")
    elif isinstance(obj, str):
        if SECRET_VALUE_PATTERN.search(obj):
            yield path


def iter_relative_files(root: str, suffix: str = ".json"):
    for base, _dirs, files in os.walk(root):
        for name in sorted(files):
            if name.endswith(suffix):
                yield os.path.join(base, name)


def print_backend() -> None:
    print(f"[sdb] YAML backend: {yaml_backend()} | python: {sys.version.split()[0]}")
