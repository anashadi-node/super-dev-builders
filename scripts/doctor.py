#!/usr/bin/python3
"""Doctor — cek kapabilitas host ekosistem vs registry/tools.yaml.

Pemakaian: /usr/bin/python3 scripts/doctor.py [--json out.json]
Exit: 0 bila kapabilitas wajib tersedia, 3 bila ada yang kurang.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sdb_common import PROFILES_DIR, load_yaml, now_iso, repo_path, write_json, yaml_backend

REQUIRED = ["git", "python3", "node", "npm"]
OPTIONAL = ["docker", "jq", "playwright", "pytest", "uv", "gh", "semgrep", "trivy", "syft", "ruff"]


def which(name: str):
    return shutil.which(name)


def version_of(cmd, args):
    try:
        out = subprocess.run([cmd, *args], capture_output=True, text=True, timeout=15)
        return (out.stdout or out.stderr).strip().splitlines()[0][:80]
    except Exception:
        return "unknown"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Capability check")
    ap.add_argument("--json", dest="json_out")
    args = ap.parse_args(argv)

    report = {"checked_at": now_iso(), "yaml_backend": yaml_backend(), "host": {}, "profiles": {}, "registry": {}}
    missing_required = []
    for name in REQUIRED + OPTIONAL:
        path = which(name)
        if not path:
            report["host"][name] = {"present": False}
            if name in REQUIRED:
                missing_required.append(name)
            continue
        vargs = ["--version"]
        report["host"][name] = {"present": True, "path": path, "version": version_of(path, vargs)}

    # python yang dipakai: pastikan ada interpreter dengan PyYAML
    system_py = which("python3")
    report["host"]["python3_default"] = system_py
    for candidate in ("/usr/bin/python3", system_py):
        if candidate and os.path.exists(candidate):
            try:
                out = subprocess.run(
                    [candidate, "-c", "import yaml,sys;print('yaml-ok',sys.version.split()[0])"],
                    capture_output=True, text=True, timeout=15)
                report["host"][f"yaml_in:{candidate}"] = (out.stdout or out.stderr).strip()
            except Exception:
                report["host"][f"yaml_in:{candidate}"] = "error"

    # profil divisi
    # Resolusi id logis sdb-* -> direktori profil aktual cc-* memakai agents/*.yaml
    # (pola sama dengan scripts/install_skills.py:load_profile_aliases).
    expected = ["sdb-orchestrator", "sdb-recon", "sdb-architect", "sdb-builder",
                "sdb-reviewer", "sdb-security", "sdb-devops"]
    aliases = {}
    agent_dir = repo_path("agents")
    if os.path.isdir(agent_dir):
        for name in os.listdir(agent_dir):
            if not name.endswith(".yaml"):
                continue
            try:
                data = load_yaml(os.path.join(agent_dir, name)) or {}
            except Exception:
                continue
            logical, real = data.get("id"), data.get("hermes_profile")
            if logical and real:
                aliases[logical] = real
    for logical in expected:
        d = os.path.join(PROFILES_DIR, aliases.get(logical, logical))
        present = os.path.isdir(d)
        report["profiles"][logical] = {
            "present": present,
            "resolved": d if present else aliases.get(logical, logical),
            "soul_md": os.path.exists(os.path.join(d, "SOUL.md")) if present else False,
            "skills_dir": os.path.isdir(os.path.join(d, "skills")) if present else False,
        }

    tools_path = repo_path("registry", "tools.yaml")
    if os.path.exists(tools_path):
        reg = load_yaml(tools_path) or {}
        for section in ("present", "pending_approval", "quarantine", "deferred"):
            items = reg.get(section) or []
            report["registry"][section] = [i.get("id") if isinstance(i, dict) else str(i) for i in items]
        inst = [t.get("id") for t in (reg.get("present") or []) if isinstance(t, dict) and which(t.get("id", ""))]
        report["registry"]["verified_on_host"] = inst

    if args.json_out:
        write_json(args.json_out, report)

    print(f"doctor — {report['checked_at']} | YAML backend: {report['yaml_backend']}")
    for name in REQUIRED + OPTIONAL:
        info = report["host"][name]
        mark = "OK  " if info.get("present") else ("MISS" if name in REQUIRED else "-   ")
        extra = info.get("path", "")
        print(f"  [{mark}] {name:<12} {extra} {info.get('version','')}")
    print("  profil divisi:")
    for name, info in report["profiles"].items():
        print(f"    {'OK ' if info['present'] else 'MISS'} {name} (soul={info.get('soul_md')})")
    if missing_required:
        print(f"  KURANG (wajib): {missing_required}")
        return 3
    print("  kapabilitas wajib tersedia")
    return 0


if __name__ == "__main__":
    sys.exit(main())
