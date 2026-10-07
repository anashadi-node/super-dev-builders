# Temuan: 37 celah dependency di venv Hermes Agent — butuh KEPUTUSAN Anda

Tanggal audit: 2026-10-07 · Trivy 0.75.0 · Lokasi: `~/.hermes/hermes-agent/venv`
Hermes terpasang: v0.21.5+6718.g158fd63.dirty (upstream 158fd638)

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