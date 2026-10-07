#!/usr/bin/env python3
"""sdb — satu pintu masuk ekosistem Super Dev Builders.

Masalah yang diselesaikan: 17 skrip deterministik + installer tersebar, sehingga
"cara pakai" menuntut hafal nama file dan urutannya. CLI ini hanya PEMETAAN
nama-perintah -> skrip yang sudah ada; ia tidak menambah logika bisnis, tidak
membaca rahasia, dan tidak pernah mengubah artefak sendiri.

Aturan desain:
- Fail-closed: perintah tak dikenal -> exit 2 + usage (bukan tebakan).
- Exit code skrip anak diteruskan apa adanya (PASS=0 / FAIL=1 / BLOCKED=2),
  supaya `sdb gate` bisa dipakai di skrip lain tanpa menerjemahkan status.
- Interpreter = sys.executable yang sedang menjalankan CLI ini, supaya dependensi
  (PyYAML) konsisten dengan pemanggilnya.

Pemakaian:
    sdb list                 # daftar perintah (mesin-terbaca dengan --json)
    sdb doctor               # kapabilitas host
    sdb gate X               # Gate #0 (izin/scope) -> PASS/FAIL/BLOCKED
    sdb init X               # workspace target
    ...
Semua argumen setelah nama perintah diteruskan apa adanya ke skrip tujuan.
"""
from __future__ import annotations

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# nama perintah -> (jenis, tujuan RELATIF ROOT REPO, ringkasan)
# jenis "py"  : dijalankan dengan interpreter aktif sebagai python <script>
# jenis "sh"  : dijalankan dengan bash <script>
# Catatan: jalur relatif ROOT (bukan relatif scripts/) — sebagian perintah menunjuk
# berkas di root repo (install.sh), dan pemetaan yang menebak 'scripts/' pernah lolos
# ke produksi; tes test_sdb_every_command_points_to_existing_script menjaganya.
COMMANDS: dict[str, tuple[str, str, str]] = {
    "doctor": ("py", "scripts/doctor.py", "kapabilitas host + drift skill + pin dependency"),
    "gate": ("py", "scripts/gate_check.py", "Gate #0 (otorisasi & scope) -> PASS/FAIL/BLOCKED"),
    "init": ("py", "scripts/init_target.py", "buat workspace target (evidence/normalized/...)"),
    "capture": ("py", "scripts/capture_web.py", "capture terkendali (wajib Gate #0 PASS)"),
    "redact": ("py", "scripts/redact_network.py", "redaksi rahasia pada artefak jaringan"),
    "normalize": ("py", "scripts/normalize_capture.py", "normalisasi artefak capture -> JSON"),
    "lint": ("py", "scripts/evidence_lint.py", "evidence lint (metadata, confidence, redaksi)"),
    "fidelity": ("py", "scripts/fidelity_compare.py", "bandingkan capture original vs rebuild"),
    "fidelity-report": ("py", "scripts/fidelity_report.py", "laporan fidelity 9 dimensi"),
    "release": ("py", "scripts/release_check.py", "release gate berbasis artefak"),
    "workflow": ("py", "scripts/workflow_run.py", "runner 16 tahap berbasis bukti"),
    "registry-lint": ("py", "scripts/registry_lint.py", "validasi registry skill/tool"),
    "scan": ("py", "scripts/third_party_scan.py", "pindai pola eksekusi/eksfiltrasi pihak ketiga"),
    "inventory": ("py", "scripts/inventory_ecosystem.py", "inventaris ekosistem"),
    "list-skills": ("py", "scripts/install_skills.py", "daftar/pasang skill ke profil"),
    "install": ("sh", "install.sh", "pasang skill + CLI ke host (dry-run default)"),
    "uninstall": ("sh", "uninstall.sh", "hapus pemasangan (dry-run default)"),
}

# Perintah yang argumennya perlu awalan eksplisit agar sama dengan CLI aslinya.
PREFIX: dict[str, list[str]] = {"list-skills": []}


def resolve(command: str) -> tuple[str, str, list[str]]:
    """Kembalikan (jenis, path absolut, args tetap) untuk sebuah perintah.

    Dipisah dari eksekusi supaya bisa diuji tanpa menjalankan apa pun.
    """
    if command not in COMMANDS:
        raise KeyError(command)
    kind, rel, _ = COMMANDS[command]
    return kind, os.path.join(ROOT, rel), list(PREFIX.get(command, []))


def usage() -> str:
    lines = ["sdb — satu pintu masuk ekosistem Super Dev Builders", "", "Perintah:"]
    width = max(len(k) for k in COMMANDS)
    for name in sorted(COMMANDS):
        lines.append(f"  {name:<{width}}  {COMMANDS[name][2]}")
    lines += ["", "Semua argumen setelah nama perintah diteruskan ke skrip tujuan."]
    lines += ["Contoh: sdb init sdb-local-demo", "        sdb gate sdb-local-demo", "        sdb workflow sdb-local-demo", "        sdb release sdb-local-demo"]
    return "\n".join(lines)


def run(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(usage())
        return 0 if argv else 2
    if argv[0] == "list":
        if "--json" in argv[1:]:
            import json

            print(json.dumps(
                [{"command": k, "kind": COMMANDS[k][0], "target": COMMANDS[k][1], "summary": COMMANDS[k][2]}
                 for k in sorted(COMMANDS)], indent=2, ensure_ascii=False))
        else:
            print(usage())
        return 0

    name, rest = argv[0], argv[1:]
    try:
        kind, path, fixed = resolve(name)
    except KeyError:
        print(f"sdb: perintah tidak dikenal: {name}", file=sys.stderr)
        print(usage(), file=sys.stderr)
        return 2
    if not os.path.isfile(path):
        print(f"sdb: skrip tujuan tidak ada: {path}", file=sys.stderr)
        return 2

    if kind == "sh":
        cmd = ["bash", path, *fixed, *rest]
    else:
        cmd = [sys.executable, path, *fixed, *rest]
    try:
        return subprocess.call(cmd, cwd=ROOT)
    except KeyboardInterrupt:
        return 130


def main(argv: list[str] | None = None) -> int:
    return run(list(sys.argv[1:] if argv is None else argv))


if __name__ == "__main__":
    raise SystemExit(main())
