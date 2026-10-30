# SPEC — e1-app (clean-room reconstruction)

Target: fixture `e1-app` (kelas A, milik sendiri). Sumber: observasi HTTP buta
`evidence/e1-app/observations.json` (16 observasi, E1–E16).
Label tiap butir: `observasi` (terlihat langsung), `inferensi` (disimpulkan dari
pola), `tidak-diketahui` (butuh uji tambahan). Tidak ada kode atau string sumber
target di dokumen ini.

Tanggal: 2026-10-30. Penulis: D3 (dari bukti D1). Pembaca: D4/D5.

## 1. Model data

- Entitas `item` memiliki tiga medan: `id` (bilangan bulat, unik, naik), `name`
  (teks), `completed` (boolean). [E6 · observasi]
- Daftar awal berisi tiga item dengan id 1, 2, 3. [E2 · observasi]
- `completed` bernilai boolean JSON (`false`/`true`), bukan string. [E13 · observasi]

## 2. Endpoint baca

| ID | Permintaan | Perilaku teramati | Label |
|---|---|---|---|
| F01 | GET /health | 200, badan `{"status":"ok"}` | observasi [E1] |
| F02 | GET /api/items | 200, larik item | observasi [E2] |
| F04 | GET /api/items/{id} | 200 + item bila ada; 404 + `{"error":"not found"}` bila tidak | observasi [E8,E9] |
| F09 | GET /api/items?limit=&offset= | 200, larik terpotong: `offset` dilewati lebih dulu, lalu `limit` | observasi [E12] |
| F10 | GET /api/items?completed=true\|false | 200, hanya item dengan nilai `completed` yang diminta | observasi [E13,E14] |

Paginasi tanpa parameter mengembalikan seluruh daftar. [E2 · inferensi]
Bila `limit`/`offset` bukan bilangan, perilaku belum diketahui. [tidak-diketahui]

## 3. Autentikasi

- POST /api/login dengan `{"password": "<benar>"}` → 200 + `{"token": "<string>"}`. [E3 · observasi]
- Password salah → 401 + `{"error":"unauthorized"}`. [E4 · observasi]
- Operasi tulis (POST item, PATCH, DELETE) tanpa header `Authorization: Bearer <token>`
  → 401 + `{"error":"unauthorized"}`. [E5,E11 · observasi]
- Token berlaku selama proses hidup; tidak ada kedaluwarsa yang teramati. [E3,E6 · inferensi]
- Kredensial demo untuk harness: password `rahasia-demo` → token `tok-e1-demo`. [E3 · observasi]

## 4. Operasi tulis

| ID | Permintaan | Perilaku teramati | Label |
|---|---|---|---|
| F03 | POST /api/items + token, `{"name": ...}` | 201 + item baru; `id` = id tertinggi + 1 | observasi [E6] |
| F05 | PATCH /api/items/{id} + token | 200 + item terubah (medan yang dikirim saja) | observasi [E10] |
| F06 | DELETE /api/items/{id} + token | 204 tanpa badan; berikutnya 404 | observasi [E15,E16] |
| F08 | POST /api/items nama kosong/spasi | 422 + `{"error":"name wajib diisi"}` | observasi [E7] |

- `completed` pada POST opsional, default `false`. [E6 · observasi]
- PATCH dengan nama kosong → 422 (pola sama dengan F08). [E7 · inferensi]
- PATCH/DELETE id yang tidak ada → 404 `{"error":"not found"}`. [E9,E16 · inferensi]

## 5. Kesalahan umum

- Rute tidak dikenal → 404 + `{"error":"not found"}`. [E9 · inferensi]
- Badan JSON rusak → belum diuji. [tidak-diketahui]

## 6. Yang TIDAK boleh ditiru

- Nama, merek, dan teks milik target tidak dipakai; fixture ini memakai data contoh sendiri.
- Tidak ada aset visual target. Tidak ada kode sumber target di dokumen ini.

## 7. Cakupan benchmark

10 fitur (F01–F10). Fitur dinyatakan "ada di replika" hanya bila uji buta
`benchmarks/e1/checks.py` lulus pada replika dengan perilaku sama seperti target.
