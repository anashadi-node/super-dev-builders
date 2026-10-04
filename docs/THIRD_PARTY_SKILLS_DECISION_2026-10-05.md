# Keputusan Skill Pihak Ketiga — 2026-10-05

**Mandat Owner**: *"Approve silahkan jalankan, saya mengikuti saran rekomendasi dari analisa terbaik, riset penelitian terbaik dan perhitungan terbaik dari anda, lakukan yang paling terbaik untuk Visi, isi dan Tujuan Utama Project ini sesuai dokumen acuan terakhir."*

**Acuan**: `docs/00_MASTER_BLUEPRINT_V2.2.html` §6 (pipeline supply-chain), §0 (plugin tidak diaktifkan default), `registry/skills.yaml` §B, skill `third-party-tool-vetting`, `riset-penelitian` (falsifikasi + triangulasi).

**Prinsip yang dipakai untuk memutuskan**
1. Dokumen acuan menang atas preferensi.
2. Ukur cakupan sebelum menambah (jangan pasang yang sudah ada).
3. Oracle deterministik dulu; dependensi baru harus menambah informasi, bukan mode kegagalan.
4. Gate keamanan tidak pernah dibypass; blokir = dilaporkan, bukan dipaksa.
5. Satu fakta penting = ≥2 sumber independen.

---

## 1. Ringkasan keputusan

| Sumber | Lisensi (terverifikasi) | Keputusan | Status |
|---|---|---|---|
| `trailofbits/skills` | **CC-BY-SA-4.0** | **DIPASANG (6 dari 9 skill)** | `INSTALLED` |
| `variant-analysis` (bagian ToB) | idem | **DIBLOKIR hub** (11 findings, caution) | tidak dibypass |
| `modern-python`, `post-patch-validation` | idem | menunggu kuota GitHub API | dijadwalkan ulang |
| `anthropics/skills` | **tidak ada lisensi** | **DITOLAK** | `REJECTED_LICENSE` |
| `obra/superpowers` | MIT | **DITOLAK** (dilarang acuan + sudah tercakup) | `REJECTED_BLUEPRINT` |
| `getsentry/skills` | Apache-2.0 | **DITOLAK** (cakupan terukur 2/4 ada di disk) | `REJECTED_COVERED` |
| `getsentry/sentry-for-ai` | MIT | tetap OPTIONAL (butuh akun SaaS, data keluar host) | ditunda |
| `github/github-mcp-server`, `upstash/context7` | MIT | **DITUNDA** (butuh kredensial; oracle read-only sudah ada) | pending |

Yang terpasang: **semgrep, codeql, sarif-parsing, differential-review, fp-check, audit-context-building** — 6 skill, semuanya **byte-identik** dengan commit pin `82fe8226252622fa807643bdca1710901198553a`.

---

## 2. Triangulasi lisensi (kenapa `anthropics/skills` gugur)

| Sumber independen | Hasil |
|---|---|
| GitHub API `license` | `spdx_id = null` (tidak ada lisensi terdeteksi) |
| Isi direktori root repo | **tidak ada berkas LICENSE** — hanya `README.md`, `THIRD_PARTY_NOTICES.md`, `.gitignore`, dan folder skill |
| Frontmatter `SKILL.md` | `license: Complete terms in LICENSE.txt` — **tetapi `LICENSE.txt` tidak ada di repo** |

Kesimpulan: kontradiksi internal, tidak ada lisensi efektif → tanpa lisensi berarti hak cipta penuh pemilik. **Tidak dipasang.** Keputusan ini juga menjadi moot karena kapabilitasnya sudah tertutup (bagian 3). Bila Owner ingin menempuh jalur ini, langkahnya adalah meminta pernyataan lisensi tertulis dari pemilik repo — bukan menebak.

Lisensi ToB terverifikasi **CC-BY-SA-4.0** (API + berkas `LICENSE` di repo). Konsekuensi yang diterapkan: atribusi dicatat di `registry/skills.yaml`, skill dipasang **apa adanya** (tidak dimodifikasi), dan **tidak digabungkan** ke skill MIT milik kami. Bila suatu saat dimodifikasi, versi turunannya wajib CC-BY-SA-4.0.

---

## 3. Pengukuran cakupan (bukti, bukan selera)

Perintah: hitung berkas skill kita yang menyebut tiap kapabilitas (`grep -rIl` atas `skills/` + bundle profil).

