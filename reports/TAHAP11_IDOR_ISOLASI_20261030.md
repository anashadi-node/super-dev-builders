# Tahap 11 — Uji IDOR & Isolasi Tenant (2026-10-30)

Lingkup: control plane SDB (`sdb_platform/control_plane/app.py`), seluruh rute yang
memakai identitas tenant. Metode: panggilan langsung `Api.handle` (tanpa socket) —
deterministik, cepat, tidak bergantung jaringan.

## Hasil: 11/11 lulus — tidak ditemukan IDOR

| # | Vektor | Harapan | Hasil |
|---|---|---|---|
| 1 | GET job tenant B dengan kunci A | 404 (bukan 403, tanpa bocor keberadaan) | LULUS |
| 2 | GET artefak job B dengan kunci A | larik kosong, bukan data B | LULUS |
| 3 | POST artefak ke job B dengan kunci A | ditolak 404; jumlah artefak B tidak berubah | LULUS |
| 4 | POST cancel job B dengan kunci A | 404; `cancel_requested` B tetap 0 | LULUS |
| 5 | GET billing/ledger/invoices/usage dengan kunci A | tidak memuat identifier B | LULUS |
| 6 | Job baru milik A | kuota/pemakaian B tidak berubah | LULUS |
| 7 | Kunci tenant ke 6 rute admin | 401 semua | LULUS |
| 8 | Kunci tenant ke 3 rute worker | 401 semua | LULUS |
| 9 | 7 varian kunci palsu (kosong, terpotong, spasi, huruf besar) | 401 semua | LULUS |
| 10 | Worker sah menyelesaikan job B | status B berubah, tenant lain tidak | LULUS |
| 11 | `idempotency_key` sama lintas tenant A & B | dua job berbeda, tidak saling replay | LULUS |

Berkas uji: `tests/test_idor_isolasi.py` (11 test).

## Dua kesalahan penulis uji yang ditemukan & diperbaiki (transparansi)

1. Rute status tenant yang benar adalah `/v1/admin/tenants/{id}/status`, bukan
   `/v1/tenants/{id}/status`. Kesalahan ada di uji, bukan di aplikasi — aplikasi
   mengembalikan 404 yang benar.
2. Invoice dengan `period_end` di masa depan ditolak `period_not_closed` — ini
   perilaku yang benar (mencegah pembekuan total). Uji diperbaiki memakai periode
   tertutup (Januari 2026).

Keduanya penting dicatat: tanpa dicatat, "11/11 lulus" bisa disalahartikan sebagai
"uji pertama langsung benar".

## Temuan residual (belum diperbaiki — di luar lingkup uji)

**R-11.1 — `worker_id` adalah identitas yang diakui sendiri (self-asserted).**
Semua worker memakai satu `X-Worker-Key` bersama; kepemilikan lease diperiksa dengan
`lease_owner == worker_id` (`store.py:390`, `store.py:506`). Worker yang mengetahui
`worker_id` worker lain dapat mengirim heartbeat atau `/complete` atas nama worker itu.
Dampak: worker tepercaya dapat mencuri lease worker lain.
Batas: ini batas kepercayaan internal (worker key tidak diberikan ke tenant).
Rekomendasi (belum dieksekusi): kunci worker per-proses + tabel `workers`, atau
token lease acak per klaim yang dikembalikan sekali dan wajib disertakan.
Keputusan: TIDAK diubah sekarang — perubahan skema butuh migrasi dan persetujuan.

**R-11.2 — Tidak ada uji beban/race pada klaim job lintas tenant.** `claim_next_job`
atomik per baris (UPDATE ... WHERE status='queued'), tetapi uji paralel multi-proses
belum dijalankan pada tahap ini. Sudah ada uji paralel SQLite di
`tests/test_audit_regressions.py`; khusus klaim lintas tenant belum.

## Kesimpulan

Isolasi tenant pada control plane **terbukti pada tingkat unit test** untuk 11 vektor
utama. Ini bukan jaminan bebas IDOR pada tingkat deploy (proxy, header rewriting,
cache) — itu lingkup tahap 12 (uji integrasi HTTP + reverse proxy).
