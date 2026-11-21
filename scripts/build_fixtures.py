#!/usr/bin/python3
"""Bangun fixture DID untuk profil `mobile` dan `desktop` (L3 statis, tanpa Java).

KENAPA ADA
----------
`platform/did_profiles.json` menyatakan 7 profil, tetapi benchmark hanya pernah
menyentuh `web` (e1-app) dan `binary` (elf-demo). Artinya klaim "DID mendukung
mobile/desktop" tak punya satu pun artefak yang bisa diperiksa — prosa, bukan bukti.

Fixture di sini **dibangun dari sumber yang ikut git**, bukan diunduh, supaya:
  - tidak ada lisensi pihak ketiga yang perlu divetting;
  - hash artefak bisa diverifikasi ulang (`--verify`) oleh siapa pun;
  - label ground truth bisa diambil dari sumber, bukan dari teks handoff.

BATAS JUJUR (jangan dihapus saat menyunting):
  - Mesin ini TIDAK punya JDK/JADX/apktool/MobSF/Ghidra. Karena itu fixture mobile
    memakai `AndroidManifest.xml` **teks** dan tidak memuat `classes.dex`: yang diuji
    adalah disiplin inventaris + bukti + handoff, BUKAN decompile DEX.
  - Fixture desktop adalah ELF x86-64 hasil gcc; tidak ada lapisan UI/GUI toolkit.

Pemakaian:
    python3 scripts/build_fixtures.py            # bangun semua fixture
    python3 scripts/build_fixtures.py --verify   # bangun ulang di tmp, bandingkan sha256
"""
from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
import tempfile
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EPOCH = 1_791_000_000  # 2026-10-06; dipakai agar zip tidak bergantung waktu build
ZIP_TIME = (2026, 11, 6, 9, 0, 0)
CC = "/usr/bin/gcc-13"
LD = "/usr/bin/ld.bfd"
CC_VERSION = "gcc-13 (Ubuntu 13.4.0-10ubuntu1) 13.4.0"
LD_VERSION = "GNU ld (GNU Binutils for Ubuntu) 2.46"
BUILD_ENV = {
    "LANG": "C",
    "LC_ALL": "C",
    "PATH": "/usr/bin:/bin",
    "SOURCE_DATE_EPOCH": str(EPOCH),
}

ANDROID_MANIFEST = """<?xml version="1.0" encoding="utf-8"?>
<!-- Fixture: manifest TEKS, bukan AXML biner (tidak ada aapt di mesin ini). -->
<manifest xmlns:android="http://schemas.android.com/apk/res/android"
    package="io.mini.demo" android:versionName="2.1.0" android:versionCode="21">
  <uses-permission android:name="android.permission.INTERNET"/>
  <uses-permission android:name="android.permission.CAMERA"/>
  <uses-sdk android:minSdkVersion="24" android:targetSdkVersion="34"/>
  <application android:label="Mini Demo" android:allowBackup="false">
    <activity android:name=".MainActivity" android:exported="true">
      <intent-filter>
        <action android:name="android.intent.action.MAIN"/>
        <category android:name="android.intent.category.LAUNCHER"/>
      </intent-filter>
    </activity>
    <activity android:name=".SettingsActivity" android:exported="false"/>
    <meta-data android:name="io.mini.UPDATE_URL"
               android:value="https://updates.mini.example/v1/android"/>
  </application>
</manifest>
"""

ANDROID_CONFIG = """{
  "api_base": "https://api.mini.example/v2",
  "storage": {"driver": "sqlite", "db": "mini.db", "dir": "files/"},
  "upload": {"endpoint": "https://upload.mini.example/v2/photo", "retry": 2}
}
"""

ANDROID_STRINGS = """<?xml version="1.0" encoding="utf-8"?>
<resources>
  <string name="app_name">Mini Demo</string>
  <string name="settings_title">Pengaturan</string>
</resources>
"""

ANDROID_NATIVE = r"""
/* Pustaka native fixture — dipakai untuk memberi bukti ELF di dalam APK. */
const char *mini_sign(const char *payload) { return payload ? "signed" : "unsigned"; }
int mini_size(void) { return 32; }
"""

DESKTOP_C = r"""
/* Fixture aplikasi desktop: alamat update, kanal IPC, dan penyimpanan lokal. */
#include <stdio.h>
#include <string.h>

static const char *UPDATE_URL = "https://updates.mini.example/v1/desktop";
static const char *UPDATE_CHANNEL = "stable";
static const char *IPC_SOCKET = "/tmp/mini-desktop.sock";
static const char *STORE_PATH = "~/.local/share/mini-desktop/mini.db";

const char *cek_update(void) { return UPDATE_URL; }
const char *kanal(void) { return UPDATE_CHANNEL; }
const char *alamat_ipc(void) { return IPC_SOCKET; }
const char *path_state(void) { return STORE_PATH; }

int main(void) {
    printf("mini-desktop 1.4.2\n");
    printf("update=%s channel=%s\n", cek_update(), kanal());
    printf("ipc=%s store=%s\n", alamat_ipc(), path_state());
    return 0;
}
"""

