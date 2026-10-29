# Gerbang Keamanan Tahap 10 — kontrak alat dan arti verdict

Dokumen ini mengikat: ia menjelaskan **apa yang benar-benar diperiksa** sebelum rilis SDB
dan apa arti setiap status. Sebelum 30 Okt 2026 gerbang ini hanya ada di kode, tanpa
dokumen — akibatnya satu-satunya cara mengetahui cakupannya adalah membaca 500 baris
skrip, dan drift (lihat §5) tidak terlihat oleh siapa pun.

## 1. Dua kanal, satu verdict

Produsen tunggal: `scripts/security_verdict.py` → `reports/security-verdict.json`.
Tidak ada jalur manual untuk menandai PASS (`policy` di berkas verdict menyatakan ini).

| Kanal | Berkas | Alat | Keluaran |
|---|---|---|---|
| `scan-keamanan` | `tools/scan-keamanan.sh` | semgrep (SAST), syft (SBOM), trivy (kerentanan + rahasia + misconfig), ruff (pola keamanan), pemanggilan kanal privasi | log per-alat + ringkasan |
| `privasi-media` | `tools/scan-privasi-media.py` | tesseract OCR (+ ffmpeg untuk video) atas **media terlacak git** | `reports/raw/privasi-media.json` |

Verdict = `PASS` hanya bila **kedua** kanal keluar 0. Prosa alat tidak mengikat: alat yang
mencetak "semua aman" tetapi keluar ≠0 tetap `FAIL`.

## 2. Arti status (jangan disamakan)

| Status | Arti | Boleh rilis? |
|---|---|---|
| `PASS` | Alat berjalan dan keluar 0 | Ya |
| `FAIL` | Ada temuan, atau alat keluar ≠0 | **Tidak** |
| `BLOCKED` | Alat tidak ada / tidak bisa dijalankan | **Tidak** — "tidak diperiksa" bukan "bersih" |
| `TAK DIVERIFIKASI` (keluar 2) | Cakupan tidak diketahui, atau alat buta (mis. OCR membaca 0 teks dari semua media) | **Tidak** |
| `TIDAK BERLAKU` (keluar 0) | Kanal memang tidak berlaku: 0 media dari ≥1 berkas terlacak git | Ya — dan dicatat eksplisit, bukan diklaim "bersih" |

`TIDAK BERLAKU` sengaja dipisahkan dari `PASS` di ringkasan supaya tidak ada yang membaca
"0 temuan" sebagai "sudah diperiksa dan bersih".

## 3. Aturan yang tidak bisa dinegosiasikan oleh proyek

1. **Inti keamanan ruff dipaksa alat.** `ruff check --isolated --select S,BLE,E9` selalu
   dijalankan. `ruff.toml` proyek hanya boleh **menambah** aturan, tidak mematikan deteksi.
   Alasan konkret: proyek yang memilih hanya `E9,B` meloloskan `eval(x)` (S307) dengan
   verdict `PASS` — terbukti pada uji negatif 30 Okt 2026.
2. **Negatif-kontrol semgrep.** Setiap pemindaian menanam satu pola yang wajib terdeteksi.
   Jika kontrol = 0, artinya aturan tidak termuat → kanal `FAIL`, bukan "bersih".
3. **Cakupan = berkas terlacak git.** Berkas tak terlacak tidak diperiksa; karena itu
   "0 temuan" pada repo tanpa berkas terlacak adalah `TAK DIVERIFIKASI`.
4. **Daftar larangan identitas wajib ada** bila ada media: `real_system.privacy_scan.TERLARANG`
   atau `privacy-terms.json` (`["istilah", ...]`). Tidak ada sumber = keluar 2, bukan "bersih".
5. **Baseline risiko terbuka** (`risiko-diterima.json`) hanya menurunkan temuan yang sudah
   tercatat; tanpa baseline, semua temuan dihitung baru.
