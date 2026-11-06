---
name: did-evidence-ledger
description: "Ledger temuan DID: bukti, inferensi, unknown"
version: 1.0.0
author: Super Dev Builders Ecosystem
license: BUSL-1.1
platforms: [linux, macos]
metadata:
  hermes:
    tags: [investigation, evidence, ledger, confidence]
    divisions: [D1]
    related_skills: [did-handoff, evidence-normalizer, reconstruction-scope-gate]
---

# DID Evidence Ledger

Satu tempat untuk menjawab: **apa yang benar-benar terlihat, apa yang hanya disimpulkan, dan apa yang belum diketahui** — dengan bukti yang bisa diperiksa ulang mesin.

Tanpa ledger, laporan investigasi berubah jadi cerita. Dengan ledger, setiap kalimat punya alamat bukti.

## Kapan dipakai
Setiap kali target masuk tahap `01C DID DEEP INVESTIGATION`. Ledger adalah isi `findings`, `unknowns`, `coverage`, dan `evidence_manifest` di `runs/<target>/did/handoff.json` — bukan dokumen terpisah yang bisa basi.

## Empat status (tidak ada status lain)
| Status | Arti | Syarat wajib |
|---|---|---|
| `OBSERVED` | Terlihat langsung pada artefak/respons yang tersimpan | minimal 1 `evidence` id |
| `INFERRED` | Disimpulkan dari bukti, tidak terlihat langsung | `confidence` 0–100 **dan** `falsification.test` + `falsification.expected` |
| `UNKNOWN` | Belum bisa dipastikan dalam lingkup/biaya | `probe` konkret + `impact` (`blocking`/`non-blocking`) |
| `OUT_OF_SCOPE` | Sengaja tidak diperiksa (butuh login, di luar otorisasi) | alasan di `claim` |

`FACT` hanya boleh dipakai bila nilainya identik dengan artefak (mis. string yang dikutip persis). Ragu antara FACT dan INFERRED → pilih INFERRED.

## Aturan penulisan temuan
1. **Satu temuan = satu klaim yang bisa salah.** "Ada 12 route dan 3 di antaranya butuh login" = dua temuan.
2. **Lokator wajib.** `locator` harus menunjuk tempat yang bisa dibuka orang lain: `#/settings`, `bundle.js:2491`, `response GET /api/orders`, `AndroidManifest.xml:permissions`.
3. **Kutip, jangan parafrase angka.** Harga, limit, timeout, nama field: salin apa adanya ke `claim`.
4. **Jangan menyimpulkan mesin/server.** "Dipakai PostgreSQL" tanpa artefak = UNKNOWN, bukan INFERRED.
5. **Redaksi sebelum simpan.** Cookie, token, email, nomor telepon → ganti `[REDACTED]`; `redaction_applied: true` di `discipline`.
6. **Anggaran dicatat, bukan dikira.** Isi `budget.used` (tool_calls, minutes, evidence_bytes) setiap kali alat dijalankan.

## Rubrik confidence (INFERRED)
| Nilai | Kondisi |
|---|---|
| 90–100 | Dua bukti independen saling menguatkan, tanpa alternatif masuk akal |
| 70–89 | Satu bukti kuat + konvensi teknologi yang jelas |
| 40–69 | Satu bukti tidak langsung; alternatif masih mungkin |
| 10–39 | Pola umum semata (nama field, kemiripan UI) — **jangan dipakai untuk keputusan build** |
| <10 | Buang; tulis sebagai UNKNOWN |

Ambang keputusan: fitur `must` hanya boleh bersandar pada `OBSERVED`; `INFERRED` ≥70 boleh jadi `should` dengan probe; `INFERRED` <70 wajib jadi UNKNOWN.

## Bentuk evidence yang sah
`evidence_manifest` minimal berisi `id`, `path`, `sha256`, `captured_at`, `status`, `authority` (alat/sumber). Berkas harus di dalam repo, ada, dan hash-nya cocok saat divalidasi — `did_validate.py` menghitung ulang, bukan percaya.

## Pemeriksaan mesin (R04–R06)
`python3 scripts/did_validate.py validate --target <t>` menolak ledger yang: evidence hilang/hash berubah/berisi rahasia, `OBSERVED` tanpa bukti, `INFERRED` tanpa falsifikasi, `UNKNOWN` tanpa probe, atau rujukan evidence menggantung.

## Anti-pola
- Menyalin kesimpulan laporan lama tanpa menandai `captured_at` asli.
- Menyebut "kemungkinan besar" di dalam `claim` status `OBSERVED`.
- Menyimpan satu berkas besar berisi semua respons; pecah per interaksi agar hash bermakna.
- Menghapus UNKNOWN yang tidak nyaman — UNKNOWN yang jujur lebih berharga daripada kepastian palsu.
