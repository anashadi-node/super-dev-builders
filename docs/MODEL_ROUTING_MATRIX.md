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
| 10 | SECURITY | D8 | **Opus 5.5** + SAST/dep/secret scan (keputusan Owner 2026-10-30) | GPT-5.6 Sol (cadangan bila Anthropic down) |
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
| D8 Security | triase temuan, exploitability | **strong — Opus 5.5 permanen** | false negative mahal; produk multi-tenant berbayar |
| D9 Audit/Assurance | architecture drift, verdict rilis | **strong (tertinggi)** | verdict sistemik |
| D10 DevOps | build/deploy/rollback/observability | cheap/mid (strong untuk observability) | prosedural, wajib deterministik |
| D11 Docs | README/runbook/handover | cheap | volume tulis, risiko rendah |

## Status ketersediaan & PENERAPAN (revisi 3 — 2026-10-09)

**Pembaruan penting.** Setelah saldo TokenRouter diisi pemilik, `/v1/models` TokenRouter **kini menyajikan semua
model yang dibutuhkan**: `anthropic/claude-sonnet-5.5`, `anthropic/claude-opus-5.5`, `openai/gpt-5.6-sol`,
`z-ai/glm-5.3-flash`, `deepseek/deepseek-v4.1-flash`, `z-ai/glm-5.3`, `z-ai/glm-5.3-free`, `nvidia/nemotron-...:free`.
Batas 5 model sebelumnya = efek **saldo kosong**, bukan batas tetap kunci.

### Kebijakan penyedia per-model (keputusan pemilik, 9 Okt 2026)
> **Native dulu, TokenRouter kedua.** Tiap model memakai langganan aslinya lebih dulu; TokenRouter = jaring kedua.

| Model | Penyedia utama (native) | Cadangan |
|---|---|---|
| DeepSeek V4.1 Flash | **DeepSeek API** — ID sah `deepseek-flash` (`deepseek-v4.1-flash` -> HTTP 400) | `opencode-go` -> `glm-5.3-flash` (DeepSeek **tidak** lewat perantara) |
| Sonnet 5.5 | **Anthropic** — `claude-sonnet-5-5` | `tokenrouter` -> `anthropic/claude-sonnet-5.5` |
| Opus 5.5 | **Anthropic** — `claude-opus-5-5` | `tokenrouter` -> `anthropic/claude-opus-5.5` |
| GPT-5.6 Sol | **OpenAI (Codex OAuth)** — `gpt-5.6-sol` | `tokenrouter` -> `openai/gpt-5.6-sol` |
| GLM 5.3 Flash | **TokenRouter** — `z-ai/glm-5.3-flash` | `tokenharbor` -> `glm-5.3-flash` |

### Pemetaan peran -> profil (TERPASANG & TERVERIFIKASI — 10 profil PONG)
| Peran | Profil | Model | Utama | Cadangan |
|---|---|---|---|---|
| Research/recon | cc-capture-forensics | **GLM 5.3 Flash** | tokenrouter `z-ai/glm-5.3-flash` | tokenharbor `glm-5.3-flash` -> opencode-go `glm-5.3-flash` |
| Frontend | cc-frontend | **GLM 5.3 Flash** | tokenrouter `z-ai/glm-5.3-flash` | tokenharbor `glm-5.3-flash` -> opencode-go `glm-5.3-flash` |
| Plan/intake/docs | cc-orchestrator | DeepSeek V4.1 Flash | **deepseek `deepseek-flash`** (API resmi) | opencode-go `glm-5.3-flash` |
| Backend | cc-builder | **DeepSeek V4.1 Flash** | **deepseek `deepseek-flash`** (API resmi) | opencode-go `glm-5.3-flash` |
| DevOps deploy/docs | cc-devops-docs | DeepSeek V4.1 Flash | **deepseek `deepseek-flash`** (API resmi) | opencode-go `glm-5.3-flash` |
| Arsitektur/ADR | cc-architect | Sonnet 5.5 | anthropic `claude-sonnet-5-5` | tokenrouter `anthropic/claude-sonnet-5.5` |
| Code review | cc-reviewer-qa | Sonnet 5.5 | anthropic `claude-sonnet-5-5` | tokenrouter `anthropic/claude-sonnet-5.5` |
| **QA Assurance/Testing/E2E** | cc-reviewer-qa | **Sonnet 5.5** | anthropic `claude-sonnet-5-5` | tokenrouter `anthropic/claude-sonnet-5.5` |
| Observability/smoke | cc-observability | Sonnet 5.5 | anthropic `claude-sonnet-5-5` | tokenrouter `anthropic/claude-sonnet-5.5` |
| Security | cc-security-governor | Opus 5.5 | anthropic `claude-opus-5-5` | tokenrouter `anthropic/claude-opus-5.5` |
| **Audit Assurance** | auditor | **Opus 5.5 (atau Sol)** | anthropic `claude-opus-5-5` | openai-codex `gpt-5.6-sol` -> tokenrouter `anthropic/claude-opus-5.5` |
| Safety/Privasi | keamanan | Sonnet 5.5 | anthropic `claude-sonnet-5-5` | tokenrouter `anthropic/claude-sonnet-5.5` |

**Fallback config MAIN:** `tokenrouter/anthropic/claude-sonnet-5.5` -> `deepseek` `deepseek-flash` (API resmi) -> `openai-codex/gpt-5.6-sol`.

**Catatan teknis (jebakan yang ditemukan & diperbaiki).** Saat pindah ke provider bawaan, field sisa
`model.base_url`/`model.key_env` warisan scaffold `custom` **harus dihapus** — jika tidak, permintaan bisa
salah alamat/kunci (contoh: `key_env: TOKENHARBOR_API_KEY` tersangkut di profil ber-`base_url` TokenRouter).
Sudah dibersihkan di sepuluh profil di atas. Backup: `config.yaml.bak-routing2-20261009` per profil.

