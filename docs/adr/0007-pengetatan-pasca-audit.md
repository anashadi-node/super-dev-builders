# ADR-0007 — Pengetatan pasca-audit: siapa boleh menutup job, kapan uang bergerak

Status: diterima · 2026-10-29 · menggantikan sebagian ADR-0005 §hold/charge dan ADR-0006 §3

## Konteks

Audit fundamental 29 Okt (`reports/SDB_AUDIT_FUNDAMENTAL_20261029.md`) mereproduksi 26 cacat di
v0.5.0, 8 di antaranya menyangkut uang: tenant bisa menutup job yang sedang dikerjakan worker
(tagihan hilang), penutupan ke status antrean membuat job dikerjakan ulang gratis, worker lambat
bisa menimpa hasil worker baru, invoice tumpang-tindih menagih charge yang sama dua kali, dan cek
kuota/idempotensi berada di luar transaksi.

## Keputusan

1. **Penutupan job hanya dua pintu**: worker pemegang lease (`POST /v1/jobs/{id}/complete`) atau
   tenant lewat `POST /v1/jobs/{id}/cancel`. `POST /v1/jobs/{id}/finish` → `410 endpoint_removed`.
2. **`finish_job` atomik**: cek kepemilikan + status + UPDATE + gerak uang di satu `BEGIN IMMEDIATE`.
   Status tujuan wajib salah satu `succeeded|failed|blocked|budget_exceeded|cancelled`.
3. **Batal setelah kerja terjadi ditagih sebesar pemakaian.** Token yang sudah dibakar adalah biaya
   nyata ke penyedia LLM atas permintaan tenant. Batal sebelum diklaim → kredit utuh kembali.
4. **Batal + worker mati** → job langsung `cancelled` saat lease dipanen (dulu macet `queued`).
5. **Klaim hanya untuk tenant `active`**; tenant `deleted` → antrean ditutup + kredit dilepas.
6. **Fair-share**: klaim memilih tenant dengan job berjalan paling sedikit, lalu FIFO (`rowid`).
7. **Idempotensi jujur**: kunci sama + isi beda → `409 idempotency_conflict`.
8. **Invoice diterbitkan admin** (`POST /v1/admin/invoices`), periode wajib sudah tertutup dan tidak
   tumpang-tindih; `job_charges.ts` presisi mikrodetik untuk batas setengah-terbuka `[start, end)`.
9. **Ledger hash v2** (JSON kanonik, mengikat `entry_id` + `memo`); baris v1 lama tetap diverifikasi
   lewat kolom `hv`. `verify_chain` juga memeriksa kontinuitas `balance_after`/`held_after`.
10. **URI artefak wajib di ruang tenant** (`s3://<bucket>/<tenant_id>/…` atau `artifact://<tenant_id>/…`).
11. **Worker CLI wajib `--executor`**; `echo` (token fiktif yang tetap ditagih) dikunci di balik
    `SDB_ALLOW_ECHO_EXECUTOR=1`. Heartbeat otomatis di thread terpisah (interval lease/3).

## Konsekuensi

- Perubahan API tidak kompatibel → versi 0.6.0. Klien yang memakai `/finish` atau `POST /v1/invoices`
  harus pindah.
- Fair-share memakai subquery per kandidat: O(job antre) per klaim, memadai untuk SQLite satu node;
  versi Postgres perlu tabel hitungan `running` per tenant.
- DB v0.5.0 termigrasi otomatis (kolom `hv`, indeks baru); tidak ada data yang ditulis ulang.
