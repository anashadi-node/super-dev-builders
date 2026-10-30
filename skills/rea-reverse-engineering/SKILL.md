---
name: rea-reverse-engineering
description: "Reverse-engineering artefak terkirim (Electron/JS, web, binary, APK) dengan REA CLI terpin"
version: 1.0.0
author: Super Dev Builders Ecosystem
license: BUSL-1.1
platforms: [linux]
metadata:
  hermes:
    tags: [reconstruction, reverse-engineering, evidence, electron, javascript, native, gate0]
    divisions: [D1, D3, D7, D8]
    related_skills: [reconstruction-scope-gate, target-inventory, ui-ux-state-mapper, reconstruction-spec, reconstruction-fidelity, evidence-normalizer]
    upstream:
      package: "rea-agents@6.8.0"
      integrity: "sha512-9QDeRnGqEDzABZyr04eLnBXBv/c6I9/TWu/6M0MD4pEfkySI/BIgwTODIbAReX3C1x6hjw9+Jlx4A2yUSPZ9ww=="
      audit: "reports/REA_AUDIT_20261026.md"
---

# REA — Reverse Engineer Anything (integrasi SDB)

REA menjawab satu jenis pertanyaan yang tidak bisa dijawab source repo: **apa yang sebenarnya dilakukan
artefak yang dikirim ke pengguna** — bundle Electron, ASAR, APK, biner native, halaman web. Setiap temuan
dibawa sebagai Evidence ber-hash dengan label CONFIRMED / INFERRED / UNKNOWN.

Integrasi ini **CLI-first**. MCP server REA (229 tool, 3,79 MB skema) **tidak** didaftarkan ke profil Hermes
mana pun secara default — alasannya biaya konteks, bukan ketidakpercayaan. Lihat `reports/REA_AUDIT_20261026.md` §5.

## 1. Kapan dipakai — dan kapan tidak

Pakai bila klaim bergantung pada **artefak terkirim**, bukan source:
- aplikasi Electron/ASAR, aplikasi web yang sudah dibundel, APK, biner native, firmware, paket hasil build;
- membandingkan dua versi aplikasi (apa yang berubah di perilaku/permukaan API);
- memetakan perilaku sebelum membangun ulang (clean-room): route, IPC, boundary, dependensi nyata.

**Jangan** pakai bila:
- source repo lengkap tersedia dan bisa dibaca langsung → pakai `codebase-map` / tools repo biasa;
- target tidak punya izin tertulis → **STOP**, Gate #0 dulu (§2);
- pertanyaannya sekadar "aplikasi ini pakai framework apa" → fingerprint visual/capture biasa lebih murah;
- target memuat data pribadi/kredensial yang tidak boleh masuk konteks (§7).

## 2. Prasyarat wajib — Gate #0 (tidak bisa dilewati)

```bash
cd ~/super-dev-builders
/usr/bin/python3 scripts/gate_check.py --target <slug>     # harus PASS
```

`evidence/<slug>/authorization.yaml` wajib memuat target yang benar-benar dianalisis. Untuk biner/APK:
`allowed_targets.apk_ipa_binaries` + `deep_analysis_allowed: true` hanya sah pada **mode B** +
`written_permission`. Gate FAIL/BLOCKED = berhenti, lapor Owner — jangan "cari jalan lain".

## 3. Tool & versi (terpin, terisolasi)

```text
binary   ~/.hermes/tools/rea-6.8.0/node_modules/rea-agents/scripts/rea.mjs   (rea-agents 6.8.0)
wrapper  ~/super-dev-builders/scripts/rea
install  npm install --prefix ~/.hermes/tools/rea-6.8.0 --ignore-scripts rea-agents@6.8.0
```

Cek cepat sebelum kerja: `scripts/rea --version` → harus `6.8.0`. Bila berbeda, **jangan** lanjut: jalankan
audit ulang (versi lain = artefak yang belum diaudit).

