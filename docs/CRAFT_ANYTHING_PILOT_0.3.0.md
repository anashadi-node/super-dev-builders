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

Belum jalan: `rebuild` — subperintah ini butuh AI backend (`ai add`), dan `ai list` masih kosong.
Jadi kolom "dua mesin" baru terbukti untuk analisis, **bukan** untuk pembangunan ulang.

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
