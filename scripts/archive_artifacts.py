#!/usr/bin/env python3
"""Arsipkan artefak kerja keluar dari git (ADR-0002), dengan bukti hash.

Kenapa: 24 MB `runs/`, 5 MB `evidence/`, 4 MB `verification/` dilacak git. Git menyimpan setiap versi
dan tidak punya retensi/akses per tenant. Skrip ini menyalin artefak ke arsip di luar repo, memverifikasi
sha256 per berkas, lalu (dengan --apply) melepasnya dari indeks git **tanpa menghapus berkas kerja**.

Pakai:
    python3 scripts/archive_artifacts.py --dir runs evidence --dest ~/sdb-archive/2026-10-26        # uji
    python3 scripts/archive_artifacts.py --dir runs evidence --dest ~/sdb-archive/2026-10-26 --apply
    python3 scripts/archive_artifacts.py --verify --dest ~/sdb-archive/2026-10-26                  # cek ulang

Jaminan: tidak ada penghapusan berkas. `--apply` hanya `git rm --cached` + entri .gitignore.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import shutil
import subprocess
import sys

SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", "node_modules"}
KEEP_IN_REPO = {"INDEX.md"}          # indeks tetap di git sebagai peta
GITIGNORE_MARK = "# artefak kerja — diarsipkan ke luar git (ADR-0002), jangan dilacak lagi"


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def repo_root() -> str:
    out = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                         capture_output=True, text=True, check=True).stdout.strip()
    return out


def walk(root: str, rel_dir: str) -> list[str]:
    base = os.path.join(root, rel_dir)
    found = []
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            if name in KEEP_IN_REPO:
                continue
            full = os.path.join(dirpath, name)
            found.append(os.path.relpath(full, root))
    return sorted(found)


def archive(root: str, dir_rel: str, dest: str) -> dict:
    files = walk(root, dir_rel)
    target = os.path.join(dest, dir_rel)
    os.makedirs(target, exist_ok=True)
    entries, copied, bytes_total, mismatch = [], 0, 0, []
    for rel in files:
        src = os.path.join(root, rel)
        out = os.path.join(dest, rel)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        shutil.copy2(src, out)
        src_hash, dst_hash = sha256(src), sha256(out)
        size = os.path.getsize(src)
        bytes_total += size
        entries.append({"path": rel, "size": size, "sha256": src_hash})
        copied += 1
        if src_hash != dst_hash:
            mismatch.append(rel)
    manifest = {
        "archived_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "dir": dir_rel,
        "file_count": copied,
        "bytes": bytes_total,
        "sha256_manifest": "",
        "files": entries,
    }
    body = json.dumps(entries, sort_keys=True, separators=(",", ":")).encode()
    manifest["sha256_manifest"] = hashlib.sha256(body).hexdigest()
    with open(os.path.join(target, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=1, ensure_ascii=False)
        fh.write("\n")
    return {"dir": dir_rel, "files": copied, "bytes": bytes_total, "mismatch": mismatch, "manifest": manifest}


def verify_archive(dest: str) -> int:
    fails = 0
    for entry in sorted(os.listdir(dest)):
        mpath = os.path.join(dest, entry, "manifest.json")
        if not os.path.exists(mpath):
            continue
        with open(mpath, encoding="utf-8") as fh:
            manifest = json.load(fh)
        bad = []
        for f in manifest["files"]:
            p = os.path.join(dest, f["path"])
            if not os.path.exists(p) or sha256(p) != f["sha256"]:
                bad.append(f["path"])
        status = "OK  " if not bad else "FAIL"
        print(f"arsip: {status} {entry}: {manifest['file_count']} berkas, {manifest['bytes'] / 1e6:.1f} MB"
              + ("" if not bad else f", {len(bad)} rusak"))
        fails += bool(bad)
    return 1 if fails else 0


def apply_detach(root: str, dirs: list[str]) -> None:
    for d in dirs:
        subprocess.run(["git", "-C", root, "rm", "-r", "-q", "--cached", "--", d], check=False)
    gi = os.path.join(root, ".gitignore")
    with open(gi, encoding="utf-8") as fh:
        content = fh.read()
    if GITIGNORE_MARK not in content:
        with open(gi, "a", encoding="utf-8") as fh:
            fh.write(f"\n{GITIGNORE_MARK}\n")
            for d in dirs:
                fh.write(f"/{d}/\n")
            fh.write("!runs/INDEX.md\n!evidence/INDEX.md\n")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Arsip artefak SDB (ADR-0002)")
    ap.add_argument("--dir", nargs="+", default=[], help="direktori relatif di repo: runs evidence ...")
    ap.add_argument("--dest", default=os.path.expanduser("~/sdb-archive"))
    ap.add_argument("--apply", action="store_true", help="lepas dari indeks git + tulis .gitignore")
    ap.add_argument("--verify", action="store_true", help="verifikasi arsip yang sudah ada")
    args = ap.parse_args(argv)

    if args.verify:
        return verify_archive(os.path.abspath(args.dest))

    root = repo_root()
    dest = os.path.abspath(args.dest)
    if dest.startswith(root + os.sep):
        print("arsip: TOLAK — tujuan arsip tidak boleh di dalam repo", file=sys.stderr)
        return 2
    if not args.dir:
        print("arsip: TOLAK — sebutkan --dir", file=sys.stderr)
        return 2

    results = [archive(root, d, dest) for d in args.dir]
    total_files = sum(r["files"] for r in results)
    total_bytes = sum(r["bytes"] for r in results)
    bad = [r["dir"] for r in results if r["mismatch"]]
    for r in results:
        print(f"arsip: {r['dir']}: {r['files']} berkas, {r['bytes'] / 1e6:.1f} MB, "
              f"sha256 {r['manifest']['sha256_manifest'][:12]}, mismatch {len(r['mismatch'])}")
    print(f"arsip: total {total_files} berkas / {total_bytes / 1e6:.1f} MB -> {dest}")

    if bad:
        print(f"arsip: BATAL apply — hash tidak cocok pada {bad}", file=sys.stderr)
        return 1
    if not args.apply:
        print("arsip: mode uji. Jalankan ulang dengan --apply untuk melepas dari indeks git.")
        return 0

    apply_detach(root, args.dir)
    print("arsip: dilepas dari indeks git (berkas kerja TIDAK dihapus). Verifikasi: git status")
    return 0


if __name__ == "__main__":
    sys.exit(main())
