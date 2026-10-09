---
name: geo-audit
description: "Audit and implement GEO for generative engines"
version: 1.0.0
author: Super Dev Builders Ecosystem
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [geo, seo, llm, structured-data, robots, llms-txt, schema]
    divisions: [D0, D2, D3, D4]
    related_skills: [feature-workflow, product-execution]
---

# geo-audit

Audit & implementasi Generative Engine Optimization (GEO) — optimasi agar situs
 dikutip oleh ChatGPT, Perplexity, Claude, Gemini (AI Overviews), Copilot.

## Kapan dipakai

- Request "audit GEO", "AI visibility", "kenapa ChatGPT/Perplexity tidak kutip situs kami".
- Pre-launch website/Next.js new: pastikan crawler AI bisa akses.
- Enhance existing site: ukuran Readiness & Checklist.

## 4 Pilar GEO

1. **Crawler Access** — allow AI crawler via robots.txt: GPTBot, OAI-SearchBot,
   ChatGPT-User, PerplexityBot, Perplexity-User, ClaudeBot, anthropic-ai,
   claude-web, Google-Extended. 200 OK di domain root. 
2. **llms.txt** — di domain root, `200 OK` TANPA redirect: PerplexityBot
   tidak follow redirect, GPTBot/ClaudeBot membatasi 2 hop.
3. **Structured Data (JSON-LD)** — `schema.org`: Organization, WebSite + SearchAction,
   Article, FAQPage, HowTo, BreadcrumbList.
4. **Extractability** — heading hierarchy rapi, jawaban inti 40-60 kata
   di awal tiap section, tabel & data konkret (recall up to +40% Citation).

## Penggunaan

```bash
# Audit situs live (read-only, tanpa autentikasi):
python3 scripts/geo_scan.py https://your-site.com

# Generator: buat robots.txt/llms.txt/JSON-LD dari situs:
python3 scripts/geo_gen.py --site-name "Nama" --url https://your-site.com \
  --description "..." --pages /,/pricing,/docs --output ./geo-out/
```

## Dimensi GeoScan (5)

| # | Dimensi | Ketika gagal |
|---|---|---|
| D1 | robots.txt — 9 AI UA harus Allow | AI crawler terblokir → tak mungkin dikutip |
| D2 | llms.txt — 200 di domain root | LLM tidak bisa navigasi konten |
| D3 | sitemap.xml — hadir + valid | discovery lambat/tak lengkap |
| D4 | JSON-LD — min. 1 schema valid | situs jadi sulit dipahami mesin |
| D5 | Content readiness — TTFB < 2.5s; Crawl-delay ≤ 10s kalau ada | pengalaman bot & UX riil |

## Fail-Fast

- Satu skill = satu tujuan — audit-and-report only; tak ada tambahan di luar ini.
- `--url` wajib valid http(s) → fail-fast dengan code exit 1 kalau tidak.

## Peringatan

- Sebelum menulis robots.txt produksi: pahami tipe crawler (search vs training).
  Blokir **training** crawler kalau tidak ingin konten jadi data training.
- Kalau Anda tidak yakin konfigurasi sudah benar → cek pengaruh `geo_gen.py` output
  dengan manual review MANUAL dulu sebelum deploy.

## Boundaries

- Tidak memodifikasi server code — laporan aja.
- Tidak dijalankan tanpa persetujuan pemilik situs (rate limit 1 req/detik).
- Tidak bandingkan dengan SEO klasik — bertingkat di atasnya bukan mengganti.

## Referensi

- Princeton GEO paper: "GEO: Generative Engine Optimization" (KDD 2024)
- https://llmstxt.org — spesifikasi llms.txt
- Perplexity docs: https://docs.perplexity.ai/docs/resources/perplexity-crawlers
