---
name: did-benchmark
description: "Ukur presisi/recall investigasi vs ground truth"
version: 1.0.0
author: Super Dev Builders Ecosystem
license: BUSL-1.1
platforms: [linux, macos]
metadata:
  hermes:
    tags: [benchmark, precision, recall, hallucination]
    divisions: [D1]
    related_skills: [did-handoff, did-evidence-ledger, verification-before-completion]
---

# DID Benchmark

Klaim "investigasi kami akurat" tanpa angka adalah opini. Skill ini mengubahnya jadi tiga angka yang bisa dibantah: **precision, recall, hallucination rate**.

## Kapan dipakai
- Sebelum mengumumkan perubahan metode/alat investigasi.
- Saat membandingkan dua kedalaman (L2 vs L3) atau dua provider (REA vs Craft).
- Setiap kali handoff menyentuh target yang punya ground truth.

## Ground truth (berkas kecil, ditulis manusia)
```json
{
  "target": "e1-app",
  "labeler": "Owner",
  "labeled_at": "2026-11-06",
  "features": [
    {"id": "F01", "name": "Daftar produk dengan filter harga", "keywords": ["filter harga", "price range"]}
  ]
}
```
Aturan: label ditulis **sebelum** investigasi dijalankan pada target itu, dan tidak diubah setelahnya. Menambah label setelah melihat hasil = membatalkan pengukuran.

## Cara mengukur
```bash
python3 scripts/did_validate.py bench \
  --handoff runs/e1-app/did/handoff.json \
  --truth benchmarks/e1/ground_truth.json \
  --json-out reports/e1-app/did-bench.json
```
Keluaran: `precision`, `recall`, `f1`, `hallucination_rate`, daftar `missed` (label tidak tertangkap), `hallucinated` (fitur diklaim tanpa label).

## Ambang yang dipakai SDB
| Metrik | Minimum | Alasan |
|---|---|---|
| recall | ≥ 0.80 | Fitur hilang = cacat produk yang baru ketahuan setelah build |
| precision | ≥ 0.85 | Klaim palsu = Builders mengerjakan hal yang tidak ada |
| hallucination_rate | ≤ 0.10 | Satu klaim palsu merusak kepercayaan seluruh paket |
| n label | ≥ 10 | Di bawah 10, angka hanya indikasi (`MONITOR`), bukan keputusan |

n < 10 atau target tanpa ground truth → tulis "belum terukur", jangan mengarang angka.

## Protokol pembandingan yang sah
1. Bekukan ground truth + versi alat (`provider_snapshot.py`).
2. Jalankan A, simpan handoff + laporan validasi.
3. Jalankan B pada kondisi identik (target, kedalaman, anggaran).
4. Bandingkan `recall` dulu (keselamatan), baru `precision`, baru biaya (`budget.used`).
5. Perbedaan < 0.05 pada n<30 → **belum ada bukti**; ulangi atau perbesar sampel.

## Jebakan
- **Kebocoran label**: menulis label dari hasil investigasi (recall jadi 1.0 palsu).
- **Mencocokkan longgar**: kata umum ("login", "dashboard") membuat semua fitur cocok. Pakai `keywords` spesifik.
- **Mengukur pada target yang sudah pernah diinvestigasi** tanpa menyebutkannya — sebutkan status "pernah dilihat" di laporan.
- **Mengoptimalkan angka, bukan produk**: recall tinggi untuk fitur sepele tidak menolong Builders.
