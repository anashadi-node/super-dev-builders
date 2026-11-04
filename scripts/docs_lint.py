#!/usr/bin/python3
"""Gerbang konsistensi dokumen: indeks, rujukan mati, format generate, klaim angka.

Kenapa ada: `docs/INDEX.md` §"Aturan menambah dokumen" mewajibkan setiap dokumen baru
terindeks dan melarang `.html`/`.pdf` hasil generate disimpan di repo (ADR-0002).
Sebelum skrip ini ada, aturan itu hanya prosa — audit 2026-11-04 menemukan 11 dokumen
`docs/*.md` tanpa entri indeks, 3 PDF hasil generate masih terlacak, dan README
mengklaim "kini 39" padahal registry berisi 40 custom skill. Aturan tanpa gerbang
adalah hiasan; skrip ini membuatnya bisa gagal.

Pemakaian: python3 scripts/docs_lint.py [--root DIR] [--json]
Exit: 0 bersih, 1 ada pelanggaran.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sdb_common import load_yaml

# Dokumen HTML hasil generate yang SENGAJA dilacak agar bisa dibaca langsung dari repo
# (keputusan ADR-0008). Daftar ini harus eksplisit: berkas HTML baru tidak boleh lolos
# diam-diam, dan setiap entri wajib punya alasan.
ALLOWLIST = os.path.join("platform", "docs-html-allowlist.json")

# Rujukan di tabel indeks yang menunjuk pola/glob sengaja dilewati — bukan tautan tunggal.
GLOB_CHARS = ("*", "{", "}")

INDEX_MIN_RULE = 1  # minimal satu entri per dokumen; tidak ada batas atas


def _git_files(root: str, *patterns: str) -> list[str]:
    try:
        out = subprocess.run(
            ["git", "-C", root, "ls-files", *patterns],
            check=False, capture_output=True, text=True, timeout=30,
        ).stdout
    except (OSError, subprocess.SubprocessError):  # repo tanpa git = tanpa data terlacak
        return []
    return [line.strip() for line in out.splitlines() if line.strip()]


def _read(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return ""


def _index_refs(index_text: str) -> list[str]:
    """Ambil kandidat rujukan dari sel tabel indeks (`...`) yang menunjuk berkas konkret.

    Token yang hanya berupa ekstensi (`.md`, `.yaml`) adalah prosa, bukan tautan — dilewati.
    Pola glob (`*.md`, `{a,b}.md`) juga dilewati: bukan satu berkas yang bisa diperiksa.
    """
    refs = []
    for token in re.findall(r"`([^`]+)`", index_text):
        token = token.strip()
        if not token.endswith((".md", ".yaml", ".json", ".schema.json")):
            continue
        if any(ch in token for ch in GLOB_CHARS):
            continue
        if os.path.basename(token).startswith("."):
            continue
        refs.append(token)
    return refs


def _custom_skill_count(root: str) -> int | None:
    reg = load_yaml(os.path.join(root, "registry", "skills.yaml")) or {}
    if isinstance(reg, list):
        return len(reg)
    custom = reg.get("custom") if isinstance(reg, dict) else None
    return len(custom) if isinstance(custom, list) else None


def lint(root: str) -> dict:
    errors: list[str] = []
    warnings: list[str] = []
    docs_dir = os.path.join(root, "docs")
    index_path = os.path.join(docs_dir, "INDEX.md")
    index_text = _read(index_path)
    if not index_text:
        return {"errors": ["docs/INDEX.md tidak ditemukan atau kosong"], "warnings": [], "stats": {}}

    # 1. Setiap docs/**/*.md (kecuali indeks + arsip) wajib dirujuk indeks.
    docs_md = []
    for base, dirs, files in os.walk(docs_dir):
        dirs[:] = sorted(d for d in dirs if d != "archive")
        for name in sorted(files):
            if name.endswith(".md"):
                rel = os.path.relpath(os.path.join(base, name), docs_dir).replace(os.sep, "/")
                docs_md.append(rel)
    for rel in docs_md:
        if rel == "INDEX.md":
            continue
        # ADR diindeks lewat nomornya (ADR-0008) karena tabel indeks menautkan nomor, bukan nama berkas.
        if rel.startswith("adr/"):
            nomor = re.match(r"(\d{4})-", os.path.basename(rel))
            if nomor and f"ADR-{nomor.group(1)}" in index_text:
                continue
        if os.path.basename(rel) not in index_text:
            errors.append(f"dokumen tanpa entri indeks: docs/{rel}")

    # 2. Rujukan indeks tidak boleh mati (fail-closed: lebih baik ribut daripada tautan hantu).
    #    Rujukan ditulis relatif terhadap docs/ ATAU akar repo (README platform, notices).
    for ref in sorted(set(_index_refs(index_text))):
        kandidat = (os.path.normpath(os.path.join(docs_dir, ref)), os.path.normpath(os.path.join(root, ref)))
        if not any(os.path.exists(k) for k in kandidat):
            errors.append(f"rujukan indeks mati: {ref}")

    # 3. PDF hasil generate tidak boleh terlacak (ADR-0002).
    for path in _git_files(root, "*.pdf"):
        errors.append(f"PDF hasil generate terlacak: {path} — sumber .md sudah ada, PDF untuk dibaca saja")

    # 4. HTML hasil generate hanya boleh terlacak bila ada di allowlist berjustifikasi.
    allow: dict[str, str] = {}
    allow_path = os.path.join(root, ALLOWLIST)
    raw = json.loads(_read(allow_path) or "{}")
    for item in raw.get("files") or []:
        if isinstance(item, dict) and item.get("path"):
            allow[item["path"]] = item.get("reason") or ""
    tracked_html = [p for p in _git_files(root, "*.html") if p.startswith(("docs/", "reports/"))]
    for path in tracked_html:
        if path not in allow:
            errors.append(f"HTML hasil generate terlacak tanpa izin: {path} — daftarkan di {ALLOWLIST} atau "
                          f"pindahkan ke object store")
        elif not allow[path].strip():
            warnings.append(f"{path}: allowlist tanpa alasan tertulis")
    for path in allow:
        if path not in tracked_html:
            warnings.append(f"{ALLOWLIST}: entri usang (berkas tidak terlacak lagi): {path}")

    # 5. Klaim jumlah skill di README harus sama dengan registry (klaim yang tidak diukur = iklan).
    readme = _read(os.path.join(root, "README.md"))
    claim = re.search(r"kini\s+(\d+)", readme)
    n_custom = _custom_skill_count(root)
    if claim and n_custom is not None and int(claim.group(1)) != n_custom:
        errors.append(f"README mengklaim 'kini {claim.group(1)}' skill, registry berisi {n_custom}")

    # 6. Repo resmi harus tertaut di README (permintaan Owner 2026-11-04: mudah ditemukan).
    if "github.com/anashadi-node/super-dev-builders" not in readme:
        errors.append("README tidak memuat tautan repo resmi github.com/anashadi-node/super-dev-builders")

    return {
        "errors": errors,
        "warnings": warnings,
        "stats": {"docs_md": len(docs_md) - 1, "html_dilacak": len(tracked_html), "html_diizinkan": len(allow),
                  "custom_skill": n_custom, "klaim_readme": int(claim.group(1)) if claim else None},
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Gerbang konsistensi dokumen SDB")
    ap.add_argument("--root", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    result = lint(args.root)
    result["ok"] = not result["errors"]
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"docs_lint: {'PASS' if result['ok'] else 'FAIL'}")
        s = result["stats"]
        if s:
            print(f"  dokumen md: {s['docs_md']} | html terlacak: {s['html_dilacak']} "
                  f"(diizinkan {s['html_diizinkan']}) | custom skill: {s['custom_skill']} "
                  f"(klaim README: {s['klaim_readme']})")
        for e in result["errors"]:
            print(f"  ERROR: {e}")
        for w in result["warnings"]:
            print(f"  WARN: {w}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
