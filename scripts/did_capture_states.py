#!/usr/bin/python3
"""Tangkap state terautentikasi/diam dari target web loopback — bukti, bukan klaim.

Kenapa alat ini ada: handoff DID yang hanya memotret halaman pra-login membuat
`states` berhenti di PARTIAL. State kosong/error adalah tempat bug paling mahal
(data warga salah RT, tagihan hilang), jadi harus dibuktikan dengan respons nyata,
bukan disimpulkan dari nama fungsi.

Aturan yang dilekatkan pada alat ini:
  * hanya loopback (127.0.0.1/::1/localhost) — kecuali `--allow-remote` eksplisit,
    supaya investigasi tidak pernah menyentuh instance produksi;
  * kredensial dibaca dari env, tidak pernah ditulis ke berkas bukti;
  * keluaran diperiksa ulang: kalau ada satu nilai rahasia yang lolos ke JSON,
    alat gagal (exit 2) dan berkasnya dihapus.

Pemakaian:
  python3 scripts/did_capture_states.py --config platform/state_probes/<t>.json \
      --out runs/<t>/did/evidence/states-auth.json
"""
from __future__ import annotations

import argparse
import hashlib
import http.cookiejar
import json
import os
import re
import sys
import urllib.error
import urllib.request

LOOPBACK = ("127.0.0.1", "::1", "localhost")
TAKSIR_MARKER = ["Belum ada", "Tidak ada", "belum ada", "tidak ada", "kosong", "empty"]


def _isi_env(nilai: str) -> str:
    """Ganti ${VAR} dengan env; gagal keras bila kosong (jangan pernah pakai default)."""
    def sub(m: re.Match) -> str:
        nama = m.group(1)
        v = os.environ.get(nama, "")
        if not v:
            raise SystemExit(f"did_capture_states: env {nama} kosong — kredensial tidak boleh di-hardcode")
        return v

    return re.sub(r"\$\{([A-Z0-9_]+)\}", sub, str(nilai))


def _klien():
    jar = http.cookiejar.CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar)), jar


def _kepala_auth(role: dict, rahasia: list[str]) -> dict:
    """Header statis untuk target yang tidak punya endpoint login.

    Dashboard internal sering memakai token per peran (header), bukan sesi
    cookie. Tanpa jalur ini, state terautentikasi target semacam itu hanya bisa
    diklaim — persis yang dilarang kontrak DID.
    """
    auth = role.get("auth") or {}
    if not auth:
        return {}
    if auth.get("type", "header") != "header":
        raise SystemExit("did_capture_states: auth.type hanya 'header' yang didukung")
    nilai = _isi_env(auth["value"])
    rahasia.append(nilai)
    return {auth.get("name", "Authorization"): nilai}


