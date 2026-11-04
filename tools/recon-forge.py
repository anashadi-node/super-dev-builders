#!/usr/bin/env python3
"""recon-forge — satu alat, lima tahap: gate → bukti (REA) → kewajiban → paritas → laporan.

Kenapa alat ini ada
-------------------
Sebelum ini SDB punya REA (Zona A), punya `replica-skill` (Zona B), punya
`capture_web.py` + `fidelity_compare.py` — tetapi **tidak ada satu pun skrip** yang
memanggil REA. Akibatnya tahap 01B di `workflow_run.py` hanya memeriksa *apakah berkas
bukti ada*, bukan *apakah bukti itu benar-benar dipanen*. Alat ini menutup celah itu:
satu perintah menghasilkan bukti bertanda tangan hash, dan tahap pipeline menjadi
sesuatu yang dieksekusi, bukan diasumsikan.

Pembagian peran (kombinasi, bukan pilih salah satu)
---------------------------------------------------
  bukti/recon   : REA 6.8.0 (CLI, terpin, tanpa MCP)          -> Zona A
  gerbang       : scripts/gate_check.py (izin Gate #0)        -> wajib sebelum apa pun
  pengambil bukti: scripts/capture_web.py (Playwright)        -> hanya host allowed
  hakim paritas : scripts/fidelity_compare.py (deterministik) -> angka, bukan opini
  pembangun     : replica-skill (agen) ATAU craft-anything    -> Zona B, terpisah

Aturan yang ditegakkan alat ini (bukan imbauan):
  1. Tanpa `reports/<target>/gate0-verdict.json` ber-verdict PASS  -> berhenti (exit 2).
  2. Target harus slug sah, URL harus ada di `allowed_targets` manifest.
  3. Setiap panggilan alat dicatat ke `audit/audit-log.jsonl` (rantai hash).
  4. Semua keluaran disimpan ke disk dengan sha256 — laporan hanya menyebut yang ada.
  5. Yang tidak diukur ditulis UNPROVEN, tidak pernah dikarang jadi PASS.

Contoh
------
    python3 tools/recon-forge.py doctor
    python3 tools/recon-forge.py plan  --target forge-demo --kind web
    python3 tools/recon-forge.py chain --target forge-demo \\
        --original-url http://127.0.0.1:8201/ --rebuilt-url http://127.0.0.1:8202/

Exit: 0 sukses · 2 gate/argumen tak sah · 3 mesin tidak terpasang · 4 artefak kurang
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
REA_WRAPPER = REPO / "scripts" / "rea"
AUDIT_LOG = REPO / "audit" / "audit-log.jsonl"
REA_PIN = "6.8.0"

# Mesin yang boleh dipakai per jenis target. `effects` disalin dari deklarasi REA
# (rea capabilities) supaya pembaca tahu apa yang akan terjadi sebelum menjalankan.
PLANS: dict[str, list[dict]] = {
    "web": [
        {"stage": "01B.recon", "engine": "rea",
         "ops": ["list-browser-targets", "analyze-web-bundle", "capture-web-screenshot"],
         "effects": ["may_access_network", "may_write_filesystem"]},
        {"stage": "01B.capture", "engine": "sdb",
         "ops": ["capture_web.py"], "effects": ["may_access_network", "may_write_filesystem"]},
        {"stage": "09.parity", "engine": "sdb",
         "ops": ["fidelity_compare.py"], "effects": ["may_write_filesystem"]},
    ],
    "native": [
        {"stage": "01B.recon", "engine": "rea",
         "ops": ["analyze", "decompile-all"], "effects": ["may_write_filesystem"]},
        {"stage": "01B.capture", "engine": "sdb",
         "ops": ["(manual: tangkapan UI milik sendiri)"], "effects": []},
        {"stage": "09.parity", "engine": "sdb",
         "ops": ["fidelity_compare.py"], "effects": ["may_write_filesystem"]},
    ],
    "artifact": [
        {"stage": "01B.recon", "engine": "rea",
         "ops": ["analyze-javascript-application", "analyze-web-bundle"],
         "effects": ["may_access_network", "may_write_filesystem"]},
        {"stage": "09.parity", "engine": "sdb",
         "ops": ["fidelity_compare.py"], "effects": ["may_write_filesystem"]},
    ],
}


class ForgeError(RuntimeError):
    """Kegagalan yang sudah punya kode keluar pasti (bukan crash)."""

    def __init__(self, msg: str, code: int = 1):
        super().__init__(msg)
        self.code = code


# --------------------------------------------------------------------------- util
def now_iso() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def stamp() -> str:
    return dt.datetime.now().strftime("%Y%m%dT%H%M%S")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_tree(root: Path) -> str:
    """Digest deterministik direktori artefak: relpath + isi tiap berkas, urut nama.

    Tanpa ini artefak direktori (mis. hasil `decompile-all`) masuk manifest dengan
    sha256 null — jejak audit jadi tidak bisa membuktikan isinya tidak berubah.
    """
    h = hashlib.sha256()
    for p in sorted(x for x in root.rglob("*") if x.is_file()):
        h.update(p.relative_to(root).as_posix().encode("utf-8"))
        h.update(bytes.fromhex(sha256_file(p)))
    return h.hexdigest()


def tree_bytes(root: Path) -> int:
    return sum(p.stat().st_size for p in root.rglob("*") if p.is_file())


def stamp_artifact(art: dict) -> None:
    """Isi sha256 + bytes untuk artefak berkas maupun direktori (in-place)."""
    p = REPO / art["file"]
    if p.is_file():
        art["sha256"], art["bytes"] = sha256_file(p), p.stat().st_size
    elif p.is_dir():
        art["sha256"], art["bytes"] = sha256_tree(p), tree_bytes(p)
    else:
        art["sha256"], art["bytes"] = None, 0


def write_json(path: Path, data) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)
    return path


def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def repo_rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO))
    except ValueError:
        return str(path)


def audit(actor: str, tool: str, target: str, action: str, result: str, detail: str = "") -> None:
    """Catat ke rantai audit. Gagal mencatat = gagal menjalankan (aturan repo)."""
    if os.environ.get("SDB_AUDIT_DISABLED") == "1":  # hanya untuk uji hermetik
        return
    script = REPO / "tools" / "audit-log.py"
    if not script.exists():
        raise ForgeError("tools/audit-log.py tidak ada — rantai audit wajib", 3)
    cmd = [sys.executable, str(script), "append", "--log", str(AUDIT_LOG), "--actor", actor,
           "--tool", tool, "--target", target, "--action", action, "--result", result]
    if detail:
        cmd += ["--detail", detail[:500]]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        raise ForgeError(f"audit-log gagal: {proc.stderr.strip() or proc.stdout.strip()}", 1)


def gate_verdict(target: str) -> dict | None:
    return read_json(REPO / "reports" / target / "gate0-verdict.json")


def require_gate(target: str) -> dict:
    """Gate #0 wajib PASS. Kelas D (larangan) tidak pernah dilanjutkan."""
    verdict = gate_verdict(target)
    if not verdict:
        raise ForgeError(
            f"Gate #0 belum ada untuk '{target}'. Jalankan dulu:\n"
            f"  python3 scripts/gate_check.py --target {target}", 2)
    if str(verdict.get("target") or target) != target:
        raise ForgeError(
            f"verdict gate milik '{verdict.get('target')}', bukan '{target}' — tolak", 2)
    if str(verdict.get("verdict", "")).upper() != "PASS":
        raise ForgeError(
            f"Gate #0 = {verdict.get('verdict')} (fail={verdict.get('fail')}) — STOP", 2)
    return verdict


