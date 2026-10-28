# Runbook — membersihkan artefak dari riwayat git

**Sifat: destruktif.** Menulis ulang seluruh SHA, menghapus remote tracking, tidak bisa dibatalkan
tanpa backup. Jalankan hanya dengan persetujuan Owner.

## Kapan perlu

Repo membengkak karena artefak hasil kerja (`runs/`, `evidence/`, `verification/`, `normalized/`,
`reconstruction/`) pernah di-commit. Setelah ADR-0002, artefak baru tidak masuk git — runbook ini
hanya untuk **utang lama**.

## Prasyarat

- working tree bersih (`git status --porcelain` kosong);
- `git-filter-repo` terpasang (`python3 -m pip install --user git-filter-repo`);
- ruang disk ≥ 3× ukuran `.git` untuk backup;
- daftar path yang akan dihapus **sudah diverifikasi** berisi artefak saja, bukan kode.

## Prosedur (yang dipakai 2026-10-29)

```bash
D=~/sdb-archive/pre-purge-$(date +%Y%m%d) ; mkdir -p "$D"
git rev-list --all > "$D/pre_shas.txt"
git for-each-ref --format='%(refname) %(objectname)' > "$D/pre_refs.txt"
git ls-tree -r HEAD | grep -vE $'\t(runs|evidence|verification|normalized|reconstruction)/' > "$D/tree_before.txt"
git clone --mirror . "$D/git-mirror.git"          # backup penuh
git bundle create "$D/sdb-pre-purge.bundle" --all # backup portabel
cp --parents runs/INDEX.md evidence/INDEX.md "$D/index_backup/"   # INDEX akan ikut terhapus

git filter-repo --force --invert-paths \
  --path runs --path evidence --path verification --path normalized --path reconstruction

# pulihkan indeks (berisi daftar arsip, bukan artefak)
cp -r "$D/index_backup/runs" "$D/index_backup/evidence" .
git add -f runs/INDEX.md evidence/INDEX.md && git commit -m "docs(artefak): pulihkan indeks setelah pembersihan riwayat"
```

## Verifikasi wajib setelah rewrite

| Cek | Perintah | Lulus jika |
|---|---|---|
| objek artefak hilang | `git rev-list --objects --all \| grep -cE $' (runs\|evidence\|verification\|normalized\|reconstruction)/'` | `0` |
| isi lain tidak berubah | `diff <(git ls-tree -r HEAD \| grep -v artefak) tree_before.txt` | kosong |
| tag masih ada | `git tag --list` | sama seperti sebelum |
| tes tetap hijau | `make check` | RC=0 |
| ukuran turun | `du -sh .git` | jauh lebih kecil |

## Setelah itu

- `filter-repo` **menghapus remote `origin`**. Tambahkan kembali bila perlu, tetapi **jangan push**
  sebelum semua clone lain dianggap usang: `git push --force` ke remote bersama akan memutus riwayat
  semua kolaborator.
- Setiap clone lama masih memuat artefak; minta re-clone, bukan `git pull`.
- Catat hasil (ukuran sebelum/sesudah, jumlah commit, SHA baru) di luar repo.
