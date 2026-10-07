#!/usr/bin/python3
"""Doctor — cek kapabilitas host ekosistem vs registry/tools.yaml.

Pemakaian: /usr/bin/python3 scripts/doctor.py [--json out.json] [--drift-only]
Exit: 0 bila kapabilitas wajib tersedia, 3 bila ada yang kurang,
      1 bila --drift-only dan ada skill MISSING/DIFF/COLLISION.
"""
from __future__ import annotations

import argparse
import filecmp
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from install_skills import dest_root, load_profile_aliases, load_registry, resolve_profile
from sdb_common import HERMES_HOME, PROFILES_DIR, load_yaml, now_iso, repo_path, write_json, yaml_backend

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


_IGNORE = ["__pycache__", ".pytest_cache"]


def _same_tree(a: str, b: str) -> bool:
    c = filecmp.dircmp(a, b, ignore=_IGNORE)
    if c.left_only or c.right_only or c.diff_files or c.funny_files:
        return False
    # dircmp membandingkan shallow (stat); bandingkan isi agar tidak lolos palsu
    _, mismatch, errors = filecmp.cmpfiles(a, b, c.common_files, shallow=False)
    return not mismatch and not errors and all(_same_tree(os.path.join(a, d), os.path.join(b, d)) for d in c.common_dirs)


def _skill_names(root: str) -> dict:
    """nama skill (frontmatter / nama dir) -> path, untuk SKILL.md di luar namespace kita."""
    out = {}
    if not os.path.isdir(root):
        return out
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in ("node_modules", ".git", "super-dev-builders", *_IGNORE)]
        if "SKILL.md" in filenames:
            out.setdefault(os.path.basename(dirpath), dirpath)
    return out


def skill_drift() -> list[dict]:
    """Bandingkan skill terpasang (main + profil per registry) dengan sumber repo.

    Status: OK | MISSING | DIFF | COLLISION (nama sama dengan skill lain di luar
    namespace -> Hermes tidak bisa memuat salah satunya)."""
    aliases = load_profile_aliases()
    rows = []
    for c in load_registry():
        sid = c["id"]
        src = repo_path("skills", sid)
        for logical in [None, *(c.get("profiles") or [])]:
            profile = resolve_profile(logical, aliases)
            if profile and not os.path.isdir(os.path.join(PROFILES_DIR, profile)):
                continue
            dst = os.path.join(dest_root(profile), sid)
            status = "MISSING" if not os.path.isdir(dst) else ("OK" if _same_tree(src, dst) else "DIFF")
            rows.append({"skill": sid, "where": profile or "main", "status": status})
    # tabrakan hanya nyata bila skill kita TERPASANG di root yang sama dengan skill senama lain
    installed = {(r["where"], r["skill"]) for r in rows if r["status"] != "MISSING"}
    for where, root in [("main", os.path.join(HERMES_HOME, "skills")),
                        *[(p, os.path.join(PROFILES_DIR, p, "skills")) for p in sorted(set(aliases.values()))]]:
        for name, path in _skill_names(root).items():
            if (where, name) in installed:
                rows.append({"skill": name, "where": where, "status": "COLLISION", "other": path})
    return rows


def dep_check() -> list[dict]:
    """Pin [project.dependencies] vs metadata .venv (reproducibility, bukan sistem-kernel).

    Baca langsung *.dist-info/METADATA di .venv: metadata sistem python tidak relevan,
    yang menentukan adalah env yang dibuat `uv sync --frozen`."""
    import email.parser
    import glob
    import os

    import tomllib
    sp_root = []
    for pat in ("lib/python*/site-packages", "Lib/site-packages"):
        sp_root += glob.glob(str(repo_path(".venv", pat)))
    installed: dict[str, str] = {}
    parser = email.parser.BytesParser()
    for meta in glob.glob(os.path.join(sp_root[0], "*.dist-info", "METADATA")) if sp_root else []:
        msg = parser.parse(open(meta, "rb"))
        name = msg.get("Name")
        if name:
            installed[name.lower().replace("_", "-")] = msg.get("Version", "")
    with open(repo_path("pyproject.toml"), "rb") as fh:
        deps = tomllib.load(fh).get("project", {}).get("dependencies") or []
    rows = []
    for d in deps:
        name_spec = d.split(";")[0].split("[")[0].strip()
        if "==" not in name_spec:
            rows.append({"dep": name_spec, "status": "UNPINNED"})
            continue
        name, ver = name_spec.split("==", 1)
        got = installed.get(name.lower().replace("_", "-"))
        rows.append({"dep": name, "want": ver, "installed": got,
                     "status": "OK" if got == ver else "MISSING_OR_DRIFT"})
    return rows


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Capability check")
    ap.add_argument("--json", dest="json_out")
    ap.add_argument("--drift-only", action="store_true", help="hanya cek drift skill terpasang vs repo")
    args = ap.parse_args(argv)

    drift = skill_drift()
    deps = dep_check()
    bad = [r for r in drift if r["status"] != "OK"] +           [{"skill": d["dep"], "status": d["status"]} for d in deps if d["status"] != "OK"]
    if args.drift_only:
        for r in bad:
            print(f"  {r['status']:<9} {r['skill']:<32} @ {r['where']} {r.get('other', '')}")
        print(f"skill drift: {len(drift) - len(bad)}/{len(drift)} OK, {len(bad)} bermasalah")
        return 1 if bad else 0

    report = {"checked_at": now_iso(), "yaml_backend": yaml_backend(), "host": {}, "profiles": {}, "registry": {},
              "skill_drift": drift}
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
    dep_ok = sum(1 for d in deps if d["status"] == "OK")
    dep_bad = [d["dep"] for d in deps if d["status"] != "OK"]
    print(f"  deps pinned: {dep_ok}/{len(deps)} OK" + ("" if not dep_bad else f" -> {dep_bad}"))
    print(f"  skill drift: {len(drift) - len(bad)}/{len(drift)} OK, {len(bad)} bermasalah"
          + (" -> jalankan `make drift`" if bad else ""))
    if missing_required:
        print(f"  KURANG (wajib): {missing_required}")
        return 3
    print("  kapabilitas wajib tersedia")
    return 0


if __name__ == "__main__":
    sys.exit(main())
