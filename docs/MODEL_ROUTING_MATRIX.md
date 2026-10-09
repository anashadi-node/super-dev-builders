# Model Routing Matrix — hemat token, kuat di tempat yang tepat

Sumber: blueprint §8 (cheap model untuk rutin, strong model untuk arsitektur/debug/security/final audit)
+ **keputusan Owner 2026-10-09** (pemetaan spesifik 4 model ke 16 tahap `WORKFLOW_GATES.md` §1).

## Prinsip
1. **Sequential by default.** Maksimum 1-2 spesialis aktif; paralel hanya untuk task independen nyata.
2. **Progressive disclosure.** System prompt hanya memuat nama+deskripsi skill; isi SKILL.md dimuat saat terpicu.
3. **Artifact handoff.** Kirim requirement/ADR/diff/SARIF, bukan transkrip.
4. **Tool before model.** Fakta deterministik (compiler/linter/test/scanner) dijawab tool, bukan LLM.
5. **Eskalasi berbasis bukti.** Naik kelas model HANYA setelah kegagalan nyata (2-3 siklus), bukan preventif.

## Keputusan Owner — pemetaan 16 tahap -> model (2026-10-09)

| # | Tahap (WORKFLOW_GATES §1) | Divisi | Model utama | Eskalasi |
|---|---|---|---|---|
| 01 | USER OBJECTIVE | D0 | DeepSeek V4.1 Flash | — |
| 01A | AUTHORIZATION / SCOPE GATE | D0 + `gate_check.py` | **tool deterministik** (+ DeepSeek untuk ringkas) | — |
| — | RE / RECONSTRUCTION | D1 | GLM 5.3 Flash | Sonnet 5.5 (klasifikasi sulit) |
| 02 | ORCHESTRATOR clarification | D0 | DeepSeek V4.1 Flash | — |
| 03 | RESEARCH | D2 | DeepSeek V4.1 Flash | GLM 5.3 Flash (dokumen panjang/multibahasa) |
| 04 | ARCHITECTURE + ADR | D3 | **Sonnet 5.5** | Opus 5.5 / GPT-5.6 Sol |
| 05 | HUMAN DESIGN APPROVAL | (manusia) | — | — |
| 06 | IMPLEMENTATION PLAN | D0/D3 | **DeepSeek V4.1 Flash** | Sonnet 5.5 (sistem besar) |
| 07 | FRONTEND / BACKEND | D4/D5 | **DeepSeek V4.1 Flash** | Sonnet 5.5 (algoritma/desain sulit) |
| 08 | CODE REVIEW | D6 | **Sonnet 5.5** (critical/high) · GLM 5.3 Flash (rutin) | Opus 5.5 / GPT-5.6 Sol (sengketa) |
| 09 | QA / INTEGRATION / E2E | D7 | GLM 5.3 Flash | Sonnet 5.5 (kegagalan sulit ditriase) |
| 10 | SECURITY | D8 | **Sonnet 5.5** + SAST/dep/secret scan | Opus 5.5 / GPT-5.6 Sol (keputusan kritis) |
| 11 | CODE AUDIT & ASSURANCE | D9 | **Opus 5.5 / GPT-5.6 Sol (WAJIB)** | — |
| 12 | RELEASE GATE | D10 + `release_check.py` | **tool deterministik** (+ GLM 5.3 Flash) | — |
| 13 | HUMAN APPROVAL produksi | (manusia) | — | — |
| 14 | DEVOPS DEPLOY | D10 | **DeepSeek V4.1 Flash** | Sonnet 5.5 (perubahan infra rumit) |
| 15 | OBSERVABILITY / SMOKE | D10 | **Sonnet 5.5** | Opus 5.5 / GPT-5.6 Sol |
| 16 | DOCUMENTATION + HANDOVER | D11 | **DeepSeek V4.1 Flash** | — |

## Matriks kelas pekerjaan -> kelas model (per divisi)

