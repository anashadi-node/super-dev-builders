# Clone & Reconstruction Policy — Super Dev Builders

Sumber acuan utama (dua PRD Owner, 30 Okt 2026):
1. `PRD_Super_Dev_Builders.html` — Pipeline F0-F8, gerbang G0/G1/G2/G3, kelas otorisasi A-D.
2. `Super_Dev_Builders_REA_Replica_Master_PRD.html` — Master PRD: gate G0-G4, threat model, benchmark A/B/C.

Arsitektur yang sudah ada (workflows/reconstruction-pipeline.yaml, workflows/gate0.yaml,
skills/reconstruction-*, skills/rea-reverse-engineering) SUDAH sejalan dengan kedua PRD —
kebijakan ini mengikat keduanya ke komponen konkret.

## 1. Kelas otorisasi (F0 / G0)

| Kelas | Definisi | Analisis |
|---|---|---|
| A | Milik sendiri / lisensi tertulis | Penuh (REA static, tanpa runtime capture tanpa GR) |
| B | Open source / izin tertulis pemilik | Penuh + deep analysis (mode B di gate0) |
| C | Publik tanpa izin khusus | Pengamatan publik SAJA. Tanpa dekompilasi, tanpa REA runtime |
| D | Meragukan / dilarang | STOP. Tidak masuk pipeline |

Gate0 (workflows/gate0.yaml) adalah gerbang pemilik verdict — skill
`reconstruction-scope-gate` + `scripts/gate_check.py` menegakkannya.
Kelas D atau bukti izin tidak jelas = BLOCKED, bukan WARNING.

## 2. Zona isolasi

| Zona | Isi | Aturan |
|---|---|---|
| A (lab) | REA, bukti mentah `evidence/<target>/` | Tidak pernah dibaca Zona B; env bersih; egress default-deny |
| B (studio) | Zona pembangun: skills/reconstruction-spec, builder divisi D4/D5 | Hanya baca `reconstruction/<target>/SPEC.md` |
| C (gerbang rilis) | fidelity check, fidelity.md, RELEASE_GATE | 0 aset sama, 0 string >=40 char sama, 0 rahasia |
| Rahasia | kredensial, kunci wallet/exchange | Di luar jangkauan SEMUA zona. Uji canary tiap sesi |

## 3. Firewall spesifikasi (G1)

- Spesifikasi = `reconstruction/<target>/SPEC.md` + FEATURE_MATRIX.md (skill
  `reconstruction-spec`) — teks perilaku dengan kata sendiri + Evidence ID + label
  (observasi | inferensi | tidak-diketahui).
- DILARANG berisi: pseudocode hasil dekompilasi, string literal target, aset, rahasia, PII.
- Hash SHA-256 SPEC dicatat saat G1 dilewati. Perubahan SPEC membuka ulang G1.
- Alat verifikasi dari replica-skill (`integrations/replica-skill/`): contrast.py,
  imgdiff.py, parity.py, reviews.py, sweep.py, listing.py — hanya dipanggil Zona C
  (verification), tidak pernah oleh pembangun untuk "memperbaiki skor".

## 4. Routing tool (PRD #1 bagian 6)

| Tahap | Default | REA boleh jika |
|---|---|---|
| Recon publik website | skills/ui-ux-state-mapper + target-inventory | Hanya mode A/B; mode C = pengamatan publik terbatas |
| Electron/JS/ASAR | known owned source tools | Mode A/B |
| Android APK | listing toko / owned project | APK sah + izin dekompilasi (mode B) |
| Native binary | docs / owned source | Mode A/B, static-first, runtime di Zona A |
| Game | mechanic spec, aset sendiri | Mode A/B binary inspection; STOP di DRM/anti-cheat |
| Pembangunan | D4/D5 via SPEC.md | REA output hanya via sanitized SPEC |

## 5. Kontrak keluaran (pemetaan ke struktur repo)

| PRD meminta | Lokasi di SDB |
|---|---|
| evidence-index.jsonl | `evidence/<target>/` (evidence-normalizer) |
| authorization.json/yaml | `evidence/<target>/authorization.yaml` (templates/authorization_manifest.yaml) |
| SPEC + FEATURE_MATRIX | `reconstruction/<target>/` (skills/reconstruction-spec) |
| parity / imgdiff | `verification/<target>/fidelity.md` (skills/reconstruction-fidelity + replica-diff helpers) |
| audit-log.jsonl | append-only, hash per baris (menyusul; belum ada — lihat §7) |

## 6. Gerbang rilis (G3 = RELEASE_GATE)

Sebelum deploy apapun:
1. 0 aset dengan hash sama ke aset target.
2. 0 string identik >= 40 karakter (istilah fungsional umum dikecualikan).
3. 0 rahasia (pemindaian secrets scanner).
4. Semua test lulus (fidelity dimensions: visual, navigation, interaction,
   responsive, functional, accessibility, performance, api_contract).
5. Persetujuan manusia eksplisit. Tidak ada deploy otonom.

## 7. Utang yang diakui jujur (belum dibangun)

- [ ] `audit-log.jsonl` append-only per panggilan tool (PRD #1 bagian 7).
- [ ] Pemindai G1 otomatis (spesifikasi teks-only) — saat ini review manual.
- [ ] Pembanding SHA-256 aset otomatis di G3 — saat ini prosedur manual.
- [ ] Uji canary tiap sesi Zona A.
- [ ] Benchmark E1-E7 (recall 90%, presisi 95%, injection 0/50) sebelum dipakai target nyata.
- [ ] Benchmark A/B/C: Replica-only vs REA+Replica vs baseline (min. 3 run per fixture).

Semua utang tidak menghalangi penggunaan pada target kelas A milik sendiri,
tetapi WAJIB ditutup sebelum target pihak ketiga kelas B/C.
