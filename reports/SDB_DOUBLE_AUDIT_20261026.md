# Double Audit SDB — Struktur, Keamanan, dan Kesiapan Skala Komersial

**Tanggal**: 2026-10-26 · **Repo**: `~/super-dev-builders` @ `4a10d28` · **Metode**: dua lintasan independen
**Pass A** = struktur, konsistensi registry, tes, dokumen. **Pass B** = keamanan, legal/lisensi, operasional, skala.
Kedua lintasan dijalankan dengan pertanyaan berbeda supaya temuan tidak saling mengonfirmasi diri sendiri;
hasilnya direkonsiliasi di §5.

> Konteks dari Owner: sistem ini akan dijual sebagai **subscription berbayar**, dengan kemungkinan ribuan user.
> Karena itu audit ini tidak hanya menilai "apakah hari ini jalan", tetapi **"apakah pondasinya bisa tumbuh"**.

---

## 1. Skor per dimensi

| Dimensi | Skor | Dasar |
|---|---:|---|
| Disiplin gerbang & bukti (Gate #0, evidence taxonomy) | **9/10** | `gate_check.py` memvalidasi 20+ field wajib, tipe, dan nilai lawan; tidak ada jalur "lolos karena kosong" yang ditemukan |
| Kualitas kode & tes hari ini | **8/10** | 54 berkas Python, 9.479 baris; 252 tes PASS (<20 s); `ruff` bersih |
| Konsistensi registry ↔ profil | **8/10** | `registry_lint` PASS; skill drift 116/116; 39 custom skill semuanya punya `license` + `profiles` |
| Higiene repo | **4/10** | 20 MB artefak dilacak git, 5 berkas >1 MB, 0 tag rilis, 90 berkas kotor |
| Keamanan & privasi data | **6/10** | 0 kunci API ter-hardcode; 0 `.raw` terkomit; tetapi email uji dan capture jaringan tersimpan di artefak |
| Legal / lisensi untuk dijual | **2/10** | **tidak ada `LICENSE` di root**; 1 pack CC-BY-SA terpasang; 1 GPL-3.0 berstatus karantina |
| Kesiapan multi-tenant / SaaS | **1/10** | tidak ada auth, tenancy, billing, API server, queue, container, metrik |
| Observabilitas & operasi | **3/10** | dashboard lokal `:8484` (stdlib, read-only) + `doctor.py`; tidak ada metrik/SLO/alert produksi |
| **Total sebagai produk subscription** | **3/10** | toolkit internal yang sangat baik; produk SaaS-nya **belum ada** |

Kalimat tunggal: **yang sudah matang adalah disiplin kerja dan gerbangnya; yang belum ada adalah produknya.**

---

## 2. Pass A — struktur & konsistensi

### 2.1 Angka dasar (terukur)

| Metrik | Nilai |
|---|---|
| Berkas (tanpa `.git`/`.venv`) | 590 · 39,36 MB |
| Python | 54 berkas · 9.479 baris |
| Markdown | 140 berkas · 10.485 baris |
| Shell | 8 berkas · 945 baris |
| YAML | 31 berkas |
| Skill custom | 39 (86 KB teks `SKILL.md`) |
| Profil divisi | 8 agen (`agents/*.yaml`) ↔ 8 profil Hermes |
| Riwayat git | 91 commit, 1 branch (`master`), **0 tag**, 90 entri kotor |
| Ukuran dilacak git | 20 MB |

Komposisi direktori terbesar: `runs/` 202 berkas · `skills/` 79 · `evidence/` 78 · `reports/` 67 · `docs/` 29.

### 2.2 Yang sehat

- `make check` RC=0: `ruff` + `registry_lint` + 252 tes + drift 116/116.
- Semua 39 skill custom: `license: MIT`, `divisions`, `profiles` terisi — tidak ada entri "liar".
- 0 tautan lokal mati di `docs/*.md` (diperiksa 29 berkas).
- `gate_check.py` menolak manifest yang tidak lengkap: `forbidden_actions`/`forbidden_data` wajib memuat inti,
  `redact_before_prompt` wajib `true`, `sandbox` punya nilai "wajib" (bukan default permisif), dan exit code
  membedakan PASS/FAIL/BLOCKED. Ini bagian terkuat sistem.
- CI (`.github/workflows/ci.yml`) menjalankan lint + registry + tes + drift pada `push`/`PR`, dengan catatan
  portabilitas Python yang jujur di komentar.

### 2.3 Temuan Pass A

| ID | Sev | Temuan | Bukti | Dampak |
|---|---|---|---|---|
| A-1 | HIGH | 20 MB artefak pelanggan dilacak git; 5 berkas >1 MB (PNG peta 2,7 MB, screenshot 2,2 MB, SBOM 1,5 MB) | `git ls-files \| xargs du` = 20 MB | Setiap clone = 20 MB; riwayat tidak bisa dikecilkan tanpa rewrite; data tenant bercampur produk |
| A-2 | HIGH | Tidak ada tag rilis & hanya 1 branch; 90 entri kotor menumpuk | `git tag \| wc -l` = 0 | Tidak ada artefak rilis yang bisa dipatok; rollback = revert manual; pelanggan tidak bisa memilih versi |
| A-3 | MED | `uv.lock` masuk `.gitignore` | `.gitignore` baris `uv.lock` | Dependency tidak reproducible untuk produk yang dijual; build pelanggan bisa berbeda |
| A-4 | MED | Dokumen ganda format (`INTEGRASI_GITHUB_VERCEL_SUPABASE.{md,html,pdf}`) + 3 dokumen audit paralel (`AUDIT_20261007_R2/R3`, `ronde-3-audit-*`) tanpa indeks | `ls docs`, `ls reports` | Onboarding lambat; sumber kebenaran tidak jelas |
| A-5 | LOW | Nama profil fisik `cc-*`, alias `sdb-*` hanya di `agents/*.yaml` | `ls ~/.hermes/profiles` | Salah sebut di runbook/otomasi; order ke profil salah = kerja tidak jalan |
| A-6 | LOW | `dashboard/server.py` = dashboard lokal stdlib, bukan API — mudah disalahpahami sebagai "sudah ada backend" | docstring berkas | Ekspektasi keliru soal kesiapan SaaS |

---

## 3. Pass B — keamanan, legal, operasional, skala

### 3.1 Keamanan (hasil scan)

| Uji | Hasil |
|---|---|
| Pola kunci (`AKIA…`, `ghp_…`, `sk-…`, `BEGIN PRIVATE KEY`, `xox…`) | **0 temuan** |
| `.env` di dalam repo | **0** |
| `*.raw` / `*.har` terkomit | **0** (`.gitignore` bekerja: `**/*.raw`) |
| Email pribadi di artefak | **3** — `admin@uji-railway.<tld>` (2 log Railway), 1 email maintainer (trivy), 1 email maintainer (SBOM) — alamat lengkap sengaja **tidak** dicantumkan di laporan |
| NIK 16 digit di evidence | 0 (yang cocok hanya angka di capture `network.json` — bukan PII) |
| `identity-scan.json` (peta identitas pelanggan) | di-gitignore ✅ |

Kesimpulan keamanan: **tidak ada kebocoran kredensial**. Yang ada: *hygiene* artefak — log uji dan SBOM
membawa email pihak ketiga ke dalam repo produk. Kalau repo ini nanti dibagikan ke pelanggan/kontraktor,
itu menjadi kebocoran data kecil yang tidak perlu.

### 3.2 Legal & lisensi — **blocker komersial**

| Fakta | Konsekuensi |
|---|---|
| Tidak ada `LICENSE` di root repo | Secara default = *all rights reserved*. Pelanggan tidak otomatis mendapat hak pakai, modifikasi, atau distribusi — kontrak jual belum punya dasar |
| 39 skill custom menyatakan `license: MIT` di frontmatter | Menyatakan MIT **tanpa** berkas lisensi induk = ambigu; kalau benar-benar MIT, siapa pun boleh menjual ulang |
| `trailofbits/skills` — **CC-BY-SA-4.0**, status **INSTALLED** (9 skill) | Share-alike: distribusi turunan wajib atribusi + lisensi sama → **tidak bisa** dimasukkan begitu saja ke bundel proprietary |
| `anthropics/skills` — tanpa deklarasi lisensi, status `REJECTED_LICENSE` | Sudah benar ditolak — pertahankan |
| `MobSF` — GPL-3.0, status `QUARANTINE` | Benar dikarantina; jangan pernah dipanggil sebagai proses tertanam di produk |

**Tindakan wajib sebelum jual**: (1) putuskan lisensi repo (proprietary/EULA vs open-core), (2) pisahkan
"third-party pack" CC-BY-SA menjadi paket terpisah dengan `NOTICE` + atribusi, atau ganti dengan implementasi
sendiri, (3) audit ulang setiap skill yang `adopt`-nya berasal dari pack tersebut.

### 3.3 Operasional

- Tidak ada container/IaC (`0` Dockerfile/compose), tidak ada metrik (`0` prometheus/OTel), tidak ada queue.
- Satu host menjalankan 8 profil divisi secara berurutan; tidak ada isolasi proses per pekerjaan selain sandbox
  yang dideklarasikan di manifest.
- Observabilitas hari ini = `doctor.py` + dashboard `:8484` (read-only, tanpa secret) + `runs/*/logs`.
  Untuk pelanggan berbayar ini belum cukup: tidak ada SLO, tidak ada alert, tidak ada metrik biaya per tenant.

### 3.4 Skala — tiga penghalang struktural (bukan soal server lebih besar)

**H-1 Distribusi skill = salin-per-profil.**
Hari ini 25 direktori skill berisi ~2,5–3,7 MB masing-masing (±65 MB total), dan profil `default` memuat
**193 skill**. Biaya indeks deskripsi masih wajar (default ≈ 2.474 token; divisi 1.275–1.389 token), jadi
bukan konteks yang mahal — **tetapi** model "salin ke setiap profil" berarti: 1.000 tenant × 8 profil ×
2,6 MB = **±20 GB berkas skill**, dan setiap pembaruan skill harus disalin ke ribuan lokasi. Tidak ada
versioning, tidak ada manifest per paket langganan, tidak ada cara mencabut skill yang berbahaya dari
pelanggan yang sudah memasangnya.

**H-2 Artefak pelanggan hidup di git.**
`runs/` 24 MB / 210 berkas dalam 22 hari ≈ **1,1 MB/hari untuk satu pilot**. Linear saja: 1.000 tenant ≈
**1,1 GB/hari ≈ 400 GB/tahun**, dan git menyimpan setiap versi — historisnya tidak bisa dipangkas tanpa
rewrite. Git bukan object store; ini akan menjadi biaya dan risiko privasi terbesar.

**H-3 Tidak ada bidang kendali (control plane).**
`signals` audit: `api_server` kosong, `billing` kosong, `tenant` kosong, `queue` kosong. Artinya: tidak ada
tempat mendaftarkan tenant, menagih, memberi kuota, menjadwalkan pekerjaan, atau mengisolasi data. Ini bukan
"kurang fitur" — ini **belum ada produknya**.

### 3.5 Temuan Pass B

| ID | Sev | Temuan | Dampak |
|---|---|---|---|
| B-1 | **BLOCKER** | Tidak ada `LICENSE` root; 39 skill mengklaim MIT; 1 pack CC-BY-SA terpasang | Tidak bisa dijual tanpa dasar hukum yang jelas |
| B-2 | **BLOCKER** | Tidak ada model tenancy & isolasi (state global di `~/.hermes`, artefak di repo) | Dua pelanggan = satu filesystem; tidak ada batas data |
| B-3 | **BLOCKER** | Tidak ada control plane (auth, billing, kuota, penjadwalan) | Tidak ada mekanisme menagih/membatasi/melayani pelanggan |
| B-4 | HIGH | Artefak & log pelanggan di git (A-1) + email pihak ketiga di log (diredaksi di laporan ini) | Biaya, privasi, dan kontaminasi repo produk |
| B-5 | HIGH | Distribusi skill salin-per-profil, tanpa versioning/manifest | Tidak bisa merilis/mencabut skill secara terkendali |
| B-6 | HIGH | Tidak ada metrik/SLO/alert; tidak ada pengukuran biaya per pekerjaan | Tidak bisa menetapkan harga atau SLA |
| B-7 | MED | `uv.lock` tidak dilacak (A-3) | Build tidak reproducible |
| B-8 | MED | Tidak ada baseline coverage (pytest-cov tidak terpasang) | Regresi kualitas tidak terdeteksi dini |

---

## 4. Rekonsiliasi kedua lintasan

| Pertanyaan | Pass A | Pass B | Kesimpulan |
|---|---|---|---|
| Apakah sistem ini "rapi"? | Cukup (registry & docs konsisten, 0 link mati) | Tidak (artefak 20 MB, duplikasi format) | **Rapi di dalam, berantakan di tepi** — yang kotor adalah artefak, bukan kode |
| Apakah aman? | Ya (tidak ada secret) | Ya untuk kredensial, tidak untuk higiene data | **Aman secara kredensial, belum aman secara data pelanggan** |
| Bisa dijual? | Tidak dinilai | Tidak (3 blocker legal/arsitektur) | **Belum** — dan penyebabnya bukan kualitas kerja, tapi belum adanya lapisan produk |
| Bisa diskalakan? | Skrip & tes tidak menghalangi | Distribusi skill + artefak + absennya control plane menghalangi | **Kode bisa tumbuh; model penyimpanan & distribusi harus diganti lebih dulu** |

Satu temuan yang **hanya** muncul karena dua lintasan dibandingkan: **biaya konteks bukan masalah, biaya
*duplikasi* yang masalah.** Banyak audit akan menyimpulkan "193 skill terlalu banyak untuk konteks" (salah —
hanya 2.474 token deskripsi yang di-inject). Yang benar: menyalin 2,6 MB skill ke setiap profil, lalu
mengulanginya untuk setiap tenant, adalah model yang tidak akan bertahan.

---

## 5. Verdict

**Sebagai toolkit internal 1 operator: LULUS (8/10).**
**Sebagai produk subscription: BELUM (3/10)** — 3 blocker, 3 risiko tinggi.

Urutan yang benar adalah **fondasi dulu, fitur kemudian**, dan itu berarti tiga keputusan yang tidak bisa
ditunda: lisensi, model tenancy, dan tempat penyimpanan artefak. Semua sudah dirancang di
`docs/ARSITEKTUR_SAAS.md` dan `docs/PETA_STRUKTUR.md`; kerangka yang bisa dieksekusi hari ini ada di
`platform/` + `scripts/repo_hygiene.py`.

---

## 6. Rencana 90 hari (ringkas; detail di ARSITEKTUR_SAAS §9)

| Fase | Isi | Kriteria selesai |
|---|---|---|
| **0 (hari ini)** | Audit ganda; peta struktur; kontrak tenant/job/artifact; gerbang higiene repo; baseline artefak | `make check` hijau + `make hygiene` PASS + ADR tenancy tertulis |
| **1 (0–30 hari)** | Skill store tunggal + manifest per paket; artefak keluar dari git ke object store; tag rilis `v0.1.0`; lisensi diputuskan | Tenant uji bisa memakai skill pack tanpa salinan; repo < 10 MB; 1 tag rilis |
| **2 (30–90 hari)** | Control plane minimal: auth, tenant registry, kuota, billing hook, worker queue, isolasi sandbox per job | 10 tenant pilot berjalan terpisah; 1 tagihan per tenant; metrik biaya per job |
| **3 (90–180 hari)** | Multi-region/HA, SLO+SLA, self-serve onboarding, audit log append-only, paket enterprise (silo) | 100 tenant; SLO terukur; tidak ada insiden lintas-tenant |

---

## 7. Lampiran: perintah reproduksi

```bash
cd ~/super-dev-builders
/usr/bin/python3 ~/.hermes/cache/scratch/sdb-audit/inventory.py          # inventaris penuh (JSON)
git ls-files -z | xargs -0 du -ch | tail -1                              # 20 MB
git tag | wc -l                                                          # 0
grep -rInE --exclude-dir=.venv "AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{30,}|BEGIN [A-Z ]*PRIVATE KEY" .
/usr/bin/python3 scripts/registry_lint.py                                # PASS
/usr/bin/python3 -m pytest tests -q                                      # 252 PASS
make hygiene                                                             # gerbang baru (fase 0)
```
