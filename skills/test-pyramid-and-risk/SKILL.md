---
name: test-pyramid-and-risk
description: "Choose test level by risk, not habit"
version: 1.0.0
author: Super Dev Builders Ecosystem
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [testing, test-pyramid, risk, e2e, unit, contract]
    divisions: [D7, D5]
    related_skills: [reconstruction-fidelity, engineering-release-audit, accessibility-audit]
---


# Test Pyramid & Risk

Memilih tingkat pengujian berdasarkan **risiko dan biaya**, bukan kebiasaan.

## Pemetaan level -> penggunaan
| Level | Dipakai untuk | Biaya | Wajib bila |
|---|---|---|---|
| Unit | logika murni, kalkulasi, parser, aturan bisnis | rendah | selalu, untuk fungsi berlogika |
| Component | UI komponen + state/interaksi lokal | rendah-sedang | UI dengan state kompleks |
| Contract | batas API/schema, integrasi antar modul | sedang | ada konsumen/layanan lain |
| Integration | DB/queue/IO nyata/terkontainer | sedang-tinggi | ada efek samping nyata |
| E2E | journey pengguna kritis | tinggi | jalur uang/otentikasi/data penting |
| Performance | ambang latensi/throughput | tinggi | ada target kinerja |

## Prosedur
1. Daftar jalur kritis + kelas risiko (LOW/MEDIUM/HIGH/CRITICAL).
2. Untuk setiap jalur: tentukan level minimum yang membuktikan perilaku, lalu tulis test **sebelum** memperbaiki/menambah.
3. Untuk bug: tulis test reproduksi yang GAGAL dulu, lalu perbaiki sampai PASS (bukti regresi nyata).
4. Jalankan suite lengkap sebelum menyerahkan; tempel output fresh (perintah + hasil + timestamp).

## Aturan
- Jangan menulis E2E untuk semua hal: lambat, rapuh, mahal.
- Jangan menghapus/melemahkan test agar hijau — itu pelanggaran rilis.
- Test harus deterministik: tanpa dependensi jaringan eksternal tanpa mock/stub yang eksplisit.
- Coverage angka bukan tujuan; tutup risiko nyata (jalur uang, auth, data loss, migrasi).

## Output
- `tests/` + `logs/tests-<timestamp>.log` + `reports/test-report.md` (level, cakupan risiko, kegagalan terbuka).
