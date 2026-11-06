# Fixture DID — profil mobile & desktop

> Status 2026-11-06: dua fixture baru, benchmark 4/4 PASS, seluruh bukti dibuat oleh alat.

## Kenapa ada

`platform/did_profiles.json` mendaftar tujuh profil (`web`, `api`, `mobile`, `desktop`,
`binary`, `game`, `source`). Sebelum hari ini hanya dua yang pernah diukur: `web`
(`e1-app`) dan `binary` (`elf-demo`). Sisanya — termasuk mobile dan desktop — hanya
klaim di dokumen. Dokumen ini menutup celah itu dengan artefak yang bisa diperiksa.

## Batas jujur (baca sebelum mengutip angka)

- Mesin ini **tidak punya JDK, JADX, apktool, MobSF, atau Ghidra**. Fixture mobile
  memakai `AndroidManifest.xml` **teks** dan **tanpa `classes.dex`**. Yang diuji adalah
  disiplin inventaris + bukti + handoff, **bukan** decompile DEX.
- Fixture desktop adalah ELF x86-64 hasil `gcc`; tidak ada toolkit GUI, tidak ada
  paket MSI/dmg, dan tidak ada auto-update yang benar-benar berjalan.
- Label dan handoff ditulis orang yang sama. Skor 1,000 berarti **cakupan dan
  kejujuran rujukan** terukur, bukan bahwa investigasi ini independen dari penulisnya.

## Artefak

| Target | Artefak | Ukuran | sha256 (16) |
|---|---|---|---|
| `android-mini` | `fixtures/android-mini/artifact/android-mini.apk` | 3.308 B | `eb0e943b55fc5a14` |
| `desktop-mini` | `fixtures/desktop-mini/artifact/desktop-mini` | 18.688 B | `6853475d2f5f8540` |

Keduanya dibangun dari sumber yang ikut git:

```
make fixtures          # bangun dari fixtures/*/src
make fixtures-verify   # bangun ulang di tmp, bandingkan hash
```

Build deterministik: `SOURCE_DATE_EPOCH` tetap, timestamp zip dipaku
(2026-11-06 09:00), `-Wl,--build-id=none`, dan `-ffile-prefix-map` agar path build
tidak bocor ke debug info. Dua kali build → hash identik.

## Hasil investigasi

### `android-mini` (profil mobile, L3)

8 temuan OBSERVED, 10 fitur, 6/6 kategori COVERED, 2 unknown non-blocking.

Temuan yang paling berguna: **APK memuat berkas sumber C di dalam folder `jni`** — sumber ikut terkirim di
dalam paket (kebocoran sumber), dan **tidak ada berkas `classes.dex`** (konsekuensi fixture,
dinyatakan terbuka, bukan disembunyikan).

### `desktop-mini` (profil desktop, L3)

8 temuan OBSERVED, 8 fitur, 6/6 kategori COVERED, 2 unknown non-blocking.

Temuan kunci: URL update `https://updates.mini.example/v1/desktop`, kanal `stable`
dengan `poll_seconds` 3600, IPC `/tmp/mini-desktop.sock`, state
`~/.local/share/mini-desktop/mini.db`, installer idempoten (`cmp` sebelum salin), dan
`main` yang memanggil `puts` + dua `__printf_chk`. Eksekusi nyata mencetak
`mini-desktop 1.4.2` dan exit 0.

## Angka benchmark

```
target          status        P      R     F1  extras halusinasi
android-mini   PASS      1.000  1.000  1.000       0          0
desktop-mini   PASS      1.000  1.000  1.000       0          0
e1-app         PASS      0.909  1.000  0.952       1          0
elf-demo       PASS      1.000  1.000  1.000       0          0
ambang: recall >= 0.9, presisi >= 0.9, halusinasi = 0 | gagal 0/4
```

Dijalankan otomatis di CI (`make did-suite`), jadi penurunan recall atau munculnya
klaim tanpa bukti akan menolak PR.

## Yang belum terukur

Profil `api`, `game`, dan `source` masih tanpa benchmark. Klaim "DID mendukung tujuh
profil" tetap **belum teruji** untuk ketiganya — jangan dikutip seolah sudah.
