# Divisi Investigasi (DID) — Desain v1

**Status:** aktif 6 November 2026 · **Tahap:** `01C` · **Agent:** `sdb-investigator` · **Pack:** `platform/packs/sdb-investigator.json`
**Dasar:** PRD SDB Deep Investigation Division v3.0 + P0 read-only discovery (`docs/…`, laporan 2026-11-06)

---

## 1. Masalah yang diselesaikan

Divisi Builders bisa menulis kode dengan cepat, tetapi kualitas produk dibatasi oleh **mutu spesifikasi**. Spesifikasi buruk punya dua penyakit: (a) mengklaim hal yang tidak pernah dilihat, (b) menyembunyikan hal yang belum diketahui. Keduanya mahal — yang pertama membuat Builders membangun fitur hantu, yang kedua membuat keputusan arsitektur diambil buta.

DID tidak menjanjikan "tahu segalanya". DID menjanjikan **tiga hal yang bisa diperiksa**:

1. Setiap klaim punya alamat bukti (berkas + hash + waktu).
2. Setiap kesimpulan tidak langsung ditandai `INFERRED` + punya tes pemalsu.
3. Setiap hal yang tidak diketahui ditulis sebagai `UNKNOWN` + probe, bukan dikarang.

## 2. Posisi di alur SDB (bukan pohon baru)

```
01    USER OBJECTIVE
01A   AUTHORIZATION/SCOPE GATE      (gate_check.py — wajib PASS)
01B   RECON / EVIDENCE PACKAGE      (REA, capture_web)
01C   DID: INVESTIGASI MENDALAM + HANDOFF   <-- divisi ini (did_validate.py)
02    KLARIFIKASI ORCHESTRATOR      (membaca handoff)
04    ARSITEKTUR + ADR
07    IMPLEMENTASI (Builders)
```

Satu tahap, satu agent, satu pack — semuanya menumpang registry yang sudah ada (`workflows/stages.yaml`, `registry/skills.yaml`, `platform/packs/`). Tidak ada daftar tahap kedua, tidak ada registry skill kedua.

## 3. Keputusan desain (dan alasannya)

| Keputusan | Alasan | Yang ditolak |
|---|---|---|
| **1 agent `sdb-investigator`, bukan 13 agent** | SDB menganut "agent = tanggung jawab; divisi lazy". 13 sesi LLM = biaya token tanpa tambahan bukti. 13 peran PRD dipetakan jadi **brief tahap** + skill, bukan 13 proses. | 13 proses terpisah yang saling menunggu |
| **Reuse profil `cc-capture-forensics`** | Nol perubahan `~/.hermes`; izin read-only ditegakkan lewat charter + gate + validator, bukan lewat profil baru. | Membuat profil Hermes ke-26 |
| **CLI-first, MCP tetap tidak didaftarkan** | REA 229 tool + Craft 315 tool akan membanjiri konteks dan menurunkan kualitas keputusan. | Mendaftarkan MCP "supaya lengkap" |
| **Handoff JSON sebagai sumber tunggal, MD sebagai turunan** | JSON bisa divalidasi & dihitung; MD untuk manusia. MD tidak pernah diedit tangan. | Laporan naratif sebagai sumber |
| **Profil & ambang di `platform/did_profiles.json`** | Kasus berubah (web, API, mobile, desktop, biner, game, source) tanpa mengubah kode. | `if target == "web"` di dalam skrip |
| **Kedalaman L1–L4 eksplisit** | Investigasi tanpa batas = biaya tak terkendali. Setiap depth punya kategori wajib + anggaran. | "Sedalam mungkin" |

## 4. Empat kedalaman

| Depth | Nama | Kategori tambahan | Anggaran (tool call / menit / bukti) |
|---|---|---|---|
| L1 | Inventory | — | 25 / 30 / 10 MB |
| L2 | Behavior (default web/API) | — | 60 / 90 / 50 MB |
| L3 | Internals read-only (default mobile/desktop/biner) | `internals` | 120 / 180 / 100 MB |
| L4 | Authorized probing | `runtime_trace` | 200 / 240 / 200 MB |

Semua depth tetap tunduk pada larangan yang sama: tanpa bypass autentikasi, captcha, paywall, DRM, rate limit; tanpa intersepsi TLS pihak ketiga; tanpa menyimpan kredensial.

