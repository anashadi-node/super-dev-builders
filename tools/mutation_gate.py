#!/usr/bin/env python3
"""Mutation smoke test untuk modul gerbang SDB.

Masalah yang diselesaikan: suite uji bisa hijau meski pemeriksaan keamanan
dimatikan. Skrip ini mematikan SATU pemeriksaan, menjalankan uji, lalu
mengembalikan berkas. Mutan yang "selamat" = regresi yang akan lolos CI.

Pemakaian:
    python3 tools/mutation_gate.py --list
    python3 tools/mutation_gate.py --run                 # semua mutan, seluruh tests/
    python3 tools/mutation_gate.py --run --fast          # hanya uji yang relevan (cepat)
    python3 tools/mutation_gate.py --run --only M1,M9
    python3 tools/mutation_gate.py --run --json reports/mutation.json

Kode keluar: 0 bila skor >= --min-score (default 90), 1 bila di bawah.
Berkas selalu dikembalikan (try/finally) dan hash awal diverifikasi sebelum
mutasi: kalau kode berubah sejak tabel ini ditulis, mutan ditandai STALE,
bukan diam-diam menguji hal lain.
"""
from __future__ import annotations

import argparse
import atexit
import hashlib
import json
import pathlib
import signal
import subprocess
import sys
import time

REPO = pathlib.Path(__file__).resolve().parents[1]
# Cadangan tahan-crash: `finally` tidak berjalan bila proses dibunuh SIGKILL/OOM.
# Sebelum memutasi, isi asli disimpan di sini; saat skrip dijalankan lagi, sisa
# cadangan dipulihkan lebih dulu (RECOVERED) supaya repo tidak tertinggal rusak.
BACKUP = REPO / ".mutation-backup"

# Setiap mutan: satu pemeriksaan keamanan dimatikan. `old` harus muncul tepat
# satu kali di berkas; kalau tidak, mutan dianggap STALE (kode sudah berubah).
MUTANTS: list[dict] = [
    {
        "id": "M1",
        "gate": "release_check: umur artefak",
        "file": "scripts/release_check.py",
        "old": 'if age_h > max_age:\n            failures.append({"gate": gate, "reason": f"artefak kedaluwarsa',
        "new": 'if False:\n            failures.append({"gate": gate, "reason": f"artefak kedaluwarsa',
        "tests": ["tests/test_scripts.py"],
    },
    {
        "id": "M2",
        "gate": "release_check: umur verdict",
        "file": "scripts/release_check.py",
        "old": 'if age_h > max_age:\n            failures.append({"gate": gate, "reason": f"verdict kedaluwarsa',
        "new": 'if False:\n            failures.append({"gate": gate, "reason": f"verdict kedaluwarsa',
        "tests": ["tests/test_scripts.py"],
    },
    {
        "id": "M3",
        "gate": "recon-forge: URL di allowed_targets",
        "file": "tools/recon-forge.py",
        "old": 'if not any(url.startswith(a.rstrip("/")) for a in allowed):',
        "new": "if False:",
        "tests": ["tests/test_recon_forge.py"],
    },
    {
        "id": "M4",
        "gate": "recon-forge: path di dalam akar izin",
        "file": "tools/recon-forge.py",
        "old": '    for root in roots:\n        if path == root or str(path).startswith(str(root) + os.sep):\n            return path',
        "new": '    for root in roots:\n        if True:\n            return path',
        "tests": ["tests/test_recon_forge.py"],
    },
    {
        "id": "M5",
        "gate": "gate_check: operator = pemilik",
        "file": "scripts/gate_check.py",
        "old": "elif operator != current_operator():",
        "new": "elif False:",
        "tests": ["tests/test_gate_check.py"],
    },
    {
        "id": "M6",
        "gate": "audit-log: prev_hash rantai",
        "file": "tools/audit-log.py",
        "old": 'if obj.get("prev_hash") != prev:',
        "new": "if False:",
        "tests": ["tests/test_scripts.py", "tests/test_gerbang_g1.py"],
    },
    {
        "id": "M7",
        "gate": "validate_slug: larangan '..'",
        "file": "scripts/sdb_common.py",
        "old": 'if not SLUG_RE.match(s) or ".." in s:',
        "new": "if not SLUG_RE.match(s):",
        "tests": ["tests/test_scripts.py"],
    },
    {
        "id": "M8",
        "gate": "capture_web: origin_allowed",
        "file": "scripts/capture_web.py",
        "old": "return o is not None and any(_origin(a) == o for a in allowed)",
        "new": "return True",
        "tests": ["tests/test_capture_scope.py"],
    },
    {
        "id": "M9",
        "gate": "capture_web: tolak redirect keluar scope",
        "file": "scripts/capture_web.py",
        "old": "if not origin_allowed(page.url, allowed):  # redirect keluar scope Gate #0",
        "new": "if False:  # redirect keluar scope Gate #0",
        "tests": ["tests/test_capture_scope.py"],
    },
    {
        "id": "M10",
        "gate": "release_check: verdict wajib PASS",
        "file": "scripts/release_check.py",
        "old": "if value not in allowed:",
        "new": "if False:",
        "tests": ["tests/test_scripts.py"],
    },
]


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:12]


def _backup_path(rel: str) -> pathlib.Path:
    return BACKUP / (rel.replace("/", "__") + ".json")


