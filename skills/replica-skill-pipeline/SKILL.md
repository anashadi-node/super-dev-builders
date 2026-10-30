---
name: replica-skill-pipeline
description: "Use when membangun replika clean-room berizin; jalur Zona B."
version: 1.0.0
author: Super Dev Builders Ecosystem
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [reconstruction, clean-room, replica, parity, zona-b]
    divisions: [D3, D4, D5, D7]
    profiles: [sdb-architect, sdb-builder, sdb-reviewer]
    related_skills: [rea-reverse-engineering, reconstruction-scope-gate, reconstruction-spec, reconstruction-fidelity, target-inventory]
    upstream:
      repo: "https://github.com/Jakeschincariol/replica-skill"
      commit: "77c9436fb3d18c3d58169efb8caf4fe906b0dc51"
      vendored: "integrations/replica-skill/"
      tree_sha256: "2d82e189436d3608695fdc4684d9b6486f4252bad99a65d1a9c3f73e16f36278"
---

# Replica Skills — Pipeline Clean-Room (Zona B)

## When to Use

Pakai skill ini saat: (a) membangun replika/clone clean-room dari target yang sudah
lolos Gate #0 (kelas A/B/C); (b) mengukur paritas fitur/visual/kontras hasil rebuild;
(c) menyiapkan rilis replika lewat G3. JANGAN pakai untuk analisis target (itu
`rea-reverse-engineering`, Zona A) atau tanpa SPEC lolos G1.

Pembangun replika dari **spesifikasi yang lolos G1** — bukan dari target, bukan dari
bukti mentah REA. Sumber helper: `integrations/replica-skill/` (pinned 77c9436,
MIT, 57 test upstream PASS, 0 network sink — audit 30 Okt 2026).

## Prasyarat WAJIB sebelum membangun

1. Gate #0 PASS: `scripts/gate_check.py --target <slug>` (kelas A/B/C — kelas D STOP).
2. Spesifikasi lolos firewall G1 — **wajib mesin, bukan mata**:
   `python3 tools/gerbang-spec.py reconstruction/<slug>/SPEC.md --verdict reports/<slug>/g1-verdict.json`
   (exit 0 = PASS; exit 1 = perbaiki SPEC; exit 2 = alat rusak → STOP, jangan anggap lolos).
3. Catat tiap panggilan alat ke audit log berantai:
   `python3 tools/audit-log.py append --log audit/audit-log.jsonl --actor D4 --tool <alat> --target <slug> --action <aksi> --result <ok|gagal>`
   Verifikasi sebelum rilis: `python3 tools/audit-log.py verify --log audit/audit-log.jsonl`.
4. Builder TIDAK PERNAH membuka `evidence/<target>/` mentah. Kalau butuh klarifikasi
   perilaku → kembali ke D1/D3, jangan intip bukti.

## Pemetaan fase PRD → helper upstream

| Fase (PRD) | Skill SDB | Helper upstream |
|---|---|---|
| F1 recon publik | target-inventory, ui-ux-state-mapper | replica-recon (prosedur SKILL.md) |
| F4 arsitektur | reconstruction-spec | — |
| F5 build | D4/D5 langsung | replica-build, replica-backend |
| F6 verifikasi | reconstruction-fidelity | replica-diff/parity.py, imgdiff.py; replica-test |
| F6 aksesibilitas | accessibility-audit | replica-design/contrast.py |
| F7 brand | — | replica-brand (sweep.py), replica-entrepreneur (reviews.py) |
| F8 rilis | release-gate | replica-launch (listing.py), replica-deploy |

## Pemakaian helper (stdlib, aman — baca input, tulis hanya ke --out)

```bash
V=~/super-dev-builders/integrations/replica-skill
TGT=<slug>

# Paritas fitur (dari features.csv — numerator/denominator jujur, tanpa cherry-pick)
python3 $V/replica-diff/parity.py reconstruction/$TGT/features.csv \
  --format json --out verification/$TGT/parity.json

# Selisih visual (referensi milik sendiri/berizin; info saja utk karya pihak ketiga)
python3 $V/replica-diff/imgdiff.py ref.png build.png --out verification/$TGT/imgdiff.json

# Kontras WCAG AA >= 4.5:1
python3 $V/replica-design/contrast.py verification/$TGT/contrast-report.json
```

## Metrik lulus (G2 — PRD #1 §8, target usulan dikalibrasi di pilot)

- Paritas fitur >= 90% fitur inti (parity.py — laporkan pembilang/penyebut mentah).
- 100% klaim spesifikasi ber-Evidence ID.
- Kontras >= 4,5:1.
- Semua test replika lulus (bukti = output eksekusi, BUKAN self-report agent).
- GAGAL G2 → putar balik ke F5 (cacat implementasi) atau F2/F3 (celah spesifikasi;
  G1 dibuka ulang). **Dilarang menurunkan ambang agar lolos.**

## Gerbang rilis (G3) — semua WAJIB, bukan opsional

1. 0 aset dengan SHA-256 sama ke aset target.
2. 0 string identik >= 40 karakter (istilah fungsional umum dikecualikan).
3. 0 rahasia (kredensial/token/cookie/PII).
4. Merek: nama, logo, teks milik sendiri (replica-brand). Dilarang menyerupai
   merek organisasi nyata — termasuk untuk demo.
5. Persetujuan manusia eksplisit sebelum deploy. Tidak ada rilis otonom.

## Larangan keras

1. Dilarang menyalin kode/aset/teks/logo/audio/font/model milik target.
2. Dilarang DRM/paywall/anti-cheat/auth bypass — termasuk "cuma untuk tes".
3. Mode C (tanpa izin khusus): tanpa dekompilasi, tanpa private API, tanpa
   konten berhak cipta — clean-room feature parity dengan merek berbeda.
4. Dilarang memakai helper ini untuk "memverifikasi" skor yang diubah sendiri —
   verification (D7) terpisah dari builder (D4/D5).
5. Dilarang upgrade upstream tanpa audit ulang G0–G2; tidak ada @latest.

## Rujukan

- Kebijakan mengikat: `governance/policies/clone-policy.md`
- PRD acuan: `PRD_Super_Dev_Builders.html` (pipeline F0–F8),
  `Super_Dev_Builders_REA_Replica_Master_PRD.html` (gate G0–G4)
- Sisi analisis (Zona A): skill `rea-reverse-engineering`
- Audit vendored: `integrations/replica-skill/PINNED.md`
