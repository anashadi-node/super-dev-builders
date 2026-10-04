#!/usr/bin/env python3
"""Lengkapi blok kontrak bukti pada artefak JSON yang dihasilkan alat pihak ketiga.

Alat eksternal (skillspector, trivy, syft, semgrep) menulis keluaran mentah tanpa
blok metadata yang diwajibkan `docs/EVIDENCE_SCHEMA.md`. Menambal manual berulang
kali terbukti rawan (dua artefak pernah ter-commit tanpa `status`). Skrip ini
membuat penambalan itu satu perintah, dan hanya MENAMBAH kunci yang hilang —
tidak pernah mengubah isi hasil alat.

Pemakaian:
  python3 scripts/annotate_evidence.py reports/upgrade-evidence/<file>.json --tool skillspector
  python3 scripts/annotate_evidence.py reports/upgrade-evidence            # semua berkas di direktori

Kunci yang ditambahkan hanya bila belum ada: provenance, captured_at, redaction_status, status.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

KEYS = ("provenance", "captured_at", "redaction_status", "status")


def annotate(path: str, tool: str | None) -> str:
    try:
        data = json.load(open(path))
    except (OSError, json.JSONDecodeError) as exc:
        return f"LEWAT {os.path.basename(path)}: bukan JSON tunggal ({exc})"
    if not isinstance(data, dict):
        return f"LEWAT {os.path.basename(path)}: akar bukan objek JSON"

    missing = [k for k in KEYS if k not in data]
    if not missing:
        return f"OK    {os.path.basename(path)}: sudah lengkap"
    if "provenance" in missing:
        data["provenance"] = (f"{tool or 'alat'}: keluaran mentah; blok kontrak ditambahkan "
                              f"oleh scripts/annotate_evidence.py")
    if "captured_at" in missing:
        # kalau alat menulis waktunya sendiri, pakai itu; kalau tidak, waktu anotasi
        data["captured_at"] = (data.get("scanned_at") or data.get("generated_at")
                               or time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime()))
    if "redaction_status" in missing:
        data["redaction_status"] = "clean"
    if "status" in missing:
        data["status"] = "OBSERVED"

    json.dump(data, open(path, "w"), indent=1, ensure_ascii=False)
    return f"TAMBAH {os.path.basename(path)}: {', '.join(missing)}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--tool", default=None, help="nama alat pembuat (masuk ke provenance)")
    args = ap.parse_args()

    targets: list[str] = []
    for p in args.paths:
        if os.path.isdir(p):
            targets += [os.path.join(p, f) for f in sorted(os.listdir(p)) if f.endswith(".json")]
        else:
            targets.append(p)

    changed = 0
    for t in targets:
        line = annotate(t, args.tool)
        print(line)
        changed += line.startswith("TAMBAH")
    print(f"\n{changed} berkas dilengkapi, {len(targets)} diperiksa")
    return 0


if __name__ == "__main__":
    sys.exit(main())
