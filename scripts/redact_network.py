#!/usr/bin/python3
"""Redaksi artefak network/trace sebelum masuk konteks LLM atau diserahkan.

Pemakaian:
    /usr/bin/python3 scripts/redact_network.py normalized/<t>/network.json            # cetak ke stdout
    /usr/bin/python3 scripts/redact_network.py <file.json> --in-place                # tulis balik + backup .raw
Exit: 0 sukses, 1 file tidak ditemukan.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sdb_common import now_iso, read_json, redact_obj


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Redact secrets/PII dari artefak network")
    ap.add_argument("file")
    ap.add_argument("--in-place", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    if not os.path.exists(args.file):
        print(f"file tidak ditemukan: {args.file}", file=sys.stderr)
        return 1
    data = read_json(args.file)
    key_hits, value_hits = [], []
    clean = redact_obj(data, key_hits, value_hits)
    out = json.dumps(clean, indent=2, ensure_ascii=False)
    if args.in_place:
        backup = args.file + ".raw"
        if not os.path.exists(backup):
            shutil.copyfile(args.file, backup)
        with open(args.file, "w", encoding="utf-8") as fh:
            fh.write(out + "\n")
        if not args.quiet:
            print(f"redacted in-place: {args.file} (backup mentah: {backup})")
    else:
        print(out)
    if not args.quiet:
        print(f"[{now_iso()}] keys diredaksi: {sorted(set(key_hits))} | nilai: {sorted(set(value_hits))}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