## 5. Tujuh kategori bukti per jenis target

| Target | Kategori wajib |
|---|---|
| `web` | routes, states, components, network, auth_flow, assets, responsive |
| `api` | endpoints, schemas, errors, auth, rate_limits |
| `mobile` | manifest, permissions, screens, storage, network |
| `desktop` | installer, update_channel, ipc, storage, network |
| `binary` | entrypoints, imports, strings, protocols, mitigations |
| `game` | scenes, assets, mechanics, save_format |
| `source` | modules, dataflow, tests, config |

Kategori yang tidak bisa diperiksa (mis. `auth_flow` karena di luar otorisasi) diisi `OUT_OF_SCOPE` **dengan alasan** — bukan dihapus, bukan ditebak.

## 6. Alat deterministik

| Alat | Fungsi | Keluaran |
|---|---|---|
| `scripts/provider_snapshot.py` | Panggil `rea doctor`/`capabilities` + deteksi engine; putuskan READY/PARTIAL/BLOCKED per jenis target | `evidence/providers/providers-YYYYMMDD.json` |
| `scripts/did_validate.py validate` | 14 aturan (R01–R13): gate, hash, status, falsifikasi, probe, coverage, must-have, seed, disiplin, anggaran, ambang mutu | `reports/<t>/did-validation.json`, `runs/<t>/did/SPEC_DID.md` |
| `scripts/did_validate.py bench` | Precision/recall/F1/hallucination vs ground truth | `reports/<t>/did-bench.json` |
| `scripts/gate_check.py` (lama) | Gate #0 — dipakai apa adanya | `reports/<t>/gate0-verdict.json` |
| `scripts/evidence_lint.py` (lama) | Lint evidence ternormalisasi | laporan lint |

Aturan yang membuat handoff **ditolak** (exit 1): hash evidence berubah, evidence berisi rahasia, `OBSERVED` tanpa bukti, `INFERRED` tanpa `confidence` + `falsification`, `UNKNOWN` tanpa `probe`, kategori wajib hilang, `must` tanpa bukti OBSERVED, `must` tanpa tes terima `given/when/then`, `replica_skill_used`/`wrote_code`/`mcp_registered` tidak `false`, anggaran terlampaui, atau Gate #0 di disk bukan PASS.

## 7. Yang diterima Divisi Builders

`runs/<target>/did/handoff.json` + `SPEC_DID.md`, berisi: ringkasan, fitur berprioritas dengan tes terima, kontrak API teramati, model data, state & edge case, token desain, unknown berprobe, dan jejak bukti ber-hash.

Aturan konsumsi untuk Builders:
- `must` hanya boleh dibangun dari temuan `OBSERVED`.
- `INFERRED ≥ 70` boleh jadi `should` dengan probe tercatat.
- `INFERRED < 70` atau `UNKNOWN` **tidak boleh** menjadi keputusan arsitektur final.
- `builders_ready: false` berarti ada unknown `blocking` — mulai dari `next_actions`, bukan menebak.

## 8. Batas jujur (kondisi 6 November 2026)

| Jalur | Status | Bukti |
|---|---|---|
| Web/JS (Playwright + REA) | READY | `provider_snapshot` verdict `web: READY` |
| Biner native (Ghidra 12.1.4 + JDK 21) | READY | provider `ghidra available=true`; `evidence/elf-demo/rea-inspect.json` |
| Source semantic (Semgrep + CodeQL) | READY | versi terpasang |
| SBOM (Syft/Trivy) | READY | versi terpasang |
| Android | PARTIAL | `jadx`/`apktool` belum ada; provider `jadx` butuh JAR pihak ketiga |
| Runtime instrumentation | BLOCKED | Frida belum terpasang (dan tidak akan tanpa keputusan Owner) |
| Craft Anything | PARTIAL (alpha) | 0.3.0, 315 tool, biner tanpa sumber; integritas sha256 perlu re-verifikasi |
| Sandbox | docker READY · bwrap UNUSABLE | `docker ps` tanpa sudo; `bwrap` gagal uid map |

Klaim "DID bisa Android penuh" atau "DID bisa instrumentasi runtime" **tidak boleh** dibuat sampai dua baris PARTIAL/BLOCKED berubah.

