# Runtime SDB — worker (Fase 2b)

```
python3 -m sdb_platform.runtime.worker --db data/control.db --once        # kerjakan 1 job lalu keluar
python3 -m sdb_platform.runtime.worker --db data/control.db --max-jobs 100 --poll 2
```

Worker membaca tabel `jobs` yang sama dengan control plane; tidak butuh HTTP. Endpoint worker di
control plane (`/v1/worker/claim`, `/heartbeat`, `/complete`) dipakai bila worker berjalan di host lain.

## Siklus satu job

1. `reap_expired()` — lease mati dikembalikan ke antrean / digagalkan + kredit dilepas.
2. `claim_next_job()` — atomik; `attempts += 1`, `lease_owner`, `lease_until` diisi.
3. `executor(job)` — fungsi murni, dibatasi `budget.tokens` dan `budget.seconds`.
4. `finish_job()` — status akhir, token dicatat, billing `settle` (sukses) atau `release` (gagal/batal).
5. Artefak hasil didaftarkan lewat `register_artifact` (wajib status redaksi, URI object store).

## Invarian yang diuji (`tests/test_billing_worker.py`)

| Invarian | Uji |
|---|---|
| Dua worker tidak bisa mengklaim job yang sama | `test_dua_worker_paralel_tidak_dobel` |
| Worker mati → job diantre ulang, bukan hilang | `test_lease_kedaluwarsa_diantre_ulang` |
| Habis percobaan → failed + kredit kembali penuh | `test_lease_kedaluwarsa_habis_percobaan_jadi_gagal_dan_refund` |
| Sukses → ditagih sesuai pemakaian, sisa pesanan kembali | `test_sukses_menagih_pemakaian_dan_mengembalikan_sisa` |
| Token boros → `budget_exceeded`, tagihan tidak melebihi pesanan | `test_token_melebihi_budget_ditagih_sebatas_pesanan` |
| Batal → tidak ditagih | `test_cancel_job_antrean_melepas_kredit` |
| Ledger dirusak → rantai hash terdeteksi | `test_ledger_dirusak_terdeteksi` |

## Yang belum ada (jangan diklaim)

- executor produksi (menjalankan skill/REA sungguhan) — sekarang `echo_executor` untuk uji alur;
- prioritas antrean, dead-letter queue terpisah, batas konkurensi per tenant;
- sandbox/isolasi proses untuk kode yang dijalankan;
- heartbeat otomatis saat eksekusi panjang (sekarang heartbeat manual/lewat HTTP);
- metrik Prometheus dan auto-scale.

## Menjalankan dua worker

Aman pada satu DB (klaim atomik). Yang **tidak** aman: dua worker menulis artefak dengan nama sama —
karena itu `artifact.uri` wajib unik per job dan ditentukan pemanggil, bukan worker.
