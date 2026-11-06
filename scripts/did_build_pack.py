#!/usr/bin/python3
"""Ubah handoff DID menjadi backlog Builders — dan tolak handoff yang belum layak dibangun.

Kenapa bukan sekadar `builders_ready: true`: bendera boolean bisa diakui benar tanpa
diperiksa. Alat ini menurunkan kesiapan menjadi enam aturan yang bisa dieksekusi
(B01..B06); bila satu saja gagal, keluar dengan kode 1 dan tidak menulis pack
kecuali `--allow-not-ready`. Jadi "siap dibangun" adalah hasil hitung, bukan pendapat.

Pemakaian:
  python3 scripts/did_build_pack.py --handoff runs/<t>/did/handoff.json \
      --out-dir runs/<t>/did [--allow-not-ready]
"""
from __future__ import annotations

import argparse
import json
import os
import sys

PRIORITAS = {"critical": "P0", "high": "P0", "medium": "P1", "low": "P2", "info": "P3"}


def periksa(handoff: dict) -> list[dict]:
    """B01..B06 — tiap temuan memuat kode, lulus/gagal, dan alasan yang bisa dibaca."""
    fitur = handoff.get("features") or []
    temuan = {f["id"]: f for f in handoff.get("findings") or []}
    ids_bukti = {e["id"]: e for e in handoff.get("evidence_manifest") or []}
    cek: list[dict] = []

    tanpa_tes = [f["id"] for f in fitur if f.get("priority") == "must" and not f.get("acceptance_tests")]
    cek.append({"kode": "B01", "nama": "fitur must punya acceptance test", "ok": not tanpa_tes,
                "detail": f"tanpa tes: {tanpa_tes}" if tanpa_tes else f"{len(fitur)} fitur diperiksa"})

    yatim = sorted({r for f in fitur for r in (f.get("findings") or []) if r not in temuan})
    cek.append({"kode": "B02", "nama": "rujukan temuan ada", "ok": not yatim,
                "detail": f"tak ditemukan: {yatim}" if yatim else "semua rujukan valid"})

    tanpa_bukti = sorted(t["id"] for t in temuan.values() if not t.get("evidence"))
    cek.append({"kode": "B03", "nama": "temuan punya alamat bukti", "ok": not tanpa_bukti,
                "detail": f"tanpa bukti: {tanpa_bukti}" if tanpa_bukti else f"{len(temuan)} temuan"})

    bukti_hilang = sorted(b for t in temuan.values() for b in t.get("evidence") or [] if b not in ids_bukti)
    cek.append({"kode": "B04", "nama": "alamat bukti ada di manifest", "ok": not bukti_hilang,
                "detail": f"tak terdaftar: {bukti_hilang}" if bukti_hilang else f"{len(ids_bukti)} entri manifest"})

    seeds = handoff.get("build_seeds") or {}
    kosong = [k for k in ("entities", "api", "states") if not seeds.get(k)]
    cek.append({"kode": "B05", "nama": "build_seeds terisi", "ok": not kosong,
                "detail": f"kosong: {kosong}" if kosong else "entitas/api/state terisi"})

    h = handoff.get("handoff") or {}
    siap = bool(h.get("builders_ready")) and int(h.get("blocking_unknowns") or 0) == 0
    cek.append({"kode": "B06", "nama": "bendera kesiapan konsisten", "ok": siap,
                "detail": f"builders_ready={h.get('builders_ready')} blocking={h.get('blocking_unknowns')}"})
    return cek


