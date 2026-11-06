# Architecture — Super Dev Builders Ecosystem V2.2

Sumber: `docs/00_MASTER_BLUEPRINT_V2.2.html` (§2 organisasi, §3 stack, §4 reconstruction, §7 workflow).

## 1. Tesis desain
Dua jalur produksi dalam satu ekosistem:

1. **Build From Specification** — requirement -> desain -> bangun -> verifikasi.
2. **Authorized Reconstruction From Existing Target** — observasi sah -> evidence -> spesifikasi ulang -> bangun ulang clean-room -> bandingkan fidelity.

Tujuan reconstruction: **understand -> specify -> rebuild -> compare**, bukan menembus proteksi.
Yang disalin adalah **observable requirements & behavior**, bukan internal implementation.

## 2. Struktur organisasi (12 divisi)

```text
                         HUMAN OWNER
                              |
                     MASTER ORCHESTRATOR          D0
                              |
        +---------------------+----------------------+
        v                     v                      v
 NEW PROJECT         EXISTING/AUTHORIZED TARGET   GOVERNANCE
        |                     |
        |                     v
        |            REVERSE ENGINEERING &
        |             RECONSTRUCTION DIVISION      D1
        |                     |
        +--------------+------+
                       v
                    RESEARCH                      D2
                       v
                  ARCHITECTURE                    D3
                       v
                  ENGINEERING                     D4/D5
                     +---+---+
                     v       v
                  FRONTEND  BACKEND (Core/API, Data/DB, Identity/Integration)

====================== INDEPENDENT ASSURANCE ======================
     CODE REVIEW (D6) -> QA/TEST (D7) -> SECURITY (D8) -> CODE AUDIT & ASSURANCE (D9)
                                                |
                                                v
                                           RELEASE GATE
                                                |
                                                v
                                             DEVOPS (D10)
                                                |
                                                v
                                            PRODUCTION
                                                |
                                      DOCUMENTATION / HANDOVER (D11)
```

## 3. Divisi -> owner profil (implementasi Hermes)

| ID | Divisi | Profil owner | Mode/skill tambahan |
|----|--------|--------------|---------------------|
| D0 | Master Orchestrator / Product & Planning | `sdb-orchestrator` | intake, plan, routing, bounded loop |
| D1 | Reverse Engineering & Reconstruction | `sdb-recon` | Mode A default; Mode B hanya dengan otorisasi tertulis |
| D2 | Research | `sdb-orchestrator` + `sdb-architect` | retrieval docs/web, artifact pendek |
| D3 | Architecture | `sdb-architect` | ADR, technology-selection |
| D4 | Engineering — Frontend | `sdb-builder` | UI/UX, a11y, TDD |
| D5 | Engineering — Backend | `sdb-builder` | Core/API, Data/DB, Identity/Integration |
| D6 | Code Review | `sdb-reviewer` | diff-first review |
| D7 | QA / Test | `sdb-reviewer` | unit/integration/E2E/contract |
| D8 | Security | `sdb-security` | SAST/dependency/secret scan, read-only |
| D9 | Code Audit & Engineering Assurance | `sdb-security` | architecture drift + release audit, independent |
| D10 | DevOps / Release / Reliability | `sdb-devops` | deploy dengan approval manusia |
| D11 | Documentation | `sdb-devops` | AGENTS.md/ADR/runbook/handover |

Aturan independence: D8/D9 **tidak boleh** berada di profil yang membangun kode (D4/D5), dan tidak punya hak deploy.
D10 satu-satunya pemegang tool deploy; produksi selalu butuh approval manusia (blueprint §6, §10A).

## 4. Komponen runtime

| Komponen | Implementasi | Catatan |
|---|---|---|
| Control plane | Hermes (skills, profiles, kanban, cron) | baseline native; plugin pihak ketiga = opt-in bergate |
| Gate #0 | `scripts/gate_check.py` + `templates/authorization_manifest.yaml` | deterministik, PASS/FAIL/BLOCKED |
| Capture engine | Playwright (primary), Crawlee (secondary, hormati rate limit/robots) | trace/DOM/screenshot/responsive states |
| Evidence store | `evidence/<target>/` (raw, redacted) -> `normalized/<target>/*.json` | provenance + confidence wajib |
| Rebuild workspace | `reconstruction/<target>/` | clean implementation dari spec/evidence |
| Verifikasi | `verification/<target>/` (visual, behavior, a11y, perf, API contract) | axe-core, Lighthouse, Playwright assertions |
| Release gate | `scripts/release_check.py` + `docs/WORKFLOW_GATES.md` | wajib fresh evidence; run DID ditolak lebih awal (exit 2), bukan tujuh baris "artefak tidak ditemukan" |
| Deep analysis (Mode B) | MobSF/JADX/Apktool/Ghidra — isolated, on-demand | hanya artefak yang diotorisasi |

## 5. Aliran gate (ringkas)
```text
Gate #0 -> intake -> (reconstruction optional) -> research -> architecture+ADR -> approval (major)
 -> plan -> implement -> review -> QA -> security -> audit/assurance -> release gate -> approval
 -> deploy -> smoke/observability -> docs/handover
```

## 6. Bottleneck yang diakui (jujur)
Bottleneck V1 bukan jumlah agent, melainkan **kualitas evidence + capture yang aman**, dan **verifikasi yang terukur**.
V2.2 menambah satu bottleneck baru yang harus dijaga: **skill/tool supply-chain** (setiap tambahan harus lewat gate,
kalau tidak ekosistem justru melemah). Karena itu registry + quarantine + scanner native diprioritaskan
di atas penambahan jumlah skill.