## 4. Tier izin

| Tier | Contoh perintah | Syarat |
|---|---|---|
| **T0 statis read-only** (default) | `analyze`, `analyze-javascript-application`, `inspect-artifact`, `extract-artifact`, `list-*`, `capabilities`, `compare-*` | Gate #0 PASS; tidak mengeksekusi target |
| **T1 capture runtime** | `capture-browser-scenario`, `observe-web-execution`, `capture-web-screenshot`, `environment-*` | Gate #0 PASS + `network_capture_allowed: true` + origin ada di `allowed_targets.urls` |
| **T2 debug/instrumentasi** | `debug-with-gdb`, `debug-with-rizin`, `execute-rizin-command`, `cutter-command`, frida | **approval tertulis per-aksi** + proses terisolasi, non-root, tanpa mount kredensial |
| **T3 perangkat** | `install-adb-package`, `uninstall-adb-package`, `capture-adb-screen`, `collect-adb-bugreport` | hanya perangkat milik sendiri/lab; approval per-aksi; **tidak pernah** perangkat pihak ketiga |

Tool di luar tier = tidak dipakai. Kalau butuh, naikkan tier secara eksplisit di laporan, bukan diam-diam.

## 5. Pola pemakaian (hemat konteks)

Selalu batasi output. Default: `--format md --token-limit 900`; untuk data mesin: `--format json` lalu
filter dengan `--filter-output`.

```bash
REA=~/super-dev-builders/scripts/rea
TGT=myapp                                  # slug Gate #0
EV=~/super-dev-builders/evidence/$TGT/rea; mkdir -p "$EV"

# 1) peta awal (murah)
$REA analyze /path/to/app --format md --token-limit 800

# 2) analisis Electron/JS statis → Evidence lengkap ke disk, ringkasan ke konteks
$REA analyze-javascript-application /path/to/app \
     --detail summary --evidence_output "$EV/app-graph.json" \
     --format md --token-limit 1200

# 3) baca bagian tertentu dari Evidence (jangan dump seluruh berkas)
$REA inspect-analysis-view "$EV/app-graph.json" --format md --token-limit 800

# 4) bandingkan dua versi
$REA compare-application-versions "$EV/v1.json" "$EV/v2.json" --format md --token-limit 900

# 5) ledger kewajiban rekonstruksi (dipakai D3 sebelum menulis spec)
$REA build-reconstruction-obligation-ledger "$EV/app-graph.json" --format md --token-limit 1200
```

Aturan output:
- `--detail summary` **wajib** disertai `--evidence_output <file>`; tanpanya REA menolak dengan
  `invalid_request / invalid_input` (terbukti 2026-10-26). Summary tanpa evidence = tidak ada bukti yang bisa diaudit.
- Jangan pernah `--full-output` kecuali Owner meminta; itu bisa puluhan ribu token.
- Evidence **lengkap** selalu ke berkas (`--evidence_output`), **ringkasan** ke konteks.
- Satu pertanyaan = satu perintah; jangan sapu semua tool untuk "eksplorasi".

## 6. Evidence & label (wajib konsisten dengan `docs/EVIDENCE_TAXONOMY.md`)

| REA | SDB | Aturan |
|---|---|---|
| CONFIRMED | **FACT** | boleh jadi dasar fidelity; sertakan `evidence_id` + digest |
| INFERRED | **INFERRED** | wajib `confidence` 0–100 + alasan; tidak boleh jadi dasar tunggal keputusan besar |
| UNKNOWN | **UNKNOWN** | dilarang diisi tebakan; architect mendesain ulang dari requirement |
| — | **OUT_OF_SCOPE** | target di luar `authorization.yaml` → STOP |

Setiap berkas Evidence di `evidence/<target>/rea/` dicatat di `evidence/<target>/rea/index.json`:
`{tool, command_digest, evidence_id, sha256, captured_at, redaction_status, tier}`.

