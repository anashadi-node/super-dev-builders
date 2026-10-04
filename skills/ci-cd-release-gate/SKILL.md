---
name: ci-cd-release-gate
description: "Use to wire build-test-scan-staging-approval-production with exit criteria."
version: 1.0.0
author: Super Dev Builders Ecosystem
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [ci, cd, pipeline, release, gate, docker]
    divisions: [D10, D8]
    related_skills: [engineering-release-audit, rollback-and-recovery, release-handover-docs]
---


# CI/CD Release Gate

Pipeline deterministik: build -> test -> scan -> artefak -> staging -> **approval manusia** -> produksi.
Semua gate punya exit criteria; tidak ada gate "kira-kira lulus".

## Tahap & exit criteria
1. **Lint/format** — nol error; peringatan baru harus dibenarkan.
2. **Build** — sukses bersih dari commit yang sama dengan artefak; hash artefak dicatat.
3. **Test** — unit/integration/contract/E2E sesuai kelas risiko; tidak ada kegagalan tak terjelaskan.
4. **Security scan** — SAST (Semgrep cepat; CodeQL pada milestone), dependency/secret/misconfig (Trivy);
   triase temuan dengan aturan stop: critical/high terbuka => berhenti.
5. **Audit/assurance** — `release_check.py` PASS (artefak segar).
6. **Staging** — deploy + smoke test + observasi; rollback sudah siap & teruji.
7. **Approval manusia** — tercatat (nama, waktu, keputusan) di `reports/human-approval-required.md`.
8. **Produksi** — deploy bertahap, satu layanan sekaligus, verifikasi health setelah tiap langkah.
9. **Post-deploy** — smoke test, pantau log/metrik periode awal, siap rollback.

## Aturan
- Docker untuk build reproducible; **jangan** memberikan socket Docker host ke pekerjaan tak-terpercaya.
- Tidak ada `--force`, `--no-verify`, atau bypass gate. Tidak ada auto-approve untuk aksi destruktif/
  publikasi/produksi.
- Credential hanya lewat secret store; tanpa secret di log/artefak.

## Output
- Konfigurasi pipeline + `reports/deploy-<versi>.md` (build, test, scan, approval, smoke, rollback ref).
