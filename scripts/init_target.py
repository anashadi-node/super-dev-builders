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
from sdb_common import now_iso, repo_path, write_json  # noqa: E402

SUBDIRS = ["raw", "screens", "dom", "trace", "assets", "notes"]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Init target workspace (Gate #0 ready)")
    ap.add_argument("slug")
    ap.add_argument("--platform", default="web")
    ap.add_argument("--mode", default="A", choices=["A", "B"])
    ap.add_argument("--force", action="store_true", help="timpa manifest bila sudah ada")
    args = ap.parse_args(argv)

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
    }
    for p in paths.values():
        os.makedirs(p, exist_ok=True)
    for sub in SUBDIRS:
        os.makedirs(os.path.join(paths["evidence"], sub), exist_ok=True)

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
        "next_step": "isi authorization.yaml lalu jalankan scripts/gate_check.py --target " + slug,
    })
    print(f"workspace siap: {paths['evidence']}")
    print(f"NEXT: isi authorization.yaml -> /usr/bin/python3 scripts/gate_check.py --target {slug}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