def bangun_pack(handoff: dict) -> dict:
    temuan = handoff.get("findings") or []
    tiket = []
    for t in temuan:
        if t.get("status") != "OBSERVED":
            continue
        pri = PRIORITAS.get(str(t.get("severity", "info")).lower(), "P2")
        if pri == "P3":
            continue
        tiket.append({"id": "T-" + t["id"], "dari_temuan": t["id"], "prioritas": pri,
                      "judul": t["claim"].split("—")[0].strip()[:120],
                      "detail": t["claim"],
                      "bukti": t.get("evidence") or []})
    tugas = []
    for f in handoff.get("features") or []:
        if not f.get("acceptance_tests"):
            continue
        tugas.append({"id": "W-" + f["id"], "fitur": f["name"], "prioritas": f.get("priority"),
                      "status_bukti": f.get("status"), "acceptance": f.get("acceptance_tests"),
                      "temuan_terkait": [x for x in (f.get("findings") or [])
                                        if any(x == t["dari_temuan"] for t in tiket)]})
    urut = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
    tiket.sort(key=lambda x: (urut[x["prioritas"]], x["id"]))
    return {"schema": "sdb.did.build_pack/1", "target": handoff.get("target"),
            "generated_from": "handoff.json",
            "tiket_perbaikan": tiket, "tugas_build": tugas,
            "ringkasan": {"p0": sum(1 for t in tiket if t["prioritas"] == "P0"),
                          "p1": sum(1 for t in tiket if t["prioritas"] == "P1"),
                          "p2": sum(1 for t in tiket if t["prioritas"] == "P2"),
                          "tugas": len(tugas)}}


def render_md(pack: dict, cek: list[dict]) -> str:
    tgt = pack.get("target") or {}
    nama = tgt.get("name") if isinstance(tgt, dict) else str(tgt)
    baris = [f"# Build pack — {nama}", "",
             "Diturunkan dari `handoff.json`; setiap tiket membawa alamat bukti.", "",
             "## Gerbang kesiapan", "", "| Kode | Aturan | Hasil | Detail |", "|---|---|---|---|"]
    for c in cek:
        baris.append(f"| {c['kode']} | {c['nama']} | {'PASS' if c['ok'] else 'FAIL'} | {c['detail']} |")
    baris += ["", f"## Tiket perbaikan ({len(pack['tiket_perbaikan'])})", ""]
    for t in pack["tiket_perbaikan"]:
        baris += [f"### {t['id']} · {t['prioritas']} · dari {t['dari_temuan']}", "",
                  t["detail"], "", f"Bukti: {', '.join(t['bukti'])}", ""]
    baris += ["## Tugas build", "", "| ID | Fitur | Prioritas | Tes penerimaan |", "|---|---|---|---|"]
    for w in pack["tugas_build"]:
        baris.append(f"| {w['id']} | {w['fitur']} | {w['prioritas']} | {len(w['acceptance'])} |")
    return "\n".join(baris) + "\n"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Handoff DID -> backlog Builders + gerbang kesiapan")
    p.add_argument("--handoff", required=True)
    p.add_argument("--out-dir", required=True)
    p.add_argument("--allow-not-ready", action="store_true")
    a = p.parse_args(argv)

    handoff = json.load(open(a.handoff, encoding="utf-8"))
    cek = periksa(handoff)
    gagal = [c for c in cek if not c["ok"]]
    if gagal and not a.allow_not_ready:
        for c in gagal:
            print(f"did_build_pack: {c['kode']} GAGAL — {c['nama']}: {c['detail']}", file=sys.stderr)
        return 1

    pack = bangun_pack(handoff)
    os.makedirs(a.out_dir, exist_ok=True)
    with open(os.path.join(a.out_dir, "build-pack.json"), "w", encoding="utf-8") as fh:
        json.dump(pack, fh, indent=1, ensure_ascii=False)
    with open(os.path.join(a.out_dir, "BUILD_PACK.md"), "w", encoding="utf-8") as fh:
        fh.write(render_md(pack, cek))
    r = pack["ringkasan"]
    print(f"did_build_pack: {'PASS' if not gagal else 'PASS (paksa)'} · {r['p0']} P0 · {r['p1']} P1 · "
          f"{r['p2']} P2 · {r['tugas']} tugas -> {a.out_dir}/BUILD_PACK.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
