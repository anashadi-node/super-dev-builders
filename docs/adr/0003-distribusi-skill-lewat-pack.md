# ADR-0003 — Distribusi skill lewat pack manifest, bukan salin-per-profil

**Status**: Accepted · **Tanggal**: 2026-10-26 · **Konteks**: audit ganda (H-1, B-5)

## Keputusan

`skills/` adalah **satu-satunya sumber**. Profil divisi dan paket langganan tidak menyimpan salinan, melainkan
**manifest** yang menunjuk skill + versi:

```json
{ "pack": "sdb-core", "version": "1.4.0", "role": "recon",
  "skills": [{"id": "target-inventory", "sha256": "..."}, ...],
  "workflows": ["gate0"], "gates": ["scope-gate"] }
```

Materialisasi ke profil bersifat turunan dan ditandai `pack_id` + versi, sehingga bisa diganti/dicabut.

## Alasan

- Hari ini 25 direktori skill ≈ 2,5–3,7 MB masing-masing (±65 MB) — menyalin 8 profil × N tenant tidak scales.
- Tidak ada versioning: membatalkan skill berbahaya berarti `git revert` di setiap profil.
- Indeks deskripsi yang di-inject sebenarnya murah (1.275–2.474 token); masalahnya adalah **duplikasi dan
  ketiadaan kendali**, bukan ukuran konteks.

## Konsekuensi

- Diperlukan `packs/*.json` + skrip materialisasi (`install_skills.py` diperluas) + hash per skill.
- Pencabutan darurat: tanda `revoked` di control plane → materialisasi berikutnya menghapus skill tersebut.
- Batas wajar **≤25 skill aktif per peran**; di atas itu pemilihan skill mulai tidak relevan.
- Rollback rilis = tukar `pack_id`, bukan revert commit.

## Alternatif yang ditolak

- **Satu profil raksasa untuk semua peran**: kontradiksi dengan pemisahan divisi dan clean-room wall.
- **Skill sebagai container image per peran**: berat, sulit diaudit, dan tidak perlu pada skala ini.
