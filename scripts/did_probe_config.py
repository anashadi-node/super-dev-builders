#!/usr/bin/env python3
"""Turunkan state_probes JSON dari sumber target (bukan dikarang tangan).

Membaca ``PAGE_ROLES`` + ``ALL_ROLES`` + ``NAV`` dari ``src/dashboard.py`` lalu
menyusun matriks izin/tolak penuh untuk setiap peran, sehingga probe DID selalu
mencakup SELURUH pasangan peran x halaman — bukan subset yang kebetulan terbaca.

Pemakaian:
    python3 scripts/did_probe_config.py --source ~/villa-agency-os \
        --out platform/state_probes/villa-agency-os.json \
        --ports 8285-8290 --token-env-prefix VILLA_TOK_ \
        --case-id demo_case_rahma

Tanpa ``--case-id`` halaman detail kasus tidak diprobe sebagai 200 (memang tidak
ada id sah di dataset kosong); ia tetap muncul sebagai probe 404 di config lain.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PERAN = ("reservation", "operations", "finance", "owner", "auditor", "gm")


def _isi_blok(teks: str, kepala: str) -> list[str]:
    """Ambil baris-baris di dalam literal yang diawali ``kepala`` di kolom 0.

    Parser berbasis baris, bukan regex DOTALL: regex ``.*?`` pernah berhenti di
    blok MappingProxyType pertama (PAGE_ROLE_BY_CANONICAL) sehingga matriks
    peran terbaca kosong — probe izin jadi 0 tanpa error.
    """
    baris = teks.splitlines()
    mulai = next((i for i, b in enumerate(baris) if b.startswith(kepala)), None)
    if mulai is None:
        return []
    isi: list[str] = []
    for b in baris[mulai + 1:]:
        if b.startswith(")") or b.startswith("]"):
            break
        isi.append(b)
    return isi


def _blok_peta(teks: str, nama: str) -> dict[str, list[str]]:
    """``{"command_center": ["owner", ...], ...}`` dari PAGE_ROLES di sumber."""
    peta: dict[str, list[str]] = {}
    for b in _isi_blok(teks, f"{nama}:"):
        m = re.match(r'\s*"([a-z_]+)":\s*(ALL_ROLES|\([^)]*\))\s*,?\s*$', b)
        if not m:
            continue
        kunci, nilai = m.group(1), m.group(2)
        if nilai == "ALL_ROLES":
            peta[kunci] = list(PERAN)
        else:
            peta[kunci] = [x.strip().strip('"') for x in nilai.strip("()").split(",") if x.strip()]
    return peta


def baca_matriks(source: str) -> tuple[dict[str, list[str]], dict[str, str]]:
    teks = open(os.path.join(source, "src", "dashboard.py"), encoding="utf-8").read()
    peta = _blok_peta(teks, "PAGE_ROLES")
    if not peta:
        raise SystemExit("did_probe_config: PAGE_ROLES tidak ditemukan/kosong")

    rute: dict[str, str] = {}
    for b in _isi_blok(teks, "NAV:"):
        m = re.match(r'\s*\("([a-z_]+)",\s*"(/[^"]*)"\)\s*,?\s*$', b)
        if m:
            rute[m.group(1)] = m.group(2)
    if not rute:
        raise SystemExit("did_probe_config: NAV tidak ditemukan")
    return peta, rute


def susun(peta: dict[str, list[str]], rute: dict[str, str], ports: dict[str, int],
          token_ref: dict[str, str], case_id: str | None, label: str,
          skema_auth: str = "Bearer") -> dict:
    roles = []
    for peran in PERAN:
        izin = sorted(p for p, ok in peta.items() if peran in ok and p in rute)
        tolak = sorted(p for p, ok in peta.items() if peran not in ok and p in rute)
        halaman = [rute[p] for p in izin]
        if case_id and "case_detail" in peta and peran in peta["case_detail"]:
            halaman.append(f"/cases/{case_id}")
        roles.append({
            "name": peran,
            "base_url": f"http://127.0.0.1:{ports[peran]}",
            "auth": {"type": "header", "name": "Authorization",
                     "value": f"{skema_auth} {token_ref[peran]}" if skema_auth else token_ref[peran]},
            "pages": sorted(set(halaman)),
            "denied": [{"path": rute[p], "expect_status": 403} for p in tolak],
        })
    role_owner = next(r for r in roles if r["name"] == "owner")
    role_owner["error_probes"] = [
        {"path": "/kasus-tidak-ada", "method": "GET", "expect_status_min": 400},
        {"path": "/cases/xxx-tidak-ada", "method": "GET", "expect_status_min": 400},
    ]
    return {
        "schema": "sdb.did.state_probes/1",
        "target": label,
        "base_url": f"http://127.0.0.1:{ports['owner']}",
        "empty_markers": ["Tidak ada data", "Belum ada data", "belum ada data", "No data available"],
        "roles": roles,
        "anon": [{"path": "/", "expect_status": 401}],
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Susun probe state dari matriks peran target")
    ap.add_argument("--source", default=os.path.expanduser("~/villa-agency-os"))
    ap.add_argument("--out", required=True)
    ap.add_argument("--label", default="villa-agency-os")
    ap.add_argument("--ports", default="8285-8290", help="rentang port, mis. 8285-8290")
    ap.add_argument("--token-prefix", default="tok")
    ap.add_argument("--token-env-prefix", default="VILLA_TOK_")
    ap.add_argument("--case-id", help="id kasus sah untuk probe detail (dataset berisi)")
    ap.add_argument("--auth-scheme", default="Bearer",
                    help="prefiks skema header Authorization (kosongkan bila target memakai token mentah)")
    a = ap.parse_args(argv)

    awal, akhir = (int(x) for x in a.ports.split("-"))
    ports = {p: awal + i for i, p in enumerate(PERAN)}
    if akhir - awal + 1 != len(PERAN):
        raise SystemExit("did_probe_config: rentang port harus 6 angka")
    token_ref = {p: f"${{{a.token_env_prefix}{p.upper()}}}" for p in PERAN}

    peta, rute = baca_matriks(a.source)
    cfg = susun(peta, rute, ports, token_ref, a.case_id, a.label, a.auth_scheme)
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, indent=2, ensure_ascii=False)
        fh.write("\n")

    total_izin = sum(len(r["pages"]) for r in cfg["roles"])
    total_tolak = sum(len(r["denied"]) for r in cfg["roles"])
    semua = len(PERAN) * len(rute)
    print(f"did_probe_config: {len(PERAN)} peran · {len(rute)} rute NAV · "
          f"{total_izin} probe izin · {total_tolak} probe tolak · "
          f"pasangan peran x rute={semua} (izin+tolak={total_izin + total_tolak})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
