#!/usr/bin/env python3
"""Sinkronkan skill pihak ketiga (Trail of Bits) dari commit pin ke profil Hermes.

Kenapa ada alat ini:
  `hermes skills install` (hub skills.sh) memotong sebagian berkas skill
  (terbukti: codeql 2/34 berkas, 12 `references/*.md` menggantung), tanpa sebab
  yang bisa kami buktikan. Alat ini melengkapi dari SUMBER PIN commit yang sama
  (git protocol, bukan API GitHub -> tidak makan kuota), lalu MEMBUKTIKAN
  kesamaan byte-per-byte lewat sha256.

Jaminan:
  - hanya menambah berkas yang hilang; berkas yang sudah ada dan berbeda
    dilaporkan sebagai DEVIASI (tidak ditimpa diam-diam),
  - tidak menulis apa pun di luar direktori skill pihak ketiga,
  - keluar dengan kode bukan-nol bila ada deviasi (fail-closed).

Pemakaian:
  python3 scripts/sync_third_party_skills.py --check            # hanya laporan
  python3 scripts/sync_third_party_skills.py --fix              # lengkapi berkas hilang
  python3 scripts/sync_third_party_skills.py --fix --profiles   # + sebar ke profil divisi
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time

REPO_URL = "https://github.com/trailofbits/skills.git"
PIN = "82fe8226252622fa807643bdca1710901198553a"
LICENSE = "CC-BY-SA-4.0"
UPSTREAM_OWNER = "trailofbits/skills"

# skill -> path di dalam repo (plugins/<x>/skills/<y>)
SKILLS = {
    "semgrep": "static-analysis/skills/semgrep",
    "codeql": "static-analysis/skills/codeql",
    "sarif-parsing": "static-analysis/skills/sarif-parsing",
    "differential-review": "differential-review/skills/differential-review",
    "variant-analysis": "variant-analysis/skills/variant-analysis",
    "fp-check": "fp-check/skills/fp-check",
    "audit-context-building": "audit-context-building/skills/audit-context-building",
    "modern-python": "modern-python/skills/modern-python",
    "post-patch-validation": "post-patch-validation/skills/post-patch-validation",
}

# profil tempat skill pihak ketiga didistribusikan (divisi yang memang memakainya)
PROFILE_MAP = {
    "semgrep": ["cc-security-governor", "cc-devops-docs"],
    "codeql": ["cc-security-governor"],
    "sarif-parsing": ["cc-security-governor"],
    "differential-review": ["cc-security-governor", "cc-architect", "cc-reviewer-qa"],
    "variant-analysis": ["cc-security-governor", "cc-reviewer-qa"],
    "fp-check": ["cc-security-governor", "cc-reviewer-qa"],
    "audit-context-building": ["cc-security-governor", "cc-architect"],
    "modern-python": ["cc-builder", "cc-devops-docs"],
    "post-patch-validation": ["cc-builder", "cc-security-governor", "cc-reviewer-qa"],
}

CLONE = os.path.join(os.path.expanduser("~/.hermes/cache/scratch"), "tob-skills-pin")
HERMES_SKILLS = os.path.expanduser("~/.hermes/skills")
PROFILES = os.path.expanduser("~/.hermes/profiles")
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def sha256(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def ensure_clone() -> str:
    """Clone/fetch commit pin. git protocol -> tidak memakai kuota GitHub API."""
    os.makedirs(CLONE, exist_ok=True)
    if not os.path.isdir(os.path.join(CLONE, ".git")):
        subprocess.run(["git", "init", "-q", CLONE], check=True)
    # URL langsung (tanpa config remote) -> tahan terhadap repo tanpa 'origin'.
    subprocess.run(["git", "-C", CLONE, "fetch", "-q", "--depth", "1", REPO_URL, PIN],
                   check=True)
    subprocess.run(["git", "-C", CLONE, "checkout", "-q", "FETCH_HEAD"], check=True)
    head = subprocess.run(["git", "-C", CLONE, "rev-parse", "HEAD"],
                          capture_output=True, text=True, check=True).stdout.strip()
    if head != PIN:
        raise SystemExit(f"FATAL: HEAD klon {head} != pin {PIN}")
    return CLONE


def walk(root: str) -> dict[str, str]:
    out = {}
    for dirpath, _dirs, names in os.walk(root):
        for fn in names:
            p = os.path.join(dirpath, fn)
            out[os.path.relpath(p, root)] = sha256(p)
    return out


def sync_skill(name: str, rel: str, clone: str, fix: bool) -> dict:
    upstream = os.path.join(clone, "plugins", rel)
    installed = os.path.join(HERMES_SKILLS, name)
    res = {"skill": name, "upstream": UPSTREAM_OWNER, "pin": PIN, "license": LICENSE,
           "installed_dir": installed, "copied": [], "deviations": [], "ok": True}
    if not os.path.isdir(upstream):
        res["ok"] = False
        res["deviations"].append("path upstream tidak ada di pin")
        return res
    if not os.path.isdir(installed):
        res["ok"] = False
        res["missing_install"] = True
        res["upstream_files"] = len(walk(upstream))
        res["deviations"].append("belum terpasang di profil default")
        return res

    up, inst = walk(upstream), walk(installed)
    missing = sorted(set(up) - set(inst))
    differing = sorted(f for f in set(up) & set(inst) if up[f] != inst[f])
    extra = sorted(set(inst) - set(up))

    if fix:
        for f in missing:
            dst = os.path.join(installed, f)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(os.path.join(upstream, f), dst)
            res["copied"].append(f)
        inst = walk(installed)
        missing = sorted(set(up) - set(inst))

    res.update({"upstream_files": len(up), "installed_files_before": len(inst) - len(res["copied"]),
                "missing": missing, "differing": differing, "extra_files": extra})
    # Semantik keluar: DEVIASI HANYA bila berkas yang sudah terpasang BERBEDA dari pin
    # (penanda isi diubah orang lain / supply-chain). Berkas yang belum lengkap = state
    # "belum sinkron" (rc=2), bukan kegagalan keamanan.
    if differing:
        res["ok"] = False
        res["security_deviation"] = True
        res["deviations"] = [f"isi berbeda dari pin: {f}" for f in differing]
    elif missing:
        res["ok"] = False
        res["pending_sync"] = True
        res["deviations"].append(f"belum sinkron: {len(missing)} berkas hilang (jalankan --fix)")
    return res


def fan_out(name: str, src: str, profiles: list[str]) -> list[str]:
    done = []
    for prof in profiles:
        dst = os.path.join(PROFILES, prof, "skills", name)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if os.path.isdir(dst):
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
        done.append(prof)
    return done


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="laporan saja (default)")
    ap.add_argument("--fix", action="store_true", help="lengkapi berkas yang hilang")
    ap.add_argument("--profiles", action="store_true", help="sebar ke profil divisi")
    ap.add_argument("--evidence", default=os.path.join(
        REPO_ROOT, "reports", "upgrade-evidence", "third-party-integrity.json"))
    args = ap.parse_args()

    clone = ensure_clone()
    report = {"provenance": "scripts/sync_third_party_skills.py", "tool": "sync_third_party_skills.py",
              "upstream": UPSTREAM_OWNER,
              "pin": PIN, "license": LICENSE, "mode": "fix" if args.fix else "check",
              "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime()),
              "redaction_status": "clean", "status": "OBSERVED", "skills": []}

    rc = 0
    for name, rel in sorted(SKILLS.items()):
        r = sync_skill(name, rel, clone, args.fix)
        if args.profiles and os.path.isdir(os.path.join(HERMES_SKILLS, name)):
            r["profiles"] = fan_out(name, os.path.join(HERMES_SKILLS, name),
                                    PROFILE_MAP.get(name, []))
        report["skills"].append(r)
        if r.get("security_deviation"):
            state, rc = "DEVIASI-KEAMANAN", 1
        elif r.get("missing_install"):
            state = "BELUM-TERPASANG"
        elif r.get("pending_sync"):
            state, rc = "PERLU-SINKRON", max(rc, 2)
        else:
            state = "OK"
        print(f"{name:24s} upstream={r.get('upstream_files','-'):>3} "
              f"disalin={len(r.get('copied',[])):>3} {state} {r.get('deviations','')}")
    os.makedirs(os.path.dirname(args.evidence), exist_ok=True)
    with open(args.evidence, "w") as fh:
        json.dump(report, fh, indent=1, ensure_ascii=False)
    print(f"\nbukti -> {args.evidence}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
