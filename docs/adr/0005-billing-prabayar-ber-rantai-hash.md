# ADR-0005 — Billing prabayar, integer micro-USD, ledger ber-rantai hash

Status: diterima · 2026-10-29

## Konteks

Kuota saja tidak menghasilkan uang. Untuk menjual langganan, setiap job harus punya **harga pasti**,
setiap rupiah harus bisa ditelusuri, dan pelanggan tidak boleh bisa memakai lebih dari yang dibayar.
Float untuk uang selalu salah; pembulatan diam-diam adalah kebocoran margin.

## Keputusan

1. **Satuan uang = micro-USD bulat** (1 μUSD = 1e-6 USD). Harga per 1 juta token per paket:
   starter $2,00 · pro $1,60 · team $1,20 · enterprise $1,00. Pembulatan selalu **ke atas**.
2. **Prabayar**: kredit dipegang (`hold`) sebesar harga budget job saat job dibuat; job ditolak
   `402 insufficient_credit` bila kredit kurang. Pemakaian nyata ditagih saat job selesai
   (`charge`), sisa pesanan dikembalikan (`release`).
3. **Ledger append-only ber-rantai hash**: setiap baris menyimpan hash baris sebelumnya; mengubah
   baris lama membuat `verify_chain()` gagal. Kredit uji dicatat sebagai entri `adjust`, bukan angka
   awal diam-diam — supaya `sum(amount) == saldo` selalu bisa diuji.
4. **Tagihan (`invoice`)** = snapshot JSON kanonik + hash ber-rantai, idempoten per (tenant, periode).
5. **Kegagalan tidak menagih**: `failed`, `cancelled`, `lease_expired` → `release`, bukan `charge`.

## Konsekuensi

- Tidak ada angka negatif: saldo tidak bisa di bawah nol karena hold dicek sebelum job dibuat.
- Harga bisa berubah kapan saja untuk job **baru**; job lama tetap memakai harga saat hold.
- Refund/koreksi manual tersedia sebagai `adjust`/`refund` + memo wajib.
- Yang belum ada: gateway pembayaran, pajak, proration saat upgrade paket, dunning untuk gagal bayar.
  Semua itu lapisan di atas ledger ini; jangan mengubah ledger untuk mengejar fitur tersebut.
