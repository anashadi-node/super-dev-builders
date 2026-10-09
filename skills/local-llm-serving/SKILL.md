---
name: local-llm-serving
description: "Serve LLMs locally; no GPU, no SaaS"
version: 1.0.0
author: Super Dev Builders Ecosystem
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [llm, serving, inference, llama-cpp, openai-api, offline, no-sudo, replace]
    divisions: [[D4, D5, D10]]
    related_skills: [model-hub-provenance, privilege-free-tooling, local-experiment-tracking]
    replaces: [serving-llms-vllm, inference-sh-cli]
---

# Local LLM Serving (pengganti `serving-llms-vllm` + `inference-sh-cli`)

Skill lama dibuang karena temuan supply-chain (`sudo ufw`, `curl | sh`, wrapper SaaS pihak
ketiga yang menulis ke `/etc`). Kapabilitas yang harus tetap ada: **menyajikan LLM lokal
dengan API kompatibel OpenAI dan throughput terkontrol, tanpa SaaS dan tanpa sudo.**

Parity dinaikkan, bukan diturunkan: vLLM **tidak dapat dipakai sama sekali** di host ini
(tidak ada GPU), sedangkan jalur di bawah terbukti jalan di CPU 16-core.

## Aturan (keras)
1. **Dilarang `sudo`** dan **dilarang `curl … | sh`** (lihat `privilege-free-tooling`).
2. Binari: bangun dari source pada **tag + commit ter-pin** (`ggml-org/llama.cpp`), lalu
   `install -m 0755` ke `~/.local/bin` atau `~/bin`. Jangan pakai binari rilis tanpa checksum.
3. Model: wajib lewat `model-hub-provenance` → **sha256 diverifikasi sebelum dipakai**.
   HuggingFace langsung **diblokir** di host ini; gunakan ModelScope atau OCI registry Ollama
   (digest = sha256, tidak perlu sumber lain).
4. Bind default **`127.0.0.1`** saja. `--host 0.0.0.0` hanya di dalam container terisolasi
   dan butuh approval Owner.
5. Tidak ada kredensial di argumen/lingkungan proses server. API key palsu (`--api-key`) hanya
   untuk membuktikan mode auth, bukan untuk produksi.
6. Naik ke vLLM **hanya** bila GPU tersedia + approval Owner (klasifikasi HIGH: tool pihak ketiga).

## Alur baku
```bash
# 1) bangun server (sekali, ~3-6 menit di 16 core; tanpa sudo)
git clone --depth 1 --branch v0.5.0 https://github.com/ggml-org/llama.cpp src
# Tag v0.5.0 = commit 7fe450e19305b828c199d602c23a8337aaa1f03b (catat SHA penuh saat build).
# Catatan: build default menghasilkan lib .so terpisah (butuh libllama.so dkk di samping binari).
# Pakai -DBUILD_SHARED_LIBS=OFF agar binari mandiri (yang dipakai di host ini).
cmake -B src/build -S src -DCMAKE_BUILD_TYPE=Release -DLLAMA_CURL=OFF \
      -DLLAMA_BUILD_TESTS=OFF -DLLAMA_BUILD_EXAMPLES=OFF -DGGML_NATIVE=ON
cmake --build src/build --target llama-server -j"$(nproc)"
install -m 0755 src/build/bin/llama-server ~/bin/llama-server
# Catatan: -DBUILD_SHARED_LIBS=OFF membuat lib pihak ketiga (llama/ggml) ter-static,
# tetapi glibc/libssl/libgomp tetap dinamis dari host -> catat apa adanya, jangan klaim "fully static".

# 2) model terverifikasi (skill model-hub-provenance)
/usr/bin/python3 skills/model-hub-provenance/scripts/fetch_gguf.py

# 3) serve + bench terdokumentasi (laporan JSON, bukan klaim)
/usr/bin/python3 skills/local-llm-serving/scripts/serve_and_bench.py \
  --model ~/models/qwen2.5-0.5b-instruct-q4_k_m.gguf --parallel 4 --tokens 64
```

## Kriteria bukti (harus ada semua)
- `llama-server --version` keluaran nyata + commit build dicatat.
- `/health` → `{"status":"ok"}` dan `/v1/models` memuat model.
- `/v1/chat/completions` mengembalikan teks nyata (bukan error).
- Bench single vs `--parallel 4`: di **setiap** run, token/s agregat > single → continuous batching aktif.
  Laporkan **median + min/max** (`--repeats 3`), jangan angka terbaik: host ini berbagi beban
  (postgres/chrome bersaing) sehingga single-shot menyesatkan.
- RSS server dicatat `os.getpid()`-nya (bukan total host) sebagai angka memori nyata.

## Kapan TIDAK memakai skill ini
- Butuh kualitas model besar (≥7B) untuk tugas produksi → pakai provider LLM ber-API atau
  ajukan GPU ke Owner; jangan memaksa CPU untuk beban yang salah.
- Butuh embedding reranking skala besar → pertimbangkan indeks vektor, bukan server chat.
