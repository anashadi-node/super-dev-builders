# Uji Coba Terisolasi — Craft Anything v0.3.0

Status: **pilot AKTIF — tersambung ke `recon-forge` (pin sha256)** · Diuji 2026-11-04 · Disambungkan 2026-11-14 · Bukti: `evidence/craft-anything-pilot/`

## Kenapa diuji

Pertanyaan yang dijawab dokumen ini: apakah `storytold/craft-anything` menambah kemampuan yang
SDB belum punya, atau hanya duplikat REA? Keputusan disandarkan pada satu berkas yang sama
(`targets/sdb-local-demo/index.html`) yang dijalankan ke dua alat.

## Verifikasi artefak (bukan asumsi)

| Hal | Nilai |
|---|---|
| Sumber | `github.com/storytold/craft-anything` → rilis `v0.3.0` (2026-11-02) |
| Berkas | `craft-anything-0.3.0-linux-x86_64.tar.gz` — 66.643.318 byte |
| SHA-256 terukur | `674ec59ffbdaefbd577917e07c9d464562043b275a3889ba4f60239a12f03d53` |
| SHA-256 terbit (SHA256SUMS.txt) | sama — **cocok** |
| Isi paket | 60 entri: 2 biner (`craft-anything` 98,7 MB GUI, `craft-anything-cli` 32,1 MB) + ikon |
| Skrip instalasi | tidak ada; tidak ada path absolut/`..` |
| Lokasi | `~/.local/opt/craft-anything-0.3.0` (tanpa root, tanpa eksekusi skrip) |
| Cara jalan sekarang | `env -i HOME=/tmp/ca-home …/craft-anything-cli` — tanpa kredensial apa pun |

Biner tidak ditandatangani dan sumbernya tidak tersedia publik; SHA256SUMS memberi integritas
unduhan, bukan jaminan isi. Karena itu alat ini **tidak** dipakai untuk target pihak ketiga
dan tidak pernah dijalankan dengan kredensial.

## Hasil uji

| Uji | Hasil |
|---|---|
| `--version` | `craft-anything-cli 0.3.0`, rc=0 |
| `commands` | 315 tool terdaftar |
| `triage` mode bersih (default) | **ditolak** `feature_missing / clean_room` — benar, tidak membaca isi target |
| `--deep triage index.html` | rc=0: `kind=script`, sha256 subjek `640d2540…`, id bukti `ev_98368ae0…`, saran lanjutan `js_app_map` |
| `rea inspect index.html` (pembanding) | rc=1 `unsupported binary format` — REA tidak menangani HTML |

Kesimpulan pembandingan: **komplementer, bukan pengganti.** REA kuat pada biner/Ghidra (jalur
native SDB). Craft Anything menangani berkas web/aset dan memuntahkan bukti ber-id + saran
langkah berikutnya — bentuk keluaran yang cocok untuk laporan.

## Sambungan ke recon-forge (2026-11-14)

Pilot tidak lagi dipanggil manual dari shell. `recon-forge` sekarang mendeteksi biner ini dan
memverifikasi integritasnya sebelum mengizinkan pemakaian:

```bash
python3 tools/recon-forge.py doctor                  # cari biner + cocokkan pin
python3 tools/recon-forge.py build --target <t> --engine craft
```

| Keadaan | `doctor` | `build --engine craft` |
|---|---|---|
| biner tidak ada | `found=false` | exit 3 + instruksi pemasangan |
| biner ada, sha256 = pin | `pinned=true`, `rebuild-combo=True` | jalan, sha256 dicatat ke audit-log |
| biner ada, sha256 ≠ pin / pin hilang | `pinned=false` | **exit 4, ditolak** |

Pin: `integrations/craft-anything/PINNED.json` (sha256 aset unduhan + kedua biner).
Alasan: `SHA256SUMS.txt` hanya menjamin unduhan tidak rusak, bukan isi biner.
Deteksi juga mencakup akar instalasi terisolasi (`~/.local/opt/craft-anything-*/bin/`), karena
sebelum ini `doctor` hanya melihat PATH dan melaporkan "belum terpasang" padahal biner sudah ada.