| Kapabilitas | Berkas skill kita yang menyebut | Vonis |
|---|---|---|
| semgrep / codeql | 1 (`ci-cd-release-gate`) | gap nyata → **pasang** |
| SARIF parsing | **0** | gap nyata → **pasang** |
| differential review | **0** | gap nyata → **pasang** |
| variant analysis | **0** | gap (diblokir hub) |
| false-positive triage | **0** | gap nyata → **pasang** |
| audit context building | **0** | gap nyata → **pasang** |
| supply chain / post-patch / mutation | **0** | gap (2 menunggu kuota; mutation tidak diadopsi — butuh dependensi baru) |

Untuk Sentry, pemetaan padanan dilakukan dengan mengecek keberadaan berkas di disk (bukan asumsi):

| Skill Sentry | Padanan di host | Vonis |
|---|---|---|
| `skill-scanner` | `skill-inspector` + `skillspector` (**ada**) | tertutup |
| `code-simplifier` | `simplify-code` (**ada**) | tertutup |
| `security-review` | set ToB (`differential-review` + semgrep/codeql) + `security-static-review` kami | tertutup |
| `agents-md` | tidak ada padanan persis | ditunda sampai ada deliverable nyata |

---

## 4. Pembacaan hasil scanner — dua bug kelas "penilai mati" yang tertangkap

### 4.1 Run LLM rusak yang menghasilkan angka meyakinkan (fail-open semu)

`skillspector scan` dengan provider `claude_cli` **gagal total** (`OSError`; CLI `claude` di host ini memang rusak: *"native binary not installed"*). Yang berbahaya: laporan tetap ditulis dengan `risk_score = 100`, severity `CRITICAL`, rekomendasi `DO_NOT_INSTALL` — **tetapi** `execution_successful = false` dan `analysis_completeness.coverage_percent = 0.0`.

Artinya angka itu **artefak run rusak**, bukan temuan. Yang menyelamatkan: harness SkillSpector menandai kegagalan (fail-closed). Yang hampir menyesatkan: angka + labelnya terlihat seperti vonis. Karena itu laporan ini hanya memakai **run statis deterministik** sebagai bukti, dan menyebut keterbatasan secara eksplisit.

### 4.2 Run statis: 24 temuan, **0 di antaranya perilaku jahat** (diperiksa satu per satu)

| Kategori | Isi sebenarnya | Vonis |
|---|---|---|
| `analysis-evasion` ×17 | berkas belum terinspeksi — remediation tool-nya sendiri: *"incomplete analysis is not proof of malicious evasion"* | artefak cakupan |
| `Tool Misuse` ×2 | `[ -n "$OUTPUT_DIR" ] && rm -rf "$OUTPUT_DIR/repos"` — pembersihan **ter-guard** di dalam OUTDIR sendiri | nyata tapi aman-terkendali → dicatat sebagai caveat operasional |
| `Dangerous Code Execution` ×3 | `subprocess` di **berkas test** milik skill itu sendiri | benign |
| `Excessive Agency` ×2 | cocok di **tabel anti-pattern** ("Lying about task status…") — konteks negasi | false positive |
| `MCP *` ×5 | tidak ada `finding`/snippet yang bisa ditindak | tak actionable |

### 4.3 Jarring ketiga: pemindai deterministik milik kami

`scripts/third_party_scan.py` (regex, bukan LLM) memeriksa 10 kelas pola terlarang (`sudo`, `curl|sh`, `wget|sh`, `eval(`, `base64 -d`, baca kredensial, exfil HTTP, `rm -rf /`, `chmod 777`, reverse shell):

- `semgrep` + `codeql` terpasang: **0 temuan**
- seluruh direktori upstream `codeql` (34 berkas): **0 temuan**
- 7 kandidat: 8 hit → **semuanya dijelaskan**: 6 hit `eval(` adalah **pola rule semgrep** (mendeteksi `eval` di kode target, bukan mengeksekusi) dan 2 hit `curl|sh` adalah **dokumentasi installer upstream** di `modern-python/references/`.

---

## 5. Hasil pemasangan & integritas

Metode: `hermes skills install skills-sh/trailofbits/skills/... --yes` → verdict hub **ALLOWED** (scanner `skills-guard-v8`, provenance fresh). Tidak ada `--force`.

| Skill | Berkas upstream | Berkas disalin oleh `sync` | Integritas vs pin |
|---|---|---|---|
| semgrep | 9 | 0 | identik |
| codeql | 34 | **32** | identik (setelah dilengkapi) |
| sarif-parsing | 8 | 0 | identik |
| differential-review | 7 | 0 | identik |
| fp-check | 9 | 0 | identik |
| audit-context-building | 6 | **3** | identik (setelah dilengkapi) |