DESKTOP_INSTALLER = """#!/bin/sh
# Installer fixture — idempoten: salinan hanya ditulis bila hash berbeda.
set -eu
PREFIX="${PREFIX:-$HOME/.local/share/mini-desktop}"
SRC="$(dirname "$0")/desktop-mini"
mkdir -p "$PREFIX"
if [ -f "$PREFIX/desktop-mini" ] && cmp -s "$SRC" "$PREFIX/desktop-mini"; then
  echo "sudah terpasang: $PREFIX/desktop-mini"
  exit 0
fi
cp "$SRC" "$PREFIX/desktop-mini"
chmod 0755 "$PREFIX/desktop-mini"
echo "terpasang: $PREFIX/desktop-mini"
"""

DESKTOP_CHANNEL = """{
  "channel": "stable",
  "check_url": "https://updates.mini.example/v1/desktop/stable.json",
  "poll_seconds": 3600
}
"""


def _tolak_ancestor_symlink(path: str) -> None:
    """Tolak symlink pada setiap komponen path yang sudah ada."""
    absolut = os.path.abspath(path)
    sekarang = os.path.sep
    for bagian in absolut.split(os.path.sep)[1:]:
        sekarang = os.path.join(sekarang, bagian)
        if os.path.lexists(sekarang) and os.path.islink(sekarang):
            raise RuntimeError(f"path output fixture melewati symlink: {sekarang}")


def _tolak_symlink(root: str) -> None:
    """Tolak symlink/hardlink yang dapat keluar dari direktori build."""
    _tolak_ancestor_symlink(root)
    if not os.path.exists(root):
        return
    if not os.path.isdir(root):
        raise RuntimeError(f"output fixture bukan direktori: {root}")
    for akar, direktori, berkas in os.walk(root, followlinks=False):
        for nama in [*direktori, *berkas]:
            path = os.path.join(akar, nama)
            if os.path.islink(path):
                raise RuntimeError(f"output fixture memuat symlink: {path}")
            info = os.stat(path, follow_symlinks=False)
            if os.path.isfile(path) and info.st_nlink != 1:
                raise RuntimeError(f"output fixture memuat hardlink: {path}")


def _tulis(path: str, isi: str, mode: int = 0o644) -> None:
    _tolak_ancestor_symlink(os.path.dirname(path))
    if os.path.lexists(path):
        if os.path.islink(path):
            raise RuntimeError(f"output fixture tidak boleh symlink: {path}")
        if os.stat(path, follow_symlinks=False).st_nlink != 1:
            raise RuntimeError(f"output fixture tidak boleh hardlink: {path}")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(isi)
    os.chmod(path, mode)


