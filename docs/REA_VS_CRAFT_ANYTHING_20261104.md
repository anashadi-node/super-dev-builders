# REA vs Craft Anything — Riset Perbandingan Mendalam

**Tanggal:** 4 November 2026 · **Konteks:** Divisi Ekosistem Super Dev Builders (SDB)
**Pertanyaan yang dijawab:** dari semua segi dan faktor, mana yang terbaik — skill/tools **REA (Reverse Engineering Anything)** atau **Craft Anything**?

---

## 1. Ringkasan untuk yang tidak punya waktu

Keduanya **bukan barang sejenis**, jadi "mana yang terbaik" tidak punya satu jawaban tunggal. Yang benar adalah: **terbaik untuk pekerjaan apa**.

| Kalau pekerjaannya… | Yang menang | Selisih |
|---|---|---|
| Membongkar biner, firmware, paket jaringan, APK, .NET, game engine, EVM bytecode | **REA** | jelas (8,30 vs 6,89) |
| Membangun ulang produk lalu **membuktikan** hasilnya mirip aslinya | **Craft Anything** | jelas (7,85 vs 6,95) |
| Dipakai hari ini di SDB, tanpa menambah risiko baru | **REA** | tipis (7,50 vs 7,35) |

**Kesimpulan operasional:** REA tetap **instrumen tetap** SDB. Craft Anything adalah **pabrik + pemeriksa** yang selama ini tidak dimiliki SDB — layak diuji sebagai **pilot terpisah**, bukan sebagai pengganti REA.

Satu kalimat: **REA lebih dalam melihat, Craft Anything lebih lengkap mengerjakan.** SDB butuh dua-duanya, di peran yang berbeda.

---

## 2. Catatan penting: angka di gambar Anda sudah kedaluwarsa

Gambar laporan yang Anda lampirkan (verifikasi 3 Nov 2026) versus data langsung GitHub API pada 4 Nov 2026 19:5x WIB:

| Item | Di gambar | Fakta 4 Nov | Catatan |
|---|---|---|---|
| Bintang (stars) | 5.677 | **9.997** | naik ~76% dalam 1 hari — tanda viral, bukan tanda kualitas |
| Fork | 968 | **1.652** | |
| Lisensi | `APACHE-2.0` | **MIT OR Apache-2.0** (dua lisensi) | GitHub hanya menampilkan satu; repo punya `LICENSE-MIT` + `LICENSE-APACHE` |
| Rilis | tidak disebut | **v0.1.0 (31 Okt) → v0.2.0 (1 Nov) → v0.3.0 (2 Nov)** | 3 rilis dalam 3 hari |
| Isu terbuka | tidak disebut | **161** | wajar untuk proyek 4 hari, tapi tetap 161 |

Artinya: laporan itu benar soal *arah*, salah soal *besaran*. Untuk keputusan teknis, angka bintang memang bukan dasar — bagian 5–7 di bawah memakai bukti yang bisa diperiksa ulang.

---

## 3. Metode riset (bisa diulang siapa pun)

Saya tidak menilai dari README saja. Yang dikerjakan:

1. **Metadata resmi** — GitHub REST API untuk kedua repo: tanggal lahir, bahasa, lisensi, bintang, fork, isu, ukuran, commit terakhir.
2. **Klon dangkal** `craft-anything` (26 MB) lalu **hitung sendiri**: 204.498 baris Rust, 460 berkas `.rs`, 14 crate.
3. **Audit status tool** bawaan proyek: `docs/tool-status.md` — 134 tool *verified* di input nyata, 52 *unverified*.
4. **Pemeriksaan lokal REA** yang sudah terpasang di mesin ini: `scripts/rea capabilities` → 53 grup operasi, **113 operasi** yang benar-benar tersedia di host ini (sisanya butuh Ghidra/IDA/Hopper/JEB yang tidak dipasang).
5. **Pencarian jejak jaringan keluar**: tidak ditemukan telemetri di kedua pihak.
6. **Baca aturan internal** proyek: `AGENTS.md`, `SECURITY.md`, `docs/STATUS.md`, `deny.toml`.