def allowed_urls(target: str) -> list[str]:
    try:
        import yaml  # hanya dipakai bila manifest ada (dependensi opsional)
    except ImportError:
        return []
    manifest = REPO / "evidence" / target / "authorization.yaml"
    if not manifest.exists():
        return []
    data = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
    return list((data.get("allowed_targets") or {}).get("urls") or [])


def require_url(target: str, url: str) -> None:
    allowed = allowed_urls(target)
    if not allowed:
        raise ForgeError(f"allowed_targets.urls kosong di evidence/{target}/authorization.yaml", 2)
    if not any(url.startswith(a.rstrip("/")) for a in allowed):
        raise ForgeError(f"TOLAK: {url} tidak ada di allowed_targets {allowed}", 2)


def run(cmd: list[str], timeout: int = 900, cwd: Path | None = None,
        env: dict | None = None) -> dict:
    started = time.time()
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                          cwd=str(cwd or REPO), env=env)
    return {"cmd": cmd, "exit": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr,
            "seconds": round(time.time() - started, 2)}


def run_tool(cmd: list[str], out_file: Path | None = None, timeout: int = 900,
             env: dict | None = None) -> dict:
    res = run(cmd, timeout=timeout, env=env)
    if out_file is not None:
        out_file.parent.mkdir(parents=True, exist_ok=True)
        payload = {"cmd": res["cmd"], "exit": res["exit"], "seconds": res["seconds"],
                   "stdout": res["stdout"], "stderr": res["stderr"]}
        write_json(out_file, payload)
    return res


def rea_version() -> str | None:
    if not REA_WRAPPER.exists():
        return None
    try:
        res = run([str(REA_WRAPPER), "--help"], timeout=120)
    except (OSError, subprocess.SubprocessError):
        return None
    m = re.search(r"rea@(\d+\.\d+\.\d+)", res["stdout"] or "")
    return m.group(1) if m else None


# Node: REA mensyaratkan patch minimum per lini (26.12.1 / 24.22.1 / 22.23.4).
# Hermes membawa node 26.7.0 yang GAGAL syarat itu, jadi alat ini mencari node yang
# memenuhi syarat secara terpisah dan menyerahkannya lewat REA_NODE_BIN — tanpa
# menyentuh node milik Hermes (mengubah PATH global bisa mematikan agen lain).
NODE_MIN = {22: (22, 23, 4), 24: (24, 22, 1), 26: (26, 12, 1), 28: (28, 0, 0)}


def ver_tuple(text: str | None):
    m = re.search(r"v?(\d+)\.(\d+)\.(\d+)", text or "")
    return tuple(int(x) for x in m.groups()) if m else None


def node_ok(version: str | None) -> bool:
    got = ver_tuple(version)
    if not got:
        return False
    floor = NODE_MIN.get(got[0])
    return bool(floor and got >= floor)


