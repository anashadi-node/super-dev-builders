"""Uji penjaga CI — termasuk kontrol negatif (alat HARUS bisa gagal).

Kelas bug yang dijaga: "tidak bisa memeriksa" dilaporkan sebagai "aman", dan
kegagalan lama dikirim berulang sampai alarm diabaikan.
"""
from __future__ import annotations

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

import ci_watch as cw

SEKARANG = "2026-10-30T03:31:43Z"


def _run(rid, conclusion, status="completed", judul="judul", cabang="master", waktu=SEKARANG):
    return {"databaseId": rid, "conclusion": conclusion, "status": status,
            "displayTitle": judul, "workflowName": "ci", "headBranch": cabang,
            "createdAt": waktu, "url": f"https://github.com/o/r/actions/runs/{rid}", "event": "push"}


def _main(tmp_path, runs, argv=(), ambil=None, kred=lambda: None, kirim=lambda *a: True):
    state = tmp_path / "state.json"
    alerts = tmp_path / "alerts.jsonl"
    panggil = ambil or (lambda repo, limit: runs)
    rc = cw.main(["--repo", "o/r", "--state", str(state), "--alert-file", str(alerts), *argv],
                 ambil=panggil, kred=kred, kirim=kirim)
    isi = [json.loads(x) for x in alerts.read_text().splitlines()] if alerts.exists() else []
    return rc, isi, state


def test_kegagalan_baru_dilaporkan(tmp_path):
    rc, isi, _ = _main(tmp_path, [_run(1, "failure")])
    assert rc == 1
    assert [k["jenis"] for k in isi] == ["ci_gagal"]
    assert isi[0]["runs"][0]["id"] == "1"


def test_kegagalan_sudah_dilihat_tidak_diulang(tmp_path):
    runs = [_run(1, "failure")]
    assert _main(tmp_path, runs)[0] == 1
    rc, isi, _ = _main(tmp_path, runs)
    assert rc == 0, "kegagalan yang sama tidak boleh dilaporkan dua kali"
    assert len(isi) == 1


def test_sukses_dan_berjalan_tidak_dilaporkan(tmp_path):
    rc, isi, _ = _main(tmp_path, [_run(2, "success"), _run(3, None, status="in_progress")])
    assert rc == 0
    assert isi == []


def test_run_pertama_tidak_membanjiri_kegagalan_lama(tmp_path):
    """Pemasangan pertama: 3 kegagalan lama + HEAD sukses -> senyap (baseline)."""
    runs = [_run(7, "success", waktu="2026-10-30T03:39:41Z"),
            _run(6, "failure", waktu="2026-10-30T03:31:43Z"),
            _run(5, "failure", waktu="2026-10-30T02:58:02Z")]
    rc, isi, state = _main(tmp_path, runs)
    assert rc == 0 and isi == []
    assert len(json.loads(state.read_text())["sudah"]) == 3


def test_run_pertama_head_merah_tetap_dilaporkan(tmp_path):
    """Baseline tidak boleh menyembunyikan keadaan merah yang sedang berlangsung."""
    runs = [_run(6, "failure", waktu="2026-10-30T03:31:43Z"),
            _run(7, "success", waktu="2026-10-30T02:00:00Z")]
    rc, isi, _ = _main(tmp_path, runs)
    assert rc == 1
    assert isi[0]["runs"][0]["id"] == "6"


def test_gh_gagal_exit_2_dan_tidak_klaim_hijau(tmp_path):
    def gagal_ambil(repo, limit):
        raise cw.GhError("gh keluar 4: not logged in")

    rc, isi, state = _main(tmp_path, [], ambil=gagal_ambil)
    assert rc == 2, "pemeriksaan gagal tidak boleh dilaporkan sebagai bersih"
    assert isi[0]["jenis"] == "pemeriksaan_gagal"
    assert not state.exists(), "state tidak boleh diperbarui saat pemeriksaan gagal"


def test_keluaran_rusak_ditolak(tmp_path, monkeypatch):
    def rusak(*_a, **_k):
        raise cw.GhError("keluaran gh bukan JSON")

    rc, isi, _ = _main(tmp_path, [], ambil=rusak)
    assert rc == 2 and isi[0]["jenis"] == "pemeriksaan_gagal"


def test_tanpa_telegram_tetap_dicatat_berkas(tmp_path):
    rc, isi, _ = _main(tmp_path, [_run(9, "failure")], kred=lambda: None)
    assert rc == 1
    assert isi[0]["kanal"] == "berkas"


def test_telegram_gagal_tidak_menghapus_bukti(tmp_path):
    rc, isi, _ = _main(tmp_path, [_run(9, "failure")],
                       kred=lambda: ("tok", "chat"), kirim=lambda *a: False)
    assert rc == 1
    assert isi[0]["kanal"] == "berkas (telegram gagal)", "kegagalan kirim harus terlihat, bukan diam"


def test_state_rusak_dianggap_baseline_bukan_hijau(tmp_path):
    state = tmp_path / "state.json"
    state.write_text("{rusak", encoding="utf-8")
    rc, isi, _ = _main(tmp_path, [_run(11, "failure")])
    assert rc == 1, "state rusak tidak boleh membuat kegagalan dianggap sudah dikenal"
    assert isi[0]["runs"][0]["id"] == "11"


def test_dedupe_lintas_proses(tmp_path):
    """State adalah satu-satunya memori: dua pemanggilan terpisah tidak boleh dobel kirim."""
    runs = [_run(21, "failure")]
    assert _main(tmp_path, runs, kred=lambda: ("t", "c"), kirim=lambda *a: True)[0] == 1
    kirim = []
    rc, isi, _ = _main(tmp_path, runs, kred=lambda: ("t", "c"), kirim=lambda *a: kirim.append(a) or True)
    assert rc == 0 and not kirim and len(isi) == 1


def test_nama_repo_tidak_valid_ditolak():
    with pytest.raises(cw.GhError):
        cw.ambil_runs("bukan repo; rm -rf /")


def test_gh_tidak_terpasang_exit_2(tmp_path):
    """FileNotFoundError (gh/git hilang) harus fail-closed, bukan traceback + exit 1."""
    def hilang(repo, limit):
        raise FileNotFoundError("gh: command not found")

    rc, isi, _ = _main(tmp_path, [], ambil=hilang)
    assert rc == 2
    assert isi[0]["jenis"] == "pemeriksaan_gagal"
