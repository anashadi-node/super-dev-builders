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
| `gate_check` target `elf-demo` (mode B, `authorization_type: owned`, `owner_operator` cocok) | **PASS** — keputusan Owner 2026-11-04: `owned` sah bila operator akun OS yang menjalankan gerbang sama dengan `owner_operator` di manifest |
| `gate_check` `owned` tanpa `owner_operator`, atau operator berbeda | **BLOCKED** — dua uji negatif (`test_mode_b_owned_tanpa_owner_operator_ditolak`, `test_mode_b_owned_operator_berbeda_ditolak`) memastikan `owned` bukan celah universal |
| `recon-forge recon --kind native --decompile` target `elf-demo` | **rc=0 ujung-ke-ujung** — 2 artefak: inspect 8.440 B + decompile-all 44.123 B, provider **Ghidra 12.1.4**, `verified: true` |

Artinya: jalur biner SDB **sudah terbukti bekerja ujung-ke-ujung** (gate → izin → REA → Ghidra
→ artefak terverifikasi). Jalur `owned` tidak melonggarkan gerbang: ia mengikat izin ke identitas
operator yang bisa diperiksa mesin, bukan ke prosa seperti "Mas Anas (pemilik)".

Pemakaian yang sah:

```bash
scripts/gate_check.py --target elf-demo                      # Gate #0
tools/recon-forge.py recon --target elf-demo --kind native \
  --path targets/elf-demo/demo --decompile --decompile-limit 10 --json
```

Bukti mentah: `evidence/elf-demo/rea/20261104T233108-inspect.json`,
`evidence/elf-demo/rea/20261104T233108-decompiled/`, `evidence/elf-demo/rea/manifest.json`.

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