**Batas kejujuran:** saya **belum** menjalankan rebuild nyata dengan Craft Anything, dan **belum** memakai REA pada target ber-Gate #0. Jadi penilaian di bawah adalah penilaian **kesiapan dan rekayasa**, bukan hasil uji lapangan. Bagian 10 menutup celah itu dengan rencana uji 14 hari.

---

## 4. Fakta dasar berdampingan

| Dimensi | REA | Craft Anything |
|---|---|---|
| Repo | `morluto/rea` | `storytold/craft-anything` |
| Lahir | 14 April 2026 (~6,7 bulan) | **31 Oktober 2026 (4 hari)** |
| Bahasa | TypeScript / Node.js | **Rust** (204.498 baris) |
| Lisensi | MIT | **MIT OR Apache-2.0** |
| Versi dipakai | `rea-agents` **6.8.0** (npm) | **0.3.0** — label sendiri: *Early alpha* |
| Bintang / fork | 429.205 / 106.756 | 9.997 / 1.652 |
| Isu terbuka | 1.661 | 161 |
| Kontributor | tidak dihitung (repo besar) | **48** |
| Commit sejak lahir | — | **348** (≈ 80/hari) |
| Ukuran terpasang | 53 MB (Node + paket) | 60–66 MB per paket install; 26 MB sumber |
| Cara pakai | CLI `rea` + MCP + skill agen | GUI desktop + CLI + MCP + plugin |
| Jumlah tool | ≈229–282 tool (229 di registry SDB; 282 nama unik di `dist` 6.8.0) | **301 tool mesin** + AI/pengaturan ≈ 320 |
| Platform | Node lintas OS; provider `native-macos` hanya macOS | Linux x86_64/aarch64/riscv64, FreeBSD, Windows, macOS |
| Biaya tambahan | tidak ada (Ghidra/IDA opsional, milik sendiri) | **token LLM agen** (Claude Code/ACP/Ollama) + aset opsional fal.ai |
| Telemetri | tidak ditemukan | tidak ditemukan |

**Analogi supaya mudah:** REA itu **laboratorium forensik** — mikroskop, spektrometer, alat bedah, dan buku catatan barang bukti. Craft Anything itu **pabrik mini lengkap dengan quality control** — bisa membongkar, lalu membangun barang baru, lalu mengukur seberapa mirip hasilnya dengan aslinya. Laboratorium tidak membangun apa pun; pabrik tanpa laboratorium tidak tahu apa yang harus dibangun.

---

## 5. Perbandingan per faktor (bukti + pemenang)

### F1. Kedalaman investigasi — **REA menang (9 vs 7)**

REA dibangun untuk "apa pun": 41 jenis target terdokumentasi, dari aplikasi desktop, Electron, JavaScript, APK/Android, Apple/Mach-O, .NET, Java, format berkas, firmware, paket jaringan, database, sampai bytecode EVM dan sinyal JTAG. Ia bekerja dengan **provider** yang bisa dipasang: Ghidra, IDA, Hopper, Kuna, JEB, `rea-dotnet-static`, `sqlite`, `rea-artifact-graph`. Yang tidak ada, tidak diklaim ada: `capabilities` menyebutkan batas tiap provider secara eksplisit.

Craft Anything punya 301 tool dengan cakupan luas juga (native, .NET, Java, Android, Apple, web, format, firmware, paket, database, game 12 engine), **tapi** audit internalnya sendiri menyatakan **52 tool belum pernah dijalankan** (23 tool Android-perangkat, 9 Frida, 5 runtime, 6 Apple, sisanya). Untuk biner eksotis, REA lebih dalam dan lebih terverifikasi.

### F2. Alur kerja end-to-end — **Craft Anything menang (9 vs 4)**

Ini pembeda terbesar. REA berhenti di **bukti**: artefak, temuan, daftar "belum diketahui". Ia tidak membangun apa pun dan tidak membandingkan hasil.

Craft Anything punya siklus penuh **Study → Build → Check → Refine**:

- Menangkap target (website: sampai 4 halaman lain, menu dibuka di desktop dan ponsel);
- Menyuruh agen pengkode membangun proyek (default clean-room);
- Membandingkan hasil vs asli di **3 lebar layar (1440/768/390 px)** dengan skor kemiripan = rata-rata *layout* + detail perseptual (SSIM), mengecualikan bagian yang berubah sendiri (difoto 3× untuk mendeteksi);
- Melaporkan hal konkret yang kurang: teks, struktur, warna, font, ukuran, spasi, halaman yang melebar ke samping, error, request gagal, celah aksesibilitas;
- Mengulang sampai **6 putaran** atau **90% kemiripan**.

Analoginya: REA memberi Anda **foto rontgen**; Craft Anything memberi rontgen **plus** operasi **plus** rontgen pasca-operasi untuk memastikan hasilnya benar.

### F3. Kematangan & stabilitas — **REA menang (9 vs 3)**

REA sudah di **6.8.0** dengan 41 jenis target, riwayat 6,7 bulan, dan sudah melewati banyak siklus perbaikan. Craft Anything di **0.3.0**, umur 4 hari, dan `STATUS.md`-nya sendiri menulis hal seperti *"no live Clean room build run yet"* (build clean-room belum pernah dijalankan nyata) dan *"local model builds: not yet"*. Itu jujur — dan justru karena jujur, kita harus memperlakukannya sebagai **alpha**.

### F4. Kecepatan perubahan — **REA lebih tenang (8 vs 3)**

348 commit dalam 4 hari = sekitar 80 commit/hari, 3 rilis dalam 3 hari. Bagus untuk perkembangan, **buruk untuk reproduksibilitas**: kalau kita pin v0.3.0 hari ini, dalam seminggu bisa ada v0.6.0 dengan perubahan format proyek. Untuk SDB yang menganut "pin + hash + approval", ini risiko nyata.

### F5. Kualitas bukti — **Craft Anything sedikit unggul (9 vs 8)**

REA: artefak + operasi ber-*effect* (`launches_process`, `may_show_ui`, `may_write_filesystem`, `may_access_network`) + daftar *unknown*.
Craft Anything: **bukti yang bisa diukur** — `checks/` berisi tiap perbandingan, skor kemiripan per halaman per lebar, daftar selisih, plus `investigation.cany/` dan `inbox/` untuk pertanyaan terbuka. Untuk klaim "hasil mirip aslinya", milik Craft Anything lebih kuat karena ada angkanya.

### F6. Keselamatan, izin, dan isolasi — **Craft Anything menang (9 vs 7)**

Craft Anything secara arsitektur:

- **Clean room adalah default**: hanya tool di `engine/src/clean_room.rs` yang boleh jalan; semua tool lain — termasuk milik plugin — **ditolak** di app, CLI, MCP, dan agen, kecuali Deep mode dinyalakan sadar.
- Setiap program luar (Ghidra, Java, adb, browser, agen CLI, ssh, git) lewat satu gerbang `platform::process`: stdin ditutup, ada batas waktu, output dibatasi, pipe tidak boleh penuh.
- Plugin WASM **tidak mengimpor apa pun**; plugin MCP harus minta izin tiap panggilan.
- Ada aturan keras **never-crash** untuk input berbahaya (input berbahaya justru input utamanya).
- `SECURITY.md` menyebut kelas bug yang dianggap serius, termasuk "agen bertindak di luar proyeknya tanpa persetujuan".

