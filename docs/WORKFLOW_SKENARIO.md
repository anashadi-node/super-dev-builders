# Workflow SDB untuk Semua Skenario

Dokumen ini menjawab satu pertanyaan: **"saya punya X (contoh situs / PRD / ide di kepala / kode
lama / ide game), bagaimana alurnya di SDB?"**

Semua skenario di bawah berjalan di atas **satu** mesin yang sama: 16 tahap workflow dengan Gate #0
(authorization/scope) di depan. Yang berbeda antar-skenario bukan mesinnya, melainkan **titik masuk**
dan **tahap mana yang boleh dipangkas**.

> Verifikasi fakta: `sdb workflow --list-stages` (18 baris: 01, 01A, 01B, 02–16).
> Runner memeriksa **keberadaan artefak**, bukan menilai kualitas. `MISSING` = belum dikerjakan.

---

## Daftar Isi

{{TOC}}

---

## 1. Peta mesin: 16 tahap (berlaku untuk semua skenario)

```text
01    USER OBJECTIVE                  tujuan terukur + definisi selesai
01A   AUTHORIZATION/SCOPE GATE        gate_check.py  ← WAJIB, tidak bisa dilewati
01B   RECON/EVIDENCE PACKAGE          bukti apa yang boleh dipakai
02    ORCHESTRATOR: KLARIFIKASI       pertanyaan sampai ambigu hilang
03    RESEARCH                        hanya bila ada ketidakpastian teknis nyata
04    ARCHITECTURE + ADR              keputusan + alasannya, tertulis
05    HUMAN DESIGN APPROVAL           Anda menyetujui desain
06    IMPLEMENTATION PLAN             urutan kerja, berkas yang disentuh
07    IMPLEMENTASI (FE/BE)            kode
08    CODE REVIEW                     diff dibaca, bukan dipercaya
09    QA / INTEGRATION / E2E          tes nyata, output nyata
10    SECURITY (SAST/DEP/SECRET)      semgrep/gitleaks/dependency
11    CODE AUDIT & ASSURANCE          audit menyeluruh
12    RELEASE GATE                    release_check.py  ← WAJIB sebelum deploy
13    HUMAN APPROVAL PRODUKSI         Anda menyetujui rilis
14    DEVOPS DEPLOY                   satu layanan sekaligus
15    OBSERVABILITY/SMOKE/ROLLBACK    bukti pasca-deploy
16    DOCS + HANDOVER                 dokumen yang bisa dibaca orang lain
```

Dua tahap punya alat deterministik: **01A** (`gate_check.py`) dan **12** (`release_check.py`).
Sisanya dijalankan agen + Anda. Itu batasan yang diketahui — bukan klaim otomatis penuh.

### Aturan yang tidak berubah di semua skenario

| Aturan | Konsekuensi bila dilanggar |
|---|---|
| Gate #0 PASS sebelum recon/scan | runner menolak; tidak ada evidence package |
| Tidak ada kredensial/PII di evidence | `evidence_lint.py` FAIL, paket tidak sah |
| Tidak ada klaim "selesai" tanpa artefak | tahap tetap `MISSING` |
| Deploy butuh persetujuan Anda | tahap 13 tidak bertanda tangan |
| Satu perubahan → satu verifikasi | rollback tidak mungkin dilacak |

---

## 2. Skenario A — Anda punya contoh: copy-clone / reverse engineering situs, SaaS, atau aplikasi

Ini skenario **paling berisiko** dan paling sering disalahpahami. SDB tidak "menyalin" situs orang
lain; SDB merekonstruksi **perilaku yang Anda berhak pelajari**, dengan batas yang Anda tulis
sendiri di `authorization.yaml`.

### A.1 Kapan ini boleh

| Kondisi | Contoh sah | Contoh TIDAK sah |
|---|---|---|
| Milik Anda sendiri | situs lama Anda, kode warisan | — |
| Lisensi mengizinkan | MIT/Apache, konten CC | repo tanpa lisensi + klaim "bebas" |
| Anda punya izin tertulis | kontrak kerja, NDA | "kata orang boleh" |
| Publik & hanya untuk belajar pola | membaca struktur halaman publik | menyalin aset berhak cipta |

### A.2 Alur (yang membedakan dari skenario lain: tahap 01B berat)

```
01   Tujuan: "rekonstruksi alur checkout X untuk dipelajari" (bukan "clone X")
01A  authorization.yaml → gate_check.py  ← PASS wajib
01B  capture terkendali: struktur halaman, alur navigasi, kontrak API yang terlihat
     → normalize_capture.py → evidence_lint.py (kredensial otomatis [REDACTED])
02   Klarifikasi: bagian mana yang direkonstruksi, bagian mana yang TIDAK
03   Research: pola alternatif yang lebih baik (jangan menyalin cacat desain)
04   ADR: keputusan teknologi Anda sendiri, bukan warisan target
05–09 desain → implementasi → review → QA
10–11 SAST, dependency, secret scan, audit
12   release_check.py
13–16 deploy (bila perlu) → smoke → dokumen
```

