# Human Approval Required — Super Dev Builders Ecosystem V2.2

Semua item di bawah **tidak dieksekusi** sampai Owner setuju. Status upgrade saat ini aman tanpa approval ini
(tidak ada pihak ketiga aktif, tidak ada deploy, tidak ada perubahan sistem operasional).

| # | Item | Kelas | Alasan butuh approval | Aksi bila disetujui |
|---|---|---|---|---|
| 1 | ~~Pasang skill pihak ketiga (Superpowers / Trail of Bits / Anthropic / Sentry)~~ **SELESAI 2026-10-05 (sebagian, sesuai keputusan Owner)** | HIGH | — | **Trail of Bits: 6 skill TERPASANG** (semgrep, codeql, sarif-parsing, differential-review, fp-check, audit-context-building) lewat hub (verdict ALLOWED) dan dilengkapi dari commit pin; **`variant-analysis` DIBLOKIR hub** (caution, 11 findings) — TIDAK dibypass; `modern-python` + `post-patch-validation` menunggu kuota GitHub API. **`anthropics/skills` DITOLAK** (lisensi kontradiktif — 3 sumber); **`getsentry/skills` DITOLAK** (2/4 sudah ada di disk, 1 tertutup ToB, `agents-md` ditunda). Bukti: `registry/skills.yaml` §B + `reports/upgrade-evidence/third-party-integrity.json` + `docs/THIRD_PARTY_SKILLS_DECISION_2026-10-05.md` |
| 2 | ~~Plugin Superpowers~~ **DITOLAK permanen 2026-10-05** | HIGH | — | Status `REJECTED_BLUEPRINT`: dokumen acuan V2.2 sendiri melarang instalasi plugin otomatis/default, DAN kapabilitas metodologinya sudah ada sebagai skill native (`systematic-debugging`, `test-driven-development`, `requesting-code-review`). Tidak ada gap yang perlu ditambal. |
| 3 | MCP server (GitHub MCP, Context7) | HIGH | akses network/fs luas + kredensial | **DITUNDA 2026-10-05**: oracle read-only sudah tersedia TANPA kredensial (REST anonim + `raw.githubusercontent` terbukti HTTP 200 pada commit pin) -> MCP hanya menambah permukaan serangan + kebutuhan token. Pasang saat ada kebutuhan tetap ber-kredensial, dengan token scope minimum + allowlist tool. |
| 4 | ~~Pasang `ruff`, `semgrep`, `trivy`~~ **SELESAI 2026-10-04** | MEDIUM | — | ruff 0.16.10 + semgrep 1.179.0 (uv tool) + trivy 0.75.0 (rilis resmi, SHA256 OK). Bukti: `reports/upgrade-evidence/`, `registry/tools.yaml` |
| 5 | ~~Pasang `codeql`, `syft`, `gh`~~ **SELESAI 2026-10-04** | MEDIUM | — | Syft 1.54.0 + CodeQL 2.27.1 dipasang dengan checksum OK; **`gh` tetap pending** (belum ada remote repo; kebutuhan read-only tertutup REST anonim). Bukti: `reports/upgrade-evidence/codeql-and-sbom-summary.md` |
| 6 | Tool Mode B: `mobsf`, `jadx`, `apktool`, `ghidra` | HIGH | analisis mendalam artefak; MobSF GPL-3.0 | **DITUNDA 2026-10-05**: belum ada artefak dengan izin tertulis dari pemilik (Gate #0). Hanya dipasang setelah ada target berizin + isolasi. |
| 7 | Pasang 21 skill ke profil `default` | LOW-MED | +~402 token per turn | `/usr/bin/python3 scripts/install_skills.py --main` |
| 8 | Rename direktori profil `cc-*` -> `sdb-*` (opsional) | MEDIUM | memengaruhi state.db/riwayat sesi | prosedur `docs/ROLLBACK_PLAN.md` §2 |
| 9 | ~~**Temuan**: skill hub `inference-sh-cli` DANGEROUS (5 CRITICAL)~~ **SELESAI 2026-10-04** | HIGH | — | Dibuang via `hermes skills uninstall --yes`; backup `~/backups/sdb-upgrade-20261004_071800/quarantine/`; verifikasi list=0 + audit bersih |
| 9b | ~~**Temuan**: skill hub DANGEROUS lain — `comfyui` (61 temuan), `huggingface-hub`, `reddit-reading`~~ **SELESAI 2026-10-04** | HIGH | — | Dibuang via `hermes skills uninstall --yes`; backup 3 tar di `~/backups/.../quarantine/`; audit ulang: 0 DANGEROUS; denylist `registry/hub_skills_denylist.yaml` |
| 10 | **Temuan**: 71 advisory OSV di venv Hermes (1 CRITICAL PyJWT) | HIGH | upgrade Hermes berisiko | rencanakan upgrade + backup + rollback; jangan otomatis |
| 11 | Deploy produksi / migration / secret-IAM | HIGH-CRITICAL | blueprint §10A | prosedur manusia + bukti rollback |
| 12 | ~~Target reconstruction pertama~~ **SELESAI 2026-10-04** | MED-HIGH | — | Target `sdb-local-demo` (milik sendiri, Mode A): Gate #0 PASS, capture/redaksi/lint/fidelity/release gate semua terbukti. Lihat `docs/PIPELINE_E2E_EVIDENCE.md` |

## Cara memberi approval
```text
approve: 1,4      (skill Trail of Bits + install semgrep/trivy)
tolak: 2          (plugin Superpowers)
catatan: target pertama = <url milik saya>, Mode A
```
Setiap pemasangan tetap mencatat pin versi + hasil scan ke `registry/` dan `reports/`.
