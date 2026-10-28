#!/usr/bin/python3
"""Verdict keamanan (tahap 10b) — SATU-SATUNYA produsen reports/security-verdict.json.

MENGAPA ADA
-----------
`workflows/release-gate.yaml` mensyaratkan artefak `reports/security-verdict.json`
dengan `verdict: PASS`, tetapi tidak ada satu pun skrip di toolchain yang
menghasilkannya: gerbang menuntut artefak yang tidak punya produsen. Akibatnya satu-
satunya cara "lulus" adalah menulis berkas itu dengan tangan — persis yang dilarang
`on_fail: dilarang menandai PASS manual`.

Skrip ini menutup celah itu: PASS HANYA bisa keluar dari eksekusi alat nyata.
Tidak ada opsi --force, --override, atau --accept: kalau salah satu kanal gagal atau
tidak bisa dijalankan, hasilnya FAIL atau BLOCKED.

Kanal (fail-closed kalau berkas alat tidak ada ⇒ BLOCKED, bukan lewat):
  1. tools/scan-keamanan.sh   — 5 alat: semgrep, syft, trivy, ruff, scan rahasia
                                 (+ kanal privasi-media di dalamnya)
  2. tools/scan-privasi-media.py — kanal identitas atas berkas media TERLACAK git
                                 (0 bersih; 1 temuan baru; 2 tak terverifikasi; 3 terbuka)

Verdict: PASS bila SEMUA kanal keluar 0; FAIL bila ada kanal keluar != 0;
BLOCKED (exit 2) bila alat hilang/tidak dapat dijalankan — "tidak diperiksa" tidak
pernah boleh berubah menjadi "bersih".

Pakai: /usr/bin/python3 scripts/security_verdict.py <slug> [--run-dir DIR] [--out FILE]
Exit : 0 PASS, 1 FAIL, 2 BLOCKED.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sdb_common import now_iso, repo_path, validate_slug, write_json

DEFAULT_TIMEOUT_S = 1800


def _channel_specs(tools_dir: str) -> list[dict]:
    """Kanal yang dikenali, beserta jalur alatnya. Ketiadaan berkas = BLOCKED."""
    return [
        {
            "name": "scan-keamanan",
            "path": os.path.join(tools_dir, "scan-keamanan.sh"),
            "args": ["{project}"],
            "runner": ["/bin/bash"],
            "arti": "SAST semgrep + SBOM syft + kerentanan trivy + ruff + scan rahasia + privasi media",
        },
        {
            "name": "privasi-media",
            "path": os.path.join(tools_dir, "scan-privasi-media.py"),
            "args": ["{project}"],
            "runner": [sys.executable],
            "arti": "identitas pelanggan pada berkas media yang terlacak git",
        },
    ]


def run_channel(spec: dict, project: str, log_dir: str, timeout: int) -> dict:
    name = spec["name"]
    if not os.path.isfile(spec["path"]):
        return {"name": name, "status": "BLOCKED", "exit_code": None,
                "reason": f"alat tidak ada: {spec['path']} — tidak diperiksa bukan berarti bersih"}
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, f"security-{name}-{time.strftime('%Y%m%d-%H%M%S')}.log")
    cmd = list(spec["runner"]) + [spec["path"]] + [a.format(project=project) for a in spec["args"]]
    started = time.monotonic()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
        code, out, err = proc.returncode, proc.stdout or "", proc.stderr or ""
    except (subprocess.TimeoutExpired, OSError) as exc:
        with open(log_path, "w", encoding="utf-8") as handle:
            handle.write(f"GAGAL menjalankan {cmd}: {exc}\n")
        return {"name": name, "status": "BLOCKED", "exit_code": None, "log": log_path,
                "reason": f"alat tidak dapat dijalankan: {exc}"}
    with open(log_path, "w", encoding="utf-8") as handle:
        handle.write(f"$ {' '.join(cmd)}\n\n{out}\n--- stderr ---\n{err}\n")
    tail = [ln for ln in out.strip().splitlines() if ln.strip()][-1:] or [""]
    status = "PASS" if code == 0 else "FAIL"
    return {"name": name, "status": status, "exit_code": code, "log": log_path,
            "seconds": round(time.monotonic() - started, 1), "last_line": tail[0][:300],
            "arti": spec["arti"]}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Verdict keamanan dari eksekusi alat nyata")
    ap.add_argument("target_pos", nargs="?", help="slug target (runs/<slug>)")
    ap.add_argument("--target", default=None, help="slug target (sama dengan posisional)")
    ap.add_argument("--run-dir", default=None, help="akar run dir (menimpa resolusi slug)")
    ap.add_argument("--tools-dir", default=None, help="direktori alat (default <run>/tools)")
    ap.add_argument("--project", default=None, help="akar proyek yang dipindai (default /home/anashadi/<slug>)")
    ap.add_argument("--out", default=None, help="keluaran verdict (default <run>/reports/security-verdict.json)")
    ap.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_S)
    args = ap.parse_args(argv)

    slug = args.target or args.target_pos
    if args.run_dir:
        run_dir = os.path.abspath(args.run_dir)
    elif slug:
        try:
            validate_slug(slug)
        except ValueError as exc:
            print(f"FATAL: {exc}", file=sys.stderr)
            return 2
        run_dir = repo_path("runs", slug)
    else:
        print("FATAL: butuh <slug> atau --run-dir", file=sys.stderr)
        return 2
    if not os.path.isdir(run_dir):
        print(f"FATAL: run dir tidak ada: {run_dir}", file=sys.stderr)
        return 2

    tools_dir = args.tools_dir or os.path.join(run_dir, "tools")
    project = args.project or os.path.join(os.path.expanduser("~"), slug or os.path.basename(run_dir))

    checks = [run_channel(spec, project, os.path.join(run_dir, "logs"), args.timeout)
              for spec in _channel_specs(tools_dir)]
    blocked = [c for c in checks if c["status"] == "BLOCKED"]
    failed = [c for c in checks if c["status"] == "FAIL"]
    verdict = "PASS" if not blocked and not failed else ("BLOCKED" if blocked else "FAIL")
    exit_code = {"PASS": 0, "FAIL": 1, "BLOCKED": 2}[verdict]

    result = {
        "gate": "security-verdict",
        "verdict": verdict,
        "checked_at": now_iso(),
        "project": project,
        "run_dir": run_dir,
        "policy": "PASS hanya dari eksekusi alat nyata; tidak ada jalur manual/--force",
        "checks": checks,
        "blocking": [{"name": c["name"], "reason": c.get("reason") or f"exit {c['exit_code']}: {c.get('last_line','')}"}
                     for c in blocked + failed],
    }
    out = args.out or os.path.join(run_dir, "reports", "security-verdict.json")
    write_json(out, result)

    print(f"security verdict: {verdict}  ({out})")
    for c in checks:
        detail = c.get("reason") or f"exit={c['exit_code']} detik={c.get('seconds')} | {c.get('last_line','')}"
        print(f"  {c['status']:<7} {c['name']:<14} {detail}")
    if verdict != "PASS":
        print("  tindakan: perbaiki temuan pada kanal di atas; PASS tidak dapat ditandai manual")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
