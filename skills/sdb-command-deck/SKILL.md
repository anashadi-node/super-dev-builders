---
name: sdb-command-deck
description: Use when operating the SDB Workspace web (port 8484) — restart, PIN, health, add project.
version: 1.0.0
author: Super Dev Builders Ecosystem
license: BUSL-1.1
platforms: [linux]
metadata:
  hermes:
    tags: [sdb, dashboard, ops, monitoring, security]
    divisions: [D10, D4]
    related_skills: [rollback-and-recovery]
---

# SDB Workspace (web lokal :8484)

Web usecase Super Dev Builders: ketik ide (web / Android / SaaS) → diskusi dengan Kapten Orka
→ draft intake (Gate #0) → Approve → tahap pipeline 16. Monitoring = kantor isometrik 3D,
11 karakter + barista; tiap agent punya karakter, ruangan, dan rutinitas sendiri.

- `/` Workspace (kantor 3D + chat) · `/monitor` Command Deck lama (kartu LLM) · `/cast.html` galeri karakter.
- URL lokal `http://127.0.0.1:8484` · LAN `http://192.168.1.9:8484` (HP: WiFi sama).
- PIN untuk perangkat lain: tab **Tim** di PC server, atau `python3 dashboard/server.py --show-token`.
  Semua `/api/ws/*` wajib header `X-SDB-Token`; PIN hanya dibagikan ke klien 127.0.0.1.
- Service: `systemctl --user status sdb-command-deck` (0.0.0.0:8484). Health harian: `sdb-deck-health.timer` 07:30
  → `server.py --health-check` (PONG per profil → `dashboard/state/health.json`, valid 14 jam).
- Data: `~/sdb-workspace/` (projects.json, chats/, projects/<id>/stages/*.md, `.token`). Bukan di git.
- Shortcut desktop: `~/Desktop/sdb-command-deck.desktop` (Chrome app-window → `/`).
- Edit UI/JS → cukup refresh (no-store); edit `server.py`/`ws_api.py` → `systemctl --user restart sdb-command-deck`.

## Aturan (jangan dilanggar)
- LLM dari web dipanggil `hermes -p <profil> --ignore-rules -t todo -z` — **tanpa shell/file**
  (server terbuka di LAN; terbukti agent menjawab "TIDAK ADA TOOL SHELL"). Tahap 05 saja `-t web`.
  Jangan longgarkan tanpa persetujuan Owner.
- Hanya tahap 02–06 (dokumen) jalan dari web. Tahap 07–16 (build/test/scan/deploy) hanya membuat
  `*.brief.md` serah-terima: eksekusi tetap di terminal dengan bukti segar. Security/Audit tak punya hak deploy.
- Status tahap = file di disk, bukan klaim. Animasi jalan-jalan = dekoratif; titik hijau = probe PONG nyata.
- Probe health butuh kunci dari `~/.hermes/.env` (profil tak membacanya sendiri) → `ws_api.hermes_env()`;
  tanpa itu systemd memberi 401 palsu. Nilai kunci tak pernah dicetak/di-log.
- Ruang CONTOH selalu berlabel; jangan ubah jadi "nyata". Data sensors hanya id model/provider — jangan serve kunci/auth.json.

## Verifikasi visual (headless, tanpa GPU)
`google-chrome --headless=new --no-sandbox --enable-unsafe-swiftshader --use-gl=angle --use-angle=swiftshader
--window-size=1440,900 --virtual-time-budget=25000 --screenshot=/tmp/x.png URL` (±20–60 dtk).
`--dump-dom` menampilkan `data-stats` / `data-err` di `<html>`. Param QA: `/?focus=<id>&z=3&panel=0`.
Pitfall: event dari `createWorld()` yang dipancarkan sinkron hilang sebelum listener terpasang → gunakan `setTimeout`.

## Tambah proyek nyata
Edit `~/sdb-workspace/projects.json` (`id`,`name`,`path`,`kind: real`) + tambah ruang di `dashboard/ws/world.js`
(`ROOMS`, `project: id`); atau approve draft ide baru (entri dibuat otomatis).
