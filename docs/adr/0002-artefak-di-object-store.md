# ADR-0002 — Artefak pelanggan keluar dari git

**Status**: Accepted · **Tanggal**: 2026-10-26 · **Konteks**: audit ganda (A-1, B-4, H-2)

## Keputusan

Git hanya menyimpan kode, kontrak, dokumen, dan **contoh kecil**. Semua hasil pekerjaan (capture, evidence,
log, laporan generate, SBOM) disimpan di **object store** dengan prefix `tenant/<tenant_id>/<job_id>/`,
ber-hash, berstatus redaksi, dan punya masa retensi.

## Alasan

- Hari ini 20 MB artefak dilacak git (5 berkas >1 MB). Pertumbuhan terukur ±1,1 MB/hari untuk satu pilot →
  1.000 tenant ≈ 400 GB/tahun, dan git menyimpan setiap versi (tidak bisa dipangkas tanpa rewrite).
- Artefak memuat data pelanggan; repo produk bisa dibagikan ke kontraktor/auditor → risiko kebocoran.
- Object store memberi lifecycle policy, signed URL, dan penghapusan terjadwal — tiga hal yang tidak dimiliki git.

## Konsekuensi

- Repo tetap kecil (<10 MB target Fase 1) dan bisa di-clone cepat.
- Laporan yang selama ini ada di `runs/` harus diunggah + diverifikasi sha256 sebelum `git rm --cached`.
- Pembersihan riwayat (`git filter-repo`) dilakukan sekali, setelah arsip terverifikasi dan tag `v0.1.0` dibuat.
- Gerbang `make hygiene` memastikan tidak ada berkas baru >512 KB atau PII baru yang masuk.

## Alternatif yang ditolak

- **Git LFS**: menyelesaikan ukuran checkout, tidak menyelesaikan privasi, retensi, atau akses per tenant.
- **Biarkan di git sampai "nanti"**: setiap hari menambah biaya pembersihan riwayat yang tidak bisa dibatalkan.