def rea_node() -> tuple[str | None, str | None]:
    cands: list[Path] = []
    for base in (Path.home() / ".local" / "opt", Path.home() / ".hermes" / "tools"):
        cands += sorted(base.glob("node-v*/bin/node")) + sorted(base.glob("node-*/bin/node"))
    system = shutil.which("node")
    if system:
        cands.append(Path(system))
    best: tuple[str, str] | None = None
    for cand in cands:
        if not cand.exists():
            continue
        try:
            ver = subprocess.run([str(cand), "-v"], capture_output=True, text=True,
                                 timeout=20).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            continue
        cur = ver_tuple(ver)
        prev = ver_tuple(best[1]) if best else None
        if cur and node_ok(ver) and (prev is None or cur > prev):
            best = (str(cand), ver)
    return best or (None, None)


def ghidra_home() -> Path | None:
    for base in (Path.home() / ".local" / "opt", Path.home() / "opt", Path("/opt")):
        for cand in sorted(base.glob("ghidra_*_PUBLIC"), reverse=True):
            if (cand / "support" / "analyzeHeadless").exists():
                return cand
    return None


def jdk_ok(home: Path) -> bool:
    """JDK dianggap ada hanya bila benar-benar utuh.

    Instalasi terpotong tetap meninggalkan `bin/java` berukuran 0 byte dan `release`
    kosong; tanpa cek ini doctor menyatakan "siap recon-biner" lalu REA menolak di
    tengah jalan dengan `provider_unavailable` yang membingungkan.
    """
    java = home / "bin" / "java"
    release = home / "release"
    try:
        if java.stat().st_size == 0 or release.stat().st_size == 0:
            return False
        text = release.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return "JAVA_VERSION=" in text


def jdk_home(roots=None) -> Path | None:
    if roots is None:
        roots = (Path.home() / ".local" / "opt", Path.home() / "opt", Path.home() / "tools",
                 Path("/usr/lib/jvm"), Path("/opt"))
    cands: list[Path] = []
    for base in roots:
        if not base.is_dir():
            continue
        cands += sorted(base.glob("jdk-2*"), reverse=True)
        cands += sorted(base.glob("jdk*"), reverse=True)
    for cand in cands:
        if jdk_ok(cand):
            return cand
    return None


def rea_env() -> dict:
    """Env untuk REA: node yang memenuhi syarat, Ghidra dan JDK bila ada.

    Tidak mengubah PATH global: hanya proses REA yang melihat nilai ini.
    """
    env = dict(os.environ)
    node, _ = rea_node()
    if node:
        env["REA_NODE_BIN"] = node
    ghidra = ghidra_home()
    if ghidra and not env.get("GHIDRA_INSTALL_DIR"):
        env["GHIDRA_INSTALL_DIR"] = str(ghidra)
    jdk = jdk_home()
    if jdk:
        env["JAVA_HOME"] = str(jdk)
        env["PATH"] = f"{jdk / 'bin'}{os.pathsep}{env.get('PATH', '')}"
    return env


def allowed_paths(target: str) -> list[str]:
    try:
        import yaml
    except ImportError:
        return []
    manifest = REPO / "evidence" / target / "authorization.yaml"
    if not manifest.exists():
        return []
    data = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
    targets = data.get("allowed_targets") or {}
    out: list[str] = []
    for key in ("repos", "apps", "apk_ipa_binaries"):
        out += [str(p) for p in (targets.get(key) or [])]
    return out


def require_path(target: str, raw: str) -> Path:
    """Path harus berada DI DALAM akar yang diizinkan manifest (anti symlink-escape)."""
    path = Path(os.path.expanduser(raw)).resolve()
    if not path.exists():
        raise ForgeError(f"path tidak ada: {path}", 2)
    roots = [Path(os.path.expanduser(p)).resolve() for p in allowed_paths(target)]
    roots.append((REPO / "targets" / target).resolve())
    for root in roots:
        if path == root or str(path).startswith(str(root) + os.sep):
            return path
    raise ForgeError(f"TOLAK: {path} di luar akar izin {[repo_rel(r) for r in roots]}", 2)


def craft_bin() -> str | None:
    for name in ("craft-anything", "craft-anything-cli", "craft"):
        found = shutil.which(name)
        if found:
            return found
    return None


def chromium_bin() -> Path | None:
    base = Path.home() / ".cache" / "ms-playwright"
    for pattern in ("chromium-*/chrome-linux/chrome", "chromium-*/chrome-linux64/chrome",
                    "chromium_headless_shell-*/chrome-linux/headless_shell"):
        hits = sorted(base.glob(pattern))
        if hits:
            return hits[-1]
    return None


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


