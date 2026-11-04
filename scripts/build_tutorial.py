#!/usr/bin/env python3
"""Bangun dokumen tutorial SDB: Markdown -> HTML (mandiri, satu berkas) -> PDF (Chrome).

PDF **tidak** disimpan di git: ukurannya melewati gerbang 512 KB (aturan R1 di
`scripts/repo_hygiene.py`). Dokumen HTML dan Markdown tetap dilacak; PDF dibuat ulang kapan saja:

    make docs-tutorial            # HTML + PDF di docs/
    python3 scripts/build_tutorial.py docs/TUTORIAL_PENGGUNAAN.md

Butuh modul `markdown` (tersedia di python3 sistem pada mesin ini) dan `google-chrome`.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

CSS = """
:root{--bg:#fff;--fg:#16181d;--muted:#5b6472;--line:#e3e7ee;--accent:#1e5fbf;--accent-soft:#eef4ff;
--warn:#8a5a00;--warn-bg:#fff8e6;--code-bg:#f6f8fb}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{margin:0;color:var(--fg);background:var(--bg);
font:16px/1.72 -apple-system,"Segoe UI",Roboto,"Helvetica Neue",Arial,"Noto Sans",sans-serif;
-webkit-font-smoothing:antialiased}
.wrap{max-width:1120px;margin:0 auto;padding:0 28px 96px}
header.hero{border-bottom:1px solid var(--line);margin-bottom:36px;padding:56px 0 28px;
background:linear-gradient(180deg,var(--accent-soft),transparent)}
.hero .kicker{color:var(--accent);font-weight:700;letter-spacing:.08em;text-transform:uppercase;font-size:12px}
.hero h1{font-size:clamp(26px,4vw,40px);line-height:1.2;margin:10px 0 12px;letter-spacing:-.02em}
.hero p{margin:0;color:var(--muted);max-width:70ch}
.badges{display:flex;gap:8px;flex-wrap:wrap;margin-top:18px}
.badge{font-size:12.5px;border:1px solid var(--line);border-radius:999px;padding:4px 10px;color:var(--muted);background:#fff}
.layout{display:grid;grid-template-columns:266px minmax(0,1fr);gap:44px;align-items:start}
nav.toc{position:sticky;top:18px;max-height:calc(100vh - 36px);overflow:auto;border-right:1px solid var(--line);padding-right:14px}
nav.toc .toc-title,.toc-inline .toc-title{font-size:12px;letter-spacing:.1em;text-transform:uppercase;
color:var(--muted);font-weight:700;margin-bottom:10px}
nav.toc ul{list-style:none;margin:0;padding:0;font-size:13.5px;line-height:1.45}
nav.toc ul ul{margin:4px 0 8px 12px;border-left:1px solid var(--line);padding-left:10px}
nav.toc li{margin:6px 0}
nav.toc a{color:var(--muted);text-decoration:none;display:block;padding:2px 4px;border-radius:4px}
nav.toc a:hover{color:var(--accent);background:var(--accent-soft)}
main{min-width:0}
h1,h2,h3,h4{line-height:1.28;letter-spacing:-.015em}
h2{font-size:26px;margin:46px 0 14px;padding-top:14px;border-top:1px solid var(--line)}
h3{font-size:19.5px;margin:30px 0 10px}
h4{font-size:16.5px;margin:22px 0 8px}
p{margin:12px 0}
a{color:var(--accent)}
ul,ol{padding-left:22px}
li{margin:6px 0}
strong{font-weight:650}
hr{border:0;border-top:1px solid var(--line);margin:34px 0}
code{font-family:ui-monospace,SFMono-Regular,"JetBrains Mono",Menlo,Consolas,monospace;font-size:13.6px;
background:var(--code-bg);border:1px solid var(--line);border-radius:5px;padding:1px 5px}
pre{background:var(--code-bg);border:1px solid var(--line);border-radius:10px;padding:16px 18px;overflow:auto;line-height:1.55}
pre code{background:none;border:0;padding:0;font-size:13.2px;white-space:pre}
blockquote{margin:18px 0;padding:14px 18px;border-left:4px solid var(--warn);background:var(--warn-bg);
color:#3a2b00;border-radius:0 8px 8px 0}
blockquote p{margin:6px 0}
.table-wrap{overflow:auto;margin:18px 0;border:1px solid var(--line);border-radius:10px}
table{border-collapse:collapse;width:100%;font-size:14.2px}
th,td{padding:10px 13px;text-align:left;border-bottom:1px solid var(--line);vertical-align:top}
th{background:#f8fafc;font-weight:650;white-space:nowrap}
tbody tr:last-child td{border-bottom:0}
tbody tr:hover{background:#fbfcfe}
.toc-inline{border:1px solid var(--line);border-radius:10px;padding:16px 20px;margin:18px 0 26px;background:#fbfcfe}
.toc-inline ul{list-style:none;margin:0;padding:0;columns:2;column-gap:28px;font-size:13.8px}
.toc-inline ul ul{columns:1;margin:2px 0 6px 12px;border-left:1px solid var(--line);padding-left:10px}
.toc-inline a{color:var(--fg);text-decoration:none}
.toc-inline a:hover{color:var(--accent)}
.foot{margin-top:56px;padding-top:18px;border-top:1px solid var(--line);color:var(--muted);font-size:13.5px}
@media print{
  nav.toc{display:none}
  .layout{display:block}
  header.hero{background:none;padding-top:0}
  body{font-size:11.2pt;line-height:1.5}
  h2,h3{page-break-after:avoid;margin-top:22px}
  pre,blockquote{page-break-inside:avoid}
  table{page-break-inside:auto}
  tr,td,th{page-break-inside:avoid}
  thead{display:table-header-group}
  .table-wrap{overflow:visible}
  a{color:#000;text-decoration:none}
  .wrap{max-width:none;padding:0}
  @page{size:A4;margin:16mm 14mm}
}
@media (max-width:900px){
  .layout{display:block}
  nav.toc{position:static;max-height:none;border-right:0;border-bottom:1px solid var(--line);
    padding:0 0 14px;margin-bottom:22px}
}
"""

TEMPLATE = """<!DOCTYPE html>
<html lang="id">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta name="description" content="{desc}">
<style>{css}</style>
</head>
<body>
<header class="hero"><div class="wrap">
  <div class="kicker">{kicker}</div>
  <h1>{title}</h1>
  <p>{desc}</p>
  <div class="badges">{badges}</div>
</div></header>
<div class="wrap layout">
<nav class="toc"><div class="toc-title">Daftar Isi</div>{toc}</nav>
<main>
{body}
<div class="foot">{foot}</div>
</main>
</div>
</body>
</html>
"""


def build(src: Path, out_html: Path, out_pdf: Path | None, title: str, desc: str,
          kicker: str, badges: list[str], foot: str,
          toc_depth: str = "2-3", toc_enabled: bool = True) -> None:
    import markdown  # sengaja di dalam fungsi: pesan galat jelas bila modul tidak ada

    text = src.read_text(encoding="utf-8")
    text = re.sub(r"^# .*?\n", "", text, count=1)  # H1 pertama digantikan <h1> templat
    md = markdown.Markdown(extensions=["tables", "fenced_code", "toc", "sane_lists", "attr_list"],
                           extension_configs={"toc": {"permalink": False, "toc_depth": toc_depth}})
    body = md.convert(text).replace("<table>", '<div class="table-wrap"><table>').replace(
        "</table>", "</table></div>")
    toc = getattr(md, "toc", "")  # disuntikkan ekstensi toc
    if not toc_enabled:
        # Dokumen yang sudah punya bagian "Daftar Isi" sendiri tidak perlu TOC ganda.
        toc = ""
        body = body.replace("<p>{{TOC}}</p>", "").replace("{{TOC}}", "")
    else:
        inline = f'<div class="toc-inline"><div class="toc-title">Daftar Isi</div>{toc}</div>'
        body = body.replace("<p>{{TOC}}</p>", inline).replace("{{TOC}}", inline)
    out_html.write_text(TEMPLATE.format(
        title=title, desc=desc, css=CSS, kicker=kicker,
        toc=f'<div class="toc">{toc}</div>' if toc else "",
        body=body, foot=foot,
        badges="".join(f'<span class="badge">{b}</span>' for b in badges)), encoding="utf-8")
    print(f"html: {out_html} ({out_html.stat().st_size:,} bytes)")
    if out_pdf is None:
        return
    proc = subprocess.run(
        ["google-chrome", "--headless=new", "--no-sandbox", "--disable-gpu", "--no-pdf-header-footer",
         f"--print-to-pdf={out_pdf}", out_html.resolve().as_uri()],
        capture_output=True, text=True, timeout=240)
    if proc.returncode != 0 or not out_pdf.exists():
        print("PDF gagal dibuat (Chrome):", proc.stderr[-500:], file=sys.stderr)
        raise SystemExit(1)
    print(f"pdf: {out_pdf} ({out_pdf.stat().st_size:,} bytes)")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Bangun HTML+PDF dari Markdown tutorial SDB")
    ap.add_argument("src", type=Path)
    ap.add_argument("--html", type=Path)
    ap.add_argument("--pdf", type=Path)
    ap.add_argument("--no-pdf", action="store_true")
    ap.add_argument("--title", default="Panduan Lengkap SDB — Cara Pakai yang Baik dan Benar")
    ap.add_argument("--desc", default="Panduan operasional SDB: admin, tenant, worker, penagihan, "
                                      "metrik, keamanan, dan semua kemungkinan galat.")
    ap.add_argument("--kicker", default="Super Dev Builders · Dokumentasi Pengguna")
    ap.add_argument("--badge", action="append", default=None)
    ap.add_argument("--toc-depth", default="2-3", help='kedalaman TOC markdown, mis. "2" hanya H2')
    ap.add_argument("--no-toc", action="store_true",
                    help="jangan suntikkan TOC templat (untuk dokumen yang punya Daftar Isi sendiri)")
    args = ap.parse_args(argv)
    out_html = args.html or args.src.with_suffix(".html")
    out_pdf = None if args.no_pdf else (args.pdf or args.src.with_suffix(".pdf"))
    build(args.src, out_html, out_pdf, args.title, args.desc, args.kicker,
          args.badge or ["dokumentasi", "tanpa dependensi runtime"], foot=args.desc,
          toc_depth=args.toc_depth, toc_enabled=not args.no_toc)
    return 0


if __name__ == "__main__":
    sys.exit(main())
