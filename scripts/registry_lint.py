#!/usr/bin/python3
"""Validasi integritas registry + frontmatter skill.

Pemakaian: /usr/bin/python3 scripts/registry_lint.py
Exit: 0 bersih, 1 ada error.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sdb_common import load_yaml, repo_path

REQUIRED_TOOL_SECTIONS = {"present", "pending_approval"}
VALID_STATUS = {"KEEP", "UPDATE", "REPLACE", "ADD", "REMOVE", "QUARANTINE", "PENDING_APPROVAL",
                "IN_USE", "OPTIONAL", "DEFER", "NOT_PRESENT",
                # 2026-10-05: hasil keputusan pihak ketiga (lihat registry bagian B)
                "INSTALLED", "REJECTED_BLUEPRINT", "REJECTED_LICENSE", "REJECTED_COVERED"}


def frontmatter(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return {}
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    block = text[3:end]
    data = {}
    for line in block.splitlines():
        if line.startswith("  ") or not line.strip():
            continue
        key, _, val = line.partition(":")
        data[key.strip()] = val.strip()
    return data


def main() -> int:
    errors, warnings = [], []
    reg_path = repo_path("registry", "skills.yaml")
    reg = load_yaml(reg_path) or {}
    if isinstance(reg, list):  # toleransi format lama (daftar tanpa key)
        reg = {"custom": reg}
    custom = [c for c in (reg.get("custom") or []) if isinstance(c, dict)]
    keep = [k.get("id") for k in (reg.get("keep_local") or []) if isinstance(k, dict)]
    known_ids = {c.get("id") for c in custom} | set(keep)

    expected_custom = int(reg.get("approved_custom_count") or 21)
    if len(custom) != expected_custom:
        warnings.append(f"jumlah custom skill = {len(custom)} (disetujui Owner: {expected_custom})")
    elif len(custom) < 21:
        errors.append(f"jumlah custom skill menyusut di bawah basis blueprint: {len(custom)} < 21")

    referenced_profiles = set()
    for c in custom:
        sid = c.get("id")
        if not sid:
            errors.append("entri custom tanpa id")
            continue
        if not c.get("profiles"):
            errors.append(f"{sid}: tanpa daftar profiles")
        referenced_profiles.update(c.get("profiles") or [])
        skill_dir = repo_path("skills", sid)
        skill_md = os.path.join(skill_dir, "SKILL.md")
        if not os.path.exists(skill_md):
            errors.append(f"{sid}: SKILL.md tidak ada di {skill_dir}")
            continue
        fm = frontmatter(skill_md)
        if fm.get("name") != sid:
            errors.append(f"{sid}: frontmatter name='{fm.get('name')}' tidak cocok dengan id")
        if not fm.get("description"):
            errors.append(f"{sid}: description kosong")
        if not fm.get("version"):
            warnings.append(f"{sid}: version belum diisi di frontmatter")
        for rel in c.get("related") or []:
            if rel not in known_ids:
                warnings.append(f"{sid}: related '{rel}' tidak ada di registry")

    # agent charters harus konsisten dengan daftar profil
    agent_dir = repo_path("agents")
    agent_ids, agent_divisions = set(), {}
    if os.path.isdir(agent_dir):
        for name in sorted(os.listdir(agent_dir)):
            if not name.endswith(".yaml"):
                continue
            data = load_yaml(os.path.join(agent_dir, name)) or {}
            aid = data.get("id")
            agent_ids.add(aid)
            agent_divisions[aid] = data.get("divisions") or []
    if agent_ids != referenced_profiles:
        errors.append(f"profil di registry != profil di agents/: registry-only={sorted(referenced_profiles - agent_ids)} "
                      f"agents-only={sorted(agent_ids - referenced_profiles)}")
    covered = {d for divs in agent_divisions.values() for d in divs}
    expected = {f"D{i}" for i in range(12)}
    if expected - covered:
        warnings.append(f"divisi belum punya owner di agents/: {sorted(expected - covered)}")

    # tools registry
    tools = load_yaml(repo_path("registry", "tools.yaml")) or {}
    missing_sections = REQUIRED_TOOL_SECTIONS - set(tools.keys())
    if missing_sections:
        errors.append(f"tools.yaml kurang seksi: {sorted(missing_sections)}")
    for section, items in tools.items():
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict) or not item.get("id"):
                errors.append(f"tools.yaml[{section}]: entri tanpa id")
            elif section.startswith("third"):
                pass
    # status pihak ketiga harus dikenal
    for item in (reg.get("third_party") or []):
        if isinstance(item, dict) and item.get("status") not in VALID_STATUS:
            errors.append(f"third_party {item.get('repo')}: status tidak dikenal '{item.get('status')}'")
        if isinstance(item, dict) and not item.get("pinned_commit"):
            warnings.append(f"third_party {item.get('repo')}: tanpa pinned_commit")

    print(f"registry_lint: {'PASS' if not errors else 'FAIL'}")
    print(f"  custom skills: {len(custom)} | profiles: {len(referenced_profiles)} | keep_local: {len(keep)}")
    for e in errors:
        print(f"  ERROR: {e}")
    for w in warnings:
        print(f"  WARN: {w}")
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
