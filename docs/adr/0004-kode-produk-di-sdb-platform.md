# ADR-0004 — Kode produk di `sdb_platform/`, kontrak di `platform/`

Status: diterima · 2026-10-29

## Konteks

Rancangan awal menempatkan control plane di `platform/control_plane/`. Saat impor pertama,
`import platform.control_plane` gagal: `platform` adalah modul standar Python (`sys.platform`, dsb).
Menamai paket sama dengan modul stdlib membuat impor bergantung urutan `sys.path` — rapuh dan bisa
menutupi modul stdlib pada runtime lain. Percobaan kedua memakai nama `sdb` juga gagal saat pytest
menjalankan `tests` + `skills` bersamaan: `scripts/` masuk ke `sys.path`, dan `scripts/sdb.py`
(CLI satu pintu, sudah dipakai) menutupi paket `sdb` sehingga muncul "sdb is not a package".

## Keputusan

- **Kode Python produk** tinggal di paket `sdb_platform/` (`sdb_platform/control_plane/…`).
- **Kontrak & artefak** (schema JSON, pack manifest, baseline higiene) tetap di `platform/`.
- Tidak ada `__init__.py` di `platform/`, sehingga direktori itu tidak pernah menjadi paket Python.

## Konsekuensi

- Impor selalu eksplisit: `from sdb_platform.control_plane.store import Store`.
- `docs/PETA_STRUKTUR.md` memakai aturan: *kode yang dieksekusi → `sdb_platform/` atau `scripts/`; data yang
  dibaca mesin → `platform/`*.
- CLI tetap di `scripts/sdb.py` (nama itu sudah dipakai shim `~/.local/bin/sdb`); nama paket Python
tidak boleh bertabrakan dengannya.
- Jika kelak butuh distribusi paket, `pyproject.toml` mendaftarkan `sdb_platform*` saja.
