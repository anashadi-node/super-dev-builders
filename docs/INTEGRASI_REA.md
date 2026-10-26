# Integrasi REA ke Divisi Super Dev Builders

**Tanggal**: 2026-10-26 · **Status**: TERPASANG (CLI terpin) · **MCP**: tidak didaftarkan (opt-in)
**Dasar**: order Owner — *"tolong integrasikan Repo GitHub REA ke dalam Divisi SDB, audit scan analisa
mendalam terlebih dahulu"*.
**Audit**: `reports/REA_AUDIT_20261026.md` (bukti lengkap, semua angka terukur di host ini).

---

## 1. Apa yang diintegrasikan

| Komponen | Keputusan | Lokasi |
|---|---|---|
| Mesin REA | **CLI terpin** `rea-agents@6.8.0`, prefix terisolasi, `--ignore-scripts` | `~/.hermes/tools/rea-6.8.0/` |
| Wrapper | satu titik versi + node eksplisit, tanpa `npx`/`latest` | `scripts/rea` |
| Skill operasional | custom, MIT milik SDB (bukan salinan upstream) | `skills/rea-reverse-engineering/` |
| Registry | tool + skill + status pipeline | `registry/tools.yaml`, `registry/skills.yaml` |
| MCP server (229 tool) | **TIDAK** didaftarkan di profil mana pun | prosedur opt-in §5 |

## 2. Tiga keputusan yang menentukan bentuk integrasi

### 2.1 CLI-first, bukan MCP-first
`tools/list` REA = **3.790.552 byte** untuk 229 tool (rata-rata 16,5 KB/tool). Bila didaftarkan sebagai MCP,
skema itu ikut masuk konteks setiap sesi — ±950 K token habis sebelum satu baris pekerjaan dimulai. Itu
bertentangan langsung dengan target efisiensi token ekosistem.
Dengan CLI, biaya konteks = **hanya output yang diminta**: `--format md --token-limit 900` terbukti cukup
untuk peta aplikasi Electron (uji 2026-10-26, 1,83 s).

### 2.2 Skill tidak disalin, tapi diterjemahkan
Skill upstream (35 KB + 107 KB referensi) ditulis untuk Claude Code tanpa aturan SDB. Yang dipakai: taksonomi
CONFIRMED/INFERRED/UNKNOWN dan disiplin evidence-nya. Yang ditambahkan: Gate #0, tier izin T0–T3, redaksi,
larangan, dan pemetaan divisi. Skill upstream **tidak** dipasang apa adanya karena akan membawa serta tool
yang tidak boleh aktif (debug/frida/adb) tanpa gate kita.

### 2.3 Clean-room wall jadi kewajiban proses, bukan saran
Peran `rea-scout → rea-spec-writer → rea-builder → rea-tester` dipetakan ke D1 → D3 → D4/D5 → D7. Aturan
tambahan yang tidak ada di upstream: **builder tidak diberi akses ke `evidence/<target>/` mentah**, hanya
`spec.md` + `reports/`. Tanpa itu, "clean room" hanya slogan.

## 3. Arsitektur

```text
Owner / D0
   │  order + authorization.yaml
   ▼
Gate #0  scripts/gate_check.py --target <slug>        (PASS wajib)
   ▼
D1 Recon ── scripts/rea ──► Evidence (evidence/<slug>/rea/, ber-hash)
   │                        └─ label CONFIRMED/INFERRED/UNKNOWN → FACT/INFERRED/UNKNOWN
   ▼
D3 Architecture ── spec.md (perilaku saja; tanpa nama internal/path/aset)
   │                 └─ build-reconstruction-obligation-ledger
   ▼
D4/D5 Build ── implementasi + test        (dinding: tidak melihat evidence mentah)
   ▼
D7 QA ── compare-application-versions / evaluate-reconstruction-coverage → comparison.md
```

## 4. Tiga hal yang REA tidak bisa lakukan hari ini (jujur, bukan optimis)

1. **Decompile native/APK/Objective-C belum tersedia** — Ghidra (`GHIDRA_INSTALL_DIR` kosong), IDA, JADX,
   Hopper belum dipasang. Yang terbukti jalan: JavaScript/Electron statis, web capture, artefak statis,
   EVM bytecode (`evmole`).
