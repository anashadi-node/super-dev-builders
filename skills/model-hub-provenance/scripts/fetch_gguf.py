#!/usr/bin/env python3
"""Unduh GGUF dengan provenance (URL + ukuran + sha256) tanpa sudo, tanpa curl|sh.

Sumber default: ModelScope (hf-mirror.com me-redirect ke huggingface.co yang diblokir di host ini).
Verifikasi: sha256 wajib cocok sebelum file di-rename ke nama final.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time

MODELS_DIR = os.path.expanduser("~/models")
REPO = "Qwen/Qwen2.5-0.5B-Instruct-GGUF"
REVISION = "master"
FILE = "qwen2.5-0.5b-instruct-q4_k_m.gguf"
EXPECTED_SHA256 = "74a4da8c9fdbcd15bd1f6d01d621410d31c6fc00986f5eb687824e7b93d7a9db"
EXPECTED_SIZE = 491400032
URL = (
    f"https://www.modelscope.cn/api/v1/models/{REPO}/repo"
    f"?Revision={REVISION}&FilePath={FILE}"
)


def sha256_of(path: str, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            b = fh.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def main() -> int:
    os.makedirs(MODELS_DIR, exist_ok=True)
    final = os.path.join(MODELS_DIR, FILE)
    part = final + ".part"
    provenance = os.path.join(MODELS_DIR, "provenance.json")

    if os.path.exists(final):
        got = sha256_of(final)
        if got == EXPECTED_SHA256:
            print(f"SKIP sudah ada & sha256 cocok: {final}")
            return 0
        print(f"sha256 salah pada file final ({got[:16]}...) -> unduh ulang")

    t0 = time.time()
    # --proto/--proto-redir: redirect tak boleh turun ke http/ftp/file (sha256 tetap gerbang akhir)
    cmd = ["curl", "-L", "--proto", "=https", "--proto-redir", "=https", "--fail", "--retry", "3",
           "--max-time", "3600", "-o", part, URL]
    print("unduh:", URL)
    rc = subprocess.run(cmd, timeout=3700).returncode
    if rc != 0:
        print(f"GAGAL unduh rc={rc}")
        return rc
    dt = time.time() - t0

    size = os.path.getsize(part)
    got = sha256_of(part)
    ok_size, ok_hash = size == EXPECTED_SIZE, got == EXPECTED_SHA256
    print(f"size={size} expected={EXPECTED_SIZE} ok={ok_size}")
    print(f"sha256={got}\n       ok={ok_hash}  ({dt:.1f}s, {size / 1e6 / max(dt, 1e-9):.1f} MB/s)")
    if not (ok_size and ok_hash):
        print("VERIFIKASI GAGAL -> file .part TIDAK diaktifkan")
        return 2

    os.replace(part, final)
    rec = {
        "path": final,
        "source": "modelscope",
        "repo": REPO,
        "revision": REVISION,
        "file": FILE,
        "sha256": got,
        "size_bytes": size,
        "downloaded_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "verified": True,
        "note": "huggingface.co & hf-mirror.com TIDAK dapat dijangkau dari host ini (redirect ke HF diblokir)",
    }
    with open(provenance, "w", encoding="utf-8") as fh:
        json.dump(rec, fh, indent=2)
    print("OK ->", final)
    print("provenance ->", provenance)
    return 0


if __name__ == "__main__":
    sys.exit(main())
