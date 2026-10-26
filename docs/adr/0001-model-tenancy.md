# ADR-0001 — Model tenancy: pool + namespace sebagai default

**Status**: Accepted · **Tanggal**: 2026-10-26 · **Konteks**: audit ganda `reports/SDB_DOUBLE_AUDIT_20261026.md` (B-2)

## Keputusan

SDB berjalan dengan model **pool + namespace**: satu database, satu bucket, satu armada worker; setiap baris,
berkas, dan kredensial wajib membawa `tenant_id`. **Sandbox per job** menjadi batas eksekusi. Model *silo*
(satu stack per tenant) hanya ditawarkan pada paket Enterprise.

## Alasan

1. Biaya per tenant paling rendah untuk mayoritas pelanggan; silo ×N mahal tanpa manfaat nyata bagi pengguna kecil.
2. Isolasi yang dijual bukan "satu server per pelanggan", tetapi **tiga batas yang ditegakkan**: `tenant_id` di
   repository, prefix bucket per tenant, dan vault per tenant.
3. Skala datang dari banyak worker kecil; satu stack per tenant akan mengunci kapasitas.

## Konsekuensi

- Query tanpa `tenant_id` harus **ditolak** di lapisan repository (bukan disiplin programmer).
- Wajib ada tes negatif: tenant A tidak boleh membaca artefak tenant B.
- Enterprise/silo menambah biaya operasional → harga kontrak, bukan harga paket.
- Migrasi tenant dari pool ke silo harus punya prosedur ekspor-impor yang diuji, bukan dilakukan manual.

## Alternatif yang ditolak

- **Silo untuk semua**: biaya dan kompleksitas meledak sebelum ada permintaan.
- **Database per tenant (pool lemah)**: migrasi skema menjadi N kali kerja; tidak sepadan di 1.000 tenant.
