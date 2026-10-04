---
name: rollback-and-recovery
description: "Use when planning deploy or after failure. Backup-verify, rollback, restore, health."
version: 1.0.0
author: Super Dev Builders Ecosystem
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [rollback, recovery, backup, reliability, postmortem]
    divisions: [D10]
    related_skills: [ci-cd-release-gate, database-migration-safety]
---


# Rollback & Recovery

Kemampuan kembali ke kondisi aman adalah syarat release, bukan tambahan. Deploy tanpa rollback = tidak boleh.

## Prosedur perencanaan (sebelum deploy)
1. Identifikasi titik aman: tag/commit, image digest, snapshot DB, konfigurasi sebelumnya.
2. Verifikasi **kemampuan** backup, bukan hanya keberadaannya: uji restore ke environment terpisah.
3. Tulis prosedur rollback langkah demi langkah (perintah nyata, bukan "kembalikan versi lama").
4. Tentukan KPI pemulihan: RTO (waktu), RPO (kehilangan data yang dapat diterima), dan siapa yang memutuskan.
5. Tentukan pemicu rollback yang terukur: error rate, latensi p95, kegagalan smoke test, anomali data.

## Prosedur saat kegagalan
1. **Hentikan** penyebaran (jangan menambah perubahan saat sistem tidak stabil).
2. Nyatakan status: apa yang rusak, sejak kapan, dampak, hipotesis awal (tanpa menebak).
3. Pilih jalur: rollback aplikasi, rollback data (perhatikan kompatibilitas skema dua arah), atau perbaikan cepat
   — perbaikan cepat hanya bila kecil, teruji, dan risiko lebih rendah dari rollback.
4. Jalankan pemulihan; verifikasi health + smoke test.
5. Pasca-kejadian: akar masalah (bukan menyalahkan), perbaikan permanen, tambahan test/gate.

## Aturan
- Migrasi DB: skema harus kompatibel dengan versi aplikasi sebelumnya (expand-contract) agar rollback mungkin.
- Tidak ada penghapusan data sebagai langkah pemulihan tanpa backup terverifikasi.
- Semua tindakan recovery dicatat (perintah, waktu, hasil) untuk audit.

## Output
- `docs/runbooks/rollback-<layanan>.md`, `reports/incident-<tanggal>.md`
