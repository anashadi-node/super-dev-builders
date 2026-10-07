# Temuan: kerentanan dependency — SUDAH DIEKSEKUSI (Opsi 1)

Tanggal audit: 2026-10-07 · Trivy 0.75.0 · Status: **SELESAI — temuan turun 37 → 3**

## Koreksi penting atas laporan awal

Laporan awal menyebut lokasi `~/.hermes/hermes-agent/venv` sebagai "runtime 23 profil".
**Itu keliru.** Pemeriksaan lanjutan atas `docs/HERMES_VENV_HARDENING_2026-10-05.md` §1 dan
`~/.hermes/installs/8f187687540a47e8/facts.json` menunjukkan:

| Venv | Peran | Kondisi saat diaudit |
|---|---|---|
| `~/.hermes/installs/<key>/environments/<gen>/venv` (Python 3.14.7) | **runtime Hermes LIVE** (gateway + Desktop) | sudah tertambal sejak 2026-10-05: PyJWT 2.15.1, httpx2/httpcore2 2.13.1, tornado 6.5.10, urllib3 2.8.0 |
| `~/.hermes/hermes-agent/venv` (Python 3.11) | **legacy pra-PM** — PM tidak memakainya, TAPI masih hidup | inilah yang memuat 37 temuan; dipakai proses `real_system.prod_server` (milik `~/rt-rw-portal`) |

Jadi angka 37 nyata, tetapi bukan di runtime Hermes.

## Tindakan yang dieksekusi (Opsi 1, disetujui pemilik)

8 paket dinaikkan di venv legacy — target dikoreksi ke tempat temuan benar-benar berada:

| Paket | Sebelum | Sesudah |
|---|---|---|
| PyJWT | 2.13.0 | **2.15.1** |
| pypdf | 6.16.2 | **6.19.0** |
| httpx2 / httpcore2 | 2.7.0 | **2.13.1** |
| tornado | 6.5.8 | **6.5.10** |
| urllib3 | 2.7.0 | **2.8.0** |

Aman karena: (a) `rt-rw-portal` hanya memakai modul standar Python — tidak menyentuh paket terdampak;
(b) rollback tersedia (`~/backups/sdb-legacyvenv-20261007_204758/pip-freeze-before.txt`, 165 paket);
(c) target versi sama dengan pin repo Hermes sendiri.

## Hasil terukur

- Trivy: **37 temuan → 3** (1 CRITICAL, 20 HIGH → **0 CRITICAL, 0 HIGH**; sisa 3 MEDIUM tanpa versi perbaikan).
- Uji impor nyata: `jwt 2.15.1`, `urllib3 2.8.0`, `tornado 6.5.10`, `pypdf 6.19.0`; backend crypto PyJWT untuk HS256 aktif.
- Proses `real_system.prod_server` (PID 111572) tetap hidup (`Ssl`) setelah upgrade.
- Runtime Hermes (`hermes-gateway` = active) tidak tersentuh; paketnya tetap 2.15.1/2.13.1/6.5.10.
- Bukti: `~/.hermes/cache/scratch/{t-hv2.json,hv2/requirements.txt,hermes_venv_baseline.json}`.

## Catatan sisa (perlu keputusan terpisah)

Venv legacy TIDAK dihapus, karena satu proses hidup bergantung padanya. Utang teknis:
`~/rt-rw-portal` sebaiknya diberi venv sendiri (agar tidak bergantung pada venv legacy Hermes),
lalu venv legacy dapat dipensiunkan. Ini usulan, belum dieksekusi.

Rollback (bila diperlukan):
`/home/anashadi/.hermes/hermes-agent/venv/bin/python -m pip install -r ~/backups/sdb-legacyvenv-20261007_204758/pip-freeze-before.txt`

## Ringkas

Venv Hermes Agent punya **37 advisory (1 CRITICAL, 20 HIGH, 16 MEDIUM)** yang punya versi
perbaikan tersedia. Ini runtime agen yang sedang jalan, dipakai 23 profil.

| Paket | Terpasang | Perbaikan tersedia | Jml advisory | Tingkat |
|---|---|---|---|---|
| PyJWT | 2.13.0 | **2.14.0** | 6 | **CRITICAL** |
| pypdf | 6.16.2 | 6.19.0 | 8 | HIGH |
| httpx2 | 2.7.0 | 2.12.0 | 2 | HIGH |
| tornado | 6.5.8 | 6.5.9 | 2 | HIGH |
| urllib3 | 2.7.0 | 2.8.0 | 2 | HIGH |
| httpcore2 | 2.7.0 | 2.10.0 | 1 | HIGH |

## Bukti (semua dieksekusi hari ini)

- Laporan lama `reports/upgrade-evidence/hermes-security-audit.txt` (2026-10-04) sudah
  melaporkan hal yang sama — **identik**. Artinya remediasi belum pernah dilakukan
  (bukan risiko yang sengaja diterima).
- Verifikasi mandiri: venv diekspor ke `requirements.txt` (167 paket) lalu dipindai Trivy
  → 37 temuan, daftar sama dengan laporan lama.
- **Kontrol positif:** canary `requests==2.31.0` → 3 CVE. Scanner terbukti bekerja, jadi
  angka 37 ini nyata, bukan hasil alat yang mati.
- Catatan metode: `trivy fs` langsung ke venv/site-packages memberi `0 targets` (Trivy
  tidak membaca `*.dist-info/METADATA`). Ekspor ke requirements.txt adalah jalur yang benar.

## Mengapa ini tidak saya perbaiki sendiri

Menaikkan paket di venv Hermes = mengubah runtime tempat SEMUA profil berjalan
(termasuk sesi ini). Itu bukan perubahan repo biasa: butuh restart, berpotensi
mengganggu 23 profil, dan berada di area "Red Line" (jangan hentikan/ubah layanan
yang sedang dipakai tanpa keputusan pemilik). Karena itu ini disajikan sebagai
**keputusan untuk Anda**, lengkap dengan data — bukan dikerjakan diam-diam.

## Pilihan

1. **Upgrade patch-level sekarang** (disarankan): PyJWT 2.14.0, pypdf 6.19.0,
   httpx2 2.12.0, httpcore2 2.10.0, tornado 6.5.9, urllib3 2.8.0. Semua perubahan minor —
   tidak ada lompatan major. Efek: PyJWT 2.13→2.14 bisa mengubah perilaku validasi token
   (ada advisory soal bypass validasi kunci), perlu uji cepat setelahnya.
2. **Tunda sampai jendela sepi** (mis. malam), lalu uji `hermes --version` + satu sesi
   singkat pasca-upgrade.
3. **Abaikan dengan alasan tercatat**: hanya sah bila Anda menilai paket-paket itu tidak
   pernah memproses input tidak tepercaya di lingkungan ini. Harus ditulis alasannya di
   registry supaya bukan risiko tak sadar.

Langkah yang saya sarankan (2 menit): pilih opsi 1 atau 2. Jika 1, saya jalankan
`pip install -U` untuk 6 paket itu di venv Hermes, lalu verifikasi `hermes --version`,
`hermes mcp list`, dan Trivy ulang untuk membuktikan advisory turun — semuanya dengan
output nyata, dan saya tidak akan mengubah paket apa pun tanpa perintah Anda.