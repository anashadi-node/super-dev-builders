#!/usr/bin/env python3
"""Buat paket bukti RECON (tahap 01B) untuk target rt-rw-portal.

Menghasilkan (jalur persis yang diminta scripts/workflow_run.py):
  normalized/rt-rw-portal/inventory.json
  evidence/rt-rw-portal/source-inventory.json
  evidence/rt-rw-portal/test-baseline.json
  evidence/rt-rw-portal/identity-scan.json

Sifat bukti: dihitung dari disk (hash sha256, hitungan, tanggal), bukan diketik
manusia. Dijalankan ulang = angka berubah bila berkas berubah, jadi bukti ini
tidak bisa "menua" tanpa terlihat.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

WIB = timezone(timedelta(hours=7))
PROYEK = Path("/home/anashadi/rt-rw-portal")
ECO = Path("/home/anashadi/super-dev-builders")
TARGET = "rt-rw-portal"

ABAIKAN = {".git", "__pycache__", ".pytest_cache", "node_modules", "dist", ".venv"}
# Berkas penjaga: MEMANG memuat token terlarang (itu daftar larangannya).
PENJAGA = {
    "tests/test_no_customer_traces.py",
    "scripts/sapu_identitas_pilot.py",
    "tests/test_demo.py",
}
# Keluaran build (tidak diserahkan): masih memuat nama paket lama.
DIBANGUN = ("android/android/app/build/", "dist/", "__pycache__/", ".pytest_cache/")
# Catatan historis (disamarkan 2026-10-10; temuan/angka/tanggal tidak diubah).
INTERNAL = ("reports/", "verification/")


def kategori(rel: str) -> str:
    if rel in PENJAGA:
        return "penjaga"
    if any(rel.startswith(d) or f"/{d}" in rel for d in DIBANGUN):
        return "dibangun"
    if rel.startswith(INTERNAL) or re.search(r"AUDIT-MENYELURUH|LAPORAN-VERSI-2|WORKLOG", rel):
        return "internal"
    return "terkirim"


# Token identitas pelanggan yang wajib nol di artefak kirim (selaras penjaga tes).
TOKEN_IDENTITAS = [
    "⟨identitas-07⟩", "⟨identitas-08⟩", "⟨identitas-12⟩", "⟨identitas-05⟩", "⟨identitas-15⟩",
    "⟨identitas-06⟩", "⟨identitas-01⟩", "⟨identitas-03⟩", "⟨identitas-11⟩",
    "⟨identitas-09⟩", "⟨identitas-19⟩", "⟨identitas-16⟩", "⟨identitas-02⟩",
]


def berkas_proyek() -> list[Path]:
    out = []
    for p in PROYEK.rglob("*"):
        if not p.is_file():
            continue
        if any(b in p.parts for b in ABAIKAN):
            continue
        out.append(p)
    return sorted(out)


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for blok in iter(lambda: f.read(1 << 16), b""):
            h.update(blok)
    return h.hexdigest()


def git(*arga: str) -> str:
    try:
        r = subprocess.run(["git", "-C", str(PROYEK), *arga],
                           capture_output=True, text=True, timeout=60)
        return r.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def main() -> int:
    now = datetime.now(WIB).isoformat(timespec="seconds")
    berkas = berkas_proyek()

    # --- evidence: inventaris berkas sumber ---
    per_kategori: dict[str, int] = {}
    total_byte = 0
    daftar = []
    for p in berkas:
        rel = p.relative_to(PROYEK).as_posix()
        kategori_berkas = rel.split("/")[0] if "/" in rel else "(akar)"
        per_kategori[kategori_berkas] = per_kategori.get(kategori_berkas, 0) + 1
        ukuran = p.stat().st_size
        total_byte += ukuran
        daftar.append({"path": rel, "bytes": ukuran, "sha256": sha256(p)})

    sumber = {
        "dibuat": now,
        "target": TARGET,
        "commit": git("rev-parse", "HEAD"),
        "branch": git("rev-parse", "--abbrev-ref", "HEAD"),
        "akar_proyek": str(PROYEK),
        "jumlah_berkas": len(daftar),
        "total_byte": total_byte,
        "per_kategori": dict(sorted(per_kategori.items())),
        "berkas": daftar,
    }
    tulis(ECO / f"evidence/{TARGET}/source-inventory.json", sumber)

    # --- evidence: baseline uji ---
    uji = sorted((PROYEK / "tests").glob("test_*.py"))
    jumlah_uji = 0
    for f in uji:
        jumlah_uji += len(re.findall(r"^\s*def test_", f.read_text(encoding="utf-8"), re.M))
    modul = sorted((PROYEK / "real_system").glob("*.py"))
    baris = sum(len(m.read_text(encoding="utf-8").splitlines()) for m in modul)
    baseline = {
        "dibuat": now,
        "target": TARGET,
        "commit": git("rev-parse", "HEAD"),
        "berkas_uji": len(uji),
        "fungsi_uji": jumlah_uji,
        "daftar_berkas_uji": [f.name for f in uji],
        "modul_produk": len(modul),
        "baris_modul_produk": baris,
        "cara_jalan": "docker run --rm --network none --user <uid>:<gid> -v <salinan>:/w -w /w rt-rw-portal-evidence:1 python -m pytest tests/ -q",
    }
    tulis(ECO / f"evidence/{TARGET}/test-baseline.json", baseline)

    # --- evidence: scan identitas pelanggan ---
    temuan = []
    diperiksa = 0
    dilewati: dict[str, int] = {}
    for p in berkas:
        rel = p.relative_to(PROYEK).as_posix()
        kat = kategori(rel)
        if kat in {"penjaga", "dibangun"}:
            dilewati[kat] = dilewati.get(kat, 0) + 1
            continue
        if not (p.suffix.lower() in {".py", ".md", ".html", ".js", ".css", ".json",
                                     ".txt", ".sh", ".gradle", ".xml", ".yml", ".yaml",
                                     ".service", ".conf"} or p.name == "Caddyfile"):
            continue
        diperiksa += 1
        teks = p.read_text(encoding="utf-8", errors="ignore").lower()
        for token in TOKEN_IDENTITAS:
            if token in teks:
                temuan.append({"path": rel, "kategori": kat, "token": token,
                               "jumlah": teks.count(token)})
    scan = {
        "dibuat": now,
        "target": TARGET,
        "commit": git("rev-parse", "HEAD"),
        "berkas_diperiksa": diperiksa,
        "dilewati": dilewati,
        "alasan_lewati": {
            "penjaga": "berkas penjaga memang memuat token terlarang (daftar larangannya sendiri)",
            "dibangun": "keluaran build/gradle (gitignored, tidak diserahkan) — masih memuat nama paket lama",
            "internal": "catatan historis; identitas disamarkan 2026-10-10 (temuan/angka/tanggal tidak diubah)",
        },
        "token_dicari": TOKEN_IDENTITAS,
        "temuan": temuan,
        "ringkas_per_kategori": {},
        "kesimpulan": "BERSIH di berkas terkirim & internal" if not temuan else f"{len(temuan)} temuan",
        "cara_ulang": "python3 scripts/sapu_identitas_pilot.py && python3 tools/buat-inventaris.py",
        "risiko_sisa": [
            "berkas gambar (reports/*.png, verification/*.png) TIDAK dipindai — tangkapan layar bisa memuat nama tenant pilot secara visual",
            "android/android/app/build/ masih memuat nama paket lama (regenerasi build Android akan membersihkannya)",
        ],
    }
    per_kat: dict[str, int] = {}
    for t in temuan:
        per_kat[t["kategori"]] = per_kat.get(t["kategori"], 0) + 1
    scan["ringkas_per_kategori"] = per_kat
    tulis(ECO / f"evidence/{TARGET}/identity-scan.json", scan)

    # --- normalized: ringkasan yang dirujuk workflow_run.py ---
    ringkas = {
        "target": TARGET,
        "dibuat": now,
        "commit": git("rev-parse", "HEAD"),
        "branch": git("rev-parse", "--abbrev-ref", "HEAD"),
        "jumlah_berkas_proyek": len(daftar),
        "modul_produk": baseline["modul_produk"],
        "berkas_uji": baseline["berkas_uji"],
        "fungsi_uji": baseline["fungsi_uji"],
        "identitas_pelanggan": scan["kesimpulan"],
        "bukti": {
            "inventaris_sumber": "evidence/rt-rw-portal/source-inventory.json",
            "baseline_uji": "evidence/rt-rw-portal/test-baseline.json",
            "scan_identitas": "evidence/rt-rw-portal/identity-scan.json",
            "gate0_verdict": "reports/rt-rw-portal/gate0-verdict.json",
        },
        "verifikasi_ulang": "python3 runs/rt-rw-portal/tools/buat-inventaris.py",
    }
    tulis(ECO / f"normalized/{TARGET}/inventory.json", ringkas)

    print(f"berkas proyek   : {len(daftar)} ({total_byte/1024/1024:.1f} MB)")
    print(f"modul / baris   : {baseline['modul_produk']} / {baseline['baris_modul_produk']}")
    print(f"berkas uji      : {baseline['berkas_uji']} ({baseline['fungsi_uji']} fungsi)")
    print(f"identitas pilot : {scan['kesimpulan']} (diperiksa {diperiksa} berkas)")
    print(f"commit          : {sumber['commit'][:12]} @ {sumber['branch']}")
    return 0


def tulis(jalur: Path, data: dict) -> None:
    jalur.parent.mkdir(parents=True, exist_ok=True)
    jalur.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"  tulis {jalur.relative_to(ECO)}")


if __name__ == "__main__":
    raise SystemExit(main())
