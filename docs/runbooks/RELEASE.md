# Runbook — Menandai Rilis SDB

**Dipakai saat**: akan merilis versi untuk pelanggan/pilot. **Status hari ini**: belum ada tag (audit A-2).

## Prasyarat

1. `make check` hijau (lint + registry + 252+ tes + drift + hygiene).
2. `docs/adr/` memuat keputusan yang berubah pada rilis ini.
3. Tidak ada blocker komersial terbuka: lisensi root sudah ada (`LICENSE`), pack CC-BY-SA sudah dipisahkan.
4. Working tree bersih **untuk berkas yang dirilis** (artefak `runs/` boleh kotor selama belum diarsipkan).

## Langkah

```bash
cd ~/super-dev-builders
make check
git status --porcelain | grep -vE "^\?\? (runs|evidence|verification)/" | head

# 1) naikkan versi di pyproject.toml (semver: MAJOR.MINOR.PATCH)
# 2) changelog ringkas: bagian "## [x.y.z] — YYYY-MM-DD" di CHANGELOG.md
git add pyproject.toml CHANGELOG.md
git commit -m "chore(release): vX.Y.Z"

# 3) tag anotasi (wajib anotasi, bukan lightweight)
git tag -a vX.Y.Z -m "SDB vX.Y.Z — <ringkasan 1 baris>"
git tag --list "v*" --sort=-v:refname | head -3

# 4) verifikasi artefak rilis
git archive --format=tar.gz --prefix=sdb-X.Y.Z/ vX.Y.Z > /tmp/sdb-X.Y.Z.tar.gz
sha256sum /tmp/sdb-X.Y.Z.tar.gz | tee /tmp/sdb-X.Y.Z.sha256
```

## Rollback

```bash
# pelanggan kembali ke versi sebelumnya
git checkout vX.Y.(Z-1)
# atau, bila memakai pack: tukar pack_id di manifest, tanpa menyentuh git
```

## Larangan

- Jangan menandai rilis saat `make check` merah — sekecil apa pun yang merah.
- Jangan memindahkan tag yang sudah dipakai pelanggan; buat versi patch baru.
- Jangan merilis tanpa `CHANGELOG.md`; pelanggan berbayar butuh catatan perubahan.
