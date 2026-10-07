#!/usr/bin/python3
"""Buat workspace target + salin template manifest.

Pemakaian: /usr/bin/python3 scripts/init_target.py <slug> [--platform web] [--mode A]
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sdb_common import now_iso, repo_path, validate_slug, write_json

SUBDIRS = ["raw", "screens", "dom", "trace", "assets", "notes"]
# Workdir run (16 tahap, lihat scripts/workflow_run.py STAGES) + root implementasi.
# Tanpa ini, `sdb workflow <slug>` menolak target yang baru saja di-`sdb init`.
RUN_SUBDIRS = ["docs", "logs", "reports"]
TARGET_SUBDIRS = ["src"]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Init target workspace (Gate #0 ready)")
    ap.add_argument("slug")
    ap.add_argument("--platform", default="web")
    ap.add_argument("--mode", default="A", choices=["A", "B"])
    ap.add_argument("--force", action="store_true", help="timpa manifest bila sudah ada")
    args = ap.parse_args(argv)

    try:
        validate_slug(args.slug)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    slug = args.slug.strip().lower()
    if not slug or " " in slug:
        print("slug harus lowercase tanpa spasi", file=sys.stderr)
        return 2

    paths = {
        "evidence": repo_path("evidence", slug),
        "normalized": repo_path("normalized", slug),
        "reconstruction": repo_path("reconstruction", slug),
        "verification": repo_path("verification", slug),
        "reports": repo_path("reports", slug),
        "run": repo_path("runs", slug),
        "target": repo_path("targets", slug),
    }
    for p in paths.values():
        os.makedirs(p, exist_ok=True)
    for sub in SUBDIRS:
        os.makedirs(os.path.join(paths["evidence"], sub), exist_ok=True)
    for sub in RUN_SUBDIRS:
        os.makedirs(os.path.join(paths["run"], sub), exist_ok=True)
    for sub in TARGET_SUBDIRS:
        os.makedirs(os.path.join(paths["target"], sub), exist_ok=True)

    manifest_dst = os.path.join(paths["evidence"], "authorization.yaml")
    platform_path = os.path.join(paths["evidence"], "target_manifest.yaml")
    if not os.path.exists(manifest_dst) or args.force:
        shutil.copyfile(repo_path("templates", "authorization_manifest.yaml"), manifest_dst)
        print(f"manifest dibuat: {manifest_dst}")
    else:
        print(f"manifest sudah ada (dilewati): {manifest_dst}")
    if not os.path.exists(platform_path) or args.force:
        shutil.copyfile(repo_path("templates", "target_manifest.yaml"), platform_path)

    write_json(os.path.join(paths["evidence"], "workspace.json"), {
        "target": slug,
        "platform": args.platform,
        "mode": args.mode,
        "created_at": now_iso(),
        "paths": paths,
        "next_step": f"isi authorization.yaml lalu jalankan scripts/gate_check.py {slug}",
    })
    print(f"workspace siap: {paths['evidence']}")
    print(f"NEXT: isi authorization.yaml -> /usr/bin/python3 scripts/gate_check.py {slug}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