def backup_write(rel: str, original: str, sha: str) -> None:
    BACKUP.mkdir(exist_ok=True)
    meta = _backup_path(rel)
    (meta.with_suffix(".orig")).write_text(original, encoding="utf-8")
    meta.write_text(json.dumps({"file": rel, "sha_before": sha}), encoding="utf-8")
    atexit.register(backup_clear, rel)


def backup_clear(rel: str) -> None:
    meta = _backup_path(rel)
    for p in (meta, meta.with_suffix(".orig")):
        try:
            p.unlink()
        except FileNotFoundError:
            pass


def recover_stale(verbose: bool = True) -> list[str]:
    """Pulihkan berkas yang tertinggal termutasi oleh proses yang mati mendadak."""
    restored = []
    if not BACKUP.is_dir():
        return restored
    for meta in sorted(BACKUP.glob("*.json")):
        try:
            info = json.loads(meta.read_text(encoding="utf-8"))
            rel = info["file"]
            orig_path = meta.with_suffix(".orig")
            original = orig_path.read_text(encoding="utf-8")
        except (OSError, KeyError, json.JSONDecodeError):
            continue
        target = REPO / rel
        current = target.read_text(encoding="utf-8") if target.exists() else ""
        if _sha(current) != _sha(original):
            target.write_text(original, encoding="utf-8")
            restored.append(rel)
            if verbose:
                print(f"RECOVERED {rel} (dipulihkan dari cadangan mutasi)")
        backup_clear(rel)
    try:
        BACKUP.rmdir()
    except OSError:
        pass
    return restored


def run_mutant(m: dict, fast: bool, timeout: int) -> dict:
    path = REPO / m["file"]
    original = path.read_text(encoding="utf-8")
    started = time.time()
    base = {"id": m["id"], "gate": m["gate"], "file": m["file"], "sha_before": _sha(original)}
    count = original.count(m["old"])
    if count != 1:
        return {**base, "result": "STALE", "detail": f"pola muncul {count}x (harus 1)",
                "seconds": round(time.time() - started, 1)}
    try:
        backup_write(m["file"], original, base["sha_before"])
        path.write_text(original.replace(m["old"], m["new"], 1), encoding="utf-8")
        args = [sys.executable, "-m", "pytest", "-x", "-q", "-o", "addopts="]
        args += m["tests"] if fast else ["tests"]
        proc = subprocess.run(args, cwd=str(REPO), capture_output=True, text=True, timeout=timeout)
        killed = proc.returncode != 0
        tail = [ln for ln in proc.stdout.splitlines() if ln.strip()][-3:]
        return {**base, "result": "KILLED" if killed else "SURVIVED",
                "exit": proc.returncode, "detail": " | ".join(tail),
                "seconds": round(time.time() - started, 1)}
    except subprocess.TimeoutExpired:
        return {**base, "result": "TIMEOUT", "detail": f"uji > {timeout}s",
                "seconds": round(time.time() - started, 1)}
    finally:
        path.write_text(original, encoding="utf-8")
        if _sha(path.read_text(encoding="utf-8")) != base["sha_before"]:  # pragma: no cover
            raise SystemExit(f"GAGAL mengembalikan {m['file']} — periksa git diff!")
        backup_clear(m["file"])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Mutation smoke test modul gerbang")
    ap.add_argument("--list", action="store_true", help="cetak daftar mutan")
    ap.add_argument("--run", action="store_true", help="jalankan mutasi")
    ap.add_argument("--fast", action="store_true", help="hanya uji relevan per mutan")
    ap.add_argument("--only", default="", help="mis. M1,M9")
    ap.add_argument("--timeout", type=int, default=900)
    ap.add_argument("--min-score", type=float, default=90.0)
    ap.add_argument("--json", default="", help="tulis hasil ke berkas JSON")
    args = ap.parse_args(argv)

    # SIGTERM/SIGHUP diubah jadi KeyboardInterrupt: blok finally tetap mengembalikan berkas.
    # SIGKILL tidak bisa ditangkap — itu tugas cadangan .mutation-backup + recover_stale().
    def _term(_signum, _frame):
        raise KeyboardInterrupt

    for name in ("SIGTERM", "SIGHUP"):
        sig = getattr(signal, name, None)
        if sig is not None:
            signal.signal(sig, _term)
    recover_stale()

    if args.list or not args.run:
        for m in MUTANTS:
            print(f"{m['id']:>3}  {m['gate']:<45} {m['file']}")
        return 0

    wanted = {x.strip() for x in args.only.split(",") if x.strip()}
    picked = [m for m in MUTANTS if not wanted or m["id"] in wanted]
    results = []
    for m in picked:
        print(f"[{m['id']}] mematikan {m['gate']} …", flush=True)
        r = run_mutant(m, args.fast, args.timeout)
        print(f"      {r['result']:<9} {r['seconds']:>6}s  {r.get('detail', '')}", flush=True)
        results.append(r)

    scored = [r for r in results if r["result"] in ("KILLED", "SURVIVED")]
    killed = sum(1 for r in scored if r["result"] == "KILLED")
    score = round(100.0 * killed / len(scored), 1) if scored else 0.0
    summary = {"mutants": results, "killed": killed, "scored": len(scored),
               "score": score, "min_score": args.min_score, "fast": args.fast}
    print(f"\nmutation score: {killed}/{len(scored)} = {score}% (ambang {args.min_score}%)")
    if args.json:
        out = pathlib.Path(args.json)
        if not out.is_absolute():
            out = REPO / out
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"json: {out}")
    return 0 if score >= args.min_score else 1


if __name__ == "__main__":
    raise SystemExit(main())
