#!/usr/bin/env python3
"""Gerbang higiene repo SDB — menegakkan aturan penempatan docs/PETA_STRUKTUR.md §4.

Kenapa ada: audit 2026-10-26 menemukan 20 MB artefak pelanggan dilacak git, 5 berkas >1 MB,
dan email pihak ketiga di log. Tanpa gerbang mesin, aturan itu hanya niat.

Prinsip: baseline (`platform/hygiene-baseline.json`) mencatat utang lama sebagai WARN.
Pelanggaran BARU = FAIL. Jadi repo tidak bisa bertambah buruk, sambil tetap jujur soal masa lalu.

Exit: 0 = tidak ada FAIL, 1 = ada FAIL, 2 = salah pakai.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys

TEXT_EXT = {".md", ".json", ".log", ".txt", ".csv", ".html", ".yaml", ".yml",
            ".py", ".js", ".ts", ".sh", ".tmpl", ".xml", ".toml", ".ini"}
FORBIDDEN_SUFFIX = (".raw", ".har", ".pem", ".key", ".p12", ".pfx", ".keystore")
# Domain harus dimulai huruf: "click@8.6.0.dev" (nama paket SBOM) bukan email.
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z][A-Za-z0-9.-]*\.[A-Za-z]{2,24}")
# Nomor HP/NIK hanya ditandai bila ada penanda field — pola telanjang terlalu banyak salah positif
# (angka 16 digit di SBOM/semgrep bukan NIK).
PHONE_CTX_RE = re.compile(r"(?i)(?:phone|telepon|telp|hp|whatsapp|\bwa\b|mobile)[\"'\s:=]{1,6}(?:\+62|62|0)8[1-9][0-9]{7,10}")
NIK_CTX_RE = re.compile(r"(?i)\bnik\b[\"'\s:=]{1,6}\d{16}")
SAFE_EMAIL = ("@example.", "@users.noreply", "@schema", "git@github.com", "noreply@",
              "@anthropic.com", "@pypi.org", "@npmjs.com", "you@", "@localhost", "@portal.local",
              "@anantara.local", "npm-oidc-no-reply@github.com")


def sh(args: list[str]) -> str:
    return subprocess.run(args, capture_output=True, text=True).stdout


def tracked_files(root: str) -> list[str]:
    out = sh(["git", "-C", root, "ls-files", "-z"])
    return [p for p in out.split("\0") if p]


def load_baseline(root: str) -> dict:
    p = os.path.join(root, "platform", "hygiene-baseline.json")
    if not os.path.exists(p):
        return {"max_size_kb": 512, "allowed_large": [], "allowed_pii": [], "structure_dirs": []}
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def scan_text(path: str) -> str | None:
    if os.path.splitext(path)[1].lower() not in TEXT_EXT:
        return None
    try:
        if os.path.getsize(path) > 2 * 1024 * 1024:
            return None
        with open(path, encoding="utf-8", errors="ignore") as fh:
            return fh.read()
    except OSError:
        return None


def run(root: str) -> dict:
    baseline = load_baseline(root)
    max_bytes = int(baseline.get("max_size_kb", 512)) * 1024
    allowed_large = set(baseline.get("allowed_large") or [])
    allowed_pii = {row["path"] for row in (baseline.get("allowed_pii") or []) if row.get("path")}
    files = tracked_files(root)

    fails: list[dict] = []
    warns: list[dict] = []

    for rel in files:
        full = os.path.join(root, rel)
        if not os.path.isfile(full):
            continue

        # R1 — ukuran
        size = os.path.getsize(full)
        if size > max_bytes:
            row = {"rule": "R1_big_file", "path": rel, "detail": f"{size / 1024:.0f} KB > {max_bytes // 1024} KB"}
            (warns if rel in allowed_large else fails).append(row)

        # R2 — jenis berkas terlarang
        low = rel.lower()
        base = os.path.basename(low)
        if low.endswith(FORBIDDEN_SUFFIX) or base == ".env" or re.match(r"^id_(rsa|ed25519)", base):
            fails.append({"rule": "R2_forbidden_file", "path": rel, "detail": "jenis berkas terlarang di git"})

        # R3 — PII / kontak di artefak
        text = scan_text(full)
        if text:
            hits = []
            for m in EMAIL_RE.finditer(text):
                addr = m.group(0)
                # RFC 2606: .example/.test/.invalid/.localhost tidak mungkin PII nyata
                if addr.rsplit(".", 1)[-1].lower() in {"example", "test", "invalid", "localhost"}:
                    continue
                if not any(s in addr for s in SAFE_EMAIL):
                    hits.append(addr)
            hits.extend(m.group(0) for m in PHONE_CTX_RE.finditer(text))
            hits.extend(m.group(0) for m in NIK_CTX_RE.finditer(text))
            if hits:
                uniq = sorted(set(hits))[:3]
                row = {"rule": "R3_pii", "path": rel, "detail": f"{len(set(hits))} pola: {', '.join(uniq)}"}
                (warns if rel in allowed_pii else fails).append(row)

    # R4 — direktori artefak besar tanpa indeks
    for d in baseline.get("structure_dirs") or []:
        d_full = os.path.join(root, d)
        if not os.path.isdir(d_full):
            continue
        n = sum(1 for f in files if f.startswith(d + "/"))
        has_index = any(f in (f"{d}/INDEX.md", f"{d}/index.json") for f in files)
        if n > 20 and not has_index:
            warns.append({"rule": "R4_no_index", "path": d, "detail": f"{n} berkas ter-lacak tanpa INDEX.md"})

    # R5 — lisensi (keputusan Owner, jadi WARN bukan FAIL)
    if not any(os.path.exists(os.path.join(root, p)) for p in ("LICENSE", "LICENSE.md", "LICENSE.txt")):
        warns.append({"rule": "R5_no_license", "path": "LICENSE",
                      "detail": "belum ada lisensi root — blocker komersial (audit B-1)"})

    return {"root": root, "checked": len(files), "fails": fails, "warns": warns}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Gerbang higiene repo SDB")
    ap.add_argument("--root", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    ap.add_argument("--json", action="store_true", help="keluaran JSON")
    args = ap.parse_args(argv)

    result = run(os.path.abspath(args.root))
    if args.json:
        print(json.dumps(result, indent=1))
    else:
        print(f"hygiene: {result['checked']} berkas ter-lacak")
        for f in result["fails"]:
            print(f"  FAIL {f['rule']:18s} {f['path']} — {f['detail']}")
        for w in result["warns"]:
            print(f"  WARN {w['rule']:18s} {w['path']} — {w['detail']}")
        verdict = "PASS" if not result["fails"] else "FAIL"
        print(f"hygiene: {verdict} ({len(result['fails'])} FAIL, {len(result['warns'])} WARN)")
    return 1 if result["fails"] else 0


if __name__ == "__main__":
    sys.exit(main())
