#!/usr/bin/env python3
"""Triase temuan SAST terhadap baseline yang WAJIB beralasan dan berkedaluwarsa.

Kenapa ada: tanpa baseline, setiap repo akan selalu FAIL karena aturan seperti S603
(subprocess tanpa shell=True) dan S310 (urlopen) muncul ratusan kali pada pola yang
sah — sehingga temuan nyata tenggelam. Dengan baseline, yang dituntut bukan "nol
temuan", melainkan "setiap temuan sudah diputuskan oleh manusia, ada alasannya, dan
keputusan itu kedaluwarsa sehingga wajib ditinjau ulang".

Kontrak keluaran:
  0 = tidak ada temuan BARU (boleh ada temuan DITERIMA dan/atau baseline kedaluwarsa)
  1 = ada temuan BARU (belum diputuskan) -> gerbang menolak
  2 = alat/berkas rusak (fail-closed)

Baseline: JSON `{"aturan": [{"kode","berkas","sebab","pemilik","kedaluwarsa"}]}`.
`berkas` = pola fnmatch relatif terhadap akar proyek (mis. `scripts/*`).
Entri TANPA `sebab` atau TANPA `kedaluwarsa` diabaikan — baseline bukan jalan pintas.
"""
from __future__ import annotations

import argparse
import datetime
import fnmatch
import json
import os
import sys


def muat_temuan(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, list):
        raise ValueError(f"format temuan tidak dikenal: {path}")
    return data


def muat_baseline(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    aturan = data.get("aturan") if isinstance(data, dict) else None
    if not isinstance(aturan, list):
        raise ValueError(f"baseline tanpa daftar 'aturan': {path}")
    sah = []
    for a in aturan:
        if not isinstance(a, dict):
            continue
        if not (a.get("kode") and a.get("berkas") and a.get("sebab") and a.get("kedaluwarsa")):
            print(f"PERINGATAN baseline diabaikan (tak lengkap): {a!r}", file=sys.stderr)
            continue
        sah.append(a)
    return sah


def berlaku(aturan: dict, hari: str) -> bool:
    return str(aturan["kedaluwarsa"]) >= hari


def cocok(temuan: dict, aturan: dict, akar: str) -> bool:
    if temuan.get("code") != aturan["kode"]:
        return False
    rel = os.path.relpath(str(temuan.get("filename", "")), akar)
    return fnmatch.fnmatch(rel, aturan["berkas"])


def triase(temuan: list[dict], aturan: list[dict], akar: str, hari: str):
    baru, diterima, kedaluwarsa = [], [], set()
    for t in temuan:
        hit = [a for a in aturan if cocok(t, a, akar)]
        if not hit:
            baru.append(t)
            continue
        hidup = [a for a in hit if berlaku(a, hari)]
        if hidup:
            diterima.append((t, hidup[0]))
        else:
            for a in hit:
                kedaluwarsa.add((a["kode"], a["berkas"], a["kedaluwarsa"]))
            baru.append(t)
    return baru, diterima, sorted(kedaluwarsa)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("--temuan", required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--akar", default=".")
    ap.add_argument("--hari", default=datetime.date.today().isoformat())
    ap.add_argument("--ringkas", help="tulis ringkasan satu baris ke berkas ini")
    args = ap.parse_args(argv)

    try:
        temuan = muat_temuan(args.temuan)
        aturan = muat_baseline(args.baseline)
    except (OSError, ValueError) as exc:
        pesan = f"SAST TAK DIVERIFIKASI: {type(exc).__name__}: {exc}"
        print(pesan)
        if args.ringkas:
            open(args.ringkas, "w", encoding="utf-8").write(pesan + "\n")
        return 2

    akar = os.path.abspath(args.akar)
    baru, diterima, kedaluwarsa = triase(temuan, aturan, akar, args.hari)

    for a in kedaluwarsa:
        print(f"KEDALUWARSA {a[0]} {a[1]} (batas {a[2]}) — perpanjang dengan alasan baru "
              f"atau perbaiki kodenya", file=sys.stderr)
    for t in baru[:20]:
        rel = os.path.relpath(str(t.get("filename", "")), akar)
        print(f"BARU {t.get('code')} {rel}:{(t.get('location') or {}).get('row')}", file=sys.stderr)
    if len(baru) > 20:
        print(f"... dan {len(baru) - 20} temuan baru lain", file=sys.stderr)

    baris = (f"baru={len(baru)} diterima={len(diterima)} kedaluwarsa={len(kedaluwarsa)} "
             f"(baseline {os.path.relpath(args.baseline, akar)})")
    print(baris)
    if args.ringkas:
        with open(args.ringkas, "w", encoding="utf-8") as fh:
            fh.write(baris + "\n")
    return 1 if baru else 0


if __name__ == "__main__":
    sys.exit(main())
