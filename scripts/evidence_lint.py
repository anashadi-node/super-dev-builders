#!/usr/bin/python3
"""Validasi evidence ternormalisasi (docs/EVIDENCE_SCHEMA.md + taxonomy).

Pemakaian: /usr/bin/python3 scripts/evidence_lint.py normalized/<target> [--json out.json]
Exit: 0 bersih, 1 ada error.
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sdb_common import iter_relative_files, now_iso, read_json, scan_for_secrets, write_json  # noqa: E402

REQUIRED_META = ["provenance", "captured_at", "redaction_status", "status"]
VALID_STATUS = {"FACT", "OBSERVED", "INFERRED", "UNKNOWN", "OUT_OF_SCOPE"}
SPECULATIVE_KEYS = {"guess", "tbd", "assumption", "maybe"}


def lint_record(rec, where, errors, warnings):
    if not isinstance(rec, dict):
        warnings.append(f"{where}: record bukan objek (mungkin ringkasan file)")
        return
    for key in REQUIRED_META:
        if key not in rec:
            errors.append(f"{where}: metadata wajib hilang: {key}")
    status = str(rec.get("status", "")).upper()
    if status and status not in VALID_STATUS:
        errors.append(f"{where}: status tidak dikenal: {status}")
    if status == "INFERRED":
        conf = rec.get("confidence")
        if not isinstance(conf, (int, float)):
            errors.append(f"{where}: status INFERRED wajib confidence numerik (0-100)")
        elif not 0 <= float(conf) <= 100:
            errors.append(f"{where}: confidence di luar 0-100: {conf}")
    if status == "UNKNOWN":
        for k in list(rec.keys()):
            if k.lower() in SPECULATIVE_KEYS and rec[k]:
                errors.append(f"{where}: UNKNOWN tidak boleh berisi dugaan pada '{k}'")
    red = str(rec.get("redaction_status", ""))
    if red and red not in ("clean", "redacted", "blocked"):
        warnings.append(f"{where}: redaction_status tak lazim: {red}")
    for path in scan_for_secrets(rec):
        errors.append(f"{where}: kemungkinan rahasia belum diredaksi di {path}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Lint normalized evidence")
    ap.add_argument("path", help="folder normalized/<target> atau file .json")
    ap.add_argument("--json", dest="json_out", help="tulis ringkasan ke file")
    args = ap.parse_args(argv)

    errors, warnings, files_checked, records = [], [], 0, 0
    targets = [args.path] if os.path.isfile(args.path) else list(iter_relative_files(args.path))
    for path in targets:
        data = read_json(path)
        if data is None:
            errors.append(f"{path}: bukan JSON valid / kosong")
            continue
        files_checked += 1
        items = data if isinstance(data, list) else (data.get("items") if isinstance(data, dict) else [])
        if not isinstance(items, list):
            items = [data]
        for idx, rec in enumerate(items):
            records += 1
            lint_record(rec, f"{os.path.basename(path)}[{idx}]", errors, warnings)

    summary = {
        "checked_at": now_iso(),
        "path": args.path,
        "files_checked": files_checked,
        "records": records,
        "errors": errors,
        "warnings": warnings,
        "verdict": "PASS" if not errors else "FAIL",
    }
    if args.json_out:
        write_json(args.json_out, summary)
    print(f"evidence_lint: {summary['verdict']} ({files_checked} file, {records} record)")
    for e in errors[:40]:
        print(f"  ERROR: {e}")
    for w in warnings[:20]:
        print(f"  WARN: {w}")
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
