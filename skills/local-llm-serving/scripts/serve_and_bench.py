#!/usr/bin/env python3
"""Serve llama-server (OpenAI-compatible) + bench parallel nyata → laporan JSON.

Menggantikan `serving-llms-vllm` (tidak bisa jalan tanpa GPU) dan `inference-sh-cli`
(wrapper SaaS pihak ketiga). Semua stdlib: urllib, subprocess (list argumen), json.

Jalankan:
  /usr/bin/python3 scripts/serve_and_bench.py --model ~/models/<file>.gguf --parallel 4 --tokens 64
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

PROMPT = "Ringkas dalam satu kalimat: mengapa cache memori penting untuk sistem produksi?"


def _require_loopback(url: str) -> None:
    """Tolak apa pun selain http(s)://127.0.0.1|localhost|<port lokal> (anti-SSRF + file://)."""
    u = urllib.parse.urlsplit(url)
    if u.scheme not in ("http", "https") or (u.hostname or "") not in ("127.0.0.1", "localhost", "::1"):
        raise ValueError(f"url harus menunjuk loopback lokal, ditolak: {url}")


def post_json(url: str, payload: dict, timeout: float = 300.0) -> tuple[int, dict]:
    # Fail-closed: urlopen() mendukung file:// — kunci ke loopback lokal untuk
    # cegah SSRF / baca file bila url kelak berasal dari input.
    _require_loopback(url)
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}
    )
    # nosemgrep: python.lang.security.audit.dynamic-urllib-use-detected.dynamic-urllib-use-detected
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, json.loads(resp.read().decode())


def get_json(url: str, timeout: float = 10.0):
    _require_loopback(url)
    # nosemgrep: python.lang.security.audit.dynamic-urllib-use-detected.dynamic-urllib-use-detected
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return resp.status, json.loads(resp.read().decode())


