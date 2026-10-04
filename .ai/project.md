# Project State — Super Dev Builders Ecosystem

Tanggal upgrade: 2026-10-04 WIB
Owner: Mas Anas
Versi: V2.2 (upgrade dari "Copy Cloning Super Dev Builders" V1 — lihat docs/UPGRADE_REPORT.md)

## North Star
Ekosistem software-engineering Hermes yang mampu membangun **dan** merekonstruksi (authorized)
website/app/platform dengan gate yang kuat, evidence deterministik, dan konsumsi token/PC terkendali.

## Success Criteria V2.2
- 12 divisi V2.2 terdefinisi dengan charter, permission, dan owner profile eksplisit.
- 21 custom skill ekosistem terpasang, kecil, ter-test, dan tercatat di registry dengan sumber+pin.
- Gate #0 (authorization/scope) berjalan sebagai tool deterministik, bukan checklist manual.
- Release gate tidak bisa PASS dari pernyataan LLM; wajib fresh build/test/scan evidence.
- Whole-process isolation + least privilege untuk input untrusted/produksi.
- Semua pihak ketiga (skill/MCP/tool) berstatus register: KEEP/ADD/QUARANTINE/pending-approval.

## Hard Boundaries (dari blueprint §4)
- No auth/access-control/CAPTCHA/anti-bot/paywall/rate-limit/DRM/licensing/pinning bypass.
- No credential/session/token/PII capture atau masuk konteks LLM.
- No private source/backend/API/data extraction tanpa otorisasi tertulis.
- No deploy produksi otonom; no autonomous destructive action.
- No skill/MCP pihak ketiga tanpa lolos pipeline supply-chain.

## Legacy
V1: `/home/anashadi/copy-cloning-super-dev-builders` (diarsipkan, tidak dihapus) —
backup: `/home/anashadi/backups/sdb-upgrade-20261004_071800/`.
