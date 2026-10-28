#!/usr/bin/env python3
"""Markdown -> HTML (bertema) -> PDF via Chromium headless. Tanpa layanan pihak ketiga.

Pemakaian:
  uv run --with markdown --with playwright==1.63.0 python scripts/md_to_pdf.py docs/X.md reports/X
  -> reports/X.html + reports/X.pdf
"""
from __future__ import annotations

import html as html_lib
import os
import sys

CSS = """
:root{--fg:#172033;--muted:#647084;--line:#dfe5ef;--bg:#fff}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.62 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif}
main{max-width:900px;margin:auto;padding:34px 26px 60px}
h1{font-size:1.75rem;line-height:1.15;margin:.2em 0 .6em}
h2{font-size:1.3rem;margin-top:1.6em;border-bottom:2px solid var(--line);padding-bottom:.25em}
h3{font-size:1.08rem;margin-top:1.3em}
table{border-collapse:collapse;width:100%;margin:14px 0;font-size:.93rem}
th,td{border:1px solid var(--line);padding:8px 9px;text-align:left;vertical-align:top}
th{background:#f0f3f8}
code{background:#eef2f7;border-radius:5px;padding:2px 5px;font-size:.9em}
pre{background:#101827;color:#e7ebf3;padding:14px;border-radius:10px;overflow:auto}
blockquote{border-left:4px solid #2755d9;background:#eaf0ff;margin:12px 0;padding:10px 14px}
hr{border:0;border-top:1px solid var(--line);margin:22px 0}
footer{margin-top:28px;color:var(--muted);font-size:.85rem}
"""

def main() -> int:
    if any(a in ("-h", "--help") for a in sys.argv[1:]):
        print(__doc__)
        return 0
    if len(sys.argv) < 3:
        print(__doc__, file=sys.stderr)
        return 2
    src, out_base = sys.argv[1], sys.argv[2]
    os.makedirs(os.path.dirname(out_base) or ".", exist_ok=True)
    import markdown  # type: ignore

    raw = open(src, encoding="utf-8").read()
    body = markdown.markdown(raw, extensions=["tables", "fenced_code", "toc", "sane_lists"])
    name = html_lib.escape(os.path.basename(src))
    html = (f"<!doctype html><html lang='id'><head><meta charset='utf-8'>"
            f"<title>{name}</title><style>{CSS}</style></head>"
            f"<body><main>{body}<footer>Dihasilkan dari <code>{html_lib.escape(src)}</code> · "
            f"md_to_pdf.py · tanpa layanan pihak ketiga</footer></main></body></html>")
    html_path = out_base + ".html"
    open(html_path, "w", encoding="utf-8").write(html)

    from playwright.sync_api import sync_playwright

    pdf_path = out_base + ".pdf"
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        page = b.new_page()
        page.goto("file://" + os.path.abspath(html_path))
        page.pdf(path=pdf_path, format="A4", print_background=True,
                 margin={"top": "16mm", "bottom": "16mm", "left": "14mm", "right": "14mm"})
        b.close()
    print(f"HTML: {html_path} ({os.path.getsize(html_path)} B)")
    print(f"PDF : {pdf_path} ({os.path.getsize(pdf_path)} B)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
