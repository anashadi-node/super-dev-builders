# Jalur Biner — `recon-forge recon --kind native`

Dokumen ini menjelaskan bagaimana SDB menangani target **non-web**: ELF/PE/Mach-O, folder
aplikasi, APK/IPA, dan firmware. Jalur web dibahas di `WORKFLOW_SKENARIO.md`.

## Kapan jalur ini dipakai

| Target | Perintah |
|---|---|
| Satu biner ELF/PE/Mach-O | `recon --kind native --path <biner>` |
| Folder aplikasi (mis. hasil ekstrak APK) | `recon --kind native --path <folder>` |
| Ingin pseudocode fungsi teratas | tambahkan `--decompile --decompile-limit 20` |

Semua jalur tetap melewati **Gate #0**. Tidak ada mode "coba-coba tanpa izin".

## Dua tingkat izin, dan kenapa penting

`evidence/<target>/authorization.yaml` punya dua saklar yang tidak boleh tertukar:

| Saklar | Arti | Akibat pada jalur biner |
|---|---|---|
| `allowed_targets.apk_ipa_binaries` | berkas apa yang boleh **disentuh** | di luar daftar ini → ditolak sebelum apa pun dijalankan |
| `deep_analysis_allowed` | boleh **membedah** (provider decompiler) | `false` → jalur biner ditolak walau gate PASS |

`mode: A` selalu `deep_analysis_allowed: false`. Artinya target mode A **tidak** bisa
dianalisis binernya — gate-nya boleh PASS (itu soal URL dan akun), tapi membedah biner
butuh izin tertulis (mode B, `authorization_type: written_permission`).

Pemeriksaan `deep_analysis_allowed` ada di `_recon_native`, bukan di `gate_check`, karena
gate hanya tahu URL/akun. Sebelum pemeriksaan ini ditambahkan, `recon --kind native` pada
target mode A **lolos gate lalu memanggil Ghidra** — gate berkata PASS, izin dilanggar.
Itu sebabnya ada uji `test_native_target_mode_a_ditolak`.

## Status uji nyata (jujur, per 2026-11-04)

Biner uji: `targets/elf-demo/demo` — 16 KB, kompilasi sendiri dari `demo.c` (`file`:
ELF 64-bit PIE, x86-64, not stripped).

| Yang diuji | Hasil |
|---|---|
| `rea inspect` pada biner itu | **rc=0**, provider **Ghidra 12.1.4** benar-benar jalan: `evidence_id ev_cd0ecd1d…`, sha256 subjek `b3b9184e…`, format `elf`, arsitektur `x86_64` |
| `recon-forge recon --kind native` pada target mode A (`sdb-local-demo`) | **rc=2 ditolak** — pesan "tidak mengizinkan analisis mendalam" (uji `test_native_target_mode_a_ditolak`) |
| `gate_check` target `elf-demo` (mode B, `authorization_type: owned`) | **BLOCKED** — "mode B wajib authorization_type=written_permission" |

Artinya: rantai provider terbukti hidup, penolakan terbukti bekerja, tapi **jalur biner SDB
belum pernah berhasil ujung-ke-ujung** karena gate menuntut izin tertulis untuk mode B,
sementara artefak ini milik sendiri (`owned`). Ini keputusan Owner, bukan sesuatu yang boleh
dilonggarkan sendiri oleh alat: mengubah `gate_check` agar menerima `owned` = mengubah gerbang
keamanan.

Sampai keputusan itu ada, pemakaian yang sah:

```bash
scripts/rea inspect targets/elf-demo/demo --format json     # observasi, bukan gate SDB
```

Bukti mentah: `evidence/elf-demo/rea-inspect.json`.

## Jebakan yang sudah ditemui

1. **`rea doctor` bilang `healthy=false` padahal semua yang dipakai SDB siap.** REA tanpa
   scope menuntut registrasi klien + skill identity, yang opsional bagi SDB. `recon-forge
   doctor` sekarang melaporkan `sehat=` (kebutuhan SDB) dan memisahkan `healthy-lengkap`
   beserta daftar celah opsional — supaya tidak ada dua verdict yang saling bertentangan.
2. **Ghidra butuh lingkungan tertentu.** `scripts/rea` menyetel `GHIDRA_INSTALL_DIR`,
   `JAVA_HOME`, dan `PATH`; memanggil REA langsung dari shell lain bisa melaporkan Ghidra
   hilang padahal ada. Selalu lewat wrapper.
3. **Biner pihak ketiga bukan target latihan.** `targets/elf-demo` hanya berisi biner yang
   kita kompilasi sendiri. Menaruh biner unduhan di sana = memperluas izin tanpa keputusan.
