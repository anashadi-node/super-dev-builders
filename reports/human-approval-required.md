# Human Approval Required — Super Dev Builders Ecosystem V2.2

Semua item di bawah **tidak dieksekusi** sampai Owner setuju. Status upgrade saat ini aman tanpa approval ini
(tidak ada pihak ketiga aktif, tidak ada deploy, tidak ada perubahan sistem operasional).

| # | Item | Kelas | Alasan butuh approval | Aksi bila disetujui |
|---|---|---|---|---|
| 1 | Pasang skill pihak ketiga (Superpowers / Trail of Bits / Anthropic / Sentry) | HIGH | blueprint §6 pipeline wajib | `hermes skills install <sumber>@<pin>` setelah `hermes skills audit` PASS + review |
| 2 | Plugin Superpowers | HIGH | §0: pernah diblokir Skills Guard (dangerous) | hanya setelah PASS; kalau gagal -> port manual |
| 3 | MCP server (GitHub MCP, Context7) | HIGH | akses network/fs luas + kredensial | konfigurasi + allowlist tool + token scope minimum |
| 4 | Pasang `ruff`, `semgrep`, `trivy` | MEDIUM | perubahan environment (user-local, reversibel) | `bash scripts/bootstrap_tools.sh --install ruff semgrep --yes`; trivy via rilis resmi + checksum |
| 5 | Pasang `codeql` (berat), `syft`, `gh` | MEDIUM | ukuran/berat + kredensial | saat dibutuhkan; pin versi + checksum |
| 6 | Tool Mode B: `mobsf`, `jadx`, `apktool`, `ghidra` | HIGH | analisis mendalam artefak; MobSF GPL-3.0 | hanya artefak berizin tertulis, terisolasi |
| 7 | Pasang 21 skill ke profil `default` | LOW-MED | +~402 token per turn | `/usr/bin/python3 scripts/install_skills.py --main` |
| 8 | Rename direktori profil `cc-*` -> `sdb-*` (opsional) | MEDIUM | memengaruhi state.db/riwayat sesi | prosedur `docs/ROLLBACK_PLAN.md` §2 |
| 9 | **Temuan**: skill hub `inference-sh-cli` DANGEROUS (5 CRITICAL) | HIGH | supply-chain | `hermes skills uninstall inference-sh-cli` atau karantina |
| 10 | **Temuan**: 71 advisory OSV di venv Hermes (1 CRITICAL PyJWT) | HIGH | upgrade Hermes berisiko | rencanakan upgrade + backup + rollback; jangan otomatis |
| 11 | Deploy produksi / migration / secret-IAM | HIGH-CRITICAL | blueprint §10A | prosedur manusia + bukti rollback |
| 12 | Target reconstruction pertama | MED-HIGH | Gate #0 wajib otorisasi | isi `evidence/<slug>/authorization.yaml` -> `gate_check.py` |

## Cara memberi approval
```text
approve: 1,4      (skill Trail of Bits + install semgrep/trivy)
tolak: 2          (plugin Superpowers)
catatan: target pertama = <url milik saya>, Mode A
```
Setiap pemasangan tetap mencatat pin versi + hasil scan ke `registry/` dan `reports/`.
