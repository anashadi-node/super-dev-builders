# Intake — kanal input per skenario

Setiap skenario dan setiap tahap di Command Deck punya satu panel **Brief &
lampiran**. Panel itu menerima tiga jenis masukan sekaligus:

| Masukan | Kontrol | Dipakai untuk |
|---|---|---|
| **Teks bebas** | textarea | apa yang ingin dibuat/diubah (website, aplikasi, SaaS, API, dsb.) |
| **Contoh / referensi** | input URL → chip | halaman acuan, repo, desain, dokumentasi |
| **Lampiran** | dropzone + file picker | gambar, HTML, MD, DOC/DOCX, PDF, ZIP, apa pun |

Filenya boleh dari mana saja di disk (biasanya `~/Downloads`) — yang dipilih
adalah file asli, bukan salinan yang dibatasi folder tertentu.

## Di mana hasilnya

Setiap kiriman menjadi satu folder nyata di disk, di luar repo:

```
~/sdb-workspace/intake/20261101-094618-df1e92/
├── meta.json    # skenario, tahap, teks, link, daftar file + sha256
├── brief.md     # versi manusia & mesin — inilah yang dibaca agen
└── files/       # lampiran asli, nama sudah disanitasi
    ├── uji-lampiran.md
    └── contoh-gambar.png
```

`brief.md` memuat: intake id, skenario, tahap, target, teks Owner, daftar link,
tabel lampiran (nama, ukuran, sha256), dan catatan bahwa isi lampiran **belum
diverifikasi** sampai benar-benar dibaca.

## Alur satu kiriman

1. Buka kartu skenario → panel “Brief &amp; lampiran” di paling atas.
2. Tulis maksud, tempel link (Enter), tarik/klik file.
3. Tekan **Simpan ke Intake** → `POST /api/inbox/submit` membuat folder, lalu
   tiap file dikirim streaming ke `POST /api/inbox/file`.
4. Muncul kartu ✓ berisi intake id, path folder, tombol *Salin path* dan
   *Lihat brief.md*.
5. Tab **Intake** menampilkan semua kiriman; klik kartu untuk membaca brief,
   mengunduh lampiran, atau menghapus kiriman.

Draf teks + link disimpan otomatis di `localStorage` per skenario/tahap, jadi
berpindah drawer tidak menghilangkan tulisan yang belum dikirim.

**Batas jujur:** menekan Simpan **tidak** menjalankan agen. Ia menulis masukan
ke disk. Menjalankan tahap tetap lewat runner (`python3 scripts/workflow_run.py`).

## Dari Intake ke tahap (runner)

Kiriman tidak berguna kalau agen harus menyalin ulang. Ada satu perintah untuk
menautkannya:

```bash
python3 scripts/workflow_run.py --list-intakes                     # lihat kiriman
python3 scripts/workflow_run.py <target> --intake latest            # tautkan konteks
python3 scripts/workflow_run.py <target> --intake latest --as 01    # + isi requirements.md
```

Yang terjadi:

1. `runs/<target>/docs/intake-<id>.md` ditulis — brief **verbatim**, tabel
   lampiran dengan **path absolut** + sha256, dan daftar link. Ini yang dibaca
   agen pada tahap mana pun, tanpa perlu akses ke folder intake.
2. `runs/<target>/CONTEXT.md` menunjuk kiriman terbaru (blok idempoten —
   dijalankan sepuluh kali pun tetap satu blok).
3. `--as 01` mengisi `runs/<target>/requirements.md` **hanya bila belum ada**,
   dengan header `<!-- dibuat otomatis dari intake … — BELUM ditinjau manusia -->`.
   Tidak pernah menimpa requirements yang sudah ditulis manusia.

`--as` sengaja hanya menerima tahap **01**. Brief bukan pengganti ADR (04),
plan (06), review (08), atau log tes (09) — mengisi artefak itu dari brief akan
menghasilkan bukti palsu. Tahap lain harus dikerjakan tool/agen yang sebenarnya.

## Batas & keamanan

- Maks **25 MB per file**, **40 file** per kiriman, total **400 MB**.
- Nama file disanitasi (basename, tanpa karakter kontrol, tanpa awalan titik);
  path di-resolve dan wajib tetap di dalam folder intake.
- Ukuran dihitung **saat streaming**, bukan hanya dari header; body terpotong
  (kurang dari `Content-Length`) ditolak dan file `.part` dihapus.
- Lampiran tidak pernah dieksekusi. Unduhan non-gambar dipaksa
  `application/octet-stream` + `Content-Disposition: attachment` +
  `X-Content-Type-Options: nosniff`, sehingga `.html`/`.svg` tidak bisa jalan
  sebagai halaman. Hanya gambar raster (png/jpg/gif/webp/bmp) boleh inline.
- Semua rute `/api/inbox/*` wajib header `X-SDB-Token` (token 72-bit yang sama
  dengan `/api/ws/*`). Dari PC lokal token diisi otomatis; dari LAN, PIN diisi
  manual dan **tidak** disimpan ke storage.
- Link wajib `http://` atau `https://` — skema lain (`javascript:`, `file:`)
  ditolak server.

## API

| Rute | Metode | Isi |
|---|---|---|
| `/api/inbox/submit` | POST | JSON `{scen, scen_title, stage, text, links[], expect_files}` |
| `/api/inbox/file?id=&name=` | POST | body biner mentah file |
| `/api/inbox/list` | GET | 40 kiriman terakhir (ringkas) |
| `/api/inbox/get?id=` | GET | meta + isi `brief.md` |
| `/api/inbox/download?id=&name=` | GET | unduh satu lampiran |
| `/api/inbox/delete` | POST | JSON `{id}` — hapus folder kiriman |

Kode: `dashboard/inbox_api.py`; UI: `dashboard/app.js` (blok `intake`);
uji: `tests/test_inbox_api.py` (9 kasus, termasuk traversal, oversize, auth,
dan paksaan attachment).
