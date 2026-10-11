#!/usr/bin/env python3
"""SDB Command Deck - local dashboard for the Super Dev Builders ecosystem.

Serves dashboard/ static UI + /api/state aggregated from the Hermes runtime:
profile configs (model/provider/fallback chain), daily health checks, git HEAD.
No secrets are read or served - only model ids and provider names.

Usage:
  python3 server.py                          # 127.0.0.1:8484
  python3 server.py --host 0.0.0.0           # LAN (HP / devices on same WiFi)
  python3 server.py --health-check           # one-shot PONG probe -> state/health.json
"""
import argparse
import datetime
import json, re
import os
import subprocess
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import yaml

import ws_api

REPO = Path(__file__).resolve().parent.parent  # portabel: bukan path hard-coded mesin ini
DASH = REPO / "dashboard"
STATE = DASH / "state"
HEALTH_FILE = STATE / "health.json"
PROFILES = Path.home() / ".hermes" / "profiles"
BIN = Path.home() / ".local" / "bin"

# (label, dir-name, role, divisions)
PROFILE_META = [
    ("Orchestrator", "cc-orchestrator", "Planning / Intake / Gate-0", "D0 D2"),
    ("Recon - Research", "cc-capture-forensics", "Research (GLM)", "D1"),
    ("Architect", "cc-architect", "Architecture (Sonnet)", "D3"),
    ("Builder - Frontend", "cc-frontend", "Frontend (GLM)", "D4"),
    ("Builder - Backend", "cc-builder", "Backend (DeepSeek)", "D5"),
    ("Reviewer - QA", "cc-reviewer-qa", "QA / E2E (Sonnet)", "D6 D7"),
    ("Security Governor", "cc-security-governor", "Security (Opus)", "D8"),
    ("Auditor", "auditor", "Audit (Opus/Sol)", "D9"),
    ("DevOps - Docs", "cc-devops-docs", "DevOps (DeepSeek)", "D10 D11"),
    ("Keamanan", "keamanan", "Safety / Privacy (Sonnet)", "Guard"),
]
HEALTH_MAX_AGE_S = 14 * 3600

MODEL_SHORT = {
    "z-ai/glm-5.3-flash": "GLM 5.3 Flash",
    "glm-5.3-flash": "GLM 5.3 Flash",
    "deepseek-flash": "DeepSeek V4.1 Flash",
    "claude-sonnet-5-5": "Sonnet 5.5",
    "claude-opus-5-5": "Opus 5.5",
    "gpt-5.6-sol": "GPT-5.6 Sol",
}
PROVIDER_URLS = {
    "tokenrouter": "api.tokenrouter.com",
    "tokenharbor": "tokenharbor.ai",
    "opencode-go": "opencode.ai/zen",
    "deepseek": "api.deepseek.com",
    "anthropic": "oauth",
    "openai-codex": "oauth",
}


def read_profile_cfg(dirname):
    p = PROFILES / dirname / "config.yaml"
    try:
        cfg = yaml.safe_load(p.read_text(encoding="utf-8"))
    except Exception:
        return None
    m = cfg.get("model") if isinstance(cfg, dict) else None
    m = m if isinstance(m, dict) else {}
    model = m.get("default")
    if not model:
        return None
    chain = []
    for fb in cfg.get("fallback_providers") or []:
        if isinstance(fb, dict) and fb.get("provider"):
            chain.append({"provider": fb["provider"], "model": fb.get("model", "")})
    return {"model": model, "provider": m.get("provider", ""), "chain": chain}


def load_health():
    try:
        d = json.loads(HEALTH_FILE.read_text())
        age = time.time() - float(d.get("ts", 0))
        if age < HEALTH_MAX_AGE_S:
            return d, age
    except Exception:
        pass
    return None, None


def read_head():
    try:
        r = subprocess.run(["git", "log", "--oneline", "-1"], cwd=REPO,
                           capture_output=True, text=True, timeout=5)
        return r.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def probe_profile(dirname):
    """One-shot live PONG lewat `hermes -p <profil> -z` (path absolut, env termuat)."""
    prompt = "Balas HANYA satu kata: PONG"
    hermes = str(Path.home() / ".local/bin/hermes")
    try:
        r = subprocess.run([hermes, "-p", dirname, "-z", prompt],
                           capture_output=True, text=True, timeout=90, env=ws_api.hermes_env())
        return r.returncode == 0 and "PONG" in (r.stdout or "")
    except Exception:
        return False