## Revisi 4 — 2026-10-29: DeepSeek 100% jalur resmi (audit pemilik)

**Temuan.** Sebelas profil divisi ternyata **masih** menyimpan `model.base_url: https://api.tokenrouter.com/v1`
(warisan scaffold `custom`). Akibatnya meski `model.provider: deepseek`, permintaan DeepSeek tetap dikirim ke
TokenRouter memakai kunci `DEEPSEEK_API_KEY` -> **HTTP 401 `Invalid token`**, dan layar routing deck menampilkan
`tokenrouter - deepseek/deepseek-v4.1-flash`. Dua profil (`alpaca`, `lokal`) juga menyisakan `.env` tanpa
`DEEPSEEK_API_KEY`, sehingga agen gagal dengan `No usable credentials found for provider 'deepseek'`.

**Perbaikan (diverifikasi dengan panggilan nyata, bukan asumsi).**
1. `model.base_url` sebelas profil -> `https://api.deepseek.com/v1`: alpaca, anantara-sakti, astronacci,
   cex-binance, hl-harvest, lokal, pregain, robinhood, sodex, sodex-cex-monitor, villa-agency.
2. `DEEPSEEK_API_KEY` disebarkan ke semua `.env` profil yang belum punya (21 profil).
3. Cadangan DeepSeek yang masih menunjuk TokenRouter diganti **opencode-go `glm-5.3-flash`** untuk
   cc-orchestrator/cc-builder/cc-devops-docs: kelas model sama, tapi DeepSeek tidak pernah lewat perantara.
4. `dashboard/agents.json` `primary` -> `deepseek-flash`, `available_now` -> `deepseek-flash (DeepSeek API resmi)`.
5. alias `deepseek` di config utama -> `deepseek-flash` + provider `deepseek` (sebelumnya menunjuk TokenRouter).

**Bukti.** Panggilan uji `hermes -p <profil> -z "Balas HANYA: PONG" --usage-file` pada default, cc-builder,
cc-orchestrator, cc-devops-docs, sodex, sodex-cex-monitor, alpaca, lokal, pregain, villa-agency: semuanya
`model=deepseek-flash provider=deepseek`. Backup config sebelum perubahan: `~/.hermes/backup-deepseek-native-*`.

**Aturan tetap.** DeepSeek hanya boleh muncul dengan provider `deepseek` (atau alias `deepseek` yang menunjuk
sana). Bila platform DeepSeek bermasalah, cadangan memakai keluarga model lain — bukan DeepSeek dari perantara.

## Revisi 5 — 2026-10-30: D8 Security Governor = Opus 5.5 permanen (keputusan Owner)

**Temuan (drift dokumen-vs-config).** Matriks baris "Security | cc-security-governor | Opus 5.5" bertabrakan
dengan config aktual (`model.default: claude-sonnet-5-5`) dan dengan tabel tahap 10 yang menaruh Sonnet sebagai
primary. Deck menampilkan config nyata (Sonnet), jadi deck benar dan dokumen menyesatkan: gate keamanan terlihat
dijaga Opus padahal tidak.

**Keputusan Owner (29-Okt-2026, dipilih eksplisit dari 4 opsi).** `cc-security-governor` = **Opus 5.5 permanen**,
bukan Sonnet + eskalasi. Alasan: SDB adalah produk berbayar multi-tenant; kelas bug termahal adalah cacat logika
(IDOR, isolasi tenant, bypass otorisasi, alur pembayaran) yang lolos dari triase model kelas menengah. Trade-off
yang diterima: biaya dan latensi D8 naik pada setiap task.

**Penerapan.**
1. `~/.hermes/profiles/cc-security-governor/config.yaml` -> `model.default: claude-opus-5-5` (provider anthropic).
2. `dashboard/agents.json` `sdb-security.primary` -> `opus-5.5`; cadangan `gpt-5.6-sol`.
3. Tabel tahap 10 + tabel kelas pekerjaan D8 diperbarui (di atas).
4. Profil `keamanan` (Penjaga Keamanan/Security Guardian) **tetap Sonnet 5.5** — perannya berbeda: penjaga
   lintas-ekosistem (config, kredensial, permission, PC), bukan gate kode per-rilis.

**Bukti.** `hermes -p cc-security-governor -z "PONG" --usage-file` -> `model=claude-opus-5-5 provider=anthropic`;
`/api/state` deck kartu D8 menampilkan Opus 5.5. Backup: `~/.hermes/backup-d8-opus-*`.

**Catatan konflik prinsip.** Prinsip #5 di atas ("eskalasi hanya setelah kegagalan nyata") dilanggar secara sadar
untuk D8 — ini pengecualian yang diputuskan Owner dengan alasan risiko, bukan kelalaian. Jangan "kembalikan" D8 ke
Sonnet sebagai optimasi biaya tanpa persetujuan Owner.

## Aturan biaya
- Jangan pakai model kuat untuk transformasi mekanis berulang; jangan pakai model lemah untuk verdict keamanan/arsitektur.
- Naikkan kelas model hanya bila ada bukti kegagalan (bukan preventif tanpa alasan).
- Estimasi konsumsi: lihat `reports/token-estimate.md`.

## Batas: routing per-profil vs per-tahap
Profil Hermes menampung >1 tahap (mis. `cc-devops-docs` = D10+D11 = tahap 14/15/16). Default profil hanya bisa
menunjuk SATU model; tahap yang butuh kelas berbeda di-escalate **per-task** (lihat `model_routing` di tiap `agents/sdb-*.yaml`).
