#!/usr/bin/python3
"""Release Gate (tahap 12) — tolak PASS bila artefak evidence tidak ada/kedaluwarsa.

Pemakaian: /usr/bin/python3 scripts/release_check.py <slug> [--max-age-hours 24]
           (bentuk lama `--project <dir>` tetap didukung)
Exit: 0 PASS, 1 FAIL, 2 BLOCKED/argumen tak sah.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sdb_common import load_yaml, now_iso, repo_path, validate_slug, write_json


def newest(pattern: str):
    hits = [p for p in glob.glob(pattern, recursive=True) if os.path.isfile(p)]
    if not hits:
        return None
    best = max(hits, key=os.path.getmtime)
    return best


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Release gate evidence check")
    ap.add_argument("target_pos", nargs="?", help="slug target (alias --project runs/<slug>)")
    ap.add_argument("--project", default=None, help="root proyek yang dirilis")
    ap.add_argument("--target", default=None, help="slug target (sama dengan bentuk posisional)")
    ap.add_argument("--max-age-hours", type=float, default=None)
    ap.add_argument("--config", default=None, help="default: workflows/release-gate.yaml")
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)

    # Resolusi: slug posisional / --target / --project. Slug fail-closed (CWE-22).
    slug = args.target or args.target_pos
    if slug and not args.project:
        try:
            validate_slug(slug)
        except ValueError as e:
            print(f"FATAL: {e}", file=sys.stderr)
            return 2
        args.project = repo_path("runs", slug)
    if not args.project:
        args.project = "."

    cfg_path = args.config or repo_path("workflows", "release-gate.yaml")
    cfg = load_yaml(cfg_path) or {}
    required = cfg.get("required_artifacts") or {}
    max_age = args.max_age_hours if args.max_age_hours is not None else float(cfg.get("max_artifact_age_hours", 24))
    project = os.path.abspath(args.project)

    # Run investigasi DID menyimpan did/handoff.json, bukan artefak rilis. Tanpa
    # penjagaan ini, `make release-check` pada run DID mencetak tujuh baris
    # "artefak tidak ditemukan" yang menyesatkan (terlihat seperti rilis rusak).
    if os.path.isfile(os.path.join(project, "did", "handoff.json")):
        hit = False
        for patterns in required.values():
            for pattern in ([patterns] if isinstance(patterns, str) else patterns or []):
                if newest(os.path.join(project, pattern)):
                    hit = True
                    break
            if hit:
                break
        if not hit:
            print(f"FATAL: {os.path.basename(project)} adalah run investigasi DID "
                  "(ada did/handoff.json, tanpa artefak rilis).", file=sys.stderr)
            print("       Pakai TARGET=<slug run rilis>, atau jalankan: make did TARGET=<slug>", file=sys.stderr)
            return 2

    failures, satisfied = [], []
    for gate, patterns in required.items():
        found = None
        if isinstance(patterns, str):
            patterns = [patterns]
        for pattern in patterns or []:
            found = newest(os.path.join(project, pattern)) or newest(os.path.join(repo_path("."), pattern))
            if found:
                break
        if not found:
            failures.append({"gate": gate, "reason": "artefak tidak ditemukan", "patterns": patterns})
            continue
        age_h = (time.time() - os.path.getmtime(found)) / 3600.0
        if age_h > max_age:
            failures.append({"gate": gate, "reason": f"artefak kedaluwarsa ({age_h:.1f} jam > {max_age} jam)",
                             "path": found})
        else:
            satisfied.append({"gate": gate, "path": found, "age_hours": round(age_h, 2)})

    # A fresh decision artifact can still say FAIL. Treat verdict content as a
    # machine contract; never infer it from prose or existence alone.
    for gate, spec in (cfg.get("required_verdicts") or {}).items():
        patterns = spec.get("patterns", [])
        if isinstance(patterns, str):
            patterns = [patterns]
        found = None
        for pattern in patterns:
            found = newest(os.path.join(project, pattern))
            if found:
                break
        if not found:
            failures.append({"gate": gate, "reason": "artefak verdict tidak ditemukan", "patterns": patterns})
            continue
        age_h = (time.time() - os.path.getmtime(found)) / 3600.0
        if age_h > max_age:
            failures.append({"gate": gate, "reason": f"verdict kedaluwarsa ({age_h:.1f} jam > {max_age} jam)", "path": found})
            continue
        try:
            with open(found, encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            failures.append({"gate": gate, "reason": f"JSON tidak sah: {exc}", "path": found})
            continue
        field = spec.get("field", "verdict")
        allowed = spec.get("allowed", ["PASS"])
        value = payload.get(field) if isinstance(payload, dict) else None
        if value not in allowed:
            failures.append({"gate": gate, "reason": f"{field}={value!r}, wajib salah satu {allowed}", "path": found})
            continue
        satisfied.append({"gate": gate, "path": found, "age_hours": round(age_h, 2), field: value})

    verdict = "PASS" if not failures else "FAIL"
    result = {"gate": "release", "verdict": verdict, "checked_at": now_iso(), "project": project,
              "max_age_hours": max_age, "satisfied": satisfied, "failures": failures}
    out = args.out or os.path.join(project, "reports", "release-verdict.json")
    write_json(out, result)

    print(f"release gate: {verdict}  ({out})")
    for item in satisfied:
        print(f"  OK   {item['gate']:<12} {item['path']} (umur {item['age_hours']}j)")
    for item in failures:
        print(f"  FAIL {item['gate']:<12} {item['reason']}")
    print("  catatan: LLM statement bukan bukti — hanya artefak fresh yang dihitung")
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
