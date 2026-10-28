# Indeks `runs/`

Hasil pekerjaan per target/pilot. **Status: transisi** — direktori ini akan keluar dari git
(ADR-0002) setelah diarsipkan ke object store dengan verifikasi sha256.

| Subdir | Isi | Periode |
|---|---|---|
| `rt-rw-portal/` | pilot RT-RW Portal Warga: capture, log Railway, SBOM, laporan, panduan | 2026-10-10 → 2026-10-18 |
| `oss-sb-agency/` | pilot OSS Super Builders Agency: ringkasan & laporan | 2026-10 |

## Aturan

1. **Bukan tempat menyimpan data pelanggan jangka panjang** — maksimal sampai arsip Fase 1.
2. Berkas >512 KB wajib masuk `platform/hygiene-baseline.json` (WARN) atau tidak di-commit sama sekali.
3. Laporan yang layak dibaca ulang dipindahkan ke `reports/`, bukan dibiarkan di sini.
4. Log mentah tidak pernah di-commit tanpa redaksi (`scripts/redact_network.py` atau manual).

## Cara mengarsipkan (Fase 1)

```bash
# 1) unggah dengan hash, 2) verifikasi jumlah+sha256, 3) baru lepas dari git
/usr/bin/python3 scripts/archive_artifacts.py --dir runs/rt-rw-portal --dest s3://sdb-artifacts/  # (menyusul)
```
