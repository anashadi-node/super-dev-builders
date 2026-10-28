---
name: privilege-free-tooling
description: "Install CLI tools user-local via uv/npm"
version: 1.0.0
author: Super Dev Builders Ecosystem
license: BUSL-1.1
platforms: [linux]
metadata:
  hermes:
    tags: [tooling, install, no-sudo, supply-chain, pin]
    divisions: [[D4, D10, D8]]
    related_skills: [model-hub-provenance, html-to-video-render, local-experiment-tracking]
---


# Privilege-Free Tooling (pengganti pola bersudo di `ascii-art`, `llama-cpp`, `vllm`, `lm-eval`)

Temuan audit pada skill-skill itu bukan payload jahat, tapi **pola instruksi** berisiko:
`sudo apt install`, `sudo ufw`, `os.system(f"...")`, `curl … | sh`. Skill ini menggantikan polanya.

## Aturan (ditegakkan)
1. **Dilarang `sudo`** untuk tooling proyek. Jalur sah:
   - Python/CLI: `uv tool install <pkg>==<pin>` (revert: `uv tool uninstall <pkg>`)
   - Node: `npm i -g --prefix ~/.local <pkg>@<pin>` atau `npx <pkg>@<pin>`
   - Binari rilis: unduh → **verifikasi checksum** → `install -m 0755` ke `~/.local/bin`
   - Paket OS benar-benar diperlukan → **ajukan ke Owner**, jangan eksekusi sendiri
2. **Dilarang `curl … | sh`**; subprocess selalu bentuk list argumen + timeout eksplisit (bukan `os.system`).
3. Setiap tool baru → pin versi, catat di `registry/tools.yaml`, buktikan dengan `<tool> --version`.

## Pengganti kapabilitas spesifik
| Kapabilitas skill lama | Pengganti tanpa sudo |
|---|---|
| ASCII art (`ascii-art`) | `uv tool install pyfiglet==1.0.4` (`pyfiglet -f banner "text"`) |
| LLM lokal CPU (`llama-cpp`) | `uv tool install llama-cpp-python==0.3.36` + GGUF terverifikasi (rilis `ggml-org/llama.cpp` tidak lagi menyediakan binari siap pakai) |
| Serving GPU (`serving-llms-vllm`) | **DITUNDA**: host tanpa GPU → pakai llama.cpp CPU; vLLM hanya bila GPU ada (ajukan Owner) |
| Eval harness (`evaluating-llms-harness`) | `uv tool install lm_eval==0.4.13`, dijalankan via list argumen |
| TouchDesigner MCP (`touchdesigner-mcp`) | **TIDAK DIGANTI**: butuh aplikasi desktop berlisensi yang tidak ada di host ini |

## Verifikasi
```
grep -rn "sudo \|curl .*| *sh\|os.system" skills/ | grep -v DILARANG | head   # harus kosong
for t in pyfiglet lm_eval; do printf '%s: ' $t; command -v $t >/dev/null && $t --version 2>&1 | head -1 || echo "belum dipasang"; done
```