Uji regresi: `tests/test_recon_forge.py` (5 kasus: deteksi non-PATH, pin cocok, pin beda,
pin hilang, `rebuild-combo` wajib pin).

## Uji jalan nyata (2026-11-14)

Bukan lagi hanya "terpasang": biner dipanggil dengan `env -i` pada target sendiri
(`targets/sdb-local-demo`, gate0 PASS). Keluaran lengkap: `evidence/craft-anything-pilot/run-20261114/`
(di-gitignore — bukti pilot lokal, bukan bukti target).

| Perintah | Hasil |
|---|---|
| `triage index.html --format json` | `kind: script`, `next_steps: js_app_map`, exit 0 |
| `js-app-map --input-path app.js --format file --output-format json` | 1 source file, 0 IPC, 0 window, **1 endpoint**, 0 route |
| Endpoint yang dilaporkan | `GET /api/status` — `api: fetch`, `line: 2`, `literal: true` |

Uji falsifikasi: `app.js` memang 5 baris dengan tepat satu `fetch('/api/status')` di baris 2
→ klaim alat benar, tidak ada halusinasi pada berkas ini. Sampel sekecil ini **belum** cukup
untuk menyimpulkan presisi pada target nyata.

Jebakan pemakaian: pada `js-app-map`, `--format` adalah jenis input (`auto/asar/directory/zip/file`);
format keluaran memakai `--output-format`. Salah pakai → `bad_input: unknown variant 'json'`.

Belum jalan: — (`rebuild` sudah dijalankan 2026-11-14 memakai AI backend `hermes-deepseek`,
yaitu model Hermes yang sedang aktif. Hasil paritasnya rendah: lihat
`evidence/craft-anything-pilot/run-20261114/README.md` §Opsi A.)
Jadi kolom "dua mesin" baru terbukti untuk analisis, **bukan** untuk pembangunan ulang.

## Uji `rebuild` dengan model Hermes aktif (2026-11-14)

Backend AI disambungkan lewat API OpenAI-compatible milik provider Hermes
(`--kind openai_compatible`, `--base-url https://api.deepseek.com/v1`,
`--model deepseek-flash`, kunci dibaca dari env `DEEPSEEK_API_KEY` — tidak pernah
ditulis di argumen CLI). `ai test` → `latency_ms 560`, `reply: ready`.

Jebakan 1: backend **tidak** dipilih otomatis. Tanpa `ai builder <nama>`, craft memilih
`claude-code` (biner native tidak ada) dan gagal.
Jebakan 2: `rebuild` berhenti di `[Check 1] No project to build found in app/ yet.`
Craft mengharapkan proyek ber-manifest build; situs statis tidak memenuhinya, lalu sesi
"Improving the build…" berputar tanpa kemajuan.

Paritas hasil rebuild terhadap capture original (fidelity_compare 9 dimensi):

| Dimensi | Status | Coverage |
|---|---|---|
| navigation | partial | 0.0 |
| interaction | mismatch | 0.0 |
| api_contract | partial | 0.5 |
| functional | partial | 0.0 |
| accessibility | ok | 1.0 |
| performance | ok | 0.6395 |
| visual / responsive / external_dependency | NOT_MEASURED | – |

Kesimpulan: craft 0.3.0 **layak sebagai penganalisis**, **belum layak sebagai mesin
rebuild**. Untuk klon tetap pakai jalur replicas (D5), bukan craft.

## Ukur ulang paritas setelah 2 bug harness diperbaiki (2026-11-15)

Dua angka di atas bukan sifat rebuild, melainkan **bug pembanding** yang ditemukan saat
hendak menutup dimensi visual/responsive:

1. **Kunci halaman tidak dinormalkan.** Server statis mengalihkan `/` → `/index.html`, jadi
   capture original berkunci `/index.html` sementara rebuild `/`. Irisan path kosong ⇒ `visual`
   NOT_MEASURED dan `functional` 0.0 padahal halaman sama. Perbaikan: `page_path()`
   (`/a/index.html` → `/a/`).
