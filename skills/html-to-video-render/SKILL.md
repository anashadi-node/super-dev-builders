---
name: html-to-video-render
description: "Use to render HTML/CSS animations to MP4/WebM. Playwright chromium + ffmpeg, tanpa sudo."
version: 1.0.0
author: Super Dev Builders Ecosystem
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [video, html, playwright, ffmpeg, render]
    divisions: [[D4, D5]]
    related_skills: [local-media-generation, privilege-free-tooling]
---


# HTML -> Video Render (pengganti `hyperframes`)

Kapabilitas render MP4/WebM dari komposisi HTML dipertahankan dengan mesin yang **sudah ada**
(Chromium Playwright + ffmpeg), tanpa `setup.sh` bersudo dan tanpa `curl | sh`.

## Mesin (terverifikasi ada di host)
- Chromium Playwright: `~/.cache/ms-playwright/chromium-1234`
- ffmpeg sistem (`ffmpeg -version`)

## Instalasi CLI (pin, user-local)
```
uv tool install playwright==1.63.0     # memperbaiki CLI yang sebelumnya rusak (module Python hilang)
playwright --version
```

## Prosedur
1. **Deterministik per-frame** (paling reproducible): render `composition.html?t=<detik>` per frame via
   `playwright screenshot --viewport-size=1280,720 --wait-for-timeout=50 file:///abs/path/composition.html?t=$f frames/f_$f.png`,
   lalu `ffmpeg -y -framerate 24 -i frames/f_%*.png -c:v libx264 -pix_fmt yuv420p out.mp4`.
2. **Screen-record** animasi real-time lewat Playwright video context (script kecil), lalu kompres dengan ffmpeg.

## Larangan
- DILARANG menjalankan `scripts/setup.sh` pihak ketiga (asal sudo + curl|sh).
- Selalu timeout eksplisit; blokir request jaringan saat render kecuali disengaja.

## Verifikasi
```
playwright screenshot file:///abs/path/composition.html /tmp/probe.png && file /tmp/probe.png
ffmpeg -v error -i out.mp4 -f null - && echo "video valid"
ffprobe -v error -show_entries stream=width,height,nb_frames -of csv out.mp4
```
