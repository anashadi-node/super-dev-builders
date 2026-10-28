---
name: engineering-release-audit
description: "Whole-system final engineering release gate"
version: 1.0.0
author: Super Dev Builders Ecosystem
license: BUSL-1.1
platforms: [linux, macos]
metadata:
  hermes:
    tags: [release, audit, gate, assurance, evidence]
    divisions: [D9, D10]
    related_skills: [architecture-compliance-audit, ci-cd-release-gate, test-pyramid-and-risk]
---


# Engineering Release Audit

Gate terakhir sebelum release: mengagregasi evidence seluruh divisi dan **menolak PASS tanpa artefak**.

## Yang diperiksa (semua wajib punya artefak < 24 jam)
| Aspek | Artefak |
|---|---|
| Requirement | `requirements.md` + acceptance criteria terpetakan |
| Build | log build sukses (timestamp) |
| Tests | output suite (unit/integration/E2E sesuai risk), tanpa kegagalan tak terjelaskan |
| Review | temuan critical/high tertutup atau diterima manusia secara eksplisit |
| Security | SAST + dependency + secret scan + triage |
| Audit arsitektur | `architecture-compliance.md` |
| Migrasi | `reports/migration-safety.md` + rollback teruji (bila ada) |
| Operasional | rollback/backup/health check tersedia |
| Dokumentasi | README/runbook/release notes aktual |

## Prosedur
1. Jalankan `python3 scripts/release_check.py --project <path>`.
2. Untuk setiap gate: PASS hanya bila artefak ada, valid, dan segar. Bila tidak => **FAIL (incomplete)**.
3. Baca klaim vs bukti: setiap klaim "sudah diuji/diperbaiki" harus menunjuk perintah + hasil.
4. Susun risiko residual eksplisit (tabel) untuk diterima pemilik risiko manusia.
5. Tulis verdict: PASS / FAIL / BLOCKED + daftar blocker + langkah perbaikan.

## Aturan
- Tidak ada override manual tanpa catatan siapa yang mengesahkan dan alasannya.
- Audit ini **bukan** pengganti QA atau Security: ia mengagregasi, bukan menegosiasi ulang.
- Risiko critical terbuka => tidak ada PASS dalam kondisi apa pun.

## Output
- `reports/assurance-audit.md` + `reports/release-verdict.json`
