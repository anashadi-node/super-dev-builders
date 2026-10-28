# ADR-0006 — Worker: klaim atomik, lease, dan penyelesaian tepat sekali

Status: diterima · 2026-10-29

## Konteks

Job yang dicatat tanpa dieksekusi hanya demo. Tapi worker menciptakan dua risiko uang:
**eksekusi ganda** (dua worker menagih satu job) dan **job menggantung** (worker mati setelah klaim,
kredit pelanggan tertahan selamanya).

## Keputusan

1. **Klaim atomik**: `SELECT` job tertua berstatus `queued`, lalu `UPDATE … WHERE status='queued'`
   di dalam `BEGIN IMMEDIATE`; hanya jika `rowcount == 1` klaim dianggap sah. Worker lain mendapat
   `None`. SQLite mengunci penulis, jadi tidak ada dua klaim bersamaan.
2. **Lease berbatas waktu** (default 120 s): worker wajib `heartbeat` untuk memperpanjang. Lease
   kedaluwarsa → job kembali ke antrean (`attempts` bertambah). Setelah `max_attempts` (default 3)
   → `failed` + kredit dilepas.
3. **Penyelesaian tepat sekali**: `finish_job` hanya menerima status `queued|running`, dan billing
   `settle` idempoten lewat `job_charges` (PK `job_id`). Retry penyelesaian tidak menagih dua kali.
4. **Budget ditegakkan dua arah**: token (dipotong ke budget, status `budget_exceeded`) dan
   wall-clock (`time.monotonic`, bukan waktu sistem yang bisa mundur).
5. **Executor adalah fungsi murni** `job -> ExecutionResult`; worker tidak tahu isi pekerjaan.
   Ini yang membuat worker bisa diuji tanpa jaringan dan membuat executor produksi (skill/REA)
   bisa dipasang tanpa mengubah penagihan.
6. **Worker berjalan lintas tenant** dengan `X-Worker-Key` terpisah dari API key tenant.

## Konsekuensi

- Antrean masih tabel SQLite: cukup untuk ribuan job/hari pada satu node. Skala horizontal butuh
  Postgres (`SELECT … FOR UPDATE SKIP LOCKED`) dengan semantik yang sama.
- Belum ada prioritas, kuota per-worker, dead-letter terpisah, atau eksekusi tersandbox.
- Menjalankan lebih dari satu proses worker pada satu DB aman (diuji), tetapi satu DB = satu host.
