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

## 3. Skills Guard native Hermes (`hermes skills audit`)
- Berjalan tanpa `--force`.
- Temuan: skill hub `inference-sh-cli` -> **DANGEROUS/BLOCKED** (5 CRITICAL: `curl -fsSL https://cli.inference.sh | sh`
  supply-chain, penulisan ke `/etc/bash_completion.d/`).
- Dampak: ada di instalasi Hermes, bukan bagian ekosistem ini. Rekomendasi: **uninstall/karantina**; dilarang `--force`.
  Keputusan = Owner (`reports/human-approval-required.md` #9).

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
| Skill hub DANGEROUS terpasang | HIGH | terdeteksi guard; menunggu keputusan Owner | terbuka |
| Advisory venv Hermes | HIGH | dilaporkan; upgrade menunggu approval | terbuka |
| SkillSpector coverage rendah | MEDIUM | review manual + guard native + lint internal | diakui |
| Permission divisi belum diuji runtime | MEDIUM | uji pada target nyata pertama | terbuka |
| False positive scanner keyword | LOW | triase manual + dokumentasi | ditutup |

## 8. Verdict
**PASS dengan catatan** untuk upgrade ini: repo bersih dari rahasia, gate deterministik terbukti bekerja,
tidak ada pihak ketiga yang diaktifkan tanpa approval. Tiga risiko terbuka wajib diselesaikan sebelum
reconstruction/rilis nyata pada target pihak mana pun.