| Divisi | Kelas pekerjaan | Kelas model | Alasan |
|---|---|---|---|
| D0 Orchestrator | intake, routing, status, ringkasan | cheap/fast | volume tinggi, penalaran rendah |
| D1 Recon | capture + normalisasi evidence | mid (strong untuk klasifikasi) | kualitas evidence menentukan segalanya |
| D2 Research | retrieval + ringkas dokumen | cheap/mid | output pendek, verifikasi ke sumber |
| D3 Architecture | ADR, trade-off, keputusan stack | **strong** | salah di sini mahal dan menular ke seluruh proyek |
| D4/D5 Engineering | implementasi terarah dari spec + test | cheap/mid (strong untuk desain komponen) | mayoritas transformasi; naik kelas saat desain/algoritma sulit |
| D6 Code Review | diff-first review | strong (critical/high) · mid (rutin) | butuh penalaran lintas file |
| D7 QA | tulis/jalankan test, triase kegagalan | mid | deterministik, sebagian besar mekanis |
| D8 Security | triase temuan, exploitability | **strong** | false negative mahal |
| D9 Audit/Assurance | architecture drift, verdict rilis | **strong (tertinggi)** | verdict sistemik |
| D10 DevOps | build/deploy/rollback/observability | cheap/mid (strong untuk observability) | prosedural, wajib deterministik |
| D11 Docs | README/runbook/handover | cheap | volume tulis, risiko rendah |

## Status ketersediaan model & PENERAPAN (2026-10-09)

**Dasar fakta (uji hidup `hermes -z`):** `Sonnet 5.5`, `Opus 5.5`, `GPT-5.6 Sol` **tidak tersedia** di penyedia
mana pun yang ter-wire. Model yang **tersedia & terverifikasi `PONG`**:

| Model tersedia | Penyedia | Model ID | Kelas |
|---|---|---|---|
| DeepSeek V4.1 Flash | tokenrouter | `deepseek/deepseek-v4.1-flash` | murah-cepat |
| GLM 5.3 Flash | tokenharbor | `glm-5.3-flash` | murah-cepat |
| GPT-5.6 Terra | tokenharbor | `gpt-5.6-terra` | **strong** (95,4% SWE-bench Verified) |
| GPT-5.6 Luna | tokenharbor | `gpt-5.6-luna` | strong (93%) |
| Claude Sonnet 5 (pendahulu 5.5) | tokenharbor | `claude-sonnet-5` | mid (79,6%) |

> **Keputusan interim (SUDAH diterapkan; menunggu konfirmasi owner):** karena Sonnet 5.5/Opus 5.5/Sol tidak
> tersedia, kelas **strong** (architect/review/security + Audit Assurance) memakai **GPT-5.6 Terra** — model strong
> **terkuat yang tersedia** (famili GPT-5.6 dengan Sol, 95,4% SWE-bench Verified) sehingga **melebihi** Sonnet 5.5.
> Verdict Audit (tahap 11) ditandai **`interim`** sampai Sol/Opus 5.5 benar-benar ter-wire.

### Penerapan runtime (7 profil Hermes) — 7/7 `PONG`
Perbaikan wajib ditemukan: profil `cc-*` **tak punya blok `providers:`** (tokenrouter/tokenharbor/explabs hanya di
`config.yaml` MAIN), dan `model.default` **tidak meresolve alias** — harus ID model mentah + `model.provider` eksplisit.

| Profil | Tahap | Penyedia | Model |
|---|---|---|---|
| cc-orchestrator | 01,02,03,06,16 | tokenrouter | `deepseek/deepseek-v4.1-flash` |
| cc-capture-forensics | recon | tokenharbor | `glm-5.3-flash` |
| cc-architect | 04 | tokenharbor | `gpt-5.6-terra` (interim utk `sonnet-5.5`) |
| cc-builder | 07 | tokenrouter | `deepseek/deepseek-v4.1-flash` |
| cc-reviewer-qa | 08,09 | tokenharbor | `gpt-5.6-terra` (interim utk `sonnet-5.5`) |
| cc-security-governor | 10,11 | tokenharbor | `gpt-5.6-terra` (interim utk `opus-5.5`/`sol`) |
| cc-devops-docs | 14,15,16 | tokenrouter | `deepseek/deepseek-v4.1-flash` (+ observability per-task) |

Backup konfigurasi tiap profil: `config.yaml.bak-routing-20261009`.

## Aturan biaya
- Jangan pakai model kuat untuk transformasi mekanis berulang; jangan pakai model lemah untuk verdict keamanan/arsitektur.
- Naikkan kelas model hanya bila ada bukti kegagalan (bukan preventif tanpa alasan).
- Estimasi konsumsi: lihat `reports/token-estimate.md`.

## Batas: routing per-profil vs per-tahap
Profil Hermes menampung >1 tahap (mis. `cc-devops-docs` = D10+D11 = tahap 14/15/16). Default profil hanya bisa
menunjuk SATU model; tahap yang butuh kelas berbeda di-escalate **per-task** (lihat `model_routing` di tiap `agents/sdb-*.yaml`).