# --------------------------------------------------------------------------- doctor
def cmd_doctor(args) -> int:
    rea = {"found": REA_WRAPPER.exists(), "path": repo_rel(REA_WRAPPER), "version": rea_version(),
           "pin": REA_PIN, "healthy": None, "node": None, "doctor_detail": [], "checks": {}}
    if rea["found"]:
        try:
            res = run([str(REA_WRAPPER), "doctor", "--format", "json"], timeout=180,
                      env=rea_env())
            payload = json.loads(res["stdout"]) if res["stdout"].strip().startswith("{") else {}
            rea["healthy"] = bool(payload.get("healthy"))
            for chk in payload.get("scope_checks", []):
                rea["doctor_detail"].append({k: chk.get(k) for k in ("name", "ok", "detail")})
                if chk.get("name"):
                    rea["checks"][chk["name"]] = bool(chk.get("ok"))
                if chk.get("name") == "node":
                    rea["node"] = chk.get("detail")
                if chk.get("name") in ("ghidra", "ida", "hopper", "jeb", "kuna"):
                    rea.setdefault("providers", {})[chk["name"]] = {
                        "ok": chk.get("ok"), "detail": (chk.get("detail") or "")[:120]}
        except (subprocess.SubprocessError, json.JSONDecodeError, OSError):
            rea["healthy"] = None
    craftp = craft_bin()
    craft = {"found": bool(craftp), "path": craftp, "version": None, "note": ""}
    if craftp:
        try:
            craft["version"] = (run([craftp, "--version"], timeout=60)["stdout"] or "").strip()[:80]
        except (OSError, subprocess.SubprocessError):
            craft["note"] = "biner ada tapi --version gagal"
    else:
        craft["note"] = ("belum terpasang; pilot wajib dari rilis resmi + checksum, "
                         "bukan cargo install dari HEAD")
    chrome = chromium_bin()
    node_path, node_ver = rea_node()
    providers = rea.get("providers") or {}
    checks = rea.get("checks") or {}
    # Provider "ghidra ok" saja tidak cukup: decompile baru jalan bila JDK dan headless
    # juga sehat. `ghidra-java` config_drift adalah penyebab nyata `provider_unavailable`.
    blockers = sorted(k for k, ok in checks.items()
                      if not ok and k in ("ghidra", "ghidra-java", "ghidra-headless", "java", "node"))
    rea["blockers"] = blockers
    scripts = {name: (REPO / "scripts" / name).exists() for name in
               ("capture_web.py", "fidelity_compare.py", "gate_check.py")}
    gerbang = (REPO / "tools" / "gerbang-spec.py").exists()
    data = {
        "checked_at": now_iso(),
        "engines": {
            "rea": rea,
            "craft_anything": craft,
            "chromium": {"found": bool(chrome), "path": str(chrome) if chrome else None},
            "node": {"path": node_path, "version": node_ver, "satisfies_rea": node_ok(node_ver)},
            "decompiler_providers": providers,
            "sdb_scripts": scripts,
            "gerbang_spec": gerbang,
        },
        "verdict": {
            "recon_ready": bool(rea["found"] and rea["version"] == REA_PIN and chrome),
            "parity_ready": bool(all(scripts.values()) and chrome),
            "native_ready": bool(rea["found"] and any(p.get("ok") for p in providers.values())
                                 and not blockers),
            "rebuild_ready": bool(rea["found"] and (craft["found"])),
            "honest_note": ("craft_anything belum ada = Zona B hanya lewat replica-skill (agen); "
                            "rea healthy=false berarti sebagian operasi bisa menolak jalan"),
        },
    }
    audit("D1", "recon-forge", "-", "doctor", "ok",
          f"rea={rea['version']} craft={bool(craftp)} chromium={bool(chrome)}")
    if args.json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        e = data["engines"]
        print(f"REA          : {e['rea']['version'] or 'TIDAK ADA'} (pin {REA_PIN})"
              f" healthy={e['rea']['healthy']} node={e['rea']['node']}")
        print(f"Craft Anything: {e['craft_anything']['version'] or 'belum terpasang (opsional)'}")
        print(f"Chromium      : {e['chromium']['path'] or 'TIDAK ADA'}")
        print(f"Node (REA)    : {e['node']['version'] or 'TIDAK ADA'} "
              f"{e['node']['path'] or ''} memenuhi={e['node']['satisfies_rea']}")
        prov = e["decompiler_providers"] or {}
        print("Provider biner: " + (", ".join(f"{k}={'ok' if v['ok'] else 'tidak'}"
                                              for k, v in prov.items()) or "tidak ada"))
        print(f"Skrip SDB     : {e['sdb_scripts']}  gerbang-spec={e['gerbang_spec']}")
        if e["rea"].get("blockers"):
            print(f"Penghambat    : {', '.join(e['rea']['blockers'])} "
                  f"(provider akan menolak jalan sampai ini beres)")
        print(f"Siap recon-web={data['verdict']['recon_ready']} "
              f"recon-biner={data['verdict']['native_ready']} "
              f"paritas={data['verdict']['parity_ready']} "
              f"rebuild-combo={data['verdict']['rebuild_ready']}")
    return 0


