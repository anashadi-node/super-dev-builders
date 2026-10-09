---
name: public-feed-reader
description: "Read public forums and news read-only"
version: 1.0.0
author: Super Dev Builders Ecosystem
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [rss, atom, reddit, read-only, no-auth]
    divisions: [[D2, D5]]
    related_skills: [rss-feeds, evidence-normalizer]
---


# Public Feed Reader (pengganti `reddit-reading`)

Kapabilitas "baca Reddit/forum tanpa browser" dipertahankan lewat jalur **read-only & hemat**:
RSS/Atom publik (bukan scraping halaman ber-auth).

## Hasil uji jalur (2026-10-04, curl nyata)
| Jalur | Status |
|---|---|
| `https://www.reddit.com/r/<sub>/new/.rss` | **JALAN** (Atom XML) — jalur utama |
| `https://old.reddit.com/r/<sub>/new.json` | kosong/diblokir |
| `https://api.reddit.com/r/<sub>/new` | HTML (dinding bot) |
| `https://www.reddit.com/r/<sub>/new.json` | HTML (dinding bot) |

## Prosedur (jalur terbukti)
```
UA='sdb-feed-reader/1.0 (read-only; contact: ops@localhost)'
curl -fsS -A "$UA" -m 20 "https://www.reddit.com/r/<sub>/new/.rss" -o /tmp/feed.xml
/usr/bin/python3 -c "import xml.etree.ElementTree as ET;r=ET.parse('/tmp/feed.xml').getroot();ns='{http://www.w3.org/2005/Atom}';[print(e.findtext(ns+'title')) for e in r.findall(ns+'entry')[:10]]"
```
Situs lain: pakai skill `rss-feeds` (SAFE) atau cari `<link rel="alternate" type="application/rss+xml">`.

## Larangan
- Tanpa login/kredensial; tanpa posting/membalas; tanpa bypass dinding bot/CAPTCHA.
- Hormati rate limit (>= 2 s antar permintaan per host).
- Jangan simpan data pribadi (cukup nama pengguna publik, bukan DM/konten privat).

## Verifikasi
`curl -fsS -o /dev/null -w '%{http_code}\n' -A "$UA" <url>.rss` harus 200 dan XML valid (parse OK).