Redaksi dulu, simpan kemudian: jalankan `scripts/redact_network.py` untuk capture jaringan;
`redaction_status` harus `clean|redacted|blocked` — **tidak boleh kosong**.

## 7. Larangan keras

1. Tidak ada analisis tanpa Gate #0 PASS.
2. Tidak ada `debug`/frida/adb (T2–T3) tanpa approval tertulis per aksi.
3. Tidak ada credential, cookie, token, PII, atau isi dompet/kunci privat yang masuk Evidence atau konteks.
   Bila artefak memuatnya: catat sebagai temuan "berisi data sensitif", **jangan** salin nilainya.
4. Tidak ada analisis untuk menembus DRM/anti-cheat/auth/paywall (selaras `DISCLAIMER.md` upstream dan
   `forbidden_actions` Gate #0).
5. Tidak ada salinan berkas REA ke dalam repo SDB; integrasi lewat wrapper + skill ini (lisensi & higiene).
6. Tidak ada klaim "parity" dari hasil decompiler — decompile = **evidence**, bukan source asli.
7. Tidak ada upgrade REA tanpa audit ulang (§9).

## 8. Clean-room wall → divisi SDB

REA mengirim 4 peran; petakan ke divisi, jangan biarkan satu agen memegang dua sisi dinding:

| Peran REA | Divisi | Keluaran | Dinding |
|---|---|---|---|
| `rea-scout` — mempelajari fitur target + label bukti | **D1 Recon** | `reports/<feature>.md` + Evidence | boleh melihat target |
| `rea-spec-writer` — menulis `spec.md` (perilaku saja) | **D3 Architecture** | `spec.md` (tanpa nama internal/path/aset) | hanya membaca laporan D1 |
| `rea-builder` — membangun dari `spec.md` | **D4/D5** | implementasi + test | **tidak** melihat target |
| `rea-tester` — jalankan keduanya, bandingkan | **D7 QA** | `comparison.md` + match rate | boleh melihat keduanya, hanya menilai |

Konsekuensi operasional: agen builder **tidak** diberi akses ke `evidence/<target>/` mentah — hanya
`spec.md` + `reports/`. Ini yang membuat rekonstruksi sah secara clean-room, bukan sekadar rapi.

## 9. Verifikasi & pemeliharaan

```bash
~/super-dev-builders/scripts/rea --version                      # 6.8.0
/usr/bin/python3 -m pytest ~/super-dev-builders/tests/test_rea_integration.py -q
```

Upgrade hanya lewat prosedur `docs/INTEGRASI_REA.md` §6 (audit ulang → pin baru → registry → lapor).
Rollback: `rm -rf ~/.hermes/tools/rea-6.8.0` + revert commit integrasi.

## 10. Rujukan

- Audit lengkap + bukti: `reports/REA_AUDIT_20261026.md`
- Keputusan arsitektur & prosedur MCP opt-in: `docs/INTEGRASI_REA.md`
- Gate: `skills/reconstruction-scope-gate`, `scripts/gate_check.py`
- Evidence: `docs/EVIDENCE_TAXONOMY.md`, `docs/EVIDENCE_SCHEMA.md`
- Pipeline supply-chain: `docs/SECURITY_SUPPLY_CHAIN.md`
- **PRD acuan utama Owner (30 Okt 2026)**:
  - `PRD_Super_Dev_Builders.html` — pipeline F0–F8, gerbang G0–G3, kelas A–D, eksperimen E1–E7;
  - `Super_Dev_Builders_REA_Replica_Master_PRD.html` — gate G0–G4, threat model, benchmark A/B/C;
  - kebijakan mengikat: `governance/policies/clone-policy.md`.
- **Replica Skills (Zona B)**: `integrations/replica-skill/` (pinned 77c9436) — skill
  `replica-skill-pipeline` memetakan helper-nya ke divisi SDB.
