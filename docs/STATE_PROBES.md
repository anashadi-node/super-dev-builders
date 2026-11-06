# State Probe — merekam state, bukan menyimpulkannya

Dokumen ini menetapkan kontrak `scripts/did_capture_states.py` + `platform/state_probes/<target>.json`.

## Masalah yang dijawab

Portal SPA mengembalikan **shell yang sama** untuk semua rute; seluruh state dirender
klien. Karena itu penangkapan HTTP biasa tidak bisa membuktikan state kosong/error —
"sudah ditangani" hanya bisa ditulis `INFERRED`. Probe ini memberi dua jalur bukti:

1. **HTTP (tanpa browser)** — login per peran, ambil setiap rute, simpan status, ukuran,
   `sha256`, dan penanda teks. Bila semua hash rute identik, alat menyimpulkan
   `spa_shell: true` dan **tidak** mengklaim kosong (`kosong: null`): penanda "Belum ada"
   pada kasus itu berasal dari bundel JS, bukan dari state halaman.
2. **Render klien (browser)** — dipakai untuk state yang hanya ada setelah JS berjalan:
   kosong, error validasi, error izin, rute tak dikenal. Hasilnya disimpan sebagai
   `state-<peran>_<rute>.txt` + `.png` dan diringkas di `states-rendered.json`.

## Keamanan yang melekat

| Aturan | Perilaku |
|---|---|
| Hanya loopback | `127.0.0.1`/`::1`/`localhost`; host lain ditolak kecuali `--allow-remote` |
| Kredensial dari env | `${VAR}` wajib terisi; kosong = berhenti, tidak ada nilai default |
| Tanpa rahasia di bukti | Keluaran diperiksa; bila satu nilai rahasia muncul, keluar kode **2** dan berkas tidak ditulis |

## Bentuk konfigurasi

```json
{
  "schema": "sdb.did.state_probes/1",
  "target": "rt-rw-portal",
  "base_url": "http://127.0.0.1:8091",
  "login": {"path": "/api/login", "method": "POST"},
  "empty_markers": ["Belum ada", "Tidak ada", "kosong"],
  "roles": [
    {"name": "warga", "email_env": "RT_WARGA_EMAIL", "password_env": "RT_WARGA_PASS",
     "pages": ["/iuran", "/pengaduan"],
     "error_probes": [{"path": "/api/complaints", "method": "POST", "body": {},
                       "expect_status_min": 400}]}
  ],
  "anon": [{"path": "/iuran", "expect_status": 200, "expect_text": ["Masuk"]}]
}
```

Kredensial tidak pernah ditulis di berkas konfigurasi; hanya **nama** variabelnya.

## Pemakaian

```bash
export RT_WARGA_EMAIL=... RT_WARGA_PASS=...
python3 scripts/did_capture_states.py \
    --config platform/state_probes/rt-rw-portal.json \
    --out runs/rt-rw-portal/did/evidence/states-auth.json
```

## Batas yang disengaja

- Probe tidak menilai benar/salah data; ia merekam apa yang tampil.
- State `loading` bersifat transien dan tidak diklaim: yang direkam hanya yang bisa
  diulang pada permintaan baru.
- Untuk SPA, kesimpulan state kosong **wajib** bersandar pada jalur render klien.
