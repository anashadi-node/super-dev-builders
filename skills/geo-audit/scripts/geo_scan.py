#!/usr/bin/env python3
"""geo_scan.py — audit read-only kesiapan GEO sebuah situs.

Periksa 5 dimensi: robots.txt (9 AI UA), llms.txt 200-at-root,
sitemap, JSON-LD valid, dan Crawl-delay/TTFB.
License: MIT.
"""
import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

MAX_BYTES = 5 * 1024 * 1024   # batas respons: cegah DoS memori dari target untrusted
MIN_INTERVAL = 1.0            # SKILL.md Boundaries: rate limit 1 req/detik
_last_req = [0.0]

AI_UAS = [
    "GPTBot", "OAI-SearchBot", "ChatGPT-User",
    "PerplexityBot", "Perplexity-User",
    "ClaudeBot", "anthropic-ai", "claude-web",
    "Google-Extended",
]

def valid_base(url: str) -> bool:
    """Hanya http(s) dengan host — tolak file://, ftp://, dll (cegah baca file lokal)."""
    u = urllib.parse.urlsplit(url)
    return u.scheme in ("http", "https") and bool(u.netloc)

def fetch(url: str, timeout: float = 10):
    """Kembalikan (status, body, detik, redirected). Body dipotong di MAX_BYTES."""
    wait = MIN_INTERVAL - (time.time() - _last_req[0])
    if wait > 0:
        time.sleep(wait)
    _last_req[0] = time.time()
    req = urllib.request.Request(url, headers={"User-Agent": "geo-audit/1.0"})
    start = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read(MAX_BYTES).decode("utf-8", "replace")
            return r.status, body, round(time.time() - start, 3), r.geturl() != url
    except (urllib.error.URLError, urllib.error.HTTPError, OSError) as e:
        return None, str(e), round(time.time() - start, 3), False

def parse_robots(text: str):
    """Kembalikan {ua_lower: [direktif]} dari blok robots.txt."""
    out, cur, in_ua_run = {}, [], False
    for raw in text.splitlines():
        line = raw.split("#")[0].strip()
        if not line:
            continue
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip().lower()
        val = val.strip()
        if key == "user-agent":
            # RFC 9309: baris User-agent berurutan membentuk SATU grup
            cur = [*cur, val.lower()] if in_ua_run else [val.lower()]
            in_ua_run = True
            out.setdefault(val.lower(), [])
            continue
        in_ua_run = False
        if key in ("allow", "disallow", "crawl-delay"):
            for ua in cur:
                out.setdefault(ua, []).append((key, val))
    return out

def ua_allowed(direktif: dict, ua: str) -> bool:
    """Semantik robots.txt: UA eksplisit blokir Disallow-All => False;
    UA eksplisit Allow => True; tak disebut => ikuti aturan '*' (default izin)."""
    rules = direktif.get(ua.lower()) or []
    starred = direktif.get("*") or []
    if any(k == "disallow" and v == "/" for k, v in rules):
        return False
    if any(k == "allow" for k, v in rules):
        return True
    if any(k == "disallow" and v == "/" for k, v in starred):
        return False
    if any(k == "allow" for k, v in starred):
        return True
    return True  # konvensi robots: crawler diizinkan bila tak ada larangan

def crawl_delay(direktif: dict, ua: str):
    for k, v in (direktif.get(ua.lower()) or direktif.get("*") or []):
        if k == "crawl-delay":
            try:
                return float(v)
            except ValueError:
                return None
    return None

def check_sitemap(xml_text: str) -> bool:
    # tolak DTD/entity: cegah entity-expansion (billion laughs) dari XML untrusted
    if "<!DOCTYPE" in xml_text or "<!ENTITY" in xml_text:
        return False
    try:
        root = ET.fromstring(xml_text)
        return root.tag.endswith("urlset") or root.tag.endswith("sitemapindex")
    except ET.ParseError:
        return False

def count_linked_data(html: str):
    return html.count('application/ld+json')

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    base = args.url.rstrip("/")
    if not valid_base(base):
        print(f"URL tidak valid (wajib http/https + host): {args.url}", file=sys.stderr)
        return 1

    findings, score = [], 0.0
    st, robots_txt, _, _ = fetch(base + "/robots.txt")
    delays = {}
    if st == 200:
        dit = parse_robots(robots_txt)
        allowed = [ua for ua in AI_UAS if ua_allowed(dit, ua)]
        missing = [ua for ua in AI_UAS if ua not in allowed]
        delays = {ua: d for ua in AI_UAS if (d := crawl_delay(dit, ua)) is not None}
        findings.append({
            "dim": "D1 robots.txt",
            "detail": f"allowed {len(allowed)}/{len(AI_UAS)}; missing={missing}",
            "verdict": "PASS" if len(allowed) >= 7 else ("PARTIAL" if allowed else "FAIL"),
        })
        if allowed:
            score += 0.3
    else:
        findings.append({"dim": "D1 robots.txt", "detail": f"status {st} - tidak bisa diambil", "verdict": "FAIL"})

    st, _, _, redirected = fetch(base + "/llms.txt")
    ok = st == 200 and not redirected  # PerplexityBot tidak follow redirect (SKILL.md pilar 2)
    findings.append({"dim": "D2 llms.txt", "detail": f"status {st} di root, redirect={redirected}",
                     "verdict": "PASS" if ok else "FAIL"})
    if ok:
        score += 0.2

    st, sm_text, _, _ = fetch(base + "/sitemap.xml")
    ok = st == 200 and check_sitemap(sm_text)
    findings.append({"dim": "D3 sitemap.xml", "detail": f"status {st}, valid={ok}", "verdict": "PASS" if ok else "MARGINAL"})
    if ok:
        score += 0.15

    st, home_html, ttfb, _ = fetch(base)
    if st == 200:
        nld = count_linked_data(home_html)
        findings.append({"dim": "D4 JSON-LD", "detail": f"{nld} blok ld+json di homepage", "verdict": "PASS" if nld else "MARGINAL"})
        score += 0.2 if nld else 0.05
        slow_bots = {ua: d for ua, d in delays.items() if d > 10}
        findings.append({"dim": "D5 TTFB/Crawl-delay", "detail": f"{ttfb}s home; crawl-delay>10s={slow_bots}",
                         "verdict": "PASS" if ttfb < 2.5 and not slow_bots else "MARGINAL"})
        score += 0.05
    else:
        findings.append({"dim": "D4/5 home", "detail": f"status {st}", "verdict": "FAIL"})

    if args.json:
        print(json.dumps({"base": base, "score": round(score, 2), "findings": findings}, indent=2))
    else:
        print(f"GEO Scan {base}")
        for f in findings:
            mark = {"PASS": "[✓]", "PARTIAL": "[~]", "MARGINAL": "[!]", "FAIL": "[✗]"}.get(f["verdict"], "[?]")
            print(f"  {mark} {f['dim']:24} {f['detail']}")
        print(f"\nGEO readiness score: {score:.2f} / 1.0")
    return 0

if __name__ == "__main__":
    sys.exit(main())
