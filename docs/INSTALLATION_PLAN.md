# Installation Plan (blueprint §9) — status per 2026-10-04

Urutan fase tidak boleh dilompati: foundation dulu, assurance, lalu UI/integration, governance, terakhir tool deterministik.
**Tidak ada** pemasangan pihak ketiga tanpa pipeline §6 + approval manusia.

## Phase 1 — Foundation (audited) — SEBAGIAN SELESAI
| Item | Status | Catatan |
|---|---|---|
| Hermes builtin/official skills sebagai dasar | DONE | dipakai apa adanya (`plan`, `dogfood`, `spike`, `simplify-code`, dll.) |
| `hermes skills audit` (Skills Guard native) sebagai gate pertama | VERIFIED | dijalankan 2026-10-04; menemukan 1 skill hub berstatus DANGEROUS (lihat laporan security) |
| Official optional skills (ast-grep, grill-me, rest-graphql-debug, code-wiki, subagent-driven-development) | NOT PRESENT | belum tersedia di instalasi ini; cari via `hermes skills browse --source official` bila dibutuhkan |
| Superpowers sebagai **metodologi** (bukan plugin wajib) | ADOPTED AS METHOD | port manual ke custom skill kecil (plan, TDD, debugging, verification) |
| Plugin Superpowers | PENDING APPROVAL | blueprint §0: instalasi pernah diblokir Skills Guard sebagai dangerous verdict. DILARANG bypass. |

## Phase 2 — Assurance — SELESAI (2026-10-04, approval #4 + #2)
Trail of Bits: audit-context-building, differential-review, Semgrep, CodeQL, SARIF, variant-analysis.
Semgrep = scan cepat harian; CodeQL = milestone/release (berat) **dan hanya untuk codebase OSI-approved/akademik** (batas lisensi).

## Phase 3 — UI & Integration — PENDING (butuh approval)
Anthropic: frontend-design, webapp-testing, mcp-builder. Wajib compatibility test sebelum produksi.
Catatan: repo `anthropics/skills` belum mendeklarasikan lisensi SPDX -> konfirmasi lisensi dulu.

## Phase 4 — Governance — PENDING (butuh approval)
`getsentry/skills`: skill-scanner, security-review, agents-md, code-simplifier. Secondary methodology saja;
gate pertama tetap Hermes native.

## Phase 5 — Deterministic Security Tools — SELESAI (2026-10-04)
Semgrep 1.179.0, Trivy 0.75.0, Ruff 0.16.10, Syft 1.54.0, CodeQL 2.27.1, Playwright 1.63.0 — pin versi + verifikasi SHA256 (semua OK).
Skrip: `bash scripts/bootstrap_tools.sh --check` (dry-run default; butuh `--install <tool> --yes` setelah approval).

## Prinsip yang dipegang
1. Jangan install satu repositori penuh bila hanya satu skill yang dibutuhkan.
2. Skill pihak ketiga tidak pernah otomatis production-approved.
3. Jangan menambah scanner hanya karena tersedia (overlap = noise + beban maintenance).
