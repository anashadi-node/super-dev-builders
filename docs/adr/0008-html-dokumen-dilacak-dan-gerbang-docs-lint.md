# ADR-0008 — Dokumen HTML boleh dilacak asal berdaftar; gerbang `docs_lint` menegakkannya

Status: diterima · 2026-11-04

## Konteks

`docs/INDEX.md` aturan 4 mewajibkan `.md` sebagai sumber dan melarang `.html`/`.pdf` hasil generate
disimpan di repo (ADR-0002). Kenyataannya repo berisi 9 berkas HTML dokumen dan 3 PDF yang semuanya
punya pasangan `.md`. Sebagian HTML itu **sengaja** dilacak: tutorial dan paket revisi dibaca
langsung dari repo tanpa build (lihat `Makefile` target `docs-tutorial`), sementara PDF-nya hanya
artefak kirim. Aturan prosa tanpa pemeriksaan membuat kedua hal ini tidak bisa dibedakan — dan audit
2026-11-04 menemukan tiga bentuk drift yang tidak pernah gagal di CI:

1. 10 dokumen `docs/*.md` tidak punya entri di `docs/INDEX.md` (aturan 3 dilanggar tanpa alarm).
2. 3 PDF hasil generate masih terlacak padahal sumber `.md`-nya ada.
3. README mengklaim "kini 39" skill sementara `registry/skills.yaml` berisi 40.

Akar masalahnya bukan disiplin penulis: tidak ada gerbang deterministik yang mengubah kebijakan
dokumen menjadi exit code. Kebijakan yang tidak bisa gagal sama dengan kebijakan yang tidak ada.

## Keputusan

1. **`scripts/docs_lint.py` menjadi gerbang** (`make docs-lint`, ikut `make check`). Memeriksa:
   setiap `docs/**/*.md` (kecuali `INDEX.md` dan `archive/`) terindeks — ADR lewat nomor `ADR-000N`;
   setiap rujukan berkas di indeks benar-benar ada (relatif `docs/` atau akar repo); tidak ada `.pdf`
   terlacak; tidak ada `.html` di `docs/`/`reports/` terlacak tanpa izin; klaim jumlah skill di
   README sama dengan registry; tautan repo resmi ada di README.
2. **HTML dokumen yang sengaja dilacak wajib berdaftar** di `platform/docs-html-allowlist.json`
   beserta alasan tertulis. Berkas baru tanpa entri → FAIL. Entri usang (berkasnya tak terlacak
   lagi) → WARN.
3. **PDF tidak dilacak, tanpa pengecualian.** PDF selalu bisa dibangun ulang dari `.md`; menyimpannya
   di git hanya menambah ukuran clone tanpa menambah informasi.
4. **Indeks adalah gerbang, bukan sopan santun.** Dokumen tanpa entri indeks kini menggagalkan
   `make check`, bukan sekadar "dianggap draf".

## Konsekuensi

- Menambah dokumen butuh dua baris: berkas `.md` + satu baris di `docs/INDEX.md`. Itu memang biaya
  yang diinginkan: satu tempat menemukan dokumen yang benar.
- `docs/00_MASTER_BLUEPRINT_V2.2.html` ikut allowlist meski tanpa `.md`: ia sumber kebenaran yang
  ditulis sebagai HTML, bukan hasil generate — alasan ini ditulis eksplisit di allowlist.
- Tiga PDF di-`git rm --cached` (tetap ada di disk). Riwayat git tidak ditulis ulang; klon baru tidak
  lagi membawa 3 berkas yang bisa dibangun ulang.
- Setiap dokumen baru wajib menyebut dirinya bisa diverifikasi: klaim angka di README kini diperiksa
  terhadap sumber angkanya (registry), bukan dipercaya.
