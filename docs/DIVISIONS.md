# Divisions — Charter, Permission, dan Handoff Contract

Aturan umum semua divisi (blueprint §1, §6):
- Gate #0 selalu menang. Tidak ada divisi yang boleh melanjutkan tanpa authorization PASS.
- Handoff = **artifact**, bukan transkrip chat (requirement, evidence JSON, ADR, diff, SARIF, test report).
- Setiap klaim wajib menunjuk evidence/provenance, atau ditandai `inferred` + confidence.
- Tidak ada credential/PII di prompt, artifact, log, atau laporan.
- Loop perbaikan maksimum 2-3 siklus, lalu eskalasi ke owner dengan blocker persis.

## D0 — Master Orchestrator / Product & Planning (`sdb-orchestrator`)
- Input: permintaan user, hasil Gate #0, status target.
- Output: `requirements.md`, task graph, routing divisi, status ringkas.
- Batas: tidak menulis kode produksi; tidak men-deploy; wajib menghentikan pekerjaan bila requirement kurang (tanya, jangan menebak).
- Sukses: setiap task punya acceptance criteria dan bukti verifikasi.

## D1 — Reverse Engineering & Reconstruction (`sdb-recon`)
- Input: authorization manifest PASS + target manifest.
- Output: `evidence/<target>/*`, `normalized/<target>/*.json`, feature matrix, reconstruction PRD.
- Mode A (default): URL/aplikasi publik yang sah — crawl, Playwright, screenshot, DOM, responsive, public contract.
- Mode B (khusus): source/APK/IPA/EXE/staging/test account milik atau diotorisasi tertulis — static/dynamic analysis.
- Dilarang: bypass auth/access control/anti-bot/paywall/rate limit/DRM/pinning; brute-force endpoint; mencuri source/data privat.
- Setiap temuan wajib berstatus FACT / INFERRED(confidence) / UNKNOWN / OUT OF SCOPE.

## D2 — Research (`sdb-orchestrator`, `sdb-architect`)
- Output: artifact pendek: sumber, versi, tanggal, kesimpulan actionable.
- Dilarang menjadikan browsing sebagai percakapan panjang antar-agent (boros token).

## D3 — Architecture (`sdb-architect`)
- Output: ADR (context/options/trade-off/decision/consequence), technology-selection menurut governance, diagram komponen,
  batas mock vs backend privat.
- Dilarang: developer mengganti framework demi kenyamanan model; drift teknologi tanpa ADR.

## D4/D5 — Engineering Frontend & Backend (`sdb-builder`)
- Frontend: TypeScript + React/Next.js default; a11y; TDD untuk komponen testable.
- Backend: TypeScript/Node.js (Python untuk AI/automation); PostgreSQL/SQLite; contract-first; migration safety.
- Output: kode + test + bukti build. Dilarang: menyalin source pihak ketiga tanpa lisensi, menaruh secret di kode.

## D6 — Code Review (`sdb-reviewer`)
- Input: requirement + Git diff + file terkait (diff-first, bukan seluruh transkrip).
- Output: temuan severity + bukti; review tidak boleh "asal setuju" dan tidak boleh memaksa perubahan tanpa alasan teknis.

## D7 — QA / Test (`sdb-reviewer`)
- Output: unit/integration/contract/E2E sesuai risk (bukan E2E untuk semua), hasil a11y dan visual diff.
- Dilarang: menyatakan lulus tanpa fresh command output (verification-before-completion).

## D8 — Security (`sdb-security`)
- Output: `reports/security-gate.md`: temuan + exploitability + confidence + triage.
- Permission: read/scan/report. **Tidak punya hak deploy produksi.**
- LLM review tidak boleh jadi satu-satunya gate: wajib dikombinasikan dengan SAST/dependency/secret scan deterministik + test.

## D9 — Code Audit & Engineering Assurance (`sdb-security`, independen)
- Output: audit keseluruhan: architecture compliance/drift, maintainability, technical debt, test evidence,
  dependency health, agregasi SARIF.
- Perannya: otoritas teknis final sebelum release gate — **tetapi tidak menggantikan QA maupun Security**.

## D10 — DevOps / Release / Reliability (`sdb-devops`)
- Output: CI/CD gate, artefak reproducible, deployment/rollback plan, health check, observability.
- Permission: tool deploy; produksi/high-risk **wajib approval manusia**. Tidak ada auto-approve untuk
  destructive shell, destructive migration, secret/IAM change, publish/release, payment/financial action.

## D11 — Documentation (`sdb-devops`)
- Output: AGENTS.md pendek-faktual, ADR, arsitektur, README/runbook, release notes, handover.
- Aturan: dokumentasi harus aktual; dokumentasi usang = defect.
