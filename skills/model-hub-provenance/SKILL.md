---
name: model-hub-provenance
description: "Use when downloading models/datasets. Pin revision + verify hash + license before use."
version: 1.0.0
author: Super Dev Builders Ecosystem
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [models, datasets, provenance, supply-chain, hf-cli]
    divisions: [[D4, D5, D8]]
    related_skills: [local-media-generation, privilege-free-tooling]
---


# Model & Dataset Provenance (pengganti `huggingface-hub`)

Kapabilitas `hf` CLI dipertahankan, **ditambah** kontrol provenance yang tidak dimiliki skill lama.

## Instalasi (user-local, tanpa sudo, tanpa curl|sh)
```
uv tool install "huggingface_hub[cli]==2.1.1"     # -> perintah `hf` di ~/.local/bin
hf version
```
Pin dicatat di `registry/tools.yaml`. Untuk venv proyek: `uv add huggingface_hub==2.1.1`.

## Aturan wajib (peningkatan atas skill lama)
1. **Selalu pin revision commit** (`--revision <sha40>`), jangan `main`.
2. **Verifikasi hash** bobot; prioritaskan `safetensors` (`.bin`/pickle hanya bila terpaksa & repo tepercaya).
3. **Cek lisensi** sebelum dipakai untuk produk (`--include LICENSE*`), catat hasilnya.
4. **Dilarang** menjalankan kode dari repo model: ambil hanya file bobot via `--include`.
5. `HF_TOKEN` hanya dari env; tidak pernah masuk log/artefak.

## Prosedur
```
hf download <org>/<repo> --revision <sha40> --include '*.safetensors' --include 'config.json' --local-dir ~/sdb-models/<name>
/usr/bin/python3 -c "import hashlib,pathlib;[print(p.name, hashlib.sha256(p.read_bytes()).hexdigest()[:16], p.stat().st_size) for p in sorted(pathlib.Path.home().glob('sdb-models/<name>/*.safetensors'))]"
```
Simpan (nama, sha256, size, revision, license) ke `evidence/models/<name>.json`.

## Verifikasi
`hf version && hf ls <org>/<repo> --revision <sha40> | head`