### A.3 Perintah nyata

```bash
cd ~/super-dev-builders

# 1) siapkan target + authorization
sdb init nama-target            # atau: make init TARGET=nama-target
$EDITOR targets/nama-target/authorization.yaml   # isi dasar hukum, cakupan, larangan

# 2) Gate #0 — tanpa PASS, jangan lanjut
sdb gate nama-target            # atau: python3 scripts/gate_check.py targets/nama-target

# 3) baru boleh capture/recon (terkendali, tanpa bypass)
sdb capture nama-target --url https://contoh.tld/halaman-publik
python3 scripts/evidence_lint.py targets/nama-target

# 4) jalankan sisa tahap
sdb workflow nama-target
```

### A.4 Yang **tidak** dilakukan SDB (dan tidak akan)

- Melewati login/CAPTCHA/paywall/DRM/pinning.
- Menyimpan cookie/token/PII ke evidence — `evidence_lint.py` memaksa `[REDACTED]`.
- Menyalin aset berhak cipta ke produk Anda.
- Menyalin kode tanpa lisensi lalu mengganti nama variabel.

Kalau tujuan Anda "supaya fitur sama", jalur yang benar adalah **memahami pola lalu
mengimplementasikan ulang** — itu tetap sah, dan itu yang diukur `fidelity_compare.py`
(kesamaan perilaku, bukan kesamaan kode).

### A.5 Hasil yang bisa Anda harapkan

- `targets/nama-target/evidence/` — paket bukti bersih, bisa diaudit.
- `fidelity_report` — dimensi apa yang cocok/berbeda dari target (bukan "clone 100%").
- ADR yang menjelaskan **mengapa** implementasi Anda berbeda dari target.

---

## 3. Skenario B — Anda sudah punya PRD

Ini skenario **tercepat** karena tahap 01–02 sudah 80% selesai di dokumen Anda. Yang perlu
dilakukan: mengubah PRD menjadi artefak yang bisa diperiksa mesin.

### B.1 Yang harus ada di PRD agar lancar

| Bagian PRD | Dipakai di tahap | Bila tidak ada |
|---|---|---|
| Tujuan + metrik sukses | 01 | tahap 01 `MISSING`, agen menebak — jangan |
| Daftar fitur + prioritas (MoSCoW) | 02, 06 | plan jadi acak |
| Persona/aktor + hak akses | 02, 04, 10 | kontrol akses bolong |
| Alur utama + alur gagal | 02, 09 | QA tidak punya skenario negatif |
| Non-fungsional (perf, privasi, skala) | 04, 12 | release gate tidak bisa menilai |
| Di luar cakupan (eksplisit) | 01A | scope creep tak terdeteksi |

### B.2 Alur

```
01   salin tujuan + metrik dari PRD ke objectives.md
01A  authorization.yaml: "ini produk saya, tidak ada pihak ketiga" → gate PASS
01B  evidence = PRD + wireframe + referensi (bukan scan target)
02   klien (Anda) mengonfirmasi hal yang PRD-nya masih ambigu ← jangan dilewati
03   research hanya untuk bagian yang PRD-nya menyebut teknologi belum dikenal
04   ADR dari keputusan yang PRD sudah tetapkan + yang PRD serahkan ke tim
05   Anda menyetujui desain (ini titik koreksi termurah)
06   plan per fitur, dipetakan ke acceptance criteria PRD
07–09 implementasi → review → QA terhadap acceptance criteria (bukan "kira-kira jalan")
10–11 security + audit
12   release gate: acceptance criteria PRD = daftar periksa
13–16 deploy → smoke → handover
```

### B.3 Perintah nyata

```bash
sdb init produk-baru
# taruh PRD sebagai artefak tahap 01/01B
cp ~/Dokumen/PRD-produk-baru.md targets/produk-baru/objectives.md
$EDITOR targets/produk-baru/authorization.yaml
sdb gate produk-baru
sdb workflow produk-baru
```

### B.4 Kesalahan umum (dan akibatnya)

| Kesalahan | Akibat |
|---|---|
| PRD tanpa metrik | tidak ada cara membuktikan "selesai" |
| PRD tanpa "di luar cakupan" | pekerjaan membengkak tanpa persetujuan |
| Langsung ke tahap 07 | desain tidak pernah disetujui → mahal saat revisi |
| Acceptance criteria tidak dipetakan | QA lulus, produk tidak sesuai PRD |

---