def _zip_tree(src_dir: str, out_path: str, expected: set[str]) -> None:
    """Zip hanya input yang dikenal; tolak symlink dan berkas sisa/tersembunyi."""
    _tolak_symlink(src_dir)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    if os.path.exists(out_path):
        os.remove(out_path)
    nama = []
    for akar, _, berkas in os.walk(src_dir):
        for b in berkas:
            penuh = os.path.join(akar, b)
            nama.append((os.path.relpath(penuh, src_dir).replace(os.sep, "/"), penuh))
    aktual = {rel for rel, _ in nama}
    if aktual != expected:
        kurang = sorted(expected - aktual)
        ekstra = sorted(aktual - expected)
        raise RuntimeError(f"input APK tidak sesuai allowlist: kurang={kurang}, ekstra={ekstra}")
    with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for rel, penuh in sorted(nama):
            info = zipfile.ZipInfo(rel, date_time=ZIP_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            with open(penuh, "rb") as fh:
                zf.writestr(info, fh.read())


def _versi(path: str) -> str:
    """Ambil baris versi pertama tanpa bergantung locale mesin."""
    proc = subprocess.run(
        [path, "--version"], check=True, capture_output=True, text=True, env=BUILD_ENV
    )
    return proc.stdout.splitlines()[0]


def verify_toolchain() -> None:
    """Tolak build bila compiler/linker bukan toolchain fixture yang dikunci."""
    expected = ((CC, CC_VERSION), (LD, LD_VERSION))
    for path, version in expected:
        if not os.path.isfile(path) or not os.access(path, os.X_OK):
            raise RuntimeError(f"toolchain fixture tidak tersedia: {path}")
        actual = _versi(path)
        if actual != version:
            raise RuntimeError(
                f"versi toolchain fixture bergeser: {path}: {actual!r} != {version!r}"
            )


def _gcc(src: str, out: str, args: list[str]) -> None:
    verify_toolchain()
    src_dir = os.path.dirname(os.path.abspath(src))
    # GCC merekam source path dan DW_AT_comp_dir. Compile dari source directory,
    # lalu petakan keduanya ke path virtual tetap agar CWD/scratch path tidak bocor.
    peta = [
        f"-ffile-prefix-map={src_dir}=/build",
        f"-fdebug-prefix-map={src_dir}=/build",
    ]
    subprocess.run(
        [
            CC,
            "-B/usr/bin",
            "-fuse-ld=bfd",
            *peta,
            *args,
            os.path.basename(src),
            "-o",
            os.path.abspath(out),
        ],
        check=True,
        cwd=src_dir,
        env=BUILD_ENV,
    )
    os.chmod(out, 0o700)


def build_android(out_dir: str) -> str:
    _tolak_symlink(out_dir)
    src = os.path.join(out_dir, "src")
    _tulis(os.path.join(src, "AndroidManifest.xml"), ANDROID_MANIFEST)
    _tulis(os.path.join(src, "assets", "config.json"), ANDROID_CONFIG)
    _tulis(os.path.join(src, "res", "values", "strings.xml"), ANDROID_STRINGS)
    _tulis(os.path.join(src, "res", "layout", "activity_main.xml"),
           '<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android"/>\n')
    _tulis(os.path.join(src, "jni", "libmini.c"), ANDROID_NATIVE)
    lib_dir = os.path.join(src, "lib", "x86_64")
    os.makedirs(lib_dir, exist_ok=True)
    _gcc(os.path.join(src, "jni", "libmini.c"), os.path.join(lib_dir, "libmini.so"),
         ["-O1", "-fPIC", "-shared", "-Wl,--build-id=none"])
    target = os.path.join(out_dir, "artifact", "android-mini.apk")
    expected = {
        "AndroidManifest.xml",
        "assets/config.json",
        "jni/libmini.c",
        "lib/x86_64/libmini.so",
        "res/layout/activity_main.xml",
        "res/values/strings.xml",
    }
    _zip_tree(src, target, expected)
    return target


def build_desktop(out_dir: str) -> str:
    _tolak_symlink(out_dir)
    src = os.path.join(out_dir, "src")
    _tulis(os.path.join(src, "desktop-mini.c"), DESKTOP_C)
    _tulis(os.path.join(src, "installer.sh"), DESKTOP_INSTALLER, 0o755)
    _tulis(os.path.join(src, "update-channel.json"), DESKTOP_CHANNEL)
    bin_dir = os.path.join(out_dir, "artifact")
    os.makedirs(bin_dir, exist_ok=True)
    target = os.path.join(bin_dir, "desktop-mini")
    _gcc(os.path.join(src, "desktop-mini.c"), target,
         ["-O1", "-g", "-fPIE", "-pie", "-Wl,-z,relro", "-Wl,--build-id=none"])
    return target


BUILDERS = {"android-mini": build_android, "desktop-mini": build_desktop}


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for blok in iter(lambda: fh.read(65536), b""):
            h.update(blok)
    return h.hexdigest()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Bangun fixture DID mobile/desktop")
    ap.add_argument("--only", choices=sorted(BUILDERS))
    ap.add_argument("--verify", action="store_true", help="bangun ulang & bandingkan sha256 tersimpan")
    args = ap.parse_args(argv)

    nama = [args.only] if args.only else sorted(BUILDERS)
    gagal = 0
    for target in nama:
        fixture = os.path.join(ROOT, "fixtures", target)
        stamp = os.path.join(fixture, "artifact.sha256")
        if args.verify:
            with tempfile.TemporaryDirectory() as tmp:
                path = BUILDERS[target](tmp)
                baru, lama = sha256(path), open(stamp, encoding="utf-8").read().split()[0]
                ok = baru == lama
                print(f"{target:14s} {'SAMA' if ok else 'BEDA'} {baru[:16]} vs {lama[:16]}")
                gagal += 0 if ok else 1
            continue
        path = BUILDERS[target](fixture)
        digest = sha256(path)
        _tulis(stamp, f"{digest}  {os.path.relpath(path, fixture)}\n")
        _tulis(os.path.join(fixture, ".gitignore"), "src/lib/\n")
        print(f"{target:14s} {os.path.relpath(path, ROOT):44s} {os.path.getsize(path):>7d} B  sha256={digest[:16]}")
    return 0 if gagal == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