6. **Cakupan = kode produk, bukan artefak tangkapan.** `targets/`, `runs/`, `evidence/`,
   `screens/`, `trace/`, `dom/`, `reconstruction/`, `normalization/` dikecualikan dari ruff
   dan trivy: isinya milik proyek yang **diaudit**, bukan produk ini. Tanpa aturan ini,
   SBOM target lama (43 temuan Pillow) membuat gerbang proyek sendiri gagal selamanya.
7. **Konfigurasi ruff boleh di mana saja yang sah**: `ruff.toml`, `.ruff.toml`, atau
   `pyproject.toml[tool.ruff]`. Tidak ada konfigurasi = **FAIL** (aturan tidak dipin →
   hasil tidak reproducible), bukan dilewati.
8. **`S101` (assert) hanya diabaikan di `tests/`** — assert adalah mekanisme tes. Di kode
   produk S101 tetap dilaporkan.
9. **`privacy-terms.json` sengaja gitignored** (berisi nama orang/klien);
   `privacy-terms.example.json` yang dilacak. Tanpa berkas itu, kanal privasi
   `TAK DIVERIFIKASI` — jangan diakali dengan daftar kosong.

## 4. Cara menjalankan

```bash
# satu run, otomatis memakai toolchain bersama tools/
python3 scripts/security_verdict.py --run-dir runs/<slug> --project /path/ke/proyek

# alat di tempat lain (mis. versi beku milik run lama)
python3 scripts/security_verdict.py --run-dir runs/<slug> --project <proyek> --tools-dir <dir>

# manual, satu kanal saja (untuk diagnosis)
tools/scan-keamanan.sh /path/ke/proyek
```

Urutan resolusi alat: `--tools-dir` → `<run>/tools/` → `tools/` (kanonik di repo).
Kanal menerima env `SDB_RUN_DIR` dan `SDB_TOOLS_DIR`; tanpa itu baseline dan bukti mentah
akan tertulis di tempat yang salah.

## 5. Riwayat drift yang ditutup (30 Okt 2026)

| Gejala | Akar masalah | Perbaikan |
|---|---|---|
| Setiap run/proyek baru → `BLOCKED` | alat hanya ada di `scripts/privasi/portal-rt-rw/` dan `RUN` di-hardcode ke `runs/rt-rw-portal` | alat dipromosikan ke `tools/`, jalur lewat env + fallback |
| Proyek ber-`ruff.toml` longgar lolos `eval()` | aturan keamanan sepenuhnya diserahkan ke config proyek | inti `--isolated --select S,BLE,E9` dipaksa alat |
| Proyek tanpa aset visual mustahil rilis | "0 media" dianggap `TAK DIVERIFIKASI` | `TIDAK BERLAKU` (keluar 0) bila repo punya berkas terlacak |
| Gerbang proyek sendiri gagal selamanya: 43 temuan Pillow 12.3.0 | trivy memindai SBOM **target audit** di `runs/` sebagai dependensi produk | `--skip-dirs` untuk direktori artefak (trivy + ruff) |
| Repo SDB (config di `pyproject.toml`) dianggap "aturan tidak dipin" | alat hanya menerima berkas bernama `ruff.toml` | terima `ruff.toml`/`.ruff.toml`/`pyproject.toml[tool.ruff]` |
| 631 temuan `S101` di tests menenggelamkan temuan nyata | `S101` (assert) dianggap temuan di seluruh repo | `--per-file-ignores "tests/*:S101"` |

Bukti uji: fixtures `/tmp` (backend tanpa media) → `PASS`; fixture dengan `eval(x)` →
`FAIL`; repo tanpa berkas terlacak → `TAK DIVERIFIKASI`. Semua dijalankan lewat
`security_verdict.py` sungguhan, bukan mock.

## 6. Batas yang harus jujur disebut

Gerbang ini **bukan** uji penetrasi dan tidak membuktikan tidak ada kerentanan logika
(IDOR, isolasi tenant, bypass otorisasi). Untuk kelas risiko itu, tahap 10 hanya memberi
bahan; keputusan tetap di tahap 11 (audit) dengan model terkuat, dan wajib ada uji
otorisasi per-peran di tingkat aplikasi.
