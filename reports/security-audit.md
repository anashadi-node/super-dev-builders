# Security Audit — Super Dev Builders Ecosystem V2.2 (upgrade)

Tanggal: 2026-10-04 WIB · Scope: repo `/home/anashadi/super-dev-builders`, 7 profil divisi, artefak upgrade.
Bukti mentah: `reports/upgrade-evidence/`.

## 1. Gate #0 — uji diri (deterministik)
| Kasus uji | Harapan | Hasil nyata | Artefak |
|---|---|---|---|
| Template kosong | FAIL | FAIL (3 fail, 2 blocked) exit 1 | `gate0-demo-fail.json` |
| Manifest lengkap (owned, Mode A) | PASS | PASS exit 0 | `gate0-demo-pass.json` |
| Mode B tanpa written_permission | BLOCKED | BLOCKED exit 2 | `gate0-demo-blocked.json` |
Kesimpulan: gate menolak pekerjaan tanpa otorisasi/persetujuan manusia dan tidak bisa diloloskan dengan
manipulasi nilai (Mode B tetap butuh izin tertulis + approval manusia).

## 2. Scan skill ekosistem (SkillSpector v2.12.0, `--no-llm`, recursive)
- 21 skill dipindai; **20 tanpa temuan**, 1 temuan.
- Temuan: `ci-cd-release-gate` — kategori *Excessive Agency / Autonomous Decision Making*, severity MEDIUM,
  skor risiko 8/100 (LOW), confidence 0.85.
  - Snippet pemicu (baris 35): *"Tidak ada `--force`, `--no-verify`, atau bypass gate. Tidak ada auto-approve
    untuk aksi destruktif/publikasi/produksi."*
  - **Triage: FALSE POSITIVE** — pola kata "auto-approve" terpicu justru pada kalimat yang **melarang**
    auto-approve. Kontrol aktual lebih ketat (produksi wajib approval manusia).
  - Tindakan: tidak ada perubahan; kalimat dipertahankan (kejelasan kontrol > menghindari keyword scanner).
- Batasan diakui: `coverage_percent = 23.81%` (5 file tuntas, 16 sebagian, 0 tidak diperiksa).
  **Hasil bersih bukan jaminan bebas temuan.**
- Verdict agregat scanner: `CAUTION`, max risk score 8/100.

## 2b. Scan deterministik (setelah approval item #4, 2026-10-04)
Tool terpasang dengan pin + verifikasi (lihat `registry/tools.yaml`):
- `ruff 0.16.10` — `uv tool install ruff==0.16.10`
- `semgrep 1.179.0` — `uv tool install semgrep==1.179.0`
- `trivy 0.75.0` — binari rilis resmi + **SHA256 terverifikasi** (`trivy_0.75.0_checksums.txt` -> `OK`)

| Tool | Perintah | Hasil | Artefak |
|---|---|---|---|
| ruff | `ruff check scripts tests` | **35 temuan awal -> 0 setelah diperbaiki** (EXE001, RUF100, I001, F401, RUF059, RUF005) | `ruff-check.txt` |
| semgrep | `semgrep scan --config p/default --metrics off .` | 344 rule pada 93 file (tracked git) -> **0 findings** | `semgrep.json` |
| trivy | `trivy fs --scanners vuln,misconfig,secret .` | **0 hasil** — `Number of language-specific files num=0`, `Detected config files num=0` | `trivy-fs.json` |

**Kejujuran hasil**: trivy 0 temuan berarti "tidak ada manifest dependency/IaC/Dockerfile untuk diperiksa",
**bukan** bukti bebas kerentanan. Scan trivy baru bermakna setelah repo punya `package.json`/`requirements.txt`/Dockerfile.

## 2c. Remediasi ruff (35 -> 0, tanpa suppress)
- `chmod +x scripts/*.py` (script ber-shebang memang executable)
- import diurutkan + import tak terpakai dibuang; `# noqa: E402` menjadi valid setelah `pyproject.toml` mengaktifkan `E402`
- `[cmd] + args` -> `[cmd, *args]`; variabel hasil unpack yang tak dipakai -> `_`
- Regresi: `pytest tests -q` tetap **21 passed**; `doctor.py`, `registry_lint.py`, `gate_check.py` tetap berfungsi.

