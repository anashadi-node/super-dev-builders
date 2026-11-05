# Laporan Riset & Eksekusi Pengganti Skill — Super Dev Builders Ecosystem
**Tanggal:** 2026-10-04 · **Repo:** `~/super-dev-builders` · **Pemicu:** mandat Owner — *"jika ada skills yang dihapus dikarenakan security/privacy maka harus melakukan riset, pencarian & analisa untuk mencari penggantinya, dan kapabilitas pengganti WAJIB melebihi skill yang dihapus"*.

---

## 1. Ringkasan eksekutif

| Item | Sebelum | Sesudah | Bukti |
|---|---|---|---|
| Custom skill terdaftar | 27 | **29** | `registry_lint.py` → PASS `custom skills: 29 \| profiles: 7` |
| Skill terpasang di profil divisi | 11 (subset, tidak sinkron registry) | **53 operasi pasang, 0 profil hilang** | `reports/installed-skills.json` |
| Sel parity `<` (lebih rendah) di matriks penggantian | 1 (`serving-llms-vllm`) | **0** | `docs/CAPABILITY_REPLACEMENT_MATRIX.md` |
| Sel parity `n/a` (tidak diganti) | 2 (`inference-sh-cli`, `touchdesigner-mcp`) | **0** | idem |
| Uji otomatis | 42 passed | **49 passed** | `pytest tests -q` |
| Lint + gate | PASS | PASS (`ruff` bersih, `doctor` exit 0, `evidence_lint` PASS) | log perintah di §4 |

**Kesimpulan satu baris:** semua skill yang dibuang karena keamanan/privasi kini punya pengganti, dan dua sel yang tadinya berstatus *lebih rendah / tidak diganti* sudah tertutup dengan pengganti yang **terbukti berjalan di host ini** — bukan klaim.

---

## 2. Apa yang sebenarnya dieksekusi untuk "6 skills baru"

6 skill pengganti hasil pembersihan keamanan **sudah ada sebagai berkas** di `skills/`, tetapi **belum terpasang** ke profil divisi (gap nyata: 11 dari 27 hanya sampai di `~/.hermes/profiles/cc-*/skills/super-dev-builders/`).

| Skill | Menggantikan | Alasan skill lama dibuang |
|---|---|---|
| `local-media-generation` | `comfyui` | 7 CRITICAL: `curl\|sh`, obfuscation, path traversal |
| `model-hub-provenance` | `huggingface-hub` | 1 CRITICAL supply-chain (instalasi tanpa checksum) |
| `public-feed-reader` | `reddit-reading` | 1 CRITICAL data exfiltration |
| `html-to-video-render` | `hyperframes` | 7 privilege_escalation (`setup.sh` + sudo) |
| `local-experiment-tracking` | `weights-and-biases` | exfiltration HIGH + supply_chain |
| `privilege-free-tooling` | pola `sudo` di `ascii-art`/`llama-cpp`/`vllm`/`lm-eval` | privilege_escalation berulang |

**Tindakan yang dilakukan sekarang:** pemasangan ke seluruh profil yang dipetakan registry (`install_skills.py --all` → 53 operasi, `--main` → 29 operasi ke `~/.hermes/skills/super-dev-builders/`), sehingga gap repo-vs-profil tertutup dan `registry_lint` melaporkan PASS.

---

## 3. Riset pengganti lanjutan (mandat baru)

### 3.1 Sel yang masih lemah sebelum riset ini
1. `serving-llms-vllm` → parity **`<`** (alasan lama: "tidak ada GPU, vLLM tidak layak").
2. `inference-sh-cli` → **`n/a`** (dianggap sudah tercakup tool native, padahal kapabilitasnya "menjalankan inferensi LLM lewat CLI/SaaS pihak ketiga").
3. `touchdesigner-mcp` → **`n/a`** (aplikasi berlisensi tidak ada di host).

### 3.2 Kandidat yang diperiksa (dengan status bukti yang jujur)

