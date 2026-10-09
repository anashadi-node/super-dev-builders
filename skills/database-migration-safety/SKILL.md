---
name: database-migration-safety
description: "Backup and rollback plan before schema changes"
version: 1.0.0
author: Super Dev Builders Ecosystem
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [database, migration, rollback, backup, safety]
    divisions: [D5, D8, D10]
    related_skills: [rollback-and-recovery, engineering-release-audit]
---


# Database Migration Safety

Perubahan skema/data adalah kelas risiko HIGH-CRITICAL: wajib backup, kompatibel dua arah, dan rollback nyata.

## Prosedur
1. Klasifikasikan: additive (aman) / transforming (perlu backfill) / destructive (drop, retype, rename).
2. Backup terverifikasi **sebelum** menjalankan apa pun; uji restore ke environment non-produksi.
3. Terapkan pola expand-contract:
   - expand: tambah kolom/tabel baru (nullable/default), deploy kode yang menulis keduanya;
   - migrate: backfill bertahap + validasi jumlah/checksum;
   - contract: hapus struktur lama hanya setelah tidak ada pembaca.
4. Batasi dampak: `NOT NULL` bertahap, hindari lock panjang (batch, `LIMIT`), indeks dibuat `CONCURRENTLY` bila didukung.
5. Rollback: siapkan skrip balik yang sudah diuji; dokumentasikan titik "tidak bisa balik".
6. Setelah migrasi: verifikasi di titik konsumsi (query aplikasi), bukan hanya status tabel.

## Larangan
- Tidak ada `DROP`/`TRUNCATE`/`ALTER` destruktif tanpa backup terverifikasi + approval manusia.
- Tidak ada migrasi otonom di produksi oleh agent (CRITICAL => prosedur manusia).
- Tidak ada perubahan tipe yang memotong data (mis. int->smallint) tanpa analisis jangkauan nilai.

## Output
- `migrations/<timestamp>_<name>.sql` + `migrations/<timestamp>_<name>.down.sql`
- `reports/migration-safety.md`: kelas, backup ref, rencana backfill, rollback, verifikasi.