**Cacat pemasangan yang ditemukan**: hub hanya memasang `codeql` 2 dari 34 berkas — SKILL.md-nya menunjuk 12 `references/*.md` yang **tidak ada** (skill rusak bila dibiarkan). **Sebab pemotongan tidak terbukti** dari sisi kami; yang terbukti adalah efeknya. Penyelesaian: `scripts/sync_third_party_skills.py --fix` yang melengkapi dari **commit pin yang sama** lewat git protocol (bukan API) lalu **membuktikan sha256 byte-identik**.

Karena `codeql` dilengkapi di luar jalur unduh hub, isinya diverifikasi ulang dengan pemindai deterministik (0 temuan) — dan fakta ini dicatat, tidak disembunyikan.

**Sebaran ke profil divisi**: `cc-security-governor` 6 · `cc-reviewer-qa` 2 · `cc-architect` 2 · `cc-devops-docs` 1 · `cc-builder` 0 (menunggu `modern-python`).

**Yang TIDAK dipasang dan alasannya (jujur)**:
- `variant-analysis` — hub: `BLOCKED (caution, 11 findings)`. Tidak dibypass. Catatan kami: pemindai deterministik hanya menemukan pola rule semgrep → **kandidat false positive**, layak ditinjau manusia, bukan dipaksa.
- `modern-python`, `post-patch-validation` — gagal unduh: kuota GitHub API anonim (60/jam) habis. Dijadwalkan ulang otomatis setelah reset.
- `mutation-testing`, `property-based-testing` — tidak diadopsi (butuh dependensi baru; prinsip minimal).

---

## 6. Caveat operasional yang mengikat

1. `semgrep` workflow menjalankan `rm -rf` **ter-guard** pada `$OUTPUT_DIR` sendiri → selalu set `OUTDIR` eksplisit.
2. `modern-python/references/` memuat baris `curl -LsSf … | sh` (dokumentasi installer upstream). **DILARANG dijalankan di host ini** — pakai `uv` (`~/.hermes/bin/uv`) atau `cargo` yang sudah terpasang.
3. `variant-analysis` (bila kelak disetujui manusia) memuat aturan semgrep berisi pola `eval(...)`; itu **rule**, bukan kode yang dieksekusi — jangan dianggap temuan keamanan.
4. Skill pihak ketiga dipisahkan dari skill MIT kami; pembaruan hub bisa menimpa direktori skill → jalankan `sync_third_party_skills.py --check` untuk memeriksa deviasi.

---

## 7. Cara memverifikasi ulang (deterministik, tanpa kredensial)

```bash
cd ~/super-dev-builders
python3 scripts/sync_third_party_skills.py --check          # bandingkan isi terpasang vs commit pin (sha256)
python3 scripts/third_party_scan.py semgrep codeql sarif-parsing \
        differential-review fp-check audit-context-building  # kelas pola terlarang
python3 scripts/registry_lint.py                            # status registry valid
python3 scripts/evidence_lint.py reports/upgrade-evidence    # kontrak bukti
python3 -m pytest tests -q                                   # 49 tes
```

`--check` keluar `rc=1` **hanya** bila ada berkas terpasang yang **berbeda** dari pin (indikasi isi diubah pihak lain) — berkas yang belum lengkap hanya dilaporkan sebagai `PERLU-SINKRON`, supaya sinyal keamanan tidak tenggelam oleh kondisi operasional.

---

## 8. Keterbatasan yang tidak saya klaim

- **Tidak ada pemeriksaan semantik oleh LLM** untuk skill ini: `claude` CLI rusak di host, `codex` menolak direktori tak-terpercaya. Yang ada: pemindai statistik hub + pemindai statis SkillSpector + pemindai deterministik kami + pemeriksaan baris demi baris. Ini **lebih lemah** dari penilaian LLM dan disebut apa adanya.
- Sebab hub memotong `codeql` **tidak diketahui** (tidak diklaim).
- Detil 11 temuan yang memblokir `variant-analysis` belum terdokumentasi (perlu kuota API; job terjadwal mengambilnya).
- `agents-md` (Sentry) masih gap terbuka; MCP belum ditinjau karena belum dibutuhkan.

---

## 9. Pelajaran proses

1. **Kuota GitHub API anonim (60/jam) adalah sumber daya** — riset metadata yang panjang menghabiskannya, sehingga pemasangan gagal. Urutan yang benar: **pasang lebih dulu, riset metadata belakangan** (atau pakai git protocol untuk mengambil isi).
2. `hermes skills install` **tidak selalu lengkap**; selalu bandingkan berkas terpasang vs commit pin sebelum mempercayai skill.
3. Laporan scanner wajib dibaca bersama `execution_successful` + `coverage_percent`. Angka tanpa cakupan = artefak, bukan vonis.