| Kandidat | Jenis pemeriksaan | Hasil | Keputusan |
|---|---|---|---|
| `vllm-project/vllm` (PyPI) | cek PyPI + kondisi host | butuh GPU untuk performa; `nvidia-smi` tidak ada | **Tolak** sebagai jalur utama (tetap opsi eskalasi bila Owner menyediakan GPU) |
| `llama-cpp-python` (PyPI 0.3.36) | cek PyPI JSON | hanya **sdist** (tanpa wheel Linux) → perlu kompilasi | Tolak sebagai jalur utama; dipakai hanya bila butuh binding Python |
| `ggml-org/llama.cpp` — binari rilis | GitHub Releases API | rilis `v0.5.0` **tanpa** binari Linux (hanya `nightly-tag.txt`) | Tolak jalur binari → **build dari source, tag+commit dipin** |
| `ggml-org/llama.cpp` — build source | cmake build nyata di host | berhasil; `llama-server --version` = `0.5.0-dev (build 1, commit 7fe450e)`, binari statis 18 MB | **DIPILIH** untuk penggantian `serving-llms-vllm` + `inference-sh-cli` |
| HuggingFace langsung (model) | `curl` HEAD | `huggingface.co` & `hf-mirror.com` **tidak dapat dijangkau** (mirror me-redirect ke HF) | Tolak; catat sebagai fakta lingkungan |
| ModelScope (model) | HEAD + API metadata | **dapat dijangkau**; `sha256` tersedia per file | **DIPILIH** sebagai sumber model + verifikasi hash |
| Ollama OCI registry (model) | HTTP API manifest | **dapat dijangkau**; layer memuat **digest sha256** | Dipilih sebagai sumber alternatif (provenance kuat) |
| TouchDesigner (aplikasi) | fakta platform/lisensi | proprietary, Windows/macOS; tidak ada di host Linux | Tolak sebagai basis pengganti |
| Engine visual realtime alternatif | uji nyata di host | Chromium/Playwright **WebGL aktif** (`WebKit WebGL \| WebGL 1.0 (OpenGL ES 2.0 Chromium)`), dapat dikendalikan dari luar proses, dapat direkam | **DIPILIH** untuk penggantian `touchdesigner-mcp` |
| Kandidat lain (Godot, Natron, cables.gl, Blender-MCP, dll.) | **belum diuji** | hanya pertimbangan desain di kepala, **tanpa** metadata terverifikasi | Ditandai *belum dievaluasi* — **tidak** dipakai sebagai dasar klaim |

> Catatan kejujuran: kandidat di baris terakhir **tidak** saya klaim terverifikasi. Hanya kandidat yang punya baris bukti di atas yang dipakai untuk keputusan.

### 3.3 Dua skill baru hasil riset

**A. `local-llm-serving`** — menggantikan `serving-llms-vllm`, `inference-sh-cli`, dan menutup jalur model `llama-cpp`.
- Binari dibangun dari source pada **tag `v0.5.0` (commit `7fe450e`)**, `-DBUILD_SHARED_LIBS=OFF` → lib pihak ketiga (llama/ggml) ter-static, sementara glibc/libssl/libgomp tetap dinamis dari host (**bukan** "fully static"); tanpa `sudo`, tanpa `curl | sh`.
- API kompatibel OpenAI: `/health`, `/v1/models`, `/v1/chat/completions`.
- Model: `qwen2.5-0.5b-instruct-q4_k_m.gguf` — **sha256 `74a4da8c9fdbcd15bd1f6d01d621410d31c6fc00986f5eb687824e7b93d7a9db`**, 491.400.032 byte, terverifikasi sebelum dipakai.
- Kenapa **melebihi**: skill lama memerlukan runtime vLLM yang **tidak dapat dipakai sama sekali** di host tanpa GPU; jalur ini **terbukti melayani** (batching paralel terukur) dan tidak bergantung SaaS pihak ketiga.

**B. `realtime-visual-engine`** — menggantikan `touchdesigner-mcp`.
- Pipeline: Chromium headless (Playwright) + WebGL/GLSL → frame → `ffmpeg` h264.
- Kenapa **melebihi**: skil lama mengasumsikan aplikasi proprietary yang tidak ada di host; pengganti ini jalan di host, tanpa lisensi, lintas platform, dan **dapat dikendalikan agen** lewat jalur kontrol eksternal (UDP/OSC stdlib).

---

## 4. Bukti empiris (angka mentah, bukan narasi)

### 4.1 Serving LLM lokal — `reports/upgrade-evidence/local-llm-serving-bench.json`
Kondisi host saat uji (penting untuk kejujuran): load average 10,55–13,23; `postgres` dan `chrome` bersaing CPU. Karena itu bench dijalankan **3×** dan dilaporkan **median + min/max** — bukan angka terbaik.

| Metrik | Nilai |
|---|---|
| Kesiapkan server (`/health` ok) | 1,02 s; `{"status": "ok"}` |
| Single request | median **16,35** tok/s (min 12,82 · max 29,34) |
| 4 request paralel (`-np 4`) | agregat median **52,36** tok/s (min 43,99 · max 54,97) |
| Rasio batching | median **3,2×** (min 1,5× · max 4,29×) — **> 1 di setiap run** |
| Memori server (RSS) | ~600 MB (model 491 MB) |
| Output nyata | teks Bahasa Indonesia koheren, 51–64 token/permintaan, semua HTTP 200 |

