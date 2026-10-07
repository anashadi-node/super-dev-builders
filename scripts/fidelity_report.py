#!/usr/bin/python3
"""Agregasi Reconstruction Fidelity per dimensi + coverage -> markdown.

Input: verification/<target>/fidelity.json
  [{"dimension":"visual","status":"ok","coverage":0.9,"evidence":"verification/x/visual/diff.png","note":""}]

Pemakaian: /usr/bin/python3 scripts/fidelity_report.py --target <slug> [--json in.json] [--out report.md]
Exit: 0 selalu (laporan), 2 bila input tidak ada.
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sdb_common import now_iso, read_json, repo_path, validate_slug

DIMENSIONS = ["visual", "navigation", "interaction", "responsive", "functional",
              "accessibility", "performance", "api_contract"]
LOW_COVERAGE = 0.5


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Build fidelity report")
    ap.add_argument("--target", required=True)
    ap.add_argument("--json", dest="json_in")
    ap.add_argument("--out", dest="out_md")
    args = ap.parse_args(argv)

    try:
        validate_slug(args.target)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    src = args.json_in or repo_path("verification", args.target, "fidelity.json")
    if not os.path.exists(src):
        print(f"input tidak ada: {src}", file=sys.stderr)
        print("format: [{'dimension','status','coverage','evidence','note'}]", file=sys.stderr)
        return 2
    rows = read_json(src) or []
    by_dim = {str(r.get("dimension")): r for r in rows if isinstance(r, dict)}

    lines = [f"# Reconstruction Fidelity — {args.target}", "", f"Dibuat: {now_iso()}", "",
             "Tidak ada skor tunggal. Skor tinggi dengan coverage rendah = laporan menyesatkan.", "",
             "| Dimensi | Status | Coverage | Evidence | Catatan |", "|---|---|---|---|---|"]
    warnings = []
    for dim in DIMENSIONS:
        rec = by_dim.get(dim)
        if not rec:
            lines.append(f"| {dim} | NOT_MEASURED | - | - | belum diukur |")
            warnings.append(f"dimensi {dim} belum diukur")
            continue
        cov = rec.get("coverage")
        cov_txt = f"{float(cov):.2f}" if isinstance(cov, (int, float)) else "-"
        if isinstance(cov, (int, float)) and cov < LOW_COVERAGE:
            warnings.append(f"dimensi {dim}: coverage rendah ({cov_txt})")
        lines.append(f"| {dim} | {rec.get('status','?')} | {cov_txt} | {rec.get('evidence','-')} | {rec.get('note','')} |")
    extra = [d for d in by_dim if d not in DIMENSIONS]
    if extra:
        lines.append("")
        lines.append(f"Dimensi tambahan: {', '.join(sorted(extra))}")
    if warnings:
        lines += ["", "## Peringatan"] + [f"- {w}" for w in warnings]
    lines += ["", "## Aturan pelaporan",
              "- Wajib menyertakan coverage; tanpa coverage laporan tidak diterima.",
              "- Perbedaan yang disengaja (lisensi aset, keputusan desain) dicatat sebagai intentionally_changed.",
              "- Dilarang mengklaim 'identik'."]
    out_md = args.out_md or repo_path("reports", args.target, "fidelity-report.md")
    os.makedirs(os.path.dirname(out_md), exist_ok=True)
    with open(out_md, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print(f"fidelity report: {out_md}")
    for w in warnings:
        print(f"  WARN: {w}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
