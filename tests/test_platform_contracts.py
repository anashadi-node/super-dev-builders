"""Kontrak produk (`platform/schemas`) — validasi contoh + negatif.

Kenapa ada: audit 2026-10-26 menemukan produk SaaS belum punya kontrak data. Skema yang tidak
diuji hanyalah dokumentasi; tes ini memastikan `budget`, `idempotency_key`, `redaction_status`,
dan `limits` benar-benar wajib — field-field itulah yang mencegah biaya tak terbatas, job ganda,
dan publikasi artefak yang belum diredaksi.
"""
import json
import os
import re

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEMAS = os.path.join(REPO, "platform", "schemas")
EXAMPLES = os.path.join(SCHEMAS, "examples")

PAIRS = [
    ("tenant.schema.json", "tenant.example.json"),
    ("job.schema.json", "job.example.json"),
    ("artifact.schema.json", "artifact.example.json"),
]

_TYPES = {
    "object": dict,
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
    "array": list,
}


def _validate(node, data, path="$"):
    """Validator JSON Schema subset (stdlib). Cukup untuk kontrak kita; bukan implementasi penuh."""
    errors = []
    if "type" in node:
        want = node["type"]
        py = _TYPES.get(want)
        if (py and not isinstance(data, py)) or (want == "integer" and isinstance(data, bool)):
            return [f"{path}: harus {want}, dapat {type(data).__name__}"]
    if "enum" in node and data not in node["enum"]:
        errors.append(f"{path}: {data!r} tidak ada di enum {node['enum']}")
    if isinstance(data, str):
        if "pattern" in node and not re.search(node["pattern"], data):
            errors.append(f"{path}: {data!r} tidak cocok pola {node['pattern']}")
        if "minLength" in node and len(data) < node["minLength"]:
            errors.append(f"{path}: terlalu pendek")
        if "maxLength" in node and len(data) > node["maxLength"]:
            errors.append(f"{path}: terlalu panjang")
    if isinstance(data, int) and not isinstance(data, bool):
        if "minimum" in node and data < node["minimum"]:
            errors.append(f"{path}: {data} < minimum {node['minimum']}")
        if "maximum" in node and data > node["maximum"]:
            errors.append(f"{path}: {data} > maximum {node['maximum']}")
    if isinstance(data, dict):
        for req in node.get("required", []):
            if req not in data:
                errors.append(f"{path}: field wajib hilang: {req}")
        props = node.get("properties", {})
        if node.get("additionalProperties") is False:
            extra = set(data) - set(props)
            if extra:
                errors.append(f"{path}: field tak dikenal: {sorted(extra)}")
        for key, sub in props.items():
            if key in data:
                errors.extend(_validate(sub, data[key], f"{path}.{key}"))
    return errors


def _load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


@pytest.mark.parametrize("schema_file,example_file", PAIRS)
def test_example_matches_schema(schema_file, example_file):
    schema = _load(os.path.join(SCHEMAS, schema_file))
    example = _load(os.path.join(EXAMPLES, example_file))
    assert _validate(schema, example) == []


@pytest.mark.parametrize("schema_file,_", PAIRS)
def test_schema_is_draft_2020_12(schema_file, _):
    schema = _load(os.path.join(SCHEMAS, schema_file))
    assert schema["$schema"].endswith("2020-12/schema")
    assert schema["$id"].startswith("https://schemas.sdb.dev/")
    assert schema.get("additionalProperties") is False, "kontrak harus menolak field tak dikenal"


def test_tenant_requires_limits_and_isolation():
    schema = _load(os.path.join(SCHEMAS, "tenant.schema.json"))
    example = _load(os.path.join(EXAMPLES, "tenant.example.json"))
    for field in ("limits", "isolation"):
        broken = {k: v for k, v in example.items() if k != field}
        assert any(field in e for e in _validate(schema, broken)), f"{field} seharusnya wajib"


def test_job_requires_budget_and_idempotency():
    schema = _load(os.path.join(SCHEMAS, "job.schema.json"))
    example = _load(os.path.join(EXAMPLES, "job.example.json"))
    for field in ("budget", "idempotency_key"):
        broken = {k: v for k, v in example.items() if k != field}
        assert any(field in e for e in _validate(schema, broken)), f"{field} seharusnya wajib"
    # budget di luar batas harus ditolak (pagar biaya)
    over = json.loads(json.dumps(example))
    over["budget"]["tokens"] = 5_000_000
    assert _validate(schema, over), "budget.token melebihi plafon harus ditolak"


def test_artifact_requires_redaction_and_hash():
    schema = _load(os.path.join(SCHEMAS, "artifact.schema.json"))
    example = _load(os.path.join(EXAMPLES, "artifact.example.json"))
    # hash salah
    bad = dict(example, sha256="zz")
    assert _validate(schema, bad)
    # artefak tanpa status redaksi tidak boleh lolos
    no_red = {k: v for k, v in example.items() if k != "redaction_status"}
    assert any("redaction_status" in e for e in _validate(schema, no_red))
    # uri harus menunjuk object store, bukan path lokal
    local = dict(example, uri="/home/anashadi/evidence/x.json")
    assert _validate(schema, local)


def test_ids_use_ulid_prefix_not_sequential():
    for name in ("tenant", "job", "artifact"):
        example = _load(os.path.join(EXAMPLES, f"{name}.example.json"))
        key = {"tenant": "tenant_id", "job": "job_id", "artifact": "artifact_id"}[name]
        assert re.match(r"^[tja]_[0-9A-HJKMNP-TV-Z]{26}$", example[key]), example[key]