## 4. Skenario C — Anda hanya chat: "saya mau bikin X, targetnya Y"

Ini skenario **paling umum** dan paling rawan **SLOP**: ide masih kabur, agen cenderung mengarang
kebutuhan. SDB menanganinya dengan **memaksa tahap 02 (klarifikasi)** sebelum satu baris kode.

### C.1 Alur

```
01   tulis tujuan dalam satu kalimat + definisi selesai yang bisa diukur
01A  authorization.yaml (biasanya: produk milik Anda, tanpa target pihak ketiga)
02   ORCHESTRATOR bertanya — minimal: aktor, alur utama, data, skala, batas waktu,
     apa yang TIDAK dikerjakan
03   research bila Anda menyebut teknologi yang belum dipakai tim
04   arsitektur + ADR (pilihan teknologi + alasan)
05   Anda menyetujui desain ← gerbang termurah untuk mengubah arah
06   plan
07–16 seperti biasa
```

### C.2 Contoh percakapan yang benar (dan yang salah)

**Salah** — melompat ke kode:

> Anda: "buatkan SaaS invoice"
> Agen: *langsung menulis 40 berkas*

**Benar** — klarifikasi dulu, baru kode:

> Anda: "Saya mau SaaS invoice sederhana untuk freelancer Indonesia. Target: 10 pengguna aktif
> pertama dalam 30 hari, satu orang bisa menerbitkan invoice dan kliennya membayar via transfer
> manual (belum payment gateway)."
>
> Agen (tahap 02): "Lima hal perlu dipastikan: (1) multi-tenant atau satu akun? (2) mata uang IDR
> saja? (3) invoice berulang perlu? (4) pajak/PPN dihitung? (5) siapa yang boleh melihat invoice —
> hanya pemilik atau klien juga lewat tautan?"
>
> Anda menjawab → **baru** tahap 04–07 berjalan dengan asumsi tertulis.

### C.3 Perintah nyata

```bash
sdb init saas-invoice
$EDITOR targets/saas-invoice/objectives.md     # tujuan + metrik + definisi selesai
$EDITOR targets/saas-invoice/authorization.yaml
sdb gate saas-invoice
sdb workflow saas-invoice
```

### C.4 Tanda agen sedang "slop" (hentikan)

- Menulis kode sebelum Anda menyetujui desain.
- Mengarang angka pasar ("pasti laku") tanpa sumber.
- Menambah fitur yang tidak Anda minta "untuk nanti".
- Menyatakan "selesai" tanpa tes yang dijalankan.

---

## 5. Skenario lain (lengkap)

### 5.1 Game (2D/3D, web atau desktop)

Titik masuk: **Game Design Document** berperan seperti PRD, tetapi ada tahap tambahan yang tidak
ada di web: **loop inti**, **keseimbangan**, dan **aset**.

```
01   tujuan: "game X, platform Y, durasi sesi Z menit, metrik retensi"
01A  authorization: aset sendiri / lisensi aset jelas ← sering dilupakan di game
01B  evidence: GDD, referensi mekanik (bukan aset orang)
02   klarifikasi: loop inti, kontrol, progres, monetisasi (bila ada)
03   research: engine + pola (bukan menyalin level orang)
04   ADR: engine, arsitektur state, pipeline aset
05   approval desain
06   plan per milestone (vertical slice dulu — jangan seluruh game)
07   implementasi loop inti → playable
09   QA: feel, kontrol, performa frame, crash
10–16 seperti biasa (build, distribusi, telemetri)
```

Aturan khusus game: **jangan** menilai kualitas dari daftar fitur; nilai dari **vertical slice yang
bisa dimainkan**. Tahap 09 harus menghasilkan rekaman sesi, bukan "sudah dicoba".

### 5.2 Aplikasi mobile (Android/iOS)

Sama seperti web, dengan tambahan yang wajib ada di tahap 02/04/10:

- Izin OS yang benar-benar dipakai (kamera, lokasi, notifikasi) — lebih sedikit lebih baik.
- Strategi penyimpanan lokal + sinkronisasi konflik.
- Rilis: signing key, kebijakan privasi toko, jalur rollback (versi lama tetap bisa dipasang).
- QA di perangkat nyata, bukan hanya emulator.

### 5.3 Program/CLI/otomasi (bukan web)

Skenario paling ringan; banyak tahap bisa dipangkas **dengan alasan tertulis**:

```
01, 01A, 02 (wajib) → 04 (bila >1 modul) → 06 → 07 → 08 → 09 (tes CLI nyata)
10 (dependency + secret) → 12 → 16 (README pemakaian)
```

Yang tidak boleh dipangkas: 01A, 09 (tes benar-benar dijalankan), 10 (secret scan).

### 5.4 Data pipeline / laporan / analitik

