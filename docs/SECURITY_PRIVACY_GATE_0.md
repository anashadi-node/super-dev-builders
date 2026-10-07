# Security & Privacy Gate #0

Migrasi dari V1 + penyesuaian V2.2. Gate ini wajib **sebelum** aksi apa pun: membuka target, clone repo,
install dependency, capture network, rebuild, test, deploy.

Implementasi deterministik: `python3 scripts/gate_check.py <name>` (membaca `evidence/<target>/authorization.yaml`; bentuk lama `--target <name>` tetap didukung).

## 0. Otorisasi (salah satu wajib benar)
- Milik user/perusahaan sendiri.
- Open-source dengan lisensi jelas.
- Staging/test environment yang diotorisasi.
- Pihak ketiga dengan izin tertulis + scope jelas (`authorization_type: written_permission` + `license_or_permission_ref`).
Tidak jelas => **STOP** dan minta otorisasi.

## 1. Scope wajib didefinisikan
URL/app/repo yang boleh diakses; akun test yang boleh dipakai; data yang boleh/tidak boleh direkam;
route/screen out-of-scope; apakah network capture diizinkan; durasi/retensi.

## 2. Prohibited actions
Bypass login/auth, CAPTCHA, bot protection, DRM, payment, license, certificate pinning, root/jailbreak check;
token/session replay; brute-force endpoint tersembunyi; ekstraksi source/backend/database privat;
menyimpan cookie/session/token/API key dalam evidence; deploy downloader/crawler publik tanpa sandbox+rate limit+allowlist.

## 3. Repo/link intake gate
Cek lisensi; cek status arsip/maintenance; cek audit dependency; tidak menjalankan install script tanpa review;
tidak mengeksekusi sebelum keputusan sandbox; tandai tautan one-click deploy sebagai risiko operasional tinggi.

## 4. Network safety
Capture worker wajib: blokir localhost/private IP/link-local/cloud metadata; resolve DNS sebelum fetch dan
tahan DNS rebinding; berjalan dalam container tanpa secret dan tanpa rute LAN bila memungkinkan;
allowlist per target; timeout/quota/concurrency.

## 5. Evidence privacy
Redaksi cookie, auth header, token, email/telepon bila tidak diperlukan, data pembayaran, data personal.
Hash/deduplikasi aset berdasarkan content hash. Simpan provenance. Tandai `INFERRED` bila bukan observasi langsung.

## 6. Hasil gate
- **PASS** — lanjut.
- **FAIL** — berhenti, perbaiki.
- **BLOCKED** — butuh keputusan manusia/isolasi environment; berhenti dan tanya.

## 7. Kaitan dengan gate lain
Gate #0 bukan pengganti security scan (D8) maupun release audit (D9). Gate #0 = izin masuk;
D8/D9 = verifikasi mutu dan risiko sebelum rilis.
