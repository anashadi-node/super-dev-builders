#!/usr/bin/python3
"""Pasang/copot custom skill ekosistem (daftar: registry/skills.yaml) ke profil Hermes atau skills utama.

Sumber tunggal: <repo>/skills/<id>/SKILL.md (registry: registry/skills.yaml).

Pemakaian:
    /usr/bin/python3 scripts/install_skills.py --list
    /usr/bin/python3 scripts/install_skills.py --profile sdb-builder --dry-run
    /usr/bin/python3 scripts/install_skills.py --profile sdb-builder,sdb-recon
    /usr/bin/python3 scripts/install_skills.py --all
    /usr/bin/python3 scripts/install_skills.py --uninstall --all
    /usr/bin/python3 scripts/install_skills.py --main --profile n/a     # pasang ke ~/.hermes/skills/
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sdb_common import (HERMES_HOME, PROFILES_DIR, SKILL_NAMESPACE, load_yaml, now_iso,
                        repo_path, validate_slug, write_json)


def load_registry():
    reg = load_yaml(repo_path("registry", "skills.yaml")) or {}
    custom = [c for c in (reg.get("custom") or []) if isinstance(c, dict)]
    return custom


def load_profile_aliases():
    """Peta logical division id -> direktori profil Hermes (dari agents/*.yaml)."""
    aliases = {}
    agent_dir = repo_path("agents")
    if not os.path.isdir(agent_dir):
        return aliases
    for name in sorted(os.listdir(agent_dir)):
        if not name.endswith(".yaml"):
            continue
        try:
            data = load_yaml(os.path.join(agent_dir, name)) or {}
        except Exception:
            continue
        logical, real = data.get("id"), data.get("hermes_profile")
        if logical and real:
            aliases[logical] = real
    return aliases


def resolve_profile(profile: str | None, aliases: dict):
    """Terima logical division id (sdb-*) atau nama direktori profil (cc-*)."""
    if not profile:
        return None
    if os.path.isdir(os.path.join(PROFILES_DIR, profile)):
        return profile
    return aliases.get(profile, profile)


def dest_root(profile: str | None) -> str:
    if profile:
        return os.path.join(PROFILES_DIR, profile, "skills", SKILL_NAMESPACE)
    return os.path.join(HERMES_HOME, "skills", SKILL_NAMESPACE)


def install_one(skill_id: str, profile, dry_run: bool, uninstall: bool, log):
    # skill_id dari registry (tepercaya) TETAP divalidasi: id seperti '..' membuat
    # os.path.join + shutil.rmtree menulis/menghapus di luar namespace skills (T11-7).
    # Fail-closed: tolak, jangan jalankan.
    try:
        skill_id = validate_slug(skill_id)
    except ValueError as e:
        log.append({"action": "skip", "skill": str(skill_id)[:40], "profile": profile or "main",
                    "reason": f"id tidak sah: {e}"})
        return
    src = repo_path("skills", skill_id)
    dst = os.path.join(dest_root(profile), skill_id)
    if uninstall:
        if os.path.isdir(dst):
            log.append({"action": "uninstall", "skill": skill_id, "profile": profile or "main", "path": dst})
            if not dry_run:
                shutil.rmtree(dst)
        return
    if not os.path.isdir(src):
        log.append({"action": "skip", "skill": skill_id, "profile": profile or "main", "reason": "sumber tidak ada"})
        return
    log.append({"action": "install", "skill": skill_id, "profile": profile or "main", "path": dst})
    if dry_run:
        return
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if os.path.isdir(dst):
        shutil.rmtree(dst)
    # jangan bawa cache bytecode/test ke lokasi terpasang (sumber drift palsu)
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache"))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Install/uninstall custom skills ekosistem")
    ap.add_argument("--profile", help="nama profil (boleh koma: a,b)")
    ap.add_argument("--all", action="store_true", help="semua profil yang relevan per registry")
    ap.add_argument("--main", action="store_true", help="pasang ke ~/.hermes/skills/<namespace>/")
    ap.add_argument("--uninstall", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args(argv)

    custom = load_registry()
    aliases = load_profile_aliases()
    if not custom:
        print("registry kosong / tidak terbaca", file=sys.stderr)
        return 1

    if args.list:
        for c in custom:
            logicals = c.get("profiles") or []
            resolved = ",".join(f"{p}->{resolve_profile(p, aliases)}" for p in logicals)
            print(f"{c['id']:<32} {resolved}")
        print("alias:", ", ".join(f"{k}->{v}" for k, v in sorted(aliases.items())))
        return 0

    targets = []
    if args.main:
        targets.append(None)
    if args.profile:
        targets.extend([p.strip() for p in args.profile.split(",") if p.strip()])
    if args.all:
        seen = []
        for c in custom:
            for p in (c.get("profiles") or []):
                if p not in seen:
                    seen.append(p)
        targets.extend(seen)
    if not targets:
        ap.error("pilih --profile / --all / --main")

    log, missing_profiles = [], []
    for logical in dict.fromkeys(targets):
        profile = resolve_profile(logical, aliases)
        profile_missing = bool(profile) and not os.path.isdir(os.path.join(PROFILES_DIR, profile))
        if profile_missing:
            missing_profiles.append(profile)
            if not args.dry_run:
                continue
        for c in custom:
            # cocokkan dengan logical division id (registry memakai sdb-*),
            # sedangkan pemasangan memakai direktori profil hasil resolusi alias.
            if logical is not None and logical not in (c.get("profiles") or []):
                continue
            if profile_missing:
                log.append({"action": "plan" if not args.uninstall else "plan-uninstall", "skill": c["id"],
                            "profile": logical, "path": os.path.join(dest_root(profile), c["id"])})
                continue
            install_one(c["id"], profile, args.dry_run, args.uninstall, log)

    manifest_path = repo_path("reports", "installed-skills.json")
    if not args.dry_run:
        write_json(manifest_path, {"at": now_iso(), "uninstall": args.uninstall,
                                   "operations": log, "missing_profiles": missing_profiles})
    action = "uninstall" if args.uninstall else "install"
    print(f"{action}: {len(log)} operasi" + (" (dry-run)" if args.dry_run else f" | manifest: {manifest_path}"))
    for item in log[:60]:
        print(f"  {item['action']:<9} {item['skill']:<32} -> {item.get('profile')}")
    if missing_profiles:
        print(f"  profil tidak ada (dilewati): {sorted(set(missing_profiles))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