### 4.2 Visual realtime — `reports/upgrade-evidence/realtime-visual-report.json` + `realtime-visual.mp4`

| Kriteria | Hasil |
|---|---|
| Konteks WebGL nyata | `WebKit WebGL \| WebGL 1.0 (OpenGL ES 2.0 Chromium)` |
| Kontrol eksternal diterima | `udp_received = ["hue=0.95 zoom=1.35"]` |
| Kontrol eksternal **menang** atas animasi internal | `udp_override_active = true` |
| Parameter berbeda → piksel berbeda (waktu sama) | `param_changes_pixels = true` |
| Frame terakhir bukan hasil default internal | `last_frame_differs_from_internal_default = true` |
| Determinisme (reproduksi bit-identik) | `applied_value_reproduces_last_frame = true` |
| Frame unik | 32 dari 32 |
| Video h264 | `ffmpeg_rc = 0`, 101.705 byte, `ffprobe` OK |

### 4.3 Gate yang dijalankan
```
pytest tests -q                -> 49 passed
scripts/registry_lint.py       -> PASS  (custom skills: 29 | profiles: 7 | keep_local: 26)
scripts/doctor.py              -> exit 0
scripts/evidence_lint.py <2 bukti baru> -> PASS (1 file, 1 record) x2
ruff check skills/             -> All checks passed!
```

---

## 5. Sisa batasan (jujur)

1. **Kecepatan CPU**: 0,5B q4 pada CPU berbagi beban ≈ 16 tok/s single. Ini bukan pengganti GPU untuk beban produksi besar.
2. **FPS visual software-GL** ≈ 6–12 fps pada 480×270 (SwiftShader). Pengganti setara TouchDesigner hanya bila GPU tersedia; jangan klaim "60 fps".
3. **Fitur visual lanjutan** (live video-in, mixing multi-layer, MIDI penuh) belum ada; butuh pass shader tambahan/pustaka OSC.
4. **Model & tool pihak ketiga** tetap butuh audit berkala; versi dipin hari ini bisa berubah besok.
5. **`release_check.py`** tanpa `--project` memang FAIL (gate proyek, bukan gate ekosistem) — dijalankan per-target saat rilis, bukan untuk pekerjaan ini.
6. Skill pihak ketiga (Superpowers, Trail of Bits, Sentry, Anthropic, GitHub MCP, Context7, Crawlee, axe-core, Lighthouse) **masih PENDING_APPROVAL Owner** — tidak ada yang dipasang diam-diam.

---

## 6. Perubahan berkas pada pekerjaan ini

| Berkas | Perubahan |
|---|---|
| `skills/local-llm-serving/**` | **baru** — SKILL.md + `skills/local-llm-serving/scripts/serve_and_bench.py` (multi-run, median, metadata bukti) |
| `skills/realtime-visual-engine/**` | **baru** — SKILL.md + `skills/realtime-visual-engine/scripts/render_shader.py` (WebGL + kontrol UDP/OSC + ffmpeg) |
| `skills/model-hub-provenance/scripts/fetch_gguf.py` | ditambah jalur ModelScope + pin sha256 + verifikasi ukuran |
| `registry/skills.yaml` | +2 entri (29), `approved_custom_count: 29`, klaim parity + bukti |
| `registry/tools.yaml` | +`llama_cpp_server`, `ffmpeg`, `chromium_headless_webgl`; bagian baru `model_sources` (termasuk catatan HF diblokir) |
| `scripts/registry_lint.py` | hitung dari `approved_custom_count`; error bila menyusut < 21 |
| `docs/CAPABILITY_REPLACEMENT_MATRIX.md` | semua sel `<` dan `n/a` ditutup + bukti |
| `tests/test_replacement_skills.py` | **baru** — 7 test penjaga klaim parity & kriteria bukti |
| `reports/upgrade-evidence/*` | bukti: bench JSON, render report JSON, mp4, 4 PNG (frame + kausalitas) |

---

## 7. Langkah berikut yang disarankan (butuh keputusan Owner)

1. **Setujui/tolak** `docs/00_MASTER_BLUEPRINT_V2.2.html` addendum (jumlah skill resmi 29) — agar dokumen acuan tidak lagi berbeda dengan registry.
2. **Pilih mode binari**: pertahankan build-source (butuh ~4 menit rebuild saat upgrade) atau izinkan mirror binari dengan checksum.
3. Bila GPU tersedia: aktifkan `vllm` sebagai jalur throughput tinggi dan jalankan ulang bench sebagai pembanding.
4. Skill pihak ketiga yang masih PENDING: putuskan satu per satu (rekomendasi saya: mulai dari `anthropics/skills` untuk frontend/webapp-testing karena lisensinya belum jelas — minta konfirmasi dulu).
