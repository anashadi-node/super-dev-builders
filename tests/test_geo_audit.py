"""Test geo-audit skill — offline (tanpa network): parser robots + generator."""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "skills", "geo-audit", "scripts"))

from geo_scan import count_linked_data, parse_robots, ua_allowed  # noqa: E402

def test_parse_robots_aibot_blocked():
    """GPTBot dengan Disallow: / harus dilaporkan TIDAK diizinkan."""
    robots = 'User-agent: *\nAllow: /\n\nUser-agent: GPTBot\nDisallow: /\n'
    d = parse_robots(robots)
    assert not ua_allowed(d, "GPTBot"), "GPTBot disallow-all harus dianggap diblokir"

def test_parse_robots_aibot_allowed():
    """GPTBot dengan Allow: / diizinkan; UA tak disebut jatuh ke aturan '*'."""
    robots = 'User-agent: *\nAllow: /\n\nUser-agent: GPTBot\nAllow: /\n'
    d = parse_robots(robots)
    assert ua_allowed(d, "GPTBot")

def test_parse_robots_unlisted_locked():
    """robots.txt tanpa blok sama sekali → periksa '*' ketika UA tidak disebut."""
    robots = 'User-agent: *\nAllow: /\n'
    d = parse_robots(robots)
    assert ua_allowed(d, "ClaudeBot")  # UA tak disebut → mewarisi '*' yang Allow → True (semantik robots asli)

def test_generator_files_written(tmp_path):
    """geo_gen menghasilkan 3 file dengan konten yang diharapkan."""
    import subprocess
    script = os.path.join(os.path.dirname(__file__), "..", "skills", "geo-audit", "scripts", "geo_gen.py")
    out = str(tmp_path / "geo-out")
    r = subprocess.run(
        [sys.executable, script,
         "--site-name", "T", "--url", "https://t.example",
         "--description", "situs uji", "--pages", "/,/pricing",
         "--output", out],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr
    robots = open(os.path.join(out, "robots.txt")).read()
    assert "User-agent: GPTBot" in robots
    assert "Sitemap: https://t.example/sitemap.xml" in robots
    llms = open(os.path.join(out, "llms.txt")).read()
    assert llms.startswith("# T")
    schema = json.load(open(os.path.join(out, "schema_org.jsonld")))
    assert schema["@context"] == "https://schema.org"
    assert schema["@type"] == "Organization"