## 3. Skills Guard native Hermes (`hermes skills audit`) — 18 skill hub, 2026-10-04
Ringkasan nyata (diparsing dari `reports/upgrade-evidence/hermes-skills-audit.txt`):
**4 DANGEROUS · 7 CAUTION · 7 SAFE · 11 keputusan BLOCKED**.
- DANGEROUS: `comfyui` (61 temuan), `huggingface-hub`, `reddit-reading`, `inference-sh-cli`.
- `inference-sh-cli` (katalog `official`, **upstream community**): DANGEROUS 5 temuan —
  CRITICAL supply_chain `SKILL.md:40 "curl -fsSL https://cli.inference.sh | sh"`,
  CRITICAL destructive `references/cli-reference.md:78 "infsh completion bash > /etc/bash_completion.d/infsh"`.
- **Tindakan (approval item #9)**: skill **dibuang** lewat `hermes skills uninstall --yes inference-sh-cli`.
  Backup lebih dulu: `~/backups/sdb-upgrade-20261004_071800/quarantine/inference-sh-cli-<TS>.tar.gz` (`gzip -t` OK).
  Verifikasi: terdaftar di `hermes skills list` = **0**, direktori skill hilang, audit ulang tidak lagi memindainya.
- Catatan kebijakan: BLOCKED juga dikenakan pada skill yang hanya berstatus CAUTION dengan upstream community
  (mis. `ascii-art`, `touchdesigner-mcp`) -> **BLOCKED != malware**; tetap wajib review manual, dan `--force` dilarang.
- **Terbuka (belum diputuskan Owner)**: `comfyui` (DANGEROUS), `huggingface-hub` (DANGEROUS), `reddit-reading` (DANGEROUS)
  masih terpasang di instalasi Hermes — di luar scope approval #4/#9.

## 4. Supply-chain venv Hermes (`hermes security audit`, OSV.dev)
- Hasil: **71 advisory / 136 komponen**, termasuk CRITICAL `PyJWT==2.13.0` (GHSA-ffc3-869f-jxw9, fixed 2.14.0)
  dan HIGH `hermes-agent==0.0.0` DNS-rebinding WebSocket (fixed 0.16.0).
- Scope: kondisi instalasi Hermes, **bukan** diperkenalkan upgrade ini.
- Rekomendasi: rencanakan upgrade Hermes + pin dependency; **jangan otomatis** (HIGH risk) — perlu approval + rollback.

## 5. Pemindaian rahasia pada repo baru
- `sdb_common.scan_for_secrets()` + `evidence_lint.py`: pola Bearer/JWT/AWS/`sk-`/GitHub token/private key.
- Hasil: tidak ada rahasia pada 21 skill, dokumen, registry, templates, scripts, workflows, agent charter.
- Tidak ada berkas `.env` bernilai; hanya template.

## 6. Isolasi & permission (kontrak, belum uji runtime)
- Gate #0 **memaksa**: whole_process_isolation, non-root, workspace-only mounts, tanpa socket Docker host,
  tanpa kredensial host, redaksi sebelum prompt.
- Security/Audit read/scan/report saja; hanya DevOps punya tool deploy; produksi tetap butuh approval manusia.
- Belum diuji: kepatuhan runtime profil terhadap batasan ini.

## 7. Risiko residual
| Risiko | Kelas | Mitigasi | Status |
|---|---|---|---|
| Skill/MCP pihak ketiga (belum dipasang) | HIGH bila dipasang | pipeline §6 + approval + pin | terbuka (by design) |
| Skill hub `inference-sh-cli` DANGEROUS | HIGH | **ditutup**: dibuang + backup + verifikasi audit ulang | SELESAI |
| Skill hub `comfyui`/`huggingface-hub`/`reddit-reading` DANGEROUS | HIGH | terdeteksi guard; keputusan Owner belum diambil | terbuka |
| Repo tanpa manifest dependency/IaC -> scan trivy tidak bermakna | LOW | catat sebagai keterbatasan; ulangi saat manifest ada | diakui |
| Advisory venv Hermes | HIGH | dilaporkan; upgrade menunggu approval | terbuka |
| SkillSpector coverage rendah | MEDIUM | review manual + guard native + lint internal | diakui |
| Permission divisi belum diuji runtime | MEDIUM | uji pada target nyata pertama | terbuka |
| False positive scanner keyword | LOW | triase manual + dokumentasi | ditutup |

## 8. Verdict
**PASS dengan catatan** untuk upgrade ini: repo bersih dari rahasia, gate deterministik terbukti bekerja,
tidak ada pihak ketiga yang diaktifkan tanpa approval. Tiga risiko terbuka wajib diselesaikan sebelum
reconstruction/rilis nyata pada target pihak mana pun.