Tambahan wajib: definisi sumber data, kepemilikan data, retensi, dan **cara memverifikasi angka**.
Tahap 09 harus membandingkan keluaran dengan hitungan manual pada sampel. Tanpa itu, laporan
"terlihat benar" tetapi tidak bisa dipertanggungjawabkan.

### 5.5 Maintenance / refactor kode yang sudah ada

Titik masuk bukan tahap 01, melainkan **01B (baseline)**: potret perilaku sekarang sebelum diubah.

```
01B  baseline: tes yang ada dijalankan, keluaran direkam (bukti "sebelum")
07   perubahan sekecil mungkin (surgical)
09   tes yang sama dijalankan → bandingkan dengan baseline
12   release gate: tidak ada regresi
```

Aturan: refactor tanpa baseline = tidak bisa membuktikan tidak ada yang rusak.

### 5.6 Audit keamanan / review kode pihak lain

Tahap 01B adalah inti; 07–09 biasanya tidak ada. Keluaran: temuan + tingkat keyakinan + bukti
reproduksi (bukan opini). Setiap temuan wajib punya langkah reproduksi, jika tidak → turunkan ke
"kecurigaan".

### 5.7 Menjalankan produk yang sudah ada (operasional harian)

Ini bukan pembuatan, tetapi punya alur sendiri: `sdb-health` → log → metrik → insiden → postmortem.
Aturan: satu perubahan per insiden, dan postmortem tanpa menyalahkan orang.

---

## 6. Tabel pemetaan: skenario → tahap yang dipangkas

| Skenario | Titik masuk | Dipangkas (dengan alasan) | Tidak boleh dipangkas |
|---|---|---|---|
| A. Clone/RE | 01A + 01B berat | 07 bila hanya analisis | 01A, 01B (bukti bersih), 10 |
| B. PRD jadi | 01 (salin dari PRD) | 03 bila teknologi sudah dikenal | 02 (konfirmasi ambiguitas), 05, 09, 12 |
| C. Chat ide | 01 + 02 berat | 01B ringan (tanpa target pihak ketiga) | 02, 05, 09 |
| Game | GDD sebagai 01/01B | 03 bila engine sudah dipilih | 02 (loop inti), 09 (playable), 10 |
| Mobile | 01 + 01B | 03 bila stack dikenal | 02 (izin OS), 09 (perangkat nyata), 10 |
| CLI/otomasi | 01 | 04, 05, 06, 11, 13–15 | 01A, 09, 10 |
| Data/laporan | 01 + 01B | 05, 07 sebagian | 09 (verifikasi angka), 10 |
| Refactor | 01B (baseline) | 03, 04 sebagian | 01B, 09 (bandingkan), 12 |
| Audit | 01B | 06–09 | 01B, 10, 11 |
| Operasional | — | semua tahap bangun | 15 (smoke/rollback) |

---

## 7. Kesalahan lintas-skenario (semua ini pernah merusak proyek nyata)

| Kesalahan | Kenapa fatal | Pencegahan |
|---|---|---|
| Melewati Gate #0 "karena buru-buru" | seluruh pekerjaan tidak sah, tak bisa diaudit | `sdb gate` dijalankan sebelum capture apa pun |
| Evidence berisi token/cookie | kebocoran kredensial permanen | `evidence_lint.py` wajib, `[REDACTED]` |
| "Selesai" tanpa tes dijalankan | klaim palsu | tahap 09 hanya hijau bila ada keluaran nyata |
| Deploy semua layanan sekaligus | rollback tidak terarah | satu layanan per deploy |
| Menilai dari daftar fitur | produk terlihat lengkap, tak terpakai | nilai dari alur ujung-ke-ujung |
| Desain tidak disetujui lalu dikodekan | revisi termahal | tahap 05 selalu dijalankan |

---

## 8. Ringkasan satu halaman

1. Semua skenario memakai mesin 16 tahap yang sama; yang berubah hanya titik masuk.
2. **Gate #0 tidak pernah dipangkas** — ia yang membuat pekerjaan Anda sah.
3. Skenario clone/RE: izin tertulis dulu, bukti bersih, lalu rekonstruksi perilaku (bukan salin aset).
4. Skenario PRD: paling cepat, asalkan PRD punya metrik + cakupan eksplisit.
5. Skenario chat: klarifikasi dulu; kode setelah desain Anda setujui.
6. Game/mobile/data punya tambahan wajib (loop inti, izin OS, verifikasi angka).
7. "Selesai" = ada artefak + tes dijalankan + Anda menyetujui.

---

*Bagian dari ekosistem SDB v0.7.3. Bila perilaku sistem berbeda dari dokumen ini, yang benar adalah
kode dan tesnya — laporkan selisihnya.*