# --------------------------------------------------------------------------- plan
def cmd_plan(args) -> int:
    verdict = gate_verdict(args.target)
    plan = {
        "target": args.target,
        "kind": args.kind,
        "created_at": now_iso(),
        "gate0": (verdict or {}).get("verdict", "MISSING"),
        "combination": {
            "evidence": "REA (Zona A) — hanya baca, tidak membangun",
            "gate": "SDB gate_check.py — izin sebelum tindakan",
            "capture": "SDB capture_web.py — Playwright, host terbatas",
            "parity": "SDB fidelity_compare.py — angka deterministik",
            "rebuild": "replica-skill (agen) atau craft-anything (opsional, pilot)",
        },
        "stages": PLANS[args.kind],
        "rules": [
            "tanpa Gate #0 PASS tidak ada tahap yang dijalankan",
            "evidence/<t>/ adalah Zona A: builder tidak membacanya (clone-policy)",
            "setiap tahap menulis artefak + sha256; laporan tidak mengarang",
        ],
    }
    out = REPO / "runs" / args.target / "recon-plan.json"
    write_json(out, plan)
    audit("D1", "recon-forge", args.target, "plan", "ok", f"kind={args.kind}")
    if args.json:
        print(json.dumps(plan, indent=2, ensure_ascii=False))
    else:
        print(f"rencana: {repo_rel(out)}  gate0={plan['gate0']}")
        for st in plan["stages"]:
            print(f"  {st['stage']:<16} engine={st['engine']:<5} ops={', '.join(st['ops'])}")
    return 0


# --------------------------------------------------------------------------- recon
def list_cdp_targets(port: int, timeout: float = 25.0) -> list[dict]:
    deadline = time.time() + timeout
    url = f"http://127.0.0.1:{port}/json/list"
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=3) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, OSError, json.JSONDecodeError):
            time.sleep(0.4)
    raise ForgeError(f"CDP di port {port} tidak menjawab dalam {timeout:.0f}s", 3)


