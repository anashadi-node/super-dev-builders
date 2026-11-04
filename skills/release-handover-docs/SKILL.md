---
name: release-handover-docs
description: "README, runbook, release notes at delivery"
version: 1.0.0
author: Super Dev Builders Ecosystem
license: BUSL-1.1
platforms: [linux, macos]
metadata:
  hermes:
    tags: [documentation, handover, readme, runbook, release-notes]
    divisions: [D11, D10]
    related_skills: [architecture-docs, rollback-and-recovery, ci-cd-release-gate]
---


# Release Handover Docs

Dokumen agar orang lain bisa menjalankan, memelihara, dan memulihkan sistem tanpa bertanya ke pembuatnya.

## Isi wajib (template: `templates/handover.md`)
1. Ringkasan: sistem ini apa, untuk siapa, masalah apa yang diselesaikan.
2. Cara menjalankan: prasyarat, instalasi, perintah menjalankan, perintah test (perintah nyata yang sudah diuji).
3. Arsitektur ringkas + tautan ADR.
4. Operasional: environment (nama variabel, tanpa nilai), health check, log/metrik, backup, alert.
5. Rollback: prosedur langkah demi langkah + titik aman terakhir + RTO.
6. Known limitations & technical debt: jujur, dengan dampak dan rencana.
7. Riwayat rilis + status gate.

## Aturan
- Setiap perintah di dokumen wajib **sudah pernah dijalankan** (bukan copy-paste harapan).
- Jangan pernah menempelkan nilai rahasia; hanya nama variabel dan cara mengisinya.
- Sertakan bagian "yang belum diverifikasi" secara eksplisit — lebih baik jujur daripada menyesatkan.
- Handover tanpa rollback + tanpa cara menjalankan test = belum selesai (gate docs FAIL).

## AGENTS.md
Bila repo akan dikerjakan agent: tulis `AGENTS.md` pendek-faktual: perintah build/test, konvensi, larangan,
area berisiko, dan tautan dokumen. Ringkas — ini hemat konteks, bukan tempat curhat arsitektur.

## Output
- `README.md`, `docs/runbooks/*.md`, `CHANGELOG.md`, `AGENTS.md`, `reports/handover-<tanggal>.md`

## Paket dokumen 3 format (MD + HTML + PDF)
Untuk permintaan "dokumen lengkap" dari pemilik: hasilkan `.md` (sumber), `.html` (TOC + anchor), `.pdf` (cetak).
Generator repo: `python3 scripts/build_tutorial.py <md> --html <out.html> --pdf <out.pdf> --title ... --desc ...`.

Pitfall yang sudah menimpa proyek ini:
- **repo_hygiene R1 menolak berkas > 512 KB** (`platform/hygiene-baseline.json`). PDF hasil Chromium sering
  600–700 KB → `make test` FAIL di `tests/test_repo_hygiene.py`. Kompres dulu:
  `gs -sDEVICE=pdfwrite -dPDFSETTINGS=/ebook -dNOPAUSE -dQUIET -dBATCH -sOutputFile=out.pdf in.pdf`
  (23 halaman → ~320 KB, teks tetap tajam), lalu render ulang halaman 1 untuk cek visual.
- **Tabel panjang terpotong ke halaman berikutnya menyisakan setengah halaman kosong** bila CSS cetak memakai
  `table{page-break-inside:avoid}`. Pakai `table{page-break-inside:auto}`, `tr,td,th{page-break-inside:avoid}`,
  `thead{display:table-header-group}`, dan `.table-wrap{overflow:visible}` agar header berulang dan tabel mengalir.
- Daftar isi panjang wajar tumpah ke halaman 2 — bukan bug, tapi cek `pdftotext -f 2 -l 2` untuk memastikan
  item lanjutan benar-benar tercetak.

Verifikasi wajib sebelum menyerahkan: `pdfinfo` (jumlah halaman), hitung anchor vs href (broken link harus 0),
`pdftoppm` halaman 1 + satu halaman tabel lalu periksa visual, dan pastikan angka di dokumen diambil dari
perintah nyata (bukan ingatan) dengan menyertakan lampiran cara mengecek ulang.
