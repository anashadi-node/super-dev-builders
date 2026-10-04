# Permission Matrix — Least Privilege

Prinsip (blueprint §6, §10 butir 10): **default deny / minimum privilege**.
Tidak ada divisi yang boleh lebih dari yang dibutuhkan untuk output-nya.

| Kemampuan | D0 Orchestrator | D1 Recon | D3 Architect | D4/D5 Builder | D6/D7 Review/QA | D8/D9 Security/Audit | D10/D11 DevOps/Docs |
|---|---|---|---|---|---|---|---|
| Baca workspace proyek | ya | ya (target) | ya | ya | ya | ya (read-only) | ya |
| Tulis workspace proyek | task/plan saja | evidence/normalized | docs/ADR | kode+tests | tidak | tidak | konfigurasi deploy |
| Baca home/secret host | **tidak** | **tidak** | **tidak** | **tidak** | **tidak** | **tidak** | minimal (deploy config) |
| Eksekusi capture browser | tidak | ya (Mode A) | tidak | tidak | tidak | tidak | tidak |
| Analisis artefak Mode B | tidak | ya (izin tertulis) | tidak | tidak | tidak | ya (read-only) | tidak |
| Jalankan test/lint | ya | ya | ya | ya | ya | ya | ya |
| Jalankan SAST/dependency/secret scan | tidak | tidak | tidak | terbatas (lokal) | ya | ya (utama) | ya (pra-deploy) |
| Menulis laporan gate | draf | evidence report | ADR | test report | review/QA report | security/audit report (**final**) | deploy/handover report |
| Deploy staging | tidak | tidak | tidak | tidak | tidak | tidak | ya |
| Deploy produksi | **tidak** | **tidak** | **tidak** | **tidak** | **tidak** | **tidak** | hanya dengan approval manusia |
| Rotasi credential / IAM | tidak | tidak | tidak | tidak | tidak | tidak | tidak (prosedur manusia) |

Aturan tambahan:
1. D8/D9 (Security & Audit) adalah **read/scan/report** — tidak boleh mengubah kode maupun men-deploy.
2. D10 memiliki tool deploy tetapi produksi berhenti di Gate 13 (approval manusia) — tidak ada auto-approve.
3. Builder hanya menyentuh workspace proyek; tidak ada akses home direktori lain atau vault.
4. Untuk input untrusted (web, repo pihak ketiga, MCP, plugin): wajib whole-process isolation (Hermes Docker/Compose
   atau sandbox whole-process setara), non-root, mount workspace saja, minimalkan egress, tanpa socket Docker host,
   tanpa mount kredensial host.
5. Terminal sandbox saja **bukan** containment penuh (blueprint §0 audit V2.1).

## Escalation
| Situasi | Tindakan |
|---|---|
| Butuh data/akses di luar scope | STOP -> BLOCKED -> minta otorisasi/kredensial dari Owner |
| Temuan security critical saat deploy | batal deploy, lapor, tidak ada override otonom |
| Konflik antar divisi | D9/Assurance memutuskan aspek teknis; Owner memutuskan risiko bisnis |