2. **Node host tidak sesuai deklarasi paket** (`engines` minta 22.23.4+/24.22.1+/26.12.1+; host 26.7.0).
   CLI, MCP handshake, dan analisis JS tetap berjalan normal. Bila muncul anomali, langkah pertama adalah
   memasang Node 24 LTS terisolasi khusus REA — bukan menambal host.
3. **177 perintah CLI** — jauh lebih banyak daripada yang dipakai SDB. Skill membatasi ke tier T0–T3; sisanya
   ada tapi tidak dipanggil.

## 5. Prosedur MCP opt-in (bila suatu saat benar-benar dibutuhkan)

Syarat: hanya untuk pekerjaan recon mendalam, hanya di profil khusus, **bukan** `default`.

```bash
# 1) profil terpisah supaya 229 tool tidak membebani sesi harian
hermes profile create sdb-recon-rea 2>/dev/null || true

# 2) daftarkan MCP dengan command absolut (bukan npx)
hermes mcp add rea \
  --command ~/.hermes/tools/rea-6.8.0/node_modules/rea-agents/scripts/rea.mjs \
  --args mcp --connect-timeout 90

# 3) WAJIB: perkecil tool set sebelum dipakai (229 tool = 3,79 MB)
hermes mcp configure rea

# 4) uji + ukur
hermes mcp test rea
hermes mcp list
```

Catatan: langkah 2 tanpa langkah 3 = konteks sesi membengkak ±950 K token. Bila `hermes mcp configure` tidak
bisa memangkas ke <15 tool, **jangan aktifkan** — pakai CLI (jalur default integrasi ini).

## 6. Upgrade & re-audit (wajib, tidak opsional)

```bash
# 1) audit versi baru di direktori sekali-pakai
mkdir -p ~/.hermes/cache/scratch/rea-reaudit && cd ~/.hermes/cache/scratch/rea-reaudit
npm pack rea-agents@<versi>                     # unduh, tanpa eksekusi
sha512sum rea-agents-<versi>.tgz                # bandingkan dengan registry `dist.integrity`

# 2) scan ulang: PUA/Glassworm, secret, endpoint telemetri, lifecycle scripts, tool baru
# 3) bandingkan daftar tool: tool baru bertier T2/T3 wajib ditinjau manual
# 4) baru pasang: npm install --prefix ~/.hermes/tools/rea-<versi> --ignore-scripts rea-agents@<versi>
# 5) perbarui REA_VERSION di scripts/rea + registry/tools.yaml + SKILL.md frontmatter (upstream.integrity)
/usr/bin/python3 ~/super-dev-builders/scripts/registry_lint.py
```

Aturan: **satu versi aktif**. Jangan simpan dua prefix sekaligus kecuali sedang membandingkan perilaku.

## 7. Rollback

```bash
rm -rf ~/.hermes/tools/rea-6.8.0
cd ~/super-dev-builders && git revert <commit-integrasi>
# tidak ada perubahan pada ~/.hermes/config.yaml, profil lain, kredensial, atau systemd
```

## 8. Risiko yang diterima secara sadar

| Risiko | Level | Mitigasi |
|---|---|---|
| Kapabilitas besar (debugger, frida, PTY, git client) | MEDIUM | tier T0–T3 + approval per aksi + skill yang melarang |
| Maintainer tunggal, 1.093 issue terbuka | MEDIUM | pin versi + integritas; upgrade lewat audit ulang |
| Node tidak sesuai `engines` | LOW | terbukti berfungsi; jalur perbaikan terdokumentasi (§4.2) |
| `plist`/spasi memicu 29 temuan scanner | LOW | dianalisis token-per-token, 100% FP (`REA_AUDIT` §4) |
| Data sensitif di artefak target | HIGH bila lalai | larangan §7 skill + `redaction_status` wajib |

## 9. Status implementasi

| Item | Status | Bukti |
|---|---|---|
| Audit + scan + analisis | SELESAI | `reports/REA_AUDIT_20261026.md` |
| Tool terpasang terpin | SELESAI | `scripts/rea --version` → 6.8.0 |
| Skill aktif | SELESAI | `skills/rea-reverse-engineering/`, registry `custom` |
| Registry tool/skill | SELESAI | `registry/tools.yaml`, `registry/skills.yaml` |
| Uji regresi | SELESAI | `tests/test_rea_integration.py` |
| MCP global | **TIDAK** (keputusan) | §5 |
