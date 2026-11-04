# Uji Coba Terisolasi — Craft Anything v0.3.0

Status: **pilot dilanjutkan, read-only pelengkap** · Diuji 2026-11-04 · Bukti: `evidence/craft-anything-pilot/`

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
| Skrip instalasi | tidak ada · path absolut/`..` | tidak ada |
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
