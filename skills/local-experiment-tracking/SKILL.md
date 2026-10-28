---
name: local-experiment-tracking
description: "Log ML experiments locally (MLflow, JSON)"
version: 1.0.0
author: Super Dev Builders Ecosystem
license: BUSL-1.1
platforms: [linux]
metadata:
  hermes:
    tags: [ml, experiments, tracking, local, privacy]
    divisions: [[D9, D5]]
    related_skills: [local-media-generation, model-hub-provenance]
---


# Local Experiment Tracking (pengganti `weights-and-biases`)

Pencatatan eksperimen tanpa mengirim data ke SaaS pihak ketiga (skill lama: exfiltration HIGH + supply_chain).
Semua metrik tetap di host.

## Pilihan (urut dari paling ringan)
1. **JSONL + ringkasan** (default; stdlib, nol dependency) — cukup untuk backtest/trading:
   tulis satu baris JSON per run ke `evidence/runs/runs.jsonl` dengan field `ts`, `config`, `metrics`.
2. **MLflow lokal**: `uv tool install mlflow==3.16.1` lalu
   `mlflow ui --host 127.0.0.1 --port 5000 --backend-store-uri file://$PWD/mlruns`
3. **TensorBoard** untuk kurva training: `uv tool install tensorboard==2.21.0`

## Larangan
- DILARANG API key SaaS untuk metrik tanpa approval Owner.
- DILARANG mengirim artefak/data klien ke luar host.
- DILARANG mencatat secret/API key sebagai "config" (redaksi lewat `redact_network.py`).

## Verifikasi
`ss -ltnp | grep 5000` harus menunjuk `127.0.0.1`, bukan `0.0.0.0`.
