---
name: local-media-generation
description: "Local media generation: install and serve models"
version: 1.0.0
author: Super Dev Builders Ecosystem
license: BUSL-1.1
platforms: [linux]
metadata:
  hermes:
    tags: [media, image, video, generation, docker, no-curl-pipe-sh]
    divisions: [[D4, D5]]
    related_skills: [privilege-free-tooling, evidence-normalizer]
---


# Local Media Generation (pengganti `comfyui`)

Kapabilitas `comfyui` (text-to-image/video) digantikan **tanpa** skill pihak ketiga berskrip instalasi.

## Urutan pilihan (rung sederhana dulu)
1. **Tool native Hermes** — `image_generate` (text-to-image / image-to-image) dan `video_generate`
   (text-to-video / image-to-video bila backend video dipilih di `hermes tools`).
   Jalur default: tanpa instalasi, tanpa skrip, tanpa jaringan pihak ketiga.
2. **ComfyUI lokal (opsional, bila butuh workflow sendiri)** — WAJIB di dalam Docker, image di-pin **digest**,
   tanpa bind-mount kredensial, tanpa akses socket Docker:
   `docker run --rm -p 127.0.0.1:8188:8188 --mount type=bind,src=$HOME/sdb-models,dst=/models,readonly comfyui/comfyui@sha256:<DIGEST>`
   Lalu panggil API lokal `http://127.0.0.1:8188/prompt` (bukan CLI skill pihak ketiga).
3. **Library**: `diffusers` di venv terpisah (CPU bila tanpa GPU), tanpa sudo.

## Larangan (ditegakkan)
- DILARANG menjalankan skrip instalasi pihak ketiga (`curl … | sh`, `setup.sh` sudo).
- DILARANG `--gpus all` di mesin tanpa GPU (cek `nvidia-smi` dulu).
- DILARANG memuat model tanpa verifikasi (lihat skill `model-hub-provenance`).

## Verifikasi
```
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader || echo "CPU-only -> pakai image_generate"
docker image inspect comfyui/comfyui --format '{{index .RepoDigests 0}}'   # cocokkan dengan pin
```
Hasil generate selalu disimpan sebagai artefak di `evidence/`, bukan klaim lisan.