def _minta(opener, url: str, method: str = "GET", body: dict | None = None, timeout: int = 20,
           headers: dict | None = None):
    data = None
    header = {"Accept": "text/html,application/json"}
    if headers:
        header.update(headers)
    if body is not None:
        data = json.dumps(body).encode()
        header["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=header)
    try:
        with opener.open(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def _loopback_saja(base: str, boleh_remote: bool) -> None:
    host = re.sub(r"^https?://", "", base).split("/")[0].split(":")[0]
    if host in LOOPBACK or boleh_remote:
        return
    raise SystemExit(f"did_capture_states: {host} bukan loopback — pakai --allow-remote bila memang diizinkan")


def tangkap(cfg: dict, boleh_remote: bool = False, timeout: int = 20,
            snap_dir: str | None = None) -> dict:
    base = cfg["base_url"].rstrip("/")
    _loopback_saja(base, boleh_remote)
    marker = cfg.get("empty_markers") or TAKSIR_MARKER
    hasil = {"schema": "sdb.did.states/1", "target": cfg.get("target"), "base_url": base,
             "roles": [], "anon": [], "error_probes": []}
    rahasia: list[str] = []

    for role in cfg.get("roles") or []:
        dasar = (role.get("base_url") or base).rstrip("/")
        _loopback_saja(dasar, boleh_remote)
        kepala = _kepala_auth(role, rahasia)
        if kepala:
            opener, jar = _klien()
            masuk = {"role": role["name"], "auth": role.get("auth", {}).get("type", "header"),
                     "login_status": None, "cookies": 0, "ok": None, "pages": []}
        else:
            email = _isi_env(role["email"]) if role.get("email") else _isi_env("${%s}" % role["email_env"])
            sandi = _isi_env(role["password"]) if role.get("password") else _isi_env("${%s}" % role["password_env"])
            rahasia += [email, sandi]
            opener, jar = _klien()
            login = cfg.get("login") or {"path": "/api/login", "method": "POST"}
            body = {"email": email, "password": sandi}
            status, teks = _minta(opener, dasar + login["path"], login.get("method", "POST"), body, timeout)
            masuk = {"role": role["name"], "login_status": status, "cookies": len(jar),
                     "ok": status == 200 and len(jar) > 0, "pages": []}
            if status != 200:
                masuk["pesan"] = teks[:200]
        for path in role.get("pages") or []:
            st, html = _minta(opener, dasar + path, timeout=timeout, headers=kepala)
            ketemu = sorted({m for m in marker if m in html})
            snap = None
            if snap_dir and st == 200 and not any(r and r in html for r in rahasia):
                nama = re.sub(r"[^a-z0-9]+", "-", f"{role['name']}{path}".lower()).strip("-") + ".html"
                os.makedirs(snap_dir, exist_ok=True)
                with open(os.path.join(snap_dir, nama), "w", encoding="utf-8") as fh:
                    fh.write(html)
                snap = nama
            masuk["pages"].append({"path": path, "status": st, "bytes": len(html),
                                   "sha256": hashlib.sha256(html.encode()).hexdigest(),
                                   "ditolak": st in (401, 403), "tr": html.count("<tr"),
                                   "snapshot": snap,
                                   "empty_markers": ketemu})
        # SPA: semua rute mengembalikan shell yang sama, jadi penanda "kosong" di HTML
        # berasal dari bundel JS, bukan dari state halaman. Jangan klaim kosong.
        unik = {x["sha256"] for x in masuk["pages"]}
        masuk["spa_shell"] = len(masuk["pages"]) > 1 and len(unik) == 1
        for x in masuk["pages"]:
            x["kosong"] = None if masuk["spa_shell"] else bool(x["empty_markers"])
        if kepala:
            masuk["ok"] = all(p["status"] == 200 for p in masuk["pages"]) and bool(masuk["pages"])
        masuk["denied"] = []
        for d in role.get("denied") or []:
            st, teks = _minta(opener, dasar + d["path"], timeout=timeout, headers=kepala)
            masuk["denied"].append({"path": d["path"], "status": st,
                                    "harap": d.get("expect_status", 403),
                                    "cocok": st == d.get("expect_status", 403),
                                    "bytes": len(teks)})
        for probe in role.get("error_probes") or []:
            st, teks = _minta(opener, dasar + probe["path"], probe.get("method", "POST"),
                              probe.get("body") or {}, timeout, headers=kepala)
            masuk.setdefault("error_probes", []).append(
                {"path": probe["path"], "method": probe.get("method", "POST"), "status": st,
                 "min_status": probe.get("expect_status_min", 400),
                 "cocok": st >= probe.get("expect_status_min", 400), "pesan": teks[:160]})
        hasil["roles"].append(masuk)

    for probe in cfg.get("anon") or []:
        opener, _ = _klien()
        st, html = _minta(opener, base + probe["path"], timeout=timeout)
        wajib = probe.get("expect_text") or []
        hasil["anon"].append({"path": probe["path"], "status": st,
                              "expect_status": probe.get("expect_status", 200),
                              "punya_teks": [w for w in wajib if w in html],
                              "cocok": st == probe.get("expect_status", 200)
                              and all(w in html for w in wajib)})

    mentah = json.dumps(hasil, ensure_ascii=False)
    bocor = [r for r in rahasia if r and r in mentah]
    hasil["redaction_ok"] = not bocor
    return hasil


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Tangkap state terautentikasi target loopback")
    p.add_argument("--config", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--allow-remote", action="store_true")
    p.add_argument("--timeout", type=int, default=20)
    p.add_argument("--snapshot-dir", help="simpan HTML 200 per halaman (bukti mentah)")
    a = p.parse_args(argv)

    cfg = json.load(open(a.config, encoding="utf-8"))
    hasil = tangkap(cfg, a.allow_remote, a.timeout, a.snapshot_dir)
    if not hasil["redaction_ok"]:
        print("did_capture_states: RAHASIA BOCOR ke keluaran — berkas tidak ditulis", file=sys.stderr)
        return 2
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as fh:
        json.dump(hasil, fh, indent=1, ensure_ascii=False)
    halaman = sum(len(r["pages"]) for r in hasil["roles"])
    kosong = sum(1 for r in hasil["roles"] for x in r["pages"] if x["kosong"])
    print(f"did_capture_states: {len(hasil['roles'])} peran, {halaman} halaman, {kosong} berstate kosong, "
          f"anon {sum(1 for x in hasil['anon'] if x['cocok'])}/{len(hasil['anon'])} cocok, "
          f"error probe {sum(1 for x in hasil['error_probes'] if x['cocok'])}/{len(hasil['error_probes'])} cocok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
