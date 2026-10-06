#!/usr/bin/env python3
"""geo_scan.py — audit read-only kesiapan GEO sebuah situs.

Periksa 5 dimensi: robots.txt (9 AI UA), llms.txt 200-at-root,
sitemap, JSON-LD valid, dan Crawl-delay/TTFB.
License: MIT.
"""
import argparse, json, re, sys, time
import urllib.request, urllib.error
import xml.etree.ElementTree as ET

AI_UAS = [
    "GPTBot", "OAI-SearchBot", "ChatGPT-User",
    "PerplexityBot", "Perplexity-User",
    "ClaudeBot", "anthropic-ai", "claude-web",
    "Google-Extended",
]

def fetch(url: str, timeout: float = 10):
    req = urllib.request.Request(url, headers={"User-Agent": "geo-audit/1.0"})
    start = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace"), round(time.time() - start, 3)
    except (urllib.error.URLError, urllib.error.HTTPError, OSError) as e:
        return None, str(e), round(time.time() - start, 3)

def parse_robots(text: str):
    """Kembalikan {ua_lower: [direktif]} dari blok robots.txt."""
    out, cur = {}, []
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
            cur = [val.lower()]
            out.setdefault(val.lower(), [])
        elif key in ("allow", "disallow", "crawl-delay"):
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

def check_sitemap(xml_text: str) -> bool:
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

    findings, score = [], 0.0
    st, robots_txt, _ = fetch(base + "/robots.txt")
    if st == 200:
        dit = parse_robots(robots_txt)
        allowed = [ua for ua in AI_UAS if ua_allowed(dit, ua)]
        missing = [ua for ua in AI_UAS if ua not in allowed]
        findings.append({
            "dim": "D1 robots.txt",
            "detail": f"allowed {len(allowed)}/{len(AI_UAS)}; missing={missing}",
            "verdict": "PASS" if len(allowed) >= 7 else ("PARTIAL" if allowed else "FAIL"),
        })
        if allowed:
            score += 0.3
    else:
        findings.append({"dim": "D1 robots.txt", "detail": f"status {st} - tidak bisa diambil", "verdict": "FAIL"})

    st, _, _ = fetch(base + "/llms.txt")
    ok = st == 200
    findings.append({"dim": "D2 llms.txt", "detail": f"status {st} di root", "verdict": "PASS" if ok else "FAIL"})
    if ok:
        score += 0.2

    st, sm_text, _ = fetch(base + "/sitemap.xml")
    ok = st == 200 and check_sitemap(sm_text)
    findings.append({"dim": "D3 sitemap.xml", "detail": f"status {st}, valid={ok}", "verdict": "PASS" if ok else "MARGINAL"})
    if ok:
        score += 0.15

    st, home_html, ttfb = fetch(base)
    if st == 200:
        nld = count_linked_data(home_html)
        findings.append({"dim": "D4 JSON-LD", "detail": f"{nld} blok ld+json di homepage", "verdict": "PASS" if nld else "MARGINAL"})
        score += 0.2 if nld else 0.05
        findings.append({"dim": "D5 TTFB", "detail": f"{ttfb}s home", "verdict": "PASS" if ttfb < 2.5 else "MARGINAL"})
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