def cmd_health_check():
    STATE.mkdir(parents=True, exist_ok=True)
    out = {"ts": time.time(),
           "generated": datetime.datetime.now().isoformat(timespec="seconds")}
    for _label, dirname, _role, _div in PROFILE_META:
        t0 = time.time()
        ok = probe_profile(dirname)
        out[dirname] = {"ok": ok, "ms": int((time.time() - t0) * 1000),
                        "checked": datetime.datetime.now().isoformat(timespec="seconds")}
        print(("OK  " if ok else "FAIL"), dirname, out[dirname]["ms"], "ms")
    tmp = HEALTH_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(out, indent=1))
    tmp.replace(HEALTH_FILE)
    n_ok = sum(1 for k, v in out.items() if isinstance(v, dict) and v.get("ok"))
    print(f"health.json written: {n_ok}/{len(PROFILE_META)} OK")


def build_state():
    health, age = load_health()
    profiles = []
    for label, dirname, role, div in PROFILE_META:
        c = read_profile_cfg(dirname) or {}
        model = c.get("model", "-")
        chain = [{"provider": f["provider"], "model": MODEL_SHORT.get(f["model"], f["model"]),
                  "url": PROVIDER_URLS.get(f["provider"], "")} for f in c.get("chain", [])]
        h = (health or {}).get(dirname, {})
        if health is None:
            hstate = "unknown"
        else:
            hstate = "ok" if h.get("ok") else "fail"
        profiles.append({
            "id": dirname, "label": label, "role": role, "divisions": div,
            "model": MODEL_SHORT.get(model, model), "model_id": model,
            "provider": c.get("provider", "-"),
            "provider_url": PROVIDER_URLS.get(c.get("provider", ""), ""),
            "chain": chain, "health": hstate,
            "checked": h.get("checked", ""), "ms": h.get("ms"),
        })
    agents = {}
    try:
        agents = json.loads((DASH / "agents.json").read_text())
    except Exception:
        pass
    return {
        "generated": datetime.datetime.now().isoformat(timespec="seconds"),
        "head": read_head(),
        "profiles": profiles,
        "agents": agents,
        "health_age_h": None if age is None else round(age / 3600, 1),
    }


CTYPE = {"html": "text/html; charset=utf-8", "css": "text/css", "js": "text/javascript",
         "json": "application/json", "svg": "image/svg+xml", "png": "image/png",
         "ico": "image/x-icon", "woff2": "font/woff2"}


class Handler(BaseHTTPRequestHandler):
    server_version = "SDBDeck/1.0"

    def log_message(self, fmt, *args):  # quiet
        pass

    def _send_json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if not ws_api.handle(self, "POST", self._send_json):
            self.send_error(404)

    def do_HEAD(self):
        self.do_GET(head=True)

    def do_GET(self, head=False):
        path = self.path.split("?")[0]
        if not head and path.startswith("/api/ws/"):
            if ws_api.handle(self, "GET", self._send_json):
                return
        if path == "/monitor":
            path = "/monitor.html"
        if path == "/api/state":
            body = json.dumps(build_state(), ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            if not head:
                self.wfile.write(body)
            return
        rel = Path(path.lstrip("/") or "index.html")
        if ".." in rel.parts:
            self.send_error(403)
            return
        fp = DASH / rel
        # Allowlist ekstensi (CTYPE): kode .py/.pyc/dll tidak pernah disajikan.
        # resolve()+is_relative_to: symlink tidak boleh keluar dari dashboard/.
        try:
            inside = fp.resolve().is_relative_to(DASH.resolve())
        except (OSError, ValueError):
            inside = False
        if (not inside or not fp.is_file() or "state" in rel.parts
                or fp.suffix.lstrip(".") not in CTYPE):
            self.send_error(404)
            return
        data = fp.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", CTYPE.get(fp.suffix.lstrip("."), "text/plain"))
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")  # perubahan UI langsung terlihat
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.end_headers()
        if not head:
            self.wfile.write(data)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8484)
    ap.add_argument("--show-token", action="store_true")
    ap.add_argument("--health-check", action="store_true")
    args = ap.parse_args()
    if args.show_token:
        print(ws_api.get_token())
        return
    if args.health_check:
        cmd_health_check()
        return
    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    if args.host not in ("127.0.0.1", "localhost", "::1"):
        print("PERINGATAN: bind non-loopback — HTTP tanpa TLS; PIN & /api/state terlihat di jaringan. "
              "Pakai hanya di WiFi tepercaya.", file=sys.stderr)
    print(f"SDB Workspace on http://{args.host}:{args.port} (ctrl-c to stop)")
    httpd.serve_forever()


if __name__ == "__main__":
    main()
