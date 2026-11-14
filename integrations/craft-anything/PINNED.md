# Craft Anything — Pinned & Verified Integration (PILOT)

Craft Anything — storytold/craft-anything, rilis `v0.3.0` (2026-11-02).
Paket: `craft-anything-0.3.0-linux-x86_64.tar.gz` (66.643.318 byte).
Terpasang: `~/.local/opt/craft-anything-0.3.0/` — TERISOLASI, tidak di PATH.
Pin mesin: `integrations/craft-anything/PINNED.json` (dibaca `recon-forge doctor` & `build`).
Uji asal: `docs/CRAFT_ANYTHING_PILOT_0.3.0.md`, bukti `evidence/craft-anything-pilot/`.

## Kenapa di-pin

`SHA256SUMS.txt` rilis hanya menjamin berkas tidak rusak saat diunduh — bukan jaminan isi.
Biner tidak ditandatangani dan sumbernya tidak publik. Karena itu yang dipanggil pipeline
harus persis biner yang pernah diuji, bukan sekadar "ada di folder bernama sama".

## Perilaku alat SDB

| Keadaan | `doctor` | `build --engine craft` |
|---|---|---|
| biner tidak ada | `found=false` | exit 3 + instruksi pemasangan |
| biner ada, sha256 = pin | `pinned=true` → `rebuild-combo=True` | jalan, mencatat sha256 ke audit-log |
| biner ada, sha256 ≠ pin | `pinned=false`, `note` menyebut beda | **exit 4, DITOLAK** |
| PINNED.json hilang | `pinned=false` | **exit 4, DITOLAK** |

Pencarian biner: PATH lebih dulu, lalu akar instalasi terisolasi
(`~/.local/opt/craft-anything-*/bin/`, `~/.local/bin/`, `vendor/`). Sebelum 2026-11-14
deteksi hanya lewat PATH sehingga `doctor` melaporkan "belum terpasang" padahal biner
sudah ada sejak 2026-11-04 — verdict palsu yang sudah diperbaiki.

## Batas pemakaian (mengikat, sama dengan dokumen pilot)

1. Read-only pelengkap. Bukan pengganti REA; bukan pemanggil pertama pada target baru.
2. Gate #0 tetap milik SDB — tanpa PASS tidak ada pemanggilan.
3. Tidak untuk target pihak ketiga selama audit sumber belum ada.
4. `--deep` = izin terpisah (`deep_analysis_allowed: true` di manifest).
5. Output build ke `targets/<target>/`, tidak boleh menyentuh `evidence/<target>/` (Zona A).
6. Bila pilot dihentikan: hapus `~/.local/opt/craft-anything-0.3.0` + `_karantina`, dan
   hapus berkas ini + `PINNED.json`. Tidak ada layanan atau entri PATH yang tertinggal.
