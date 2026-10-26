# platform/ — Kontrak Produk SDB

Direktori ini **bukan** tempat kode bisnis. Isinya hanya **kontrak**: bentuk data, batas paket, dan
aturan yang harus dipatuhi control plane serta worker ketika SDB dijual sebagai langganan.

Alasan keberadaannya: audit 2026-10-26 (`reports/SDB_DOUBLE_AUDIT_20261026.md`) menemukan produk SaaS-nya
belum ada — tidak ada tenancy, kuota, atau penyimpanan artefak. Kontrak ditulis **sebelum** kode supaya
implementasi pertama tidak mengunci keputusan yang salah.

## Isi

| Berkas | Fungsi | Kenapa wajib |
|---|---|---|
| `schemas/tenant.schema.json` | bentuk tenant + `limits` + `isolation` | tanpa limits tidak ada penegakan kuota; tanpa isolation tidak ada janji privasi |
| `schemas/job.schema.json` | unit pekerjaan + `budget` + `idempotency_key` | mencegah biaya tak terbatas dan job ganda |
| `schemas/artifact.schema.json` | artefak + `sha256` + `redaction_status` + retensi | artefak tanpa status redaksi tidak boleh dipublikasikan |
| `schemas/examples/*.json` | contoh valid, dipakai tes | kontrak yang tidak pernah diuji = dokumentasi |
| `hygiene-baseline.json` | utang teknis artefak yang diakui | gerbang bisa FAIL untuk pelanggaran baru tanpa menutup mata pada masa lalu |
| `packs/` (menyusul Fase 1) | manifest paket langganan: daftar skill + versi + hash | mengganti model "salin skill ke tiap profil" |

## Aturan

1. **Tidak ada data pelanggan di sini.** Hanya skema, contoh sintetis, dan manifest.
2. Setiap perubahan skema = perubahan kontrak: naikkan versi paket, catat di `docs/adr/`.
3. Field baru wajib punya alasan operasional (kuota, biaya, isolasi, audit). Tanpa itu, tolak.
4. ID memakai ULID ber-prefix (`t_`, `j_`, `a_`) — sortable dan tidak membocorkan jumlah tenant.
5. Jalankan `python3 -m pytest tests/test_platform_contracts.py -q` setelah mengubah apa pun di sini.

## Verifikasi

```bash
/usr/bin/python3 -m pytest tests/test_platform_contracts.py -q
make hygiene
```