## 9. Biaya & penghentian

- Anggaran per target: lihat §4; dicatat di `budget.used`.
- Berhenti bila: semua kategori wajib COVERED, atau anggaran habis, atau tersisa unknown `blocking` (serahkan ke Owner).
- Tidak ada retry otomatis tanpa batas. Kegagalan alat dicatat sebagai `UNKNOWN`, bukan diulang 10×.

## 10. Cara menjalankan

```bash
# 0. prasyarat
python3 scripts/gate_check.py --target <t>     # wajib PASS

# 1. bukti kapabilitas alat (sekali per sesi kerja)
make did-providers

# 2. investigasi (agent menulis evidence + handoff)
#    ... REA/capture_web, normalisasi, evidence_lint ...

# 3. gerbang mutu — exit 1 bila kontrak dilanggar
make did TARGET=<t>

# 4. skor terhadap label independen (opsional, tapi ini yang membuat mutu terukur)
make did-bench TARGET=<t> TRUTH=benchmarks/<t>/ground_truth.json

# 5. hasil untuk Builders
cat runs/<t>/did/SPEC_DID.md
```

### Hasil terukur (6 November 2026)

| Target | Profil/depth | Validasi | Benchmark (label independen) |
|---|---|---|---|
| `elf-demo` | binary / L3 | PASS · 8 temuan · must 4 · coverage 5/6 | **P 1,000 · R 1,000 · F1 1,000** · halusinasi 0 (6 label dari `demo.c` + `nm`) |
| `e1-app` | api / L2 | PASS · 13 temuan · must 8 · coverage 4/5 | **P 0,909 · R 1,000 · F1 0,952 · halusinasi 0,000** (10 label SPEC, 1 ekstra: bentuk error seragam) |

Sebelum diperbaiki, handoff `elf-demo` hanya menangkap 2 dari 6 perilaku (**recall 0,333**) dan
mengklaim program “mencetak hasil penjumlahan dua konstanta” — klaim itu **salah**: `main` mencetak
konstanta `0x2a` (42) dan simbol `tambah` punya **0 call site** (dead code). Kesalahan ditemukan dari
cross-check `objdump -d`, bukan dari skor lexical — lihat catatan di skill `did-benchmark`.

`e1-app` diuji lewat HTTP nyata (`127.0.0.1:8110`, 18 probe, token diredaksi), bukan dari kode.
Skor `hallucinated 0` berarti tidak ada fitur yang diklaim OBSERVED tanpa bukti; ekstra dipisah
dari halusinasi supaya temuan sah di luar cakupan label tidak dihukum.

## 11. Uji yang mengunci perilaku

| Berkas | Isi |
|---|---|
| `tests/test_did_contract.py` | 15 uji: handoff sah diterima; 11 jenis pelanggaran ditolak; matematika benchmark; konsistensi profil |
| `tests/test_did_gate.py` | Tahap 01C ada & bertool; charter sah; pack sehat & bebas Replica Skill; registry/dashboard sinkron |
| `tests/test_stage_registry.py` | Registry tunggal kini 19 tahap (01C disengaja) |

## 12. Rollback

DID adalah penambahan, bukan penggantian:
- Hapus tahap `01C` dari `workflows/stages.yaml` (1 blok) → alur kembali 18 tahap; uji registry disesuaikan.
- Hapus `agents/sdb-investigator.yaml` + `platform/packs/sdb-investigator.json` → pack kembali 8.
- Kembalikan `registry/skills.yaml` (count 43 → 40, 3 entri DID, 11 baris `profiles`) dari commit sebelumnya.
- `scripts/did_validate.py` & `provider_snapshot.py` tidak dipanggil otomatis oleh tahap lain; menghapusnya tidak memengaruhi divisi lama.

## 13. Yang sengaja belum dikerjakan

- Adapter Craft (inspection-only) — menunggu re-verifikasi integritas biner.
- JADX / Frida / Joern — menunggu target nyata + persetujuan instalasi.
- ZAP pasif — dinilai belum perlu; semgrep + trivy + `scan-keamanan.sh` sudah menutup.
- Benchmark pada target OSS pihak ketiga — menunggu keputusan lingkup etis/legal.
