#!/usr/bin/env python3
"""Bangun & verifikasi pack manifest per divisi (fondasi langganan, ADR-0003).

Kenapa: distribusi skill hari ini menyalin direktori ke tiap profil (±65 MB) tanpa versi dan tanpa
cara mencabut. Pack manifest = daftar skill + hash + lisensi untuk satu peran; materialisasi menjadi
turunan, sehingga rollback = tukar nomor versi, bukan revert commit di banyak tempat.

Pakai:
    python3 scripts/pack_build.py build            # tulis platform/packs/*.json
    python3 scripts/pack_build.py build --out DIR  # tulis ke direktori lain (uji determinisme)
    python3 scripts/pack_build.py verify           # hash ulang, tolak drift
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import re
import sys

import yaml

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACK_VERSION = "1.0.0"
PACK_LICENSE = "BUSL-1.1"
MAX_SKILLS = 25  # ADR-0003: di atas 25 skill per peran, pemilihan skill mulai tidak relevan
NON_REDISTRIBUTABLE = ("CC-BY-SA", "GPL", "AGPL", "none_declared", "UNLICENSED")


def _license_of(skill_dir: str) -> str:
    path = os.path.join(skill_dir, "SKILL.md")
    try:
        with open(path, encoding="utf-8") as fh:
            head = fh.read(2000)
    except OSError:
        return "MISSING"
    m = re.search(r"(?m)^license:\s*(\S+)\s*$", head)
    return m.group(1) if m else "UNSPECIFIED"


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def load_registry(root: str = REPO) -> dict:
    with open(os.path.join(root, "registry", "skills.yaml"), encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def roles(root: str = REPO) -> list[str]:
    return [os.path.splitext(os.path.basename(p))[0]
            for p in sorted(glob.glob(os.path.join(root, "agents", "*.yaml")))]


def build_packs(root: str = REPO) -> dict[str, dict]:
    reg = load_registry(root)
    required_native = list(reg.get("pipeline_required") or [])
    packs: dict[str, dict] = {}
    for role in roles(root):
        selected = [c for c in reg.get("custom") or [] if role in (c.get("profiles") or [])]
        skills = []
        for c in sorted(selected, key=lambda x: x["id"]):
            sdir = os.path.join(root, c["path"])
            skills.append({
                "id": c["id"],
                "path": c["path"],
                "sha256": _sha256(os.path.join(sdir, "SKILL.md")),
                "license": _license_of(sdir),
            })
        total = len(skills) + len(required_native)
        if total > MAX_SKILLS:
            raise SystemExit(f"{role}: {total} skill > batas {MAX_SKILLS} (ADR-0003). Kurasi dulu.")
        packs[role] = {
            "pack": role,
            "version": PACK_VERSION,
            "role": role,
            "license": PACK_LICENSE,
            "required_native": required_native,
            "source": {
                "registry_version": str(reg.get("version")),
                "registry_updated": str(reg.get("updated")),
                "skill_count": len(skills),
            },
            "skills": skills,
        }
    return packs


def pack_errors(pack: dict, root: str = REPO) -> list[str]:
    """Kembalikan daftar masalah; kosong = pack sehat."""
    errs: list[str] = []
    if pack.get("license") != PACK_LICENSE:
        errs.append(f"license pack tidak standar: {pack.get('license')}")
    if not pack.get("skills"):
        errs.append("pack tanpa skill")
    if len(pack.get("skills", [])) + len(pack.get("required_native", [])) > MAX_SKILLS:
        errs.append(f"melebihi batas {MAX_SKILLS} skill")
    for s in pack.get("skills", []):
        verdict = s.get("license", "")
        if any(verdict.startswith(p) for p in NON_REDISTRIBUTABLE):
            errs.append(f"{s['id']}: lisensi {verdict} tidak boleh masuk paket {PACK_LICENSE}")
        f = os.path.join(root, s.get("path", ""), "SKILL.md")
        if not os.path.exists(f):
            errs.append(f"{s['id']}: SKILL.md hilang ({s.get('path')})")
            continue
        actual = _sha256(f)
        if actual != s.get("sha256"):
            errs.append(f"{s['id']}: sha256 drift ({s.get('sha256', '')[:12]} -> {actual[:12]})")
        if _license_of(os.path.join(root, s.get("path", ""))) != verdict:
            errs.append(f"{s['id']}: lisensi di frontmatter berubah ({verdict})")
    return errs


def registry_drift(pack: dict, root: str = REPO) -> list[str]:
    """Deteksi skill yang seharusnya masuk/keluar pack karena registry berubah."""
    reg = load_registry(root)
    live = {c["id"] for c in reg.get("custom") or [] if pack["role"] in (c.get("profiles") or [])}
    in_pack = {s["id"] for s in pack["skills"]}
    out = []
    for missing in sorted(live - in_pack):
        out.append(f"{missing}: ada di registry tapi tidak di pack")
    for extra in sorted(in_pack - live):
        out.append(f"{extra}: ada di pack tapi tidak lagi untuk peran ini")
    return out


def write_packs(packs: dict[str, dict], out_dir: str) -> list[str]:
    os.makedirs(out_dir, exist_ok=True)
    written = []
    for role, pack in sorted(packs.items()):
        path = os.path.join(out_dir, f"{role}.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(pack, fh, indent=1, sort_keys=False, ensure_ascii=False)
            fh.write("\n")
        written.append(path)
    return written


def cmd_build(args) -> int:
    packs = build_packs(args.root)
    out = args.out or os.path.join(args.root, "platform", "packs")
    written = write_packs(packs, out)
    total = sum(len(p["skills"]) for p in packs.values())
    print(f"pack: {len(written)} berkas, {total} entri skill -> {out}")
    return 0


def cmd_verify(args) -> int:
    base = args.out or os.path.join(args.root, "platform", "packs")
    files = sorted(glob.glob(os.path.join(base, "*.json")))
    if not files:
        print(f"pack: TIDAK ADA manifest di {base}", file=sys.stderr)
        return 2
    fails = 0
    for f in files:
        with open(f, encoding="utf-8") as fh:
            pack = json.load(fh)
        errs = pack_errors(pack, args.root) + registry_drift(pack, args.root)
        name = os.path.basename(f)
        if errs:
            fails += 1
            print(f"pack: FAIL {name}")
            for e in errs:
                print(f"  - {e}")
        else:
            print(f"pack: OK   {name} ({len(pack['skills'])} skill)")
    print(f"pack: {'FAIL' if fails else 'PASS'} ({fails} gagal / {len(files)} berkas)")
    return 1 if fails else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Pack manifest SDB")
    ap.add_argument("command", choices=["build", "verify"])
    ap.add_argument("--root", default=REPO)
    ap.add_argument("--out", help="direktori keluaran (default platform/packs)")
    args = ap.parse_args(argv)
    return cmd_build(args) if args.command == "build" else cmd_verify(args)


if __name__ == "__main__":
    sys.exit(main())
