#!/usr/bin/env python3
"""geo_gen.py — generator robots.txt / llms.txt / JSON-LD siap-pakai.

License: MIT.
"""
import argparse
import json
import os

AI_SEARCH_UA = "OAI-SearchBot ChatGPT-User PerplexityBot Perplexity-User Claude-SearchBot claude-web".split()
AI_TRAIN_UA = "GPTBot ClaudeBot anthropic-ai Google-Extended CCBot Applebot-Extended".split()

def gen_robots(domain, sitemap_url, allow_training=True):
    lines = [
        "User-agent: *", "Allow: /",
        "Disallow: /admin/", "Disallow: /account/", "Disallow: /api/",
        "",
        *[f"User-agent: {ua}" for ua in AI_SEARCH_UA], "Allow: /",
        "",
        # SEMUA bot training satu grup (RFC 9309). Dulu hanya GPTBot -> --no-training
        # membiarkan ClaudeBot/Google-Extended/CCBot/dll tetap boleh.
        *[f"User-agent: {ua}" for ua in AI_TRAIN_UA],
    ]
    if allow_training:
        lines.append("Allow: /")
    else:
        lines.append("Disallow: /")
    lines += [
        "",
        "Sitemap: " + sitemap_url,
        "",
    ]
    return "\n".join(lines)

def gen_llmstxt(site_name, description, pages):
    out = [f"# {site_name}", "", f"> {description}", "",
           "## Pages", ""]
    for path, title, url in pages:
        out.append(f"- [{title}]({url}): {path}")
    out.append("")
    return "\n".join(out)

def gen_jsonld_org(name, url, description):
    obj = {
        "@context": "https://schema.org",
        "@type": "Organization",
        "name": name,
        "url": url,
        "description": description,
    }
    # "</" -> "<\/": aman bila JSON-LD ditanam di <script>; tetap JSON valid.
    return json.dumps(obj, indent=2).replace("</", "<\\/")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--site-name", required=True)
    ap.add_argument("--url", required=True)
    ap.add_argument("--description", required=True)
    ap.add_argument("--allow-training", action="store_true", default=True)
    ap.add_argument("--no-training", dest="allow_training", action="store_false")
    ap.add_argument("--pages", required=True, help="comma-separated path list")
    ap.add_argument("--output", required=True, help="output folder")
    args = ap.parse_args()

    base = args.url.rstrip("/")
    os.makedirs(args.output, exist_ok=True)

    with open(os.path.join(args.output, "robots.txt"), "w") as f:
        f.write(gen_robots(base, base + "/sitemap.xml", args.allow_training))

    pages = [(p, p.strip("/").capitalize() or "Home", base + p)
             for p in ("/" + q.strip().lstrip("/") for q in args.pages.split(",") if q.strip())]
    with open(os.path.join(args.output, "llms.txt"), "w") as f:
        f.write(gen_llmstxt(args.site_name, args.description, pages))

    with open(os.path.join(args.output, "schema_org.jsonld"), "w") as f:
        f.write(gen_jsonld_org(args.site_name, base, args.description))

    print("created: robots.txt, llms.txt, schema_org.jsonld ->", args.output)
    return 0

if __name__ == "__main__":
    import sys
    sys.exit(main())
