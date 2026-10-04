#!/usr/bin/python3
"""Snapshot inventaris ekosistem (untuk upgrade report: before/after).

Pemakaian:
    /usr/bin/python3 scripts/inventory_ecosystem.py --out reports/inventory_after.json
    /usr/bin/python3 scripts/inventory_ecosystem.py --legacy ~/copy-cloning-super-dev-builders --out reports/inventory_before.json

Catatan privasi: hanya membaca nama/struktur, TIDAK pernah menyalin nilai rahasia.
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sdb_common import HERMES_HOME, PROFILES_DIR, load_yaml, now_iso, repo_path, write_json

TOOLS = ["git", "node", "npm", "python3", "docker", "jq", "playwright", "pytest", "uv",
         "semgrep", "codeql", "trivy", "syft", "ruff", "gh", "adb", "nmap", "jadx", "apktool"]


def count_skills(path):
    n = 0
    for _base, _dirs, files in os.walk(path):
        n += sum(1 for f in files if f == "SKILL.md")
    return n


def profile_info():
    out = {}
    if not os.path.isdir(PROFILES_DIR):
        return out
    for name in sorted(os.listdir(PROFILES_DIR)):
        d = os.path.join(PROFILES_DIR, name)
        if not os.path.isdir(d):
            continue
        entry = {"skills": count_skills(os.path.join(d, "skills")) if os.path.isdir(os.path.join(d, "skills")) else 0,
                 "soul_md": os.path.exists(os.path.join(d, "SOUL.md")),
                 "memories": len(os.listdir(os.path.join(d, "memories"))) if os.path.isdir(os.path.join(d, "memories")) else 0}
        py = os.path.join(d, "profile.yaml")
        if os.path.exists(py):
            try:
                data = load_yaml(py) or {}
                entry["description"] = (data.get("description") or "")[:160]
            except Exception:
                entry["description"] = "<unreadable>"
        out[name] = entry
    return out


def cron_summary():
    path = os.path.join(HERMES_HOME, "cron", "jobs.json")
    if not os.path.exists(path):
        return {"present": False}
    try:
        import json
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception:
        return {"present": True, "error": "unreadable"}
    jobs = data if isinstance(data, list) else data.get("jobs", [])
    return {"present": True, "jobs": len(jobs) if hasattr(jobs, "__len__") else None}


def config_summary():
    """Ringkasan non-sensitif: hanya kunci struktur, bukan nilai."""
    path = os.path.join(HERMES_HOME, "config.yaml")
    if not os.path.exists(path):
        return {"present": False}
    try:
        data = load_yaml(path) or {}
    except Exception:
        return {"present": True, "parsed": False}
    top = sorted(data.keys()) if isinstance(data, dict) else []
    models = data.get("models") if isinstance(data, dict) else None
    summary = {"present": True, "parsed": True, "top_level_keys": top}
    if isinstance(models, dict):
        summary["model_roles"] = sorted(models.keys())
    mcp = data.get("mcp") or data.get("mcp_servers")
    if isinstance(mcp, dict):
        summary["mcp_servers"] = sorted(mcp.keys())
        summary["mcp_count"] = len(mcp)
    return summary


def legacy_summary(path):
    if not path or not os.path.isdir(path):
        return {"present": False}
    files = []
    for base, _dirs, names in os.walk(path):
        for n in names:
            rel = os.path.relpath(os.path.join(base, n), path)
            if rel.startswith(".git/"):
                continue
            files.append(rel)
    return {"present": True, "path": path, "file_count": len(files), "files": sorted(files)[:200]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Inventory ekosistem")
    ap.add_argument("--out", default=None)
    ap.add_argument("--legacy", default=None, help="repo V1 untuk inventaris 'before'")
    args = ap.parse_args(argv)

    snapshot = {
        "captured_at": now_iso(),
        "repo": REPO_PATH_IF_ANY(),
        "repo_files": count_repo_files(),
        "custom_skills": count_skills(repo_path("skills")),
        "profiles": profile_info(),
        "tools": {t: bool(shutil.which(t)) for t in TOOLS},
        "cron": cron_summary(),
        "config": config_summary(),
        "plugins": sorted(os.listdir(os.path.join(HERMES_HOME, "plugins")))
        if os.path.isdir(os.path.join(HERMES_HOME, "plugins")) else [],
    }
    if args.legacy:
        snapshot["legacy"] = legacy_summary(args.legacy)
    out = args.out or repo_path("reports", "inventory_after.json")
    write_json(out, snapshot)
    print(f"inventory: {out}")
    print(f"  custom skills: {snapshot['custom_skills']} | repo files: {snapshot['repo_files']}")
    print(f"  profiles: {len(snapshot['profiles'])} | tools present: {sum(1 for v in snapshot['tools'].values() if v)}/{len(TOOLS)}")
    return 0


def count_repo_files():
    n = 0
    for base, dirs, files in os.walk(repo_path(".")):
        if ".git" in base.split(os.sep):
            continue
        dirs[:] = [d for d in dirs if d != ".git"]
        n += len(files)
    return n


def REPO_PATH_IF_ANY():
    return repo_path(".")


if __name__ == "__main__":
    sys.exit(main())
