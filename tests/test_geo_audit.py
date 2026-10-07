"""Test geo-audit skill — offline (tanpa network): parser robots + generator."""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "skills", "geo-audit", "scripts"))

from geo_scan import check_sitemap, count_linked_data, crawl_delay, parse_robots, ua_allowed, valid_base


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


def test_parse_robots_grouped_user_agents():
    """RFC 9309: User-agent berurutan = satu grup; Disallow berlaku untuk SEMUA UA di grup."""
    d = parse_robots("User-agent: GPTBot\nUser-agent: ClaudeBot\nDisallow: /\n")
    assert not ua_allowed(d, "GPTBot")
    assert not ua_allowed(d, "ClaudeBot")


def test_parse_robots_groups_not_merged_across_rules():
    """Grup baru dimulai setelah ada baris aturan."""
    d = parse_robots("User-agent: GPTBot\nDisallow: /\nUser-agent: ClaudeBot\nAllow: /\n")
    assert not ua_allowed(d, "GPTBot")
    assert ua_allowed(d, "ClaudeBot")


def test_valid_base_rejects_non_http():
    """file:// dsb ditolak — cegah pembacaan file lokal lewat urllib."""
    assert valid_base("https://t.example")
    assert not valid_base("file:///etc")
    assert not valid_base("ftp://t.example")
    assert not valid_base("https://")


def test_check_sitemap_rejects_dtd_entities():
    bomb = '<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]><urlset>&a;</urlset>'
    assert not check_sitemap(bomb)
    assert check_sitemap('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"></urlset>')


def test_crawl_delay_and_linked_data():
    d = parse_robots("User-agent: *\nCrawl-delay: 30\n")
    assert crawl_delay(d, "GPTBot") == 30.0
    assert count_linked_data('<script type="application/ld+json">{}</script>') == 1


def test_cli_rejects_file_scheme():
    import subprocess
    script = os.path.join(os.path.dirname(__file__), "..", "skills", "geo-audit", "scripts", "geo_scan.py")
    r = subprocess.run([sys.executable, script, "file:///etc"], capture_output=True, text=True, timeout=30)
    assert r.returncode == 1
