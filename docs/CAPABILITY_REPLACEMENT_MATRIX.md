# Matriks Penggantian Kapabilitas — 11 skill hub yang dibersihkan (2026-10-04)

Kebijakan: **keamanan/privacy dulu, kapabilitas tidak boleh hilang**. Setiap skill yang dibuang harus punya
pengganti dengan kemampuan **setara atau lebih baik**, dengan bukti uji nyata (bukan klaim).

Legenda parity: **≥** setara atau lebih baik · **<** lebih rendah (diberi alasan) · **n/a** tidak diganti (fitur tidak tersedia di host).

## A. Skill DANGEROUS (dibuang lebih dulu, approval #9/#9b)

| Skill dibuang | Temuan berat | Kapabilitas | Pengganti | Parity | Bukti/verifikasi |
|---|---|---|---|---|---|
| `comfyui` | 7 CRITICAL: `curl\|sh`, obfuscation `comfyui_setup.sh:117-118`, traversal | text-to-image / video lokal | **tool native** `image_generate` + `video_generate`; ComfyUI lokal hanya via Docker digest-pin | **≥** (tanpa skrip pihak ketiga) | tool native tersedia di sesi ini; `nvidia-smi` = tidak ada → jalur CPU/native |
| `huggingface-hub` | 1 CRITICAL supply_chain (instalasi tanpa checksum) | unduh model/dataset HF (`hf` CLI) | skill sendiri **`model-hub-provenance`** + `uv tool install "huggingface_hub[cli]==2.1.1"` | **≥** (tambah pin revision + hash + lisensi) | PyPI 2.1.1, `requires_python>=3.10` (host 3.12) |
| `reddit-reading` | 1 CRITICAL exfiltration | baca Reddit tanpa browser | skill sendiri **`public-feed-reader`** (RSS/Atom) + skill SAFE `rss-feeds` | **≥** read-only, tanpa auth | uji curl: `.rss` = 200 Atom; `.json`/`api.reddit.com` = dinding bot |
| `inference-sh-cli` | 5 CRITICAL: `curl\|sh`, tulis `/etc/bash_completion.d` | wrapper SaaS pihak ketiga | **n/a** — kapabilitas sudah tercakup tool native Hermes (browser/web + shell) | n/a | tidak ada dependensi lain yang memakainya (grep cron/config/plugins = kosong) |

## B. Skill CAUTION/BLOCKED (dibuang setelah pengganti siap)

| Skill dibuang | Temuan | Kapabilitas | Pengganti | Parity | Bukti/verifikasi |
|---|---|---|---|---|---|
| `ascii-art` | privilege_escalation (5 × `sudo apt install`) | ASCII art | `uv tool install pyfiglet==1.0.4` (tanpa sudo) | **≥** | PyPI 1.0.4; pola `sudo` dihapus |
| `llama-cpp` | 8 supply_chain, 1 sudo, 1 exfiltration, 1 execution | LLM lokal (GGUF) | `uv tool install llama-cpp-python==0.3.36` + GGUF terverifikasi | **≥** | host tanpa GPU → CPU OK; rilis `ggml-org/llama.cpp` kini tanpa binari siap pakai (terverifikasi: 1 aset = `nightly-tag.txt`) |
| `serving-llms-vllm` | 7 supply_chain, 1 `sudo ufw` | serving LLM throughput tinggi | **DITUNDA**: `uv tool install vllm` hanya bila GPU tersedia | **<** (host tanpa GPU; fitur tidak bisa dipakai) | `nvidia-smi` tidak ada → vLLM CPU praktis tidak layak |
| `evaluating-llms-harness` | 2 execution (`os.system`), 2 supply_chain | benchmark LLM (MMLU dll) | `uv tool install lm_eval==0.4.13`, dijalankan via list argumen | **≥** (tanpa `os.system`) | PyPI 0.4.13 |
| `weights-and-biases` | exfiltration HIGH + supply_chain | pencatatan eksperimen ML | skill sendiri **`local-experiment-tracking`** (JSONL / MLflow lokal / TensorBoard) | **≥** privasi (0 data keluar host) | bind loopback wajib; MLflow 3.16.1, TB 2.21.0 |
| `touchdesigner-mcp` | privilege_escalation + persistence | kontrol TouchDesigner | **n/a** — butuh aplikasi desktop berlisensi yang tidak ada di host | n/a | tidak ada TouchDesigner di host |
| `hyperframes` | 7 privilege_escalation (`setup.sh` sudo), 7 supply_chain | render MP4/WebM dari HTML | skill sendiri **`html-to-video-render`** (Playwright Chromium + ffmpeg) | **≥** (mesin sudah ada, tanpa sudo) | Chromium `~/.cache/ms-playwright/chromium-1234` + `ffmpeg` ada; playwright pin 1.63.0 |

## C. Skill pengganti baru (milik ekosistem, sumber: `skills/`)

| Skill | Menggantikan | Divisi | Profil |
|---|---|---|---|
| `local-media-generation` | comfyui | D4, D5 | sdb-builder, sdb-devops |
| `model-hub-provenance` | huggingface-hub | D4, D5, D8 | sdb-builder, sdb-security |
| `public-feed-reader` | reddit-reading | D2, D5 | sdb-orchestrator, sdb-builder |
| `html-to-video-render` | hyperframes | D4, D5 | sdb-builder, sdb-devops |
| `local-experiment-tracking` | weights-and-biases | D9, D5 | sdb-builder, sdb-security |
| `privilege-free-tooling` | pola sudo di ascii-art/llama-cpp/vllm/lm-eval | D4, D8, D10 | sdb-builder, sdb-security, sdb-devops |

## D. Aturan permanen (ditegakkan skill `privilege-free-tooling`)
1. Tidak ada `sudo` untuk tooling proyek; paket OS → ajukan Owner.
2. Tidak ada `curl … | sh`; subprocess = list argumen + timeout.
3. Setiap tool baru: pin versi + catat `registry/tools.yaml` + buktikan `<tool> --version`.
4. Pemasangan tool eksternal tetap butuh approval Owner (denylist: `registry/hub_skills_denylist.yaml`).