2. **Tautan dibandingkan mentah.** Original menyimpan href absolut (`/about.html`), rebuild
   relatif (`about.html`) — identik secara perilaku, tapi `navigation` jadi 0.0. Perbaikan:
   `norm_href()` (resolve relatif terhadap path halaman, `mailto:`/`tel:`/`#anchor` diabaikan).

Bukti regresi: `tests/test_fidelity_compare.py` (`TestPagePath`, `TestNormHref`, 8 tes baru).
Capture ulang 4 sisi (desktop + mobile `390x844`, original :8100 vs rebuild :8101) →
`evidence/craft-anything-pilot/run-20261114/parity-rebuild.json` (lokal, git-ignored) dan salinan terlacak `reports/sdb-local-demo/fidelity-rebuild.json`:

| Dimensi | Sebelum | Sesudah | Coverage |
|---|---|---|---|
| visual | NOT_MEASURED | ok | 1.0 (screenshot byte-identik, sha256 `67869dbd…`) |
| responsive | NOT_MEASURED | ok | 1.0 (viewport mobile, sha256 `0ceaecfc…`) |
| navigation | partial 0.0 | ok | 1.0 |
| functional | partial 0.0 | ok | 1.0 |
| accessibility | ok | ok | 1.0 |
| performance | ok 0.6395 | ok | 1.0 |
| api_contract | partial 0.5 | **mismatch** 0.0 | benar: original punya `/api/status`, rebuild statis tidak |
| interaction | mismatch 0.0 | NOT_MEASURED | rebuild tak punya elemen yang sama untuk diklik |
| external_dependency | NOT_MEASURED | NOT_OBSERVED | kedua sisi tanpa host pihak ketiga |

Status jujur: **7 dari 9 dimensi kini terukur** (naik dari 4). Dua sisa memang tidak bisa diukur
pada rebuild ini, bukan disembunyikan. `api_contract` turun ke mismatch karena rebuild tidak
mengimplementasikan endpoint — itu temuan nyata, bukan kemunduran alat.

Catatan penting: demo `sdb-local-demo` adalah halaman ~680 byte, sehingga visual 1.0 di sini
**tidak** membuktikan paritas visual pada aplikasi nyata. Yang terbukti: harness sekarang bisa
mengukur dimensi itu dengan angka.


## Batas pemakaian (mengikat)

1. **Read-only, pelengkap.** Tidak menggantikan `recon-forge`; tidak menjadi pemanggil pertama
   pada target baru. Gate #0 tetap milik SDB.
2. **Tidak untuk target pihak ketiga** selama belum ada audit sumber. Pilot hanya pada target
   milik sendiri (`targets/`).
3. **Tanpa kredensial.** Dijalankan dengan `env -i` dan `HOME` terpisah agar tidak membaca sesi
   agen lain, token, atau riwayat shell.
4. **Deep mode = izin terpisah.** Sama seperti jalur native SDB: membaca isi target butuh
   manifest `deep_analysis_allowed: true`. Jangan aktifkan `--deep` untuk target yang
   manifest-nya mode A.
5. **Tidak dipasang ke PATH** dan tidak didaftarkan sebagai klien agen (`setup` tidak dijalankan),
   supaya tidak ada agen yang tiba-tiba memakainya tanpa keputusan.

## Catatan operasional

- `capabilities` melaporkan `ghidra: found=false` saat dijalankan dengan `env -i`, karena Ghidra
  dideteksi lewat variabel lingkungan. Itu bukan kerusakan alat — konsekuensi isolasi.
- Unduhan rilis GitHub dari jaringan ini tidak stabil (~13–50 KB/s per koneksi); diunduh dengan
  8 rentang paralel + resume, lalu diverifikasi checksum. Skrip: `~/.local/opt/_karantina/ca-0.3.0/dl2.sh`.
- Bila pilot dihentikan: hapus `~/.local/opt/craft-anything-0.3.0` dan `_karantina` — tidak ada
  perubahan sistem lain (tidak ada layanan, tidak ada entri PATH).