def rss_mb(pid: int) -> float | None:
    try:
        with open(f"/proc/{pid}/status", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("VmRSS:"):
                    return round(int(line.split()[1]) / 1024.0, 1)
    except OSError:
        return None
    return None


def chat(base: str, tokens: int, temperature: float = 0.0) -> dict:
    t0 = time.time()
    status, body = post_json(
        base + "/v1/chat/completions",
        {"model": "local", "messages": [{"role": "user", "content": PROMPT}],
         "max_tokens": tokens, "temperature": temperature},
    )
    dt = time.time() - t0
    usage = body.get("usage") or {}
    ct = usage.get("completion_tokens") or 0
    text = ((body.get("choices") or [{}])[0].get("message") or {}).get("content", "")
    return {"status": status, "wall_s": round(dt, 3), "completion_tokens": ct,
            "tok_per_s": round(ct / dt, 2) if dt > 0 and ct else None,
            "text_head": text[:160]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", default=os.path.expanduser("~/bin/llama-server"))
    ap.add_argument("--model", required=True)
    ap.add_argument("--parallel", type=int, default=4)
    ap.add_argument("--tokens", type=int, default=64)
    ap.add_argument("--ctx", type=int, default=2048)
    ap.add_argument("--threads", type=int, default=(os.cpu_count() or 4))
    ap.add_argument("--port", type=int, default=8091)
    ap.add_argument("--repeats", type=int, default=3,
                    help="jumlah pengulangan (host ini berbagi beban -> median lebih jujur)")
    ap.add_argument("--out", default="/tmp/local-llm-serving-report.json")
    a = ap.parse_args()

    if not os.path.exists(a.server):
        print(json.dumps({"error": f"server tidak ada: {a.server}"}))
        return 2
    if not os.path.exists(os.path.expanduser(a.model)):
        print(json.dumps({"error": f"model tidak ada: {a.model}"}))
        return 2

    base = f"http://127.0.0.1:{a.port}"
    ver = subprocess.run([a.server, "--version"], capture_output=True, text=True, timeout=60)
    # llama-server menulis versi ke STDERR; stdout saja membuat provenance "build=?".
    ver_lines = ((ver.stdout or "") + (ver.stderr or "")).strip().splitlines()
    build = ver_lines[1] if len(ver_lines) > 1 else (ver_lines[0] if ver_lines else "?")
    cmd = [a.server, "-m", os.path.expanduser(a.model), "-c", str(a.ctx), "-np", str(a.parallel),
           "-t", str(a.threads), "--host", "127.0.0.1", "--port", str(a.port), "--metrics"]
    t_start = time.time()
    # Log server ke berkas sementara, BUKAN PIPE: pipe yang tak dibaca penuh di 64 KB lalu
    # memblokir server (deadlock) pada --repeats besar.
    server_log = tempfile.TemporaryFile("w+", encoding="utf-8", errors="replace")
    proc = subprocess.Popen(cmd, stdout=server_log, stderr=subprocess.STDOUT, text=True)
    result: dict = {
        # metadata wajib kontrak bukti (docs/EVIDENCE_SCHEMA.md)
        "provenance": f"scripts/serve_and_bench.py; server={a.server}; build={build}",
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime()),
        "redaction_status": "clean",
        "status": "OBSERVED",
        "server": a.server, "model": os.path.expanduser(a.model),
        "parallel": a.parallel, "ctx": a.ctx, "threads": a.threads,
        "version_head": ver_lines[:3], "cmd": cmd,
    }
    try:
        deadline = time.time() + 180
        health = None
        while time.time() < deadline:
            if proc.poll() is not None:
                server_log.seek(0)
                out = server_log.read()
                result["error"] = "server mati sebelum siap"
                result["server_log_tail"] = out[-1200:]
                print(json.dumps(result, indent=2))
                return 3
            try:
                health = get_json(base + "/health")
                break
            except Exception:  # noqa: BLE001 — loop tunggu /health; galat apa pun = coba lagi, batas waktu di luar loop
                time.sleep(0.5)
        result["ready_seconds"] = round(time.time() - t_start, 2)
        result["health"] = health
        if not health:
            result["error"] = "timeout menunggu /health"
            print(json.dumps(result, indent=2))
            return 4

        result["models_endpoint"] = get_json(base + "/v1/models")[1]

        # Host ini berbagi beban (postgres/chrome) -> WAJIB multi-run + median, bukan single-shot.
        runs = []
        for i in range(a.repeats):
            single = chat(base, a.tokens)
            t0 = time.time()
            with ThreadPoolExecutor(max_workers=a.parallel) as ex:
                futs = [ex.submit(chat, base, a.tokens) for _ in range(a.parallel)]
                par = [f.result() for f in futs]
            wall = time.time() - t0
            total_tok = sum(p["completion_tokens"] for p in par)
            agg = round(total_tok / wall, 2) if wall else 0.0
            one = single.get("tok_per_s") or 0.0
            runs.append({
                "run": i + 1,
                "loadavg": [round(x, 2) for x in os.getloadavg()],
                "single": single,
                "parallel": {"n": a.parallel, "wall_s": round(wall, 3),
                             "total_completion_tokens": total_tok,
                             "aggregate_tok_per_s": agg,
                             "per_request_tok_per_s": [p["tok_per_s"] for p in par],
                             "all_http_200": all(p["status"] == 200 for p in par),
                             "sample_text": par[0]["text_head"]},
                "benefit_x": round(agg / one, 2) if one else None,
            })
            result["rss_mb_after_run%d" % (i + 1)] = rss_mb(proc.pid)
        result["runs"] = runs
        result["repeats"] = a.repeats

        def _med(vals):
            vals = sorted(v for v in vals if v)
            return round(statistics.median(vals), 2) if vals else None

        ones = [r["single"]["tok_per_s"] for r in runs]
        aggs = [r["parallel"]["aggregate_tok_per_s"] for r in runs]
        valid_runs = [r for r in runs if r["parallel"]["aggregate_tok_per_s"]]
        if not valid_runs:  # server tak melaporkan usage -> laporan jujur, bukan crash
            result["error"] = "tidak ada run dengan throughput valid (completion_tokens=0)"
            raise RuntimeError(result["error"])
        ones_v = [v for v in ones if v] or [0.0]
        benefits = [r["benefit_x"] for r in runs if r["benefit_x"] is not None] or [0.0]
        # representasi = run dengan throughput agregat terdekat ke median (bukan run terbaik)
        med_agg = statistics.median([v for v in aggs if v])
        rep = min(valid_runs,
                  key=lambda r: abs(r["parallel"]["aggregate_tok_per_s"] - med_agg))
        result["single"] = rep["single"]
        result["parallel_run"] = rep["parallel"]
        result["representative_run"] = rep["run"]
        result["single_tok_per_s"] = {"median": _med(ones), "min": min(ones_v), "max": max(ones_v)}
        result["aggregate_tok_per_s"] = {"median": _med(aggs), "min": min(aggs), "max": max(aggs)}
        result["batching_benefit_x"] = {"median": _med([r["benefit_x"] for r in runs]),
                                        "min": min(benefits),
                                        "max": max(benefits)}
        # klaim kuat: di SETIAP run, throughput agregat paralel > single (bukan hanya di run terbaik)
        result["continuous_batching_proven"] = all(
            r["parallel"]["aggregate_tok_per_s"] and r["single"]["tok_per_s"] and
            r["parallel"]["aggregate_tok_per_s"] > r["single"]["tok_per_s"] for r in runs)
        result["rss_mb_after_parallel"] = max(v for k, v in result.items()
                                             if k.startswith("rss_mb_after_run") and v)
    except RuntimeError:
        pass  # pesan sudah ada di result["error"]; laporan tetap ditulis di bawah
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            proc.kill()
        server_log.close()
    result["total_seconds"] = round(time.time() - t_start, 2)
    with open(a.out, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2)
    print(json.dumps(result, indent=2))
    print("report:", a.out)
    return 5 if result.get("error") else 0


if __name__ == "__main__":
    sys.exit(main())
