---
name: realtime-visual-engine
description: "Realtime generative visuals, no licensed suite"
version: 1.0.0
author: Super Dev Builders Ecosystem
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [visual, realtime, webgl, glsl, shader, osc, udp, ffmpeg, playwright, replace]
    divisions: [[D4, D5]]
    related_skills: [html-to-video-render, privilege-free-tooling, reconstruction-fidelity]
    replaces: [touchdesigner-mcp]
---

# Realtime Visual Engine (pengganti `touchdesigner-mcp`)

`touchdesigner-mcp` dibuang: temuan `privilege_escalation` + `persistence`, dan TouchDesigner
sendiri **tidak ada di host** (proprietary, Windows/macOS, berlisensi). Kapabilitas yang harus
tetap ada: **grafis realtime generatif yang bisa dikendalikan dari luar proses, dan bisa direkam.**

Parity dinaikkan: pengganti ini **berjalan di host ini**, gratis, lintas platform, dan
dapat dikendalikan agent lewat protokol sederhana (UDP/OSC) — tiga hal yang tidak dimiliki skill lama.

## Arsitektur
```
shader GLSL (WebGL, offline)  ← uniform (u_time, u_hue, u_zoom)
        ↑                                     ↑
  Playwright/CDP (kontrol)              UDP/OSC stdlib socket (kontrol eksternal)
        ↓
  frame PNG → ffmpeg (h264/gif/webm)
```

## Aturan
1. **Tanpa aplikasi berlisensi, tanpa sudo, tanpa CDN** — shader inline, semua offline.
2. Kontrol eksternal hanya **loopback** (bind `127.0.0.1`); jangan buka OSC/UDP ke jaringan.
3. Headless dulu; `--use-angle=swiftshader` untuk host tanpa GPU. FPS software-GL adalah
   batas *host*, bukan batas metode — catat `gl_renderer` agar tidak salah klaim.
4. Rekaman wajib lewat `ffmpeg` (`libx264`, `yuv420p`, `+faststart`) — `.py`/`.sh` pihak ketiga tidak dipakai.
5. Untuk target klien: patuhi `reconstruction-scope-gate` (visual generatif ≠ izin memakai
   merek/aset pihak ketiga).

## Alur baku
```bash
uv run --with playwright==1.63.0 python skills/realtime-visual-engine/scripts/render_shader.py \
  --frames 32 --fps 16 --width 480 --height 270 --out <dir> \
  --udp-selftest "hue=0.95 zoom=1.35"
```

## Kriteria bukti (semua harus `true` di `render-report.json`)
| Field | Arti |
|---|---|
| `gl_renderer` | WebGL konteks nyata (bukan fallback gagal) |
| `udp_received` | perintah eksternal benar-benar diterima runtime |
| `udp_override_active` | parameter eksternal menang atas animasi internal |
| `param_changes_pixels` | waktu sama + parameter beda → piksel beda (kausalitas) |
| `last_frame_differs_from_internal_default` | frame terakhir bukan hasil default internal |
| `applied_value_reproduces_last_frame` | reproduksi bit-identik (determinisme) |
| `unique_frames` ≈ jumlah frame | bukan video statis |
| `ffmpeg_rc == 0` + `ffprobe` | deliverable video nyata |

## Batas jujur
- Tanpa GPU nyata, fps rendah (software rasterizer). Jangan klaim "60 fps realtime".
- Belum ada live video-in/mixing multi-layer seperti TD; bila perlu, tambah pass shader
  terpisah (ping-pong FBO) di `scripts/`.
- MIDI/OSC terpadu penuh butuh `python-osc`; jalur UDP mentah sudah jelas & tanpa dependency.