def launch_browser(url: str, port: int, profile: Path) -> subprocess.Popen:
    chrome = chromium_bin()
    if not chrome:
        raise ForgeError("chromium Playwright tidak ditemukan", 3)
    profile.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen(
        [str(chrome), "--headless=new", "--no-sandbox", "--disable-dev-shm-usage",
         f"--remote-debugging-port={port}",
         f"--user-data-dir={profile}", "--no-first-run", "--no-default-browser-check",
         "--disable-gpu", "--hide-scrollbars", "--window-size=1440,900", url],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    return proc


def stop_browser(proc: subprocess.Popen) -> None:
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


def cmd_recon(args) -> int:
    require_gate(args.target)
    if args.kind == "native":
        return _recon_native(args)
    require_url(args.target, args.url)
    outdir = REPO / "evidence" / args.target / "rea"
    outdir.mkdir(parents=True, exist_ok=True)
    tag = stamp()
    port = args.cdp_port or free_port()
    profile = REPO / "evidence" / args.target / "rea" / f".profile-{port}"
    artifacts: list[dict] = []
    browser = launch_browser(args.url, port, profile)
    try:
        targets = list_cdp_targets(port)
        pages = [t for t in targets if t.get("type") == "page" and args.url.split("?")[0].rstrip("/")
                 in (t.get("url") or "")]
        if not pages:
            pages = [t for t in targets if t.get("type") == "page"]
        if not pages:
            raise ForgeError("tidak ada page target di browser", 3)
        target_id = pages[0]["id"]
        endpoint = f"http://127.0.0.1:{port}"

        bundle = outdir / f"{tag}-web-bundle.json"
        res = run_tool([str(REA_WRAPPER), "analyze-web-bundle", endpoint, target_id,
                        "--evidence_output", str(bundle), "--detail", "complete",
                        "--observation-ms", str(args.observation_ms), "--format", "json"],
                       out_file=outdir / f"{tag}-web-bundle.run.json", timeout=args.timeout,
                       env=rea_env())
        if res["exit"] != 0:
            raise ForgeError(f"analyze-web-bundle gagal: {res['stderr'][-400:] or res['exit']}", 5)
        artifacts.append({"op": "analyze-web-bundle", "file": repo_rel(bundle)})

        shot = outdir / f"{tag}-screenshot.json"
        res = run_tool([str(REA_WRAPPER), "capture-web-screenshot", endpoint, target_id,
                        "--format", "json"],
                       out_file=outdir / f"{tag}-screenshot.run.json", timeout=args.timeout,
                       env=rea_env())
        if res["exit"] == 0 and res["stdout"].strip():
            shot.write_text(res["stdout"], encoding="utf-8")
            artifacts.append({"op": "capture-web-screenshot", "file": repo_rel(shot)})
    finally:
        stop_browser(browser)
        shutil.rmtree(profile, ignore_errors=True)

    for art in artifacts:
        stamp_artifact(art)
    manifest = {
        "tool": "recon-forge", "stage": "01B.recon", "engine": f"rea@{rea_version()}",
        "target": args.target, "url": args.url, "at": now_iso(), "cdp_port": port,
        "artifacts": artifacts,
        "unknowns": [] if len(artifacts) == 2 else ["screenshot tidak terbentuk"],
        "verified": len(artifacts) == 2,
    }
    write_json(outdir / "manifest.json", manifest)
    audit("D1", "rea", args.target, "recon", "ok" if manifest["verified"] else "partial",
          f"artefak={len(artifacts)}")
    if args.json:
        print(json.dumps(manifest, indent=2, ensure_ascii=False))
    else:
        print(f"recon {args.target}: {len(artifacts)}/2 artefak → {repo_rel(outdir / 'manifest.json')}")
        for art in artifacts:
            print(f"  - {art['op']}: {art['file']} ({art['bytes']} B)")
    return 0 if manifest["verified"] else 4


def _recon_native(args) -> int:
    """Jalur non-web: biner/firmware lewat `rea inspect` (dan `decompile-all` opsional).

    Beda dari web: bukti tidak datang dari browser, tapi dari provider decompiler.
    Tanpa provider (Ghidra/IDA/Hopper/Juna) REA menolak — dan alat ini TIDAK
    berpura-pura berhasil: exit 5 + pesan penyebab yang bisa ditindaklanjuti.
    """
    if not args.path:
        raise ForgeError("kind native butuh --path <biner|folder>", 2)
    target_path = require_path(args.target, args.path)
    outdir = REPO / "evidence" / args.target / "rea"
    outdir.mkdir(parents=True, exist_ok=True)
    tag = stamp()
    snapshot = outdir / f"{tag}-analysis.snapshot"
    inspect_out = outdir / f"{tag}-inspect.json"
    res = run_tool([str(REA_WRAPPER), "inspect", str(target_path), "--snapshot", str(snapshot),
                    "--format", "json"],
                   out_file=outdir / f"{tag}-inspect.run.json", timeout=args.timeout,
                   env=rea_env())
    artifacts: list[dict] = []
    provider_block: str | None = None
    if res["exit"] != 0:
        try:
            err = json.loads(res["stdout"]).get("error", "")
        except json.JSONDecodeError:
            err = res["stderr"] or f"exit {res['exit']}"
        detail = res["stdout"][:400] if "provider_unavailable" in (res["stdout"] or "") else ""
        provider_block = f"{err} {detail}".strip()
    else:
        inspect_out.write_text(res["stdout"], encoding="utf-8")
        artifacts.append({"op": "inspect", "file": repo_rel(inspect_out)})
        if args.decompile:
            dec_dir = outdir / f"{tag}-decompiled"
            dec_cmd = [str(REA_WRAPPER), "decompile-all", str(target_path),
                       "--output", str(dec_dir)]
            if args.decompile_limit:
                dec_cmd += ["--limit", str(args.decompile_limit)]
            dec = run_tool(dec_cmd, out_file=outdir / f"{tag}-decompile-all.run.json",
                           timeout=args.timeout, env=rea_env())
            if dec["exit"] == 0:
                manifest_file = dec_dir / "manifest.json"
                artifacts.append({"op": "decompile-all",
                                  "file": repo_rel(manifest_file if manifest_file.exists()
                                                   else dec_dir)})
            else:
                provider_block = (dec["stderr"] or dec["stdout"])[-400:]

    for art in artifacts:
        stamp_artifact(art)
    verified = bool(artifacts) and provider_block is None
    manifest = {
        "tool": "recon-forge", "stage": "01B.recon", "kind": "native",
        "engine": f"rea@{rea_version()}", "target": args.target,
        "path": repo_rel(target_path), "at": now_iso(),
        "provider": (read_json(snapshot / "analysis.json") or {}).get("provider")
        if snapshot.exists() else None,
        "artifacts": artifacts,
        "unknowns": ([f"provider tidak tersedia: {provider_block}"] if provider_block else []),
        "verified": verified,
    }
    write_json(outdir / "manifest.json", manifest)
    audit("D1", "rea", args.target, "recon-native", "ok" if verified else "blocked",
          f"artefak={len(artifacts)}")
    if provider_block:
        print(f"BLOCKED: {provider_block}", file=sys.stderr)
        print("  pasang provider (Ghidra 12.1.x + JDK 21) lalu set GHIDRA_INSTALL_DIR,\n"
              "  atau ulangi dengan --provider lain. Bukti tidak dikarang.", file=sys.stderr)
        return 5
    print(f"recon native {args.target}: {len(artifacts)} artefak → "
          f"{repo_rel(outdir / 'manifest.json')}")
    for art in artifacts:
        print(f"  - {art['op']}: {art['file']} ({art['bytes']} B)")
    return 0


# --------------------------------------------------------------------------- parity
def mean_coverage(rows) -> float | None:
    """Rata-rata coverage atas dimensi yang BENAR-BENAR terukur (None tidak dihitung 0)."""
    measured = [float(r["coverage"]) for r in rows
                if isinstance(r, dict) and r.get("coverage") is not None]
    return round(sum(measured) / len(measured), 4) if measured else None


def capture_runner() -> list[str]:
    """capture_web.py butuh playwright; host ini menyediakannya lewat uv (pin 1.63.0)."""
    probe = subprocess.run([sys.executable, "-c", "import playwright"], capture_output=True)
    if probe.returncode == 0:
        return [sys.executable]
    return ["uv", "run", "--with", "playwright==1.63.0", "python"]


def cmd_parity(args) -> int:
    require_gate(args.target)
    for url in (args.original_url, args.rebuilt_url):
        if url:
            require_url(args.target, url)
    out = REPO / "reports" / args.target / "fidelity.json"
    cap_root = REPO / "evidence" / args.target / "capture"

    if args.original_url and args.rebuilt_url:
        for label, url in (("original", args.original_url), ("rebuilt", args.rebuilt_url)):
            res = run_tool([*capture_runner(), "scripts/capture_web.py", "--target", args.target,
                            "--url", url, "--out", str(cap_root / label)],
                           out_file=REPO / "runs" / args.target / f"capture-{label}.run.json",
                           timeout=args.timeout)
            if res["exit"] != 0:
                raise ForgeError(f"capture {label} gagal: {res['stderr'][-400:]}", 5)
        original, rebuilt = cap_root / "original", cap_root / "rebuilt"
    elif args.original and args.rebuilt:
        original, rebuilt = Path(args.original), Path(args.rebuilt)
    else:
        raise ForgeError("butuh --original-url/--rebuilt-url atau --original/--rebuilt (folder capture)", 2)

    res = run_tool([sys.executable, "scripts/fidelity_compare.py", "--target", args.target,
                    "--original", str(original), "--rebuilt", str(rebuilt), "--out", str(out)],
                   out_file=REPO / "runs" / args.target / "fidelity.run.json", timeout=args.timeout)
    if res["exit"] != 0 or not out.exists():
        raise ForgeError(f"fidelity_compare gagal: {res['stderr'][-400:] or res['exit']}", 5)
    data = read_json(out) or {}
    rows = data if isinstance(data, list) else (data.get("dimensions") or data.get("rows") or [])
    measured = [r for r in rows if isinstance(r, dict) and r.get("coverage") is not None]
    score = mean_coverage(rows)
    summary = {"target": args.target, "at": now_iso(), "engine": "sdb:fidelity_compare",
               "dimensions_measured": len(measured), "dimensions_total": len(rows),
               "mean_coverage": score, "artifact": repo_rel(out),
               "sha256": sha256_file(out), "rows": rows}
    write_json(REPO / "reports" / args.target / "parity-summary.json", summary)
    audit("D7", "fidelity_compare", args.target, "parity", "ok",
          f"coverage={score} dimensi={len(measured)}/{len(rows)}")
    print(json.dumps({k: summary[k] for k in
                      ("engine", "dimensions_measured", "dimensions_total", "mean_coverage",
                       "artifact")}, indent=2))
    return 0


# --------------------------------------------------------------------------- report
STAGE_FILES = {
    "01A.gate0": "reports/{t}/gate0-verdict.json",
    "01B.recon": "evidence/{t}/rea/manifest.json",
    "01B.capture": "evidence/{t}/capture/rebuilt/capture.json",
    "09.parity": "reports/{t}/parity-summary.json",
}


def cmd_report(args) -> int:
    t = args.target
    stages = []
    for name, pattern in STAGE_FILES.items():
        rel = pattern.format(t=t)
        path = REPO / rel
        exists = path.exists()
        entry = {"stage": name, "artifact": rel, "present": exists,
                 "sha256": sha256_file(path) if exists else None}
        if name == "01A.gate0":
            entry["status"] = (read_json(path) or {}).get("verdict", "MISSING") if exists else "MISSING"
        elif name == "01B.recon":
            man = read_json(path) or {}
            entry["status"] = "VERIFIED" if man.get("verified") else ("PARTIAL" if exists else "MISSING")
            entry["at"] = man.get("at")
            entry["engine"] = man.get("engine")
        elif name == "09.parity":
            par = read_json(path) or {}
            entry["status"] = "MEASURED" if par.get("mean_coverage") is not None else "UNPROVEN"
            entry["mean_coverage"] = par.get("mean_coverage")
        else:
            entry["status"] = "PRESENT" if exists else "MISSING"
        stages.append(entry)

    unknowns = []
    if not (REPO / f"evidence/{t}/capture/rebuilt/capture.json").exists():
        unknowns.append("capture rebuild belum ada — paritas hanya bisa diukur setelah ada hasil bangun")
    if not (REPO / f"reconstruction/{t}/SPEC.md").exists():
        unknowns.append("SPEC belum ada — gerbang G1 (gerbang-spec) belum bisa dijalankan")

    ladder = {
        "evidence_collected": all(s["status"] in ("VERIFIED", "PARTIAL") for s in stages if s["stage"] == "01B.recon"),
        "parity_measured": any(s["stage"] == "09.parity" and s["status"] == "MEASURED" for s in stages),
        "release_ready": False,
    }
    payload = {"target": t, "at": now_iso(), "tool": "recon-forge", "stages": stages,
               "unknowns": unknowns, "ladder": ladder,
               "honest_note": "release_ready selalu false di sini: rilis butuh G3 + approval manusia"}
    out = REPO / "reports" / t / "recon-forge-report.json"
    write_json(out, payload)

    md = [f"# Laporan recon-forge — {t}", "", f"Dibuat: {payload['at']}", "",
          "| Tahap | Status | Artefak | sha256 |", "|---|---|---|---|"]
    for s in stages:
        md.append(f"| {s['stage']} | {s['status']} | `{s['artifact']}` | "
                  f"`{(s['sha256'] or '-')[:12]}` |")
    md += ["", "## Yang belum diketahui", ""]
    md += [f"- {u}" for u in unknowns] or ["- (tidak ada)"]
    md += ["", "## Tangga", ""]
    md += [f"- {k}: **{v}**" for k, v in ladder.items()]
    (REPO / "reports" / t / "recon-forge-report.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    audit("D8", "recon-forge", t, "report", "ok", f"stages={len(stages)}")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


# --------------------------------------------------------------------------- build
def cmd_build(args) -> int:
    require_gate(args.target)
    if args.engine == "craft":
        binary = craft_bin()
        if not binary:
            print("Craft Anything belum terpasang. Jalur pilot (jangan cargo install dari HEAD):\n"
                  "  1) unduh rilis resmi v0.3.0 (aset linux-x86_64) + SHA256SUMS\n"
                  "  2) verifikasi checksum, pasang ke ~/.local/opt/craft-anything/0.3.0/\n"
                  "  3) ulangi perintah ini dengan --engine craft", file=sys.stderr)
            audit("D4", "craft-anything", args.target, "build", "blocked", "biner tidak ada")
            return 3
        print(f"craft-anything: {binary} (jalankan manual: study → build → check; "
              "output wajib di targets/<t>/ dan tidak boleh menyentuh evidence/ZX")
        audit("D4", "craft-anything", args.target, "build", "manual", str(binary))
        return 0
    spec = REPO / "reconstruction" / args.target / "SPEC.md"
    if not spec.exists():
        raise ForgeError(f"SPEC belum ada: {repo_rel(spec)} — jalankan gerbang G1 dulu", 2)
    res = run([sys.executable, "tools/gerbang-spec.py", str(spec),
               "--verdict", f"reports/{args.target}/g1-verdict.json"], timeout=600)
    if res["exit"] != 0:
        raise ForgeError(f"G1 belum lolos (exit {res['exit']}): {res['stderr'][-300:]}", 2)
    print("G1 PASS. Bangun lewat skill replica-skill-pipeline (builder tidak membaca evidence/).")
    audit("D4", "replica-skill", args.target, "build", "ready", "G1 PASS")
    return 0


# --------------------------------------------------------------------------- chain
def cmd_chain(args) -> int:
    steps = []
    try:
        require_gate(args.target)
        steps.append(("gate0", "PASS"))
        cmd_recon(argparse.Namespace(target=args.target, url=args.original_url, kind="web",
                                     cdp_port=None, observation_ms=args.observation_ms,
                                     timeout=args.timeout, json=False))
        steps.append(("recon", "OK"))
        if args.original_url and args.rebuilt_url:
            cmd_parity(argparse.Namespace(target=args.target, original_url=args.original_url,
                                          rebuilt_url=args.rebuilt_url, original=None, rebuilt=None,
                                          timeout=args.timeout))
            steps.append(("parity", "OK"))
        cmd_report(argparse.Namespace(target=args.target))
        steps.append(("report", "OK"))
    except ForgeError as exc:
        print(f"STOP: {exc}", file=sys.stderr)
        return exc.code
    print("rantai selesai:", " → ".join(f"{k}:{v}" for k, v in steps))
    return 0


# --------------------------------------------------------------------------- cli
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="recon-forge",
        description="Orkestrator copy-cloning: Gate #0 → bukti REA → paritas → laporan")
    sub = ap.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("doctor", help="deteksi mesin yang benar-benar ada")
    d.add_argument("--json", action="store_true")
    d.set_defaults(func=cmd_doctor)

    p = sub.add_parser("plan", help="rencana bertahap (tidak mengeksekusi apa pun)")
    p.add_argument("--target", required=True)
    p.add_argument("--kind", choices=sorted(PLANS), default="web")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_plan)

    r = sub.add_parser("recon", help="panen bukti dengan REA (browser CDP milik sendiri)")
    r.add_argument("--target", required=True)
    r.add_argument("--url", default="")
    r.add_argument("--path", default="")
    r.add_argument("--kind", choices=("web", "native"), default="web")
    r.add_argument("--decompile", action="store_true")
    r.add_argument("--decompile-limit", type=int, default=0)
    r.add_argument("--cdp-port", type=int, default=0)
    r.add_argument("--observation-ms", type=int, default=800)
    r.add_argument("--timeout", type=int, default=600)
    r.add_argument("--json", action="store_true")
    r.set_defaults(func=cmd_recon)

    pa = sub.add_parser("parity", help="ukur paritas lewat fidelity_compare")
    pa.add_argument("--target", required=True)
    pa.add_argument("--original-url", default="")
    pa.add_argument("--rebuilt-url", default="")
    pa.add_argument("--original", default="")
    pa.add_argument("--rebuilt", default="")
    pa.add_argument("--timeout", type=int, default=900)
    pa.set_defaults(func=cmd_parity)

    rp = sub.add_parser("report", help="rangkum artefak jadi laporan + tangga status")
    rp.add_argument("--target", required=True)
    rp.set_defaults(func=cmd_report)

    b = sub.add_parser("build", help="bangun lewat replica-skill atau craft-anything")
    b.add_argument("--target", required=True)
    b.add_argument("--engine", choices=("replica", "craft"), default="replica")
    b.set_defaults(func=cmd_build)

    c = sub.add_parser("chain", help="gate → recon → paritas → laporan dalam satu perintah")
    c.add_argument("--target", required=True)
    c.add_argument("--original-url", required=True)
    c.add_argument("--rebuilt-url", default="")
    c.add_argument("--observation-ms", type=int, default=800)
    c.add_argument("--timeout", type=int, default=600)
    c.set_defaults(func=cmd_chain)

    args = ap.parse_args(argv)
    try:
        return args.func(args)
    except ForgeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return exc.code


if __name__ == "__main__":
    sys.exit(main())
