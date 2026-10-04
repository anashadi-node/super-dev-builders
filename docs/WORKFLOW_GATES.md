# Workflow & Gates — Super Dev Builders Ecosystem V2.2

Sumber: blueprint §7 (workflow operasional final), §7 release gate minimum, §10A risk classification.

## 1. Workflow operasional (16 tahap)

```text
01  USER OBJECTIVE
01A IF EXISTING TARGET:  AUTHORIZATION / SCOPE GATE   (FAIL/BLOCKED => STOP)
     +-- REVERSE ENGINEERING & RECONSTRUCTION (evidence package, FACT/INFERRED/UNKNOWN)
02  ORCHESTRATOR: clarification (jangan menebak requirement)
03  RESEARCH (hanya bila perlu; output artifact pendek)
04  ARCHITECTURE + ADR + keputusan stack (technology governance)
05  HUMAN DESIGN/ARCHITECTURE APPROVAL (project besar)
06  IMPLEMENTATION PLAN (task kecil + file + cara verifikasi)
07  FRONTEND dan/atau BACKEND  (TDD, konteks terarah, tool deterministik)
08  CODE REVIEW
09  QA / INTEGRATION / E2E
10  SECURITY  (SAST / dependency / secret / config scan)
11  CODE AUDIT & ENGINEERING ASSURANCE  (architecture drift + whole-system release audit)
12  RELEASE GATE
13  HUMAN APPROVAL untuk produksi/aksi high-risk
14  DEVOPS DEPLOY
15  OBSERVABILITY / SMOKE TEST / ROLLBACK READINESS
16  DOCUMENTATION + HANDOVER
```

Implementasi tool: `scripts/gate_check.py` (Gate #0, tahap 01A) dan `scripts/release_check.py` (tahap 12).

## 2. Release gate minimum — wajib evidence, bukan pernyataan

| Gate | Evidence wajib | Tool/artefak |
|---|---|---|
| Requirement | Acceptance criteria terpetakan ke task | `requirements.md`, task graph |
| Build | Fresh successful build output | log build (timestamp) |
| Tests | Unit/integration/E2E sesuai risk; tanpa kegagalan tak terjelaskan | output pytest/jest/playwright |
| Review | Critical/high issue tertutup atau diterima eksplisit oleh manusia | `reports/review-*.md` |
| Security | Static + dependency + secret scan + triage | SARIF/JSON + `reports/security-gate.md` |
| Audit | Architecture compliance & release audit PASS | `reports/assurance-audit.md` |
| Operations | Rollback/backup/health check tersedia | `docs/ROLLBACK_PLAN.md` + runbook |
| Docs | Setup/runbook/release notes aktual | `docs/`, `reports/handover-*.md` |

Aturan: bila salah satu gate tidak punya artifact, hasilnya **FAIL (incomplete)** — bukan PASS bersyarat.
`scripts/release_check.py` menolak PASS selama artefak wajib belum ada/kedaluwarsa (default: 24 jam).

## 3. Klasifikasi risiko & kebijakan (blueprint §10A)

| Kelas | Contoh | Policy |
|---|---|---|
| LOW | docs, formatting, riset read-only | kontrol Hermes normal |
| MEDIUM | edit kode di workspace dev/disposable | git branch + tests + approval controls |
| HIGH | auth, payment, secret, migration, CI/CD, infra/IAM | whole-process isolation + security/audit independen + approval manusia |
| CRITICAL | aksi destruktif produksi, rotasi credential, operasi data ireversibel | **tanpa eksekusi otonom**; prosedur terkendali manusia + bukti rollback/recovery |

Konsekuensi operasional: dev/test = MEDIUM (aman otonom dalam workspace, wajib git branch + test);
deploy/migration/secret = HIGH/CRITICAL (berhenti, minta approval manusia, sediakan rollback).

## 4. Loop terbatas (anti token-loop)
- Perbaikan otomatis maksimum 2-3 siklus per task; siklus ketiga gagal => eskalasi + blocker persis.
- Satu perubahan -> satu pengukuran -> lanjut. Tidak ada "coba-coba" di produksi.
- Tidak ada klaim selesai tanpa perintah verifikasi fresh.

## 5. Status gate
- **PASS** — evidence lengkap dan sesuai kriteria, lanjut.
- **FAIL** — ada pelanggaran/kegagalan, perbaiki dulu.
- **BLOCKED** — butuh keputusan/artefak manusia (otorisasi, kredensial, akses), berhenti dan tanya.

---

## Perintah scan deterministik (aktif sejak 2026-10-04, approval item #4)

Tool: `ruff 0.16.10`, `semgrep 1.179.0`, `trivy 0.75.0` — pin + checksum di `scripts/bootstrap_tools.sh`
(instalasi hanya dengan `--install <tool> --yes` setelah approval manusia; tidak ada `curl | sh`).

```bash
cd /home/anashadi/super-dev-builders
ruff check scripts tests                       # lint cepat, target: 0 temuan
semgrep scan --config p/default --metrics off --json -o reports/upgrade-evidence/semgrep.json .
trivy fs --scanners vuln,misconfig,secret --format json -o reports/upgrade-evidence/trivy-fs.json .
/usr/bin/python3 scripts/release_check.py --project .   # gate rilis (butuh artefak < 24 jam)
```

Aturan pemakaian:
- Semgrep/ruff = scan cepat harian (murah); CodeQL hanya milestone/release (berat).
- Trivy hanya bermakna bila repo punya manifest (`package.json`, `requirements.txt`) atau IaC/Dockerfile;
  "0 temuan" pada repo tanpa manifest berarti "tidak ada yang diperiksa".
- Semua temuan masuk `reports/` sebagai artefak; temuan critical/high memblokir rilis.
