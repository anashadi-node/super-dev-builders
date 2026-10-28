# Indeks `evidence/`

Bukti mentah/ternormalisasi per target. Wajib **redacted** sebelum masuk repo; lebih baik tidak masuk sama sekali.

| Subdir | Isi | Catatan |
|---|---|---|
| `oss-sb-agency/` | capture desktop & mobile (PNG), DOM, network | PNG >1 MB → baseline higiene; keluar ke object store Fase 1 |
| `rt-rw-portal/` | capture & evidence pilot portal | — |

## Aturan

1. Satu evidence = satu klaim; sebut label FACT/INFERRED/UNKNOWN (`docs/EVIDENCE_TAXONOMY.md`).
2. Data pribadi (email, nomor HP, NIK, token, cookie) **dilarang** — `make hygiene` menolak berkas baru.
3. Evidence besar (screenshot, HAR mentah) hidup di object store; repo hanya menyimpan yang kecil & penting.
4. Setiap berkas harus bisa ditelusuri ke job/pekerjaan yang menghasilkannya.
