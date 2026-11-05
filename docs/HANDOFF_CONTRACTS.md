# Handoff Contracts — artifact per tahap

Migrasi dari V1 (berkas `AGENT_CHARTERS.md` sudah tidak ada di repo; isinya dipecah) — kini dipisah: charter per divisi ada di
`docs/DIVISIONS.md` + `agents/*.yaml`; berkas ini mengatur **kontrak serah-terima artifact**.

## Prinsip
1. Serah-terima selalu berupa artifact kecil, bukan transkrip percakapan.
2. Setiap artifact punya pemilik (divisi), konsumen, dan format yang disepakati.
3. Artifact tanpa provenance/evidence = tidak sah.

## Kontrak
| Dari -> Ke | Artifact | Format | Kriteria diterima |
|---|---|---|---|
| D0 -> semua | `requirements.md` + task graph | markdown + JSON | acceptance criteria terukur, tanpa asumsi tersembunyi |
| Gate #0 -> D0/D1 | verdict authorization | `gate_check.py` output JSON | PASS/FAIL/BLOCKED + alasan + daftar forbidden action |
| D1 -> D3/D4/D5 | evidence package | `normalized/*.json` + `evidence/` | setiap record punya status/confidence/provenance, ter-redaksi |
| D1 -> D3 | feature matrix + reconstruction PRD | markdown | observed/reproduced/changed/unknown dipisah tegas |
| D3 -> D4/D5 | ADR + architecture + plan | markdown | opsi & trade-off tercatat, batas mock vs backend privat jelas |
| D4/D5 -> D6 | diff + test report | git diff + output test | build sukses, tidak ada secret, test fresh |
| D6 -> D4/D5 | daftar temuan severity | markdown | tiap temuan punya reproduksi/bukti |
| D7 -> D8 | hasil QA (unit/integration/E2E/a11y/visual) | log + artefak | coverage + kegagalan eksplisit |
| D8 -> D9 | `reports/security-gate.md` | markdown + JSON scan | temuan + exploitability + confidence + triage |
| D9 -> Gate 12 | `reports/assurance-audit.md` | markdown | architecture compliance + dependency + test evidence agregat |
| Gate 12 -> D10 | verdict release + artifact build | JSON + hash artefak | semua gate punya evidence < 24 jam |
| D10 -> Owner | deploy plan + rollback + smoke test | markdown + log | approval manusia terlampir |
| D10/D11 -> Owner | handover docs | markdown | README, runbook, release notes, known limitations |

## Aturan eskalasi (dari V1, dipertahankan)
- Maksimum 2-3 siklus Builder <-> Reviewer; siklus gagal ketiga = eskalasi dengan blocker persis.
- Security/Audit memutuskan aspek teknis; Owner memutuskan risiko bisnis.
- Tidak ada klaim parity tanpa bukti terukur.
