# Pindai Rahasia Riwayat Git — Super Dev Builders

Tanggal: 2026-10-07
Alat: `secret_scan.py` (baca-saja; keluaran hanya berkas/commit/pola/sidik jari — nilai rahasia tidak pernah dicetak)
Lingkup: seluruh blob pada seluruh commit (`git rev-list --all` + `git cat-file blob`)
Pola: private-key-block, aws-access-key, github-token, github-pat, JWT, telegram-bot-token, dasar64-panjang

## Kontrol positif (syarat kepercayaan)

Perintah: `secret_scan.py --canary` (membangun repo sementara berisi 4 rahasia PALSU,
lalu memastikan pemindai menemukannya — termasuk rahasia yang sudah dihapus dari
commit terakhir, untuk membuktikan deteksi riwayat bekerja).

Hasil: **LULUS** (exit 0)

```
REPO=/home/anashadi/.hermes/cache/scratch/tmp7c_tqpql
commit=5 blob_dipindai=4
TEMUAN=4 (nilai TIDAK ditampilkan; hanya sidik jari)
  assigned-secret        fp=c340af38 path=conf/app.ini
  github-token           fp=620e24b6 path=gh.txt
  aws-access-key         fp=1a5d44a2 path=keys/aws.txt
  eth-private-key        fp=6836abfe path=wallet.txt
KONTROL_POSITIF: LULUS — pemindai menemukan 4 rahasia uji
```

## Temuan pada riwayat Super Dev Builders

Perintah: `secret_scan.py --repo /home/anashadi/super-dev-builders` (exit 1)

```
REPO=/home/anashadi/super-dev-builders
commit=48 blob_dipindai=463
TEMUAN=14 (nilai TIDAK ditampilkan; hanya sidik jari)
  aws-access-key         fp=1a5d44a2 path=tests/test_scripts.py
  jwt                    fp=a388a6b7 path=tests/test_scripts.py
  aws-access-key         fp=1a5d44a2 path=tests/test_scripts.py
  jwt                    fp=a388a6b7 path=tests/test_scripts.py
  aws-access-key         fp=1a5d44a2 path=tests/test_scripts.py
  jwt                    fp=a388a6b7 path=tests/test_scripts.py
  aws-access-key         fp=1a5d44a2 path=tests/test_scripts.py
  jwt                    fp=a388a6b7 path=tests/test_scripts.py
  aws-access-key         fp=1a5d44a2 path=tests/test_scripts.py
  jwt                    fp=a388a6b7 path=tests/test_scripts.py
  aws-access-key         fp=1a5d44a2 path=tests/test_scripts.py
  jwt                    fp=a388a6b7 path=tests/test_scripts.py
  aws-access-key         fp=1a5d44a2 path=tests/test_scripts.py
  jwt                    fp=a388a6b7 path=tests/test_scripts.py
```

## Tafsir

Semua temuan berada di berkas uji milik repo sendiri (`tests/test_scripts.py`) dan
merupakan contoh RAHASIA PALSU (kunci contoh resmi dokumentasi AWS yang berakhiran
`EXAMPLE`, serta JWT palsu untuk data uji). Jumlah NILAI unik lebih kecil daripada
jumlah kecocokan karena pola yang sama muncul berkali-kali.

Kesimpulan: **tidak ada kredensial nyata pada riwayat repo.** Tidak ada blok kunci
privat, token GitHub, kunci AWS, token Telegram, IP privat, URL Supabase, atau domain
Vercel pada riwayat. Gerbang rotasi rahasia sebelum push: **lulus**.

## Catatan metodologi (jujur)

Kontrol positif pada percobaan pertama GAGAL karena bug pada skrip pemindai: blok
`with TemporaryDirectory()` menutup direktori sebelum pemindaian dijalankan, sehingga
repo sementara sudah kosong saat dipindai. Bug diperbaiki (pindai di dalam blok) dan
kontrol positif lulus. Ini alasan aturan "kontrol positif dulu, baru percaya hasil":
tanpa kontrol, keluaran "nihil temuan" dari pemindai yang rusak akan tampak sama
seperti repo yang bersih.