REA punya **deklarasi efek per operasi** dan tier izin (T0 statis → T3 adb) yang kita bangun di SDB, tapi kekuatannya lebih luas: 229+ tool MCP, provider pihak ketiga, dan `native-macos` yang menjalankan proses. Tanpa pagar SDB, REA lebih "tajam". Dengan pagar SDB (yang sudah ada: Gate #0, tier, 6 tes integrasi), risikonya terkendali.

### F7. Privasi — **seri kuat (10 vs 9)**

Keduanya **tidak** mengandung telemetri; tidak ditemukan endpoint analitik di kode. Craft Anything tetap membuka koneksi hanya untuk hal yang Anda minta: model LLM (kunci Anda sendiri), unduh Ghidra, atau aset fal.ai (opsional, ada anggaran default $5/proyek). REA tanpa koneksi sama sekali kecuali Anda memakainya untuk target jaringan.

### F8. Kesesuaian dengan aturan SDB — **REA menang hari ini (8 vs 4)**

SDB mensyaratkan: Gate #0 (izin), clean-room, bukti tersimpan, rantai pasok terpin, tanpa MCP raksasa, dan tes yang menjaga semuanya.

- REA: sudah terdaftar (`skills.yaml`), terpasang 6.8.0 dengan pin commit + sha512, dimuat 5 dari 8 peran, punya 6 tes integrasi, MCP sengaja tidak didaftarkan. **Nol biaya integrasi.**
- Craft Anything: belum ada di registry, belum ada approval, ukuran permukaan besar (301 tool + GUI), butuh agen LLM untuk fungsinya, dan masih alpha. **Butuh jalur approval baru** (#20) sebelum boleh menyentuh target nyata.

### F9. Biaya & sumber daya — **REA menang (9 vs 5)**

REA: Node yang sudah ada, 53 MB, tanpa GPU, tanpa LLM. Craft Anything: biner 60–66 MB, build dari sumber butuh Rust 1.97 + 7 paket `apt` untuk GUI, dan **setiap rebuild membakar token agen** (Claude Code/ACP/Ollama). Untuk target kecil itu wajar; untuk eksperimen massal, biayanya nyata.

### F10. Portabilitas — **seri (8 vs 8)**

REA lintas OS via Node, tapi provider `native-macos` hanya macOS — di Linux, kemampuan native-nya bergantung alat yang dipasang. Craft Anything menyediakan paket Linux x86_64/aarch64/riscv64, FreeBSD, Windows, macOS — **tapi** audit tool-nya dilakukan di Windows 11, jadi keberhasilan di Linux belum terbukti menyeluruh (sebagian sudah diuji: Vineflower di JAR nyata, Ghidra 12.2 di Linux).

### F11. Lisensi — **Craft Anything sedikit unggul (10 vs 9)**

MIT dan MIT/Apache-2.0 dua-duanya permisif dan aman untuk produk komersial. Apache menambah hibah paten eksplisit — sedikit lebih nyaman untuk dijual.

### F12. Adopsi & dukungan — **REA unggul (9 vs 7)**

429 ribu bintang dan 106 ribu fork membuat REA menjadi salah satu proyek paling banyak dipakai di kategori ini; dokumentasi dan jawaban komunitas lebih mungkin ada. Craft Anything tumbuh luar biasa cepat (10 ribu bintang / 4 hari, 48 kontributor), tapi belum punya kedalaman jawaban komunitas.

**Peringatan metodologis:** bintang mengukur **perhatian**, bukan **kecocokan**. Dua-duanya punya pola pertumbuhan yang tidak wajar-cepat; jangan jadikan dasar keputusan.

### F13. Rantai pasok — **Craft Anything sedikit unggul (8 vs 7)**

Craft Anything: `Cargo.lock` (205 KB, seluruh pohon dependensi terkunci), `deny.toml` (wildcard dilarang), rilis dengan 29 aset per versi. REA: satu paket npm `rea-agents` dengan 12 dependensi langsung + `frida` opsional — lebih sedikit, tapi ekosistem npm punya riwayat insiden yang lebih banyak. SDB sudah memitigasi REA dengan pin + sha512 + audit #19.

---

## 6. Matriks skor berbobot (konteks: SDB hari ini)

Bobot dipilih karena SDB hidup dari **alur kerja + keselamatan**, bukan dari eksplorasi bebas.

| Faktor | Bobot | REA | Craft Anything |
|---|---:|---:|---:|
| Alur end-to-end (recon → bangun → uji paritas) | 20 | 4 | **9** |
| Keselamatan, izin, isolasi | 20 | 7 | **9** |
| Kematangan versi | 15 | **9** | 3 |
| Kedalaman investigasi | 15 | **9** | 7 |
| Kualitas bukti | 10 | 8 | **9** |
| Biaya & sumber daya | 10 | **9** | 5 |
| Lisensi | 5 | 9 | **10** |
| Adopsi & dukungan | 5 | **9** | 7 |
| **Skor akhir** | 100 | **7,50** | **7,35** |

Dengan bobot lain, pemenangnya berubah — dan itu justru intinya:

| Skenario | Bobot yang berubah | REA | Craft Anything |
|---|---|---:|---:|
| **Rebuild-first** (bangun ulang produk, paritas diuji) | alur 30, bukti 15, keselamatan 20 | 6,95 | **7,85** |
| **RE biner/firmware/malware** | kedalaman 35, kematangan 20 | **8,30** | 6,89 |
| **SDB hari ini** (di atas) | — | **7,50** | 7,35 |

---

## 7. Jawaban tegas: mana yang "terbaik"?

1. **Untuk membongkar dan memahami** — REA. Lebih dalam, lebih matang, lebih luas jenis target, sudah terpasang dan terpagar di SDB.
2. **Untuk menghasilkan produk jadi yang terbukti mirip** — Craft Anything. Satu-satunya dari keduanya yang punya siklus bangun + ukur kemiripan.
3. **Untuk SDB sekarang** — REA, karena skor kesiapan lebih tinggi dan biaya integrasinya nol. Tapi keunggulannya **tipis (0,15 poin)**, dan tipisnya disebabkan satu hal: SDB belum punya tahap "bangun + uji paritas", yang justru kekuatan Craft Anything.

Karena itu jawaban yang jujur bukan "pilih salah satu", melainkan: **pakai REA sebagai mata, uji Craft Anything sebagai tangan.** Mengganti REA dengan Craft Anything hari ini = menukar alat matang dengan alpha 4 hari yang belum pernah menjalankan clean-room build nyata. Menolak Craft Anything sepenuhnya = melewatkan satu-satunya jalur yang bisa membuktikan "hasil rebuild mirip aslinya" dengan angka.

---

## 8. Rekomendasi arsitektur untuk SDB

**Lapis 1 — Instrumen (tetap): REA 6.8.0**
Dipakai agen recon/architect/reviewer/security. Tetap T0 default, tetap lewat Gate #0, tetap tanpa MCP terdaftar.

**Lapis 2 — Pilot (baru, terisolasi): Craft Anything v0.3.0**
Aturan pilot:

- Dipasang **hanya** dari rilis resmi v0.3.0 (unduh aset Linux + verifikasi checksum), **bukan** `cargo install` dari HEAD — supaya reproducible;
- Jalan di **mesin/container terpisah** dari host trading; tidak menyentuh `~/anantara-sakti` sama sekali;
- Hanya **Clean room mode**; Deep mode dilarang pada pilot;
- Hanya target **milik sendiri** (`sdb-local-demo`, `rt-rw-portal` build lokal) — Gate #0 PASS tertulis sebelum eksekusi;
- Anggaran token LLM dibatasi per proyek; tidak ada kunci aset fal.ai;
- Output proyek disimpan di `evidence/craft-anything/<target>/` dan **tidak** masuk `runs/` sampai ada keputusan.

**Lapis 3 — Keputusan (setelah 14 hari)**
Craft Anything naik jadi tahap resmi pipeline SDB **hanya jika** 4 gerbang lulus:

| Gerbang | Syarat lulus |
|---|---|
| G1 Fungsional | 1 rebuild nyata pada `sdb-local-demo` mencapai status **Ready** dengan skor kemiripan ≥ 0,80 |
| G2 Keselamatan | 0 pelanggaran clean-room (tidak ada tool Deep yang jalan, tidak ada akses keluar folder proyek) |
| G3 Reproduksibilitas | Instalasi dari rilis v0.3.0 + checksum, bisa diulang di mesin kedua dengan hasil sama |
| G4 Biaya | Token per rebuild tercatat dan masuk anggaran yang disetujui |

Gagal salah satu → pilot ditutup, REA tetap satu-satunya instrumen, temuan ditulis di `reports/`.

---

## 9. Risiko yang harus diterima (dan mitigasinya)

| Risiko | Pada | Mitigasi |
|---|---|---|
| Alpha 4 hari, 348 commit/4 hari | Craft Anything | Pin v0.3.0, larang update otomatis, uji ulang tiap naik versi |
| 52 tool belum terverifikasi | Craft Anything | Batasi ke toolset yang sudah *Verified* (core, native, browser, format) |
| 161 isu terbuka | Craft Anything | Baca isu yang menyentuh toolset kita sebelum pilot |
| 229+ tool MCP membengkakkan konteks | REA | Tetap CLI-first (sudah jadi aturan SDB) |
| Provider butuh Ghidra/IDA/Hopper berlisensi | REA | Default tanpa Ghidra; bila perlu, Ghidra (gratis) saja |
| Bintang bukan ukuran mutu | keduanya | Keputusan berbasis uji 14 hari, bukan popularitas |
| Token LLM membengkak | Craft Anything | Batas anggaran per proyek, `--rounds 1` untuk uji awal |

---

## 10. Rencana uji 14 hari (konkret, bisa dieksekusi)

| Hari | Aksi | Kriteria lulus |
|---|---|---|
| 1 | Unduh rilis v0.3.0 Linux x86_64, verifikasi checksum, `doctor` | `doctor` hijau, tanpa build dari sumber |
| 2 | Tulis Gate #0 untuk `sdb-local-demo` | Berkas izin tersimpan, target = milik sendiri |
| 3–4 | Rebuild clean-room 1 putaran | Proyek dibuat, status Build tercapai |
| 5–7 | Rebuild sampai 6 putaran / 90% | Skor kemiripan tercatat per lebar layar |
| 8 | Audit jejak: apakah ada tool Deep yang jalan? | 0 pelanggaran (cek log + `checks/`) |
| 9 | Ulangi instalasi di mesin kedua | Hasil sama (G3) |
| 10 | Hitung token & biaya | Angka nyata, dibanding anggaran |
| 11–12 | Uji banding: REA pada target sama | Catat apa yang REA temukan dan Craft Anything lewatkan |
| 13 | Tulis laporan | `reports/CRAFT_ANYTHING_PILOT_2026xxxx.md` |
| 14 | Keputusan G1–G4 | Naik / tidak naik |

---

## 11. Lampiran A — perintah verifikasi (bisa diulang)

```bash
# 1. Metadata kedua repo
curl -s https://api.github.com/repos/morluto/rea | jq '{stargazers_count,forks_count,open_issues_count,created_at,license:.license.spdx_id}'
curl -s https://api.github.com/repos/storytold/craft-anything | jq '{stargazers_count,forks_count,open_issues_count,created_at,license:.license.spdx_id}'

# 2. Ukuran rekayasa Craft Anything
git clone --depth 1 https://github.com/storytold/craft-anything && cd craft-anything
find . -name '*.rs' -not -path './vendor/*' | wc -l          # 460
find . -name '*.rs' -not -path './vendor/*' | xargs cat | wc -l  # 204498
ls crates                                                    # 14 crate

# 3. Status tool yang jujur (bawaan proyek)
sed -n '1,30p' docs/tool-status.md

# 4. Kesiapan REA di host ini
cd ~/super-dev-builders && scripts/rea capabilities | head -40
scripts/rea --version                                        # 6.8.0

# 5. Cek telemetri (harus kosong)
grep -rn -iE 'posthog|sentry|amplitude|telemetry' craft-anything/crates craft-anything/apps | head
```

## 12. Lampiran B — sumber

- GitHub REST API, `morluto/rea` dan `storytold/craft-anything`, diambil 4 Nov 2026.
- `storytold/craft-anything` — `README.md`, `AGENTS.md`, `SECURITY.md`, `docs/STATUS.md`, `docs/tool-status.md`, `docs/tools.md`, `deny.toml`, rilis `v0.3.0` (29 aset).
- `rea-agents@6.8.0` lokal: `~/.hermes/tools/rea-6.8.0/node_modules/rea-agents` — `package.json` (MIT, 12 dependensi), `README.md`, `dist`, keluaran `scripts/rea capabilities` (12 entri provider, 53 grup, 113 operasi di host ini).
- Registry SDB: `registry/skills.yaml:253-262`, `registry/tools.yaml:116-121`, `scripts/workflow_run.py:53-72`, `tests/test_rea_integration.py`.

---

*Disusun oleh Hermes Anantara v3 untuk Divisi Ekosistem SDB. Semua angka dapat diperiksa ulang dengan perintah di Lampiran A. Yang belum diuji dinyatakan belum diuji.*
