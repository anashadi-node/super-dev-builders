#!/usr/bin/env python3
"""Snapshot kapabilitas penyedia (REA/Craft/engine) untuk Divisi Investigasi.

Kenapa: klaim "bisa Android" atau "Ghidra siap" harus berasal dari alat, bukan hafalan.
Skrip ini menjalankan pemeriksaan resmi (read-only), lalu menulis satu berkas bukti
ber-hash yang bisa dikutip handoff DID.

Pemakaian:
  python3 scripts/provider_snapshot.py            # tulis evidence/providers/<tanggal>.json
  python3 scripts/provider_snapshot.py --check     # cetak matriks, tidak menulis
  python3 scripts/provider_snapshot.py --json-out X.json

Exit: 0 = snapshot dibuat / matriks tercetak, 2 = REA tidak bisa dipanggil.
Hanya stdlib.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import glob
import hashlib
import json
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REA = os.path.join(ROOT, "scripts", "rea")


def _run(cmd: list[str], timeout: int = 300) -> tuple[int, str, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=ROOT)
        return p.returncode, p.stdout, p.stderr
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 127, "", str(exc)


def _json_of(cmd: list[str]) -> dict:
    code, out, err = _run(cmd)
    # exit != 0 juga menghasilkan JSON yang sah (mis. doctor exit 1 saat unhealthy)
    if not out.strip():
        return {"_error": err.strip()[:400] or f"exit {code}"}
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        # sebagian perintah menulis baris pembuka sebelum JSON
        start = out.find("{")
        try:
            return json.loads(out[start:]) if start >= 0 else {"_error": "bukan JSON"}
        except json.JSONDecodeError:
            return {"_error": "bukan JSON"}


def _first_glob(pattern: str) -> str:
    hits = sorted(glob.glob(os.path.expanduser(pattern)))
    return hits[-1] if hits else ""


def collect() -> dict:
    version_out = _run([REA, "--version"])[1].strip().splitlines()
    doctor = _json_of([REA, "doctor", "--format", "json"])
    caps = _json_of([REA, "capabilities", "--format", "json"])

    checks = doctor.get("scope_checks") or []
    failing = [{"name": c.get("name"), "detail": (c.get("detail") or "")[:200]}
               for c in checks if not c.get("ok")]
    passing = [c.get("name") for c in checks if c.get("ok")]

    providers = []
    for p in doctor.get("providerInspections") or []:
        providers.append({"id": p.get("id"), "configured": bool(p.get("configured")),
                          "available": bool(p.get("available")), "version": p.get("providerVersion")})
    for p in caps.get("capabilities") or []:
        pid = ((p.get("provider") or {}).get("id"))
        if pid and not any(x["id"] == pid for x in providers):
            groups = p.get("groups") or []
            providers.append({"id": pid, "configured": True,
                              "available": any(g.get("available") for g in groups),
                              "version": None,
                              "operations": sum(len(g.get("operations") or []) for g in groups)})

    craft_bin = _first_glob("~/.local/opt/craft-anything-*/**/bin/craft-anything-cli")
    craft = {"installed": bool(craft_bin), "binary": craft_bin}
    if craft_bin:
        craft["version"] = _run([craft_bin, "--version"])[1].strip()
        doc = _run([craft_bin, "doctor", "--json"])[1]
        try:
            craft["doctor"] = json.loads(doc)[:20] if doc.strip().startswith("[") else json.loads(doc)
        except (json.JSONDecodeError, IndexError):
            craft["doctor"] = {"_raw": doc.strip()[:400]}

    engines = {
        "ghidra": _first_glob("~/.local/opt/ghidra_*_PUBLIC"),
        "jdk": _first_glob("~/.local/opt/jdk-*"),
        "jadx": shutil.which("jadx") or "",
        "apktool": shutil.which("apktool") or "",
        "adb": shutil.which("adb") or "",
        "frida": shutil.which("frida") or "",
        "joern": shutil.which("joern") or "",
        "codeql": shutil.which("codeql") or "",
        "semgrep": shutil.which("semgrep") or "",
        "syft": shutil.which("syft") or "",
        "trivy": shutil.which("trivy") or "",
        "docker": shutil.which("docker") or "",
        "bwrap": shutil.which("bwrap") or "",
    }

    rea_ok = bool(version_out)
    optional = {"ida", "ida-registration", "hopper", "jadx", "kuna", "kuna-installation", "skill:identity"}
    core_failed = [c for c in failing
                   if not str(c.get("name", "")).startswith("registration:") and c.get("name") not in optional]
    playwright = bool(shutil.which("playwright")) or bool(glob.glob(os.path.expanduser("~/.cache/ms-playwright/chromium-*")))

    verdicts = {
        "web": "READY" if (rea_ok and playwright) else "PARTIAL",
        "javascript": "READY" if rea_ok else "PARTIAL",
        "native_elf_pe": "READY" if (engines["ghidra"] and engines["jdk"]) else "MISSING_ENGINE",
        "android": "READY" if (engines["jadx"] and engines["apktool"]) else "PARTIAL",
        "runtime_instrumentation": "READY" if engines["frida"] else "BLOCKED",
        "source_semantic": "READY" if (engines["semgrep"] and engines["codeql"]) else "PARTIAL",
        "sbom": "READY" if engines["syft"] else "MISSING_ENGINE",
        "sandbox_docker": "READY" if engines["docker"] else "MISSING_ENGINE",
        "sandbox_bwrap": "READY" if (engines["bwrap"] and bwrap_works()) else "UNUSABLE",
    }

    snap = {
        "schema": "sdb.did.providers/1",
        "generated_at": _dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "rea": {"binary": REA, "version": version_out[0] if version_out else None,
                "doctor_healthy": doctor.get("healthy"), "environment_healthy": doctor.get("environment_healthy"),
                "core_ready": bool(rea_ok) and not core_failed,
                "core_checks_failed": core_failed,
                "checks_passed": passing, "checks_failed": failing,
                "providers": providers},
        "craft_anything": craft,
        "engines": engines,
        "verdicts": verdicts,
        "note": ("checks_failed yang bersifat registrasi klien (claude_code, codex, hermes, ...) dan engine "
                 "opsional (ida/hopper/jadx/kuna) TIDAK membuat jalur web/JS/native gagal; lihat verdicts."),
    }
    return snap


def bwrap_works() -> bool:
    try:
        p = subprocess.run(["bwrap", "--ro-bind", "/", "/", "true"], capture_output=True, timeout=20)
        return p.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Snapshot kapabilitas penyedia DID")
    ap.add_argument("--check", action="store_true", help="cetak matriks saja")
    ap.add_argument("--json-out")
    args = ap.parse_args(argv)

    snap = collect()
    if snap["rea"].get("version") is None:
        print("FAIL: REA tidak bisa dipanggil (cek scripts/rea)", file=sys.stderr)
        return 2

    if args.check:
        print(f"REA {snap['rea']['version']} · core_ready={snap['rea']['core_ready']} "
              f"(doctor healthy={snap['rea']['doctor_healthy']})")
        for name, val in snap["verdicts"].items():
            print(f"  {name:24s} {val}")
        for f in snap["rea"]["checks_failed"][:8]:
            print(f"  - gagal: {f['name']}")
        return 0

    out = args.json_out or os.path.join(
        ROOT, "evidence", "providers", f"providers-{_dt.date.today():%Y%m%d}.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    blob = json.dumps(snap, indent=1, ensure_ascii=False).encode()
    with open(out, "wb") as fh:
        fh.write(blob)
    print(f"provider_snapshot: {os.path.relpath(out, ROOT)} · sha256 {hashlib.sha256(blob).hexdigest()[:16]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
