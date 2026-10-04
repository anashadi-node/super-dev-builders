#!/usr/bin/python3
"""Release Gate (tahap 12) — tolak PASS bila artefak evidence tidak ada/kedaluwarsa.

Pemakaian: /usr/bin/python3 scripts/release_check.py --project <dir> [--max-age-hours 24]
Exit: 0 PASS, 1 FAIL.
"""
from __future__ import annotations

import argparse
import glob
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sdb_common import load_yaml, now_iso, repo_path, write_json


def newest(pattern: str):
    hits = [p for p in glob.glob(pattern, recursive=True) if os.path.isfile(p)]
    if not hits:
        return None
    best = max(hits, key=os.path.getmtime)
    return best


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Release gate evidence check")
    ap.add_argument("--project", default=".", help="root proyek yang dirilis")
    ap.add_argument("--max-age-hours", type=float, default=None)
    ap.add_argument("--config", default=None, help="default: workflows/release-gate.yaml")
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)

    cfg_path = args.config or repo_path("workflows", "release-gate.yaml")
    cfg = load_yaml(cfg_path) or {}
    required = cfg.get("required_artifacts") or {}
    max_age = args.max_age_hours if args.max_age_hours is not None else float(cfg.get("max_artifact_age_hours", 24))
    project = os.path.abspath(args.project)

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
