"""Regresi audit fundamental 2026-10-29 — satu tes per cacat yang terbukti (lihat reports/).

Setiap tes ditulis agar GAGAL pada v0.5.0 dan LULUS setelah perbaikan; nomor H-xx merujuk ke
tabel temuan di reports/SDB_AUDIT_FUNDAMENTAL_20261029.md.
"""
from __future__ import annotations

import datetime as dt
import json
import sqlite3
import threading
import time
import urllib.error
import urllib.request

import pytest

from sdb_platform.control_plane.app import serve
from sdb_platform.control_plane.billing import BillingError, _hash, price_tokens
from sdb_platform.control_plane.store import ControlPlaneError, Store
from sdb_platform.runtime import worker as worker_mod
from sdb_platform.runtime.worker import ExecutionResult, Worker

ADMIN = "admin-key-uji-" + "a" * 20
WKEY = "worker-key-uji-" + "w" * 20
PACK = {"id": "sdb-recon", "version": "1.0.0"}


@pytest.fixture()
def store():
    return Store(":memory:")


def _tenant(store, plan="pro"):
    return store.create_tenant(plan=plan)


def _job(store, t, key="regresi-0001", tokens=5000, seconds=600, target="artifact://a/1"):
    return store.create_job(t["tenant_id"], "recon", PACK, target, {"tokens": tokens, "seconds": seconds}, key)[0]


def _hold(store, job):
    return store.db.execute("SELECT hold_microusd FROM jobs WHERE job_id = ?", (job["job_id"],)).fetchone()[0]


def _expire(store, job_id):
    past = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=5)).isoformat(timespec="seconds")
    store.db.execute("UPDATE jobs SET lease_until = ? WHERE job_id = ?", (past, job_id))
    store.db.commit()


def _closed_period():
    end = dt.datetime.now(dt.timezone.utc)
    return (end - dt.timedelta(days=1)).isoformat(timespec="microseconds"), end.isoformat(timespec="microseconds")


# ------------------------------------------------------------ status & uang
def test_h02_status_non_terminal_ditolak(store):
    t = _tenant(store)
    job = _job(store, t)
    for bad in ("queued", "running", "apa-saja", ""):
        with pytest.raises(ControlPlaneError) as exc:
            store.finish_job(t["tenant_id"], job["job_id"], bad, 0)
        assert exc.value.code == "invalid_status"
    assert store.get_job(t["tenant_id"], job["job_id"])["status"] == "queued"
    assert store.db.execute("SELECT COUNT(*) FROM job_charges").fetchone()[0] == 0


def test_h02_tokens_bool_ditolak(store):
    t = _tenant(store)
    job = _job(store, t)
    with pytest.raises(ControlPlaneError) as exc:
        store.finish_job(t["tenant_id"], job["job_id"], "succeeded", True)
    assert exc.value.code == "invalid_tokens"


def test_h03_batal_lalu_lease_mati_jadi_cancelled_dan_kredit_kembali(store):
    t = _tenant(store)
    start = store.billing.balance(t["tenant_id"])["credit_microusd"]
    job = _job(store, t)
    store.claim_next_job("worker-mati", 60)
    store.request_cancel(t["tenant_id"], job["job_id"])
    _expire(store, job["job_id"])
    assert store.reap_expired_leases(3) == [{"job_id": job["job_id"], "result": "cancelled"}]
    assert store.get_job(t["tenant_id"], job["job_id"])["status"] == "cancelled"
    b = store.billing.balance(t["tenant_id"])
    assert b["credit_microusd"] == start and b["held_microusd"] == 0
    assert store.billing.verify_chain(t["tenant_id"])["ok"] is True


def test_h04_batal_setelah_token_terpakai_menagih_pemakaian(store):
    t = _tenant(store)
    start = store.billing.balance(t["tenant_id"])["credit_microusd"]
    _job(store, t)

    def exe(job):
        store.request_cancel(t["tenant_id"], job["job_id"])  # batal di detik terakhir
        return ExecutionResult(tokens_used=4900)

    out = Worker(store, exe, "worker-h04", 60).run_once()
    assert out["status"] == "cancelled"
    b = store.billing.balance(t["tenant_id"])
    assert start - b["credit_microusd"] == price_tokens(4900, "pro") and b["held_microusd"] == 0


def test_h05_worker_lambat_tidak_bisa_menutup_job_worker_lain(store):
    t = _tenant(store)
    job = _job(store, t)
    store.claim_next_job("worker-lambat", 60)
    _expire(store, job["job_id"])
    store.reap_expired_leases(3)
    store.claim_next_job("worker-baru", 60)
    with pytest.raises(ControlPlaneError) as exc:
        store.finish_job(t["tenant_id"], job["job_id"], "succeeded", 10, worker_id="worker-lambat")
    assert exc.value.code == "lease_lost"
    done = store.finish_job(t["tenant_id"], job["job_id"], "succeeded", 10, worker_id="worker-baru")
    assert done["status"] == "succeeded"


def test_h05_penutupan_ganda_ditolak_tanpa_tagih_ganda(store):
    t = _tenant(store)
    job = _job(store, t)
    store.finish_job(t["tenant_id"], job["job_id"], "succeeded", 1000)
    after = store.billing.balance(t["tenant_id"])["credit_microusd"]
    with pytest.raises(ControlPlaneError) as exc:
        store.finish_job(t["tenant_id"], job["job_id"], "failed", 0)
    assert exc.value.code == "job_closed"
    assert store.billing.balance(t["tenant_id"])["credit_microusd"] == after


def test_h06_job_tenant_suspended_tidak_diklaim(store):
    t = _tenant(store)
    _job(store, t)
    store.set_status(t["tenant_id"], "suspended")
    assert store.claim_next_job("worker-h06", 60) is None
    store.set_status(t["tenant_id"], "active")
    assert store.claim_next_job("worker-h06", 60) is not None


def test_h06_tenant_dihapus_antrean_ditutup_kredit_dilepas(store):
    t = _tenant(store)
    start = store.billing.balance(t["tenant_id"])["credit_microusd"]
    job = _job(store, t)
    store.set_status(t["tenant_id"], "deleted")
    assert store.get_job(t["tenant_id"], job["job_id"])["status"] == "cancelled"
    assert store.billing.balance(t["tenant_id"])["credit_microusd"] == start


def test_h07_kunci_idempotensi_sama_isi_beda_409(store):
    t = _tenant(store)
    _job(store, t, key="kunci-sama-01", tokens=5000)
    with pytest.raises(ControlPlaneError) as exc:
        _job(store, t, key="kunci-sama-01", tokens=9000)
    assert exc.value.status == 409 and exc.value.code == "idempotency_conflict"
    _again, replayed = store.create_job(t["tenant_id"], "recon", PACK, "artifact://a/1",
                                       {"tokens": 5000, "seconds": 600}, "kunci-sama-01")
    assert replayed is True


def test_h08_kunci_api_tidak_bisa_pindah_tenant(store):
    a, b = _tenant(store), _tenant(store)
    raw = "kunci-bersama-" + "x" * 20
    store.add_api_key(a["tenant_id"], raw)
    with pytest.raises(ControlPlaneError) as exc:
        store.add_api_key(b["tenant_id"], raw)
    assert exc.value.code == "key_exists"
    assert store.tenant_for_key(raw) == a["tenant_id"]


# ---------------------------------------------------------------- invoice
def test_h09_invoice_tumpang_tindih_ditolak(store):
    t = _tenant(store)
    job = _job(store, t)
    store.finish_job(t["tenant_id"], job["job_id"], "succeeded", 1000)
    start, end = _closed_period()
    store.billing.issue_invoice(t["tenant_id"], start, end)
    mid = (dt.datetime.fromisoformat(end) - dt.timedelta(hours=1)).isoformat(timespec="microseconds")
    for a, b in ((start, mid), (mid, end)):  # sebagian di dalam periode yang sudah ditagih
        with pytest.raises(BillingError) as exc:
            store.billing.issue_invoice(t["tenant_id"], a, b)
        assert exc.value.code == "invoice_period_overlap"
    assert store.db.execute("SELECT COUNT(*) FROM invoices").fetchone()[0] == 1


def test_h09_invoice_periode_masa_depan_dan_sampah_ditolak(store):
    t = _tenant(store)
    future = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=1)).isoformat()
    with pytest.raises(BillingError) as exc:
        store.billing.issue_invoice(t["tenant_id"], "2026-01-01", future)
    assert exc.value.code == "period_not_closed"
    for a, b in (("zzz", "aaa"), ("2026-02-01", "2026-01-01"), (None, "2026-01-01")):
        with pytest.raises(BillingError):
            store.billing.issue_invoice(t["tenant_id"], a, b)


def test_h09_charge_tepat_di_batas_masuk_satu_invoice_saja(store):
    t = _tenant(store)
    for i in range(3):
        job = _job(store, t, key=f"batas-{i:04d}")
        store.finish_job(t["tenant_id"], job["job_id"], "succeeded", 1000 + i)
    ts = [r[0] for r in store.db.execute("SELECT ts FROM job_charges ORDER BY ts")]
    cut = ts[1]  # tepat di stempel waktu charge kedua: [start, cut) dan [cut, end)
    end = dt.datetime.now(dt.timezone.utc).isoformat(timespec="microseconds")
    i1 = store.billing.issue_invoice(t["tenant_id"], "2026-01-01T00:00:00+00:00", cut)
    i2 = store.billing.issue_invoice(t["tenant_id"], cut, end)
    assert i1["jobs"] + i2["jobs"] == 3 and i1["jobs"] == 1


# --------------------------------------------------------------- artefak
def test_h10_retensi_wajib_tanggal_masa_depan(store):
    t = _tenant(store)
    job = _job(store, t)
    uri = f"s3://sdb-artifacts/{t['tenant_id']}/x"
    for bad in ("bukan-tgl!", "2001-01-01", "", None):
        with pytest.raises(ControlPlaneError):
            store.register_artifact(t["tenant_id"], job["job_id"], "report", "a" * 64, 10, "clean", bad, uri)


def test_h11_uri_artefak_wajib_di_ruang_tenant_sendiri(store):
    a, b = _tenant(store), _tenant(store)
    job = _job(store, a)
    for bad in (f"s3://sdb-artifacts/{b['tenant_id']}/rahasia.zip", "s3://sdb-artifacts/x",
                f"s3://sdb-artifacts/{a['tenant_id']}/../{b['tenant_id']}/x", f"artifact://{b['tenant_id']}/x",
                f"s3://sdb-artifacts/{a['tenant_id']}x/y"):
        with pytest.raises(ControlPlaneError) as exc:
            store.register_artifact(a["tenant_id"], job["job_id"], "report", "a" * 64, 1, "clean", "2099-01-01", bad)
        assert exc.value.code == "invalid_uri", bad
    ok = store.register_artifact(a["tenant_id"], job["job_id"], "report", "a" * 64, 1, "clean", "2099-01-01",
                                 f"artifact://{a['tenant_id']}/laporan.md")
    assert ok["retention_until"].startswith("2099-01-01T00:00:00")


# ---------------------------------------------------------------- ledger
def test_h12_entry_id_respons_sama_dengan_db(store):
    t = _tenant(store)
    e = store.billing.topup(t["tenant_id"], 1_000_000)
    assert store.db.execute("SELECT COUNT(*) FROM ledger WHERE entry_id = ?", (e["entry_id"],)).fetchone()[0] == 1


def test_h13_memo_disunting_terdeteksi(store):
    t = _tenant(store)
    store.billing.topup(t["tenant_id"], 1_000_000, "topup asli")
    store.db.execute("UPDATE ledger SET memo = 'diubah diam-diam' WHERE kind = 'topup'")
    store.db.commit()
    assert store.billing.verify_chain(t["tenant_id"])["ok"] is False


def test_h13_saldo_baris_dimanipulasi_terdeteksi_walau_hash_dihitung_ulang(store):
    t = _tenant(store)
    store.billing.topup(t["tenant_id"], 1_000_000)
    # Penyerang yang menghitung ulang hash v1 tetap tertangkap pemeriksaan aritmetika saldo.
    r = store.db.execute("SELECT * FROM ledger WHERE kind='topup'").fetchone()
    store.db.execute("UPDATE ledger SET balance_after = balance_after + 5, hv = 1, hash = ? WHERE entry_id = ?",
                     (_hash(r["prev_hash"], r["tenant_id"], r["kind"], r["amount"], r["balance_after"] + 5,
                            r["held_after"], r["job_id"], r["ts"]), r["entry_id"]))
    store.db.commit()
    assert store.billing.verify_chain(t["tenant_id"])["ok"] is False


def test_h13_ledger_v1_lama_tetap_terverifikasi(tmp_path):
    """DB v0.5.0 (tanpa kolom hv, hash v1) harus termigrasi dan tetap lolos verify_chain."""
    path = str(tmp_path / "lama.db")
    s = Store(path)
    t = _tenant(s)
    s.billing.topup(t["tenant_id"], 1_000_000)
    # Turunkan ke format v1 persis seperti v0.5.0 menulisnya.
    rows = s.db.execute("SELECT * FROM ledger WHERE tenant_id = ? ORDER BY rowid", (t["tenant_id"],)).fetchall()
    prev = "0" * 64
    for r in rows:
        h = _hash(prev, r["tenant_id"], r["kind"], r["amount"], r["balance_after"], r["held_after"],
                  r["job_id"], r["ts"])
        s.db.execute("UPDATE ledger SET prev_hash = ?, hash = ? WHERE entry_id = ?", (prev, h, r["entry_id"]))
        prev = h
    s.db.commit()
    s.db.execute("ALTER TABLE ledger DROP COLUMN hv")
    s.db.commit()
    s.db.close()
    again = Store(path)  # migrasi menambah kolom hv DEFAULT 1
    assert again.billing.verify_chain(t["tenant_id"])["ok"] is True
    again.billing.topup(t["tenant_id"], 5)  # baris baru v2 menyambung rantai v1
    assert again.billing.verify_chain(t["tenant_id"])["ok"] is True


def test_h14_refund_atomik_dan_memo_wajib(store):
    t = _tenant(store)
    with pytest.raises(BillingError):
        store.billing.refund(t["tenant_id"], 100, "")
    with pytest.raises(BillingError):
        store.billing.refund(t["tenant_id"], True, "bool bukan angka")
    store.billing.refund(t["tenant_id"], 100, "kompensasi")
    assert store.billing.verify_chain(t["tenant_id"])["ok"] is True
    assert not store.db.in_transaction


# ---------------------------------------------------------------- worker
def test_h15_cli_worker_wajib_pilih_executor_dan_echo_dikunci(tmp_path, monkeypatch):
    db = str(tmp_path / "w.db")
    with pytest.raises(SystemExit):
        worker_mod.main(["--db", db, "--once"])  # --executor wajib
    monkeypatch.delenv("SDB_ALLOW_ECHO_EXECUTOR", raising=False)
    assert worker_mod.main(["--db", db, "--once", "--executor", "echo"]) == 2
    monkeypatch.setenv("SDB_ALLOW_ECHO_EXECUTOR", "1")
    assert worker_mod.main(["--db", db, "--once", "--executor", "echo"]) == 0


def test_h16_heartbeat_otomatis_memperpanjang_lease(tmp_path):
    path = str(tmp_path / "hb.db")
    s = Store(path)
    t = _tenant(s)
    job = _job(s, t)
    seen = {}

    def lambat(j):
        probe = sqlite3.connect(path)
        seen["awal"] = probe.execute("SELECT lease_until FROM jobs WHERE job_id = ?", (j["job_id"],)).fetchone()[0]
        time.sleep(4.2)  # > lease/3 (=3,33 dtk) -> minimal satu heartbeat
        seen["akhir"] = probe.execute("SELECT lease_until FROM jobs WHERE job_id = ?", (j["job_id"],)).fetchone()[0]
        probe.close()
        return ExecutionResult(tokens_used=1000)

    out = Worker(s, lambat, "worker-hb", lease_seconds=10).run_once()
    assert out["status"] == "succeeded"
    assert seen["akhir"] > seen["awal"]
    assert s.get_job(t["tenant_id"], job["job_id"])["status"] == "succeeded"


def test_h17_fair_share_antar_tenant(store):
    big, small = _tenant(store, "team"), _tenant(store)
    for i in range(5):
        _job(store, big, key=f"besar-{i:04d}")
    _job(store, small, key="kecil-0001")
    first_two = {store.claim_next_job(f"worker-{i}", 60)["tenant_id"] for i in range(2)}
    assert first_two == {big["tenant_id"], small["tenant_id"]}


def test_h17_fifo_deterministik_dalam_detik_yang_sama(store):
    t = _tenant(store, "team")
    ids = [_job(store, t, key=f"fifo-{i:04d}")["job_id"] for i in range(8)]
    claimed = [store.claim_next_job(f"worker-{i}", 60)["job_id"] for i in range(8)]
    for jid in claimed:  # tutup supaya fair-share tidak memengaruhi urutan dalam satu tenant
        store.finish_job(t["tenant_id"], jid, "succeeded", 0)
    assert claimed == ids


def test_h22_lease_di_luar_batas_ditolak(store):
    for bad in (0, 9, 3601, 10 ** 9, "120", True):
        with pytest.raises(ControlPlaneError) as exc:
            store.claim_next_job("worker-h22", bad)
        assert exc.value.code == "invalid_lease"


def test_h25_balapan_idempotensi_lintas_koneksi_jadi_replay(tmp_path):
    path = str(tmp_path / "idem.db")
    s1, s2 = Store(path), Store(path)
    t = s1.create_tenant(plan="pro")
    hasil, errors = [], []
    bar = threading.Barrier(2)

    def mk(st):
        bar.wait()
        try:
            hasil.append(st.create_job(t["tenant_id"], "recon", PACK, "artifact://a/1",
                                       {"tokens": 5000, "seconds": 600}, "balapan-0001"))
        except Exception as exc:  # pragma: no cover - justru ini yang diuji tidak terjadi
            errors.append(repr(exc))

    ths = [threading.Thread(target=mk, args=(x,)) for x in (s1, s2)]
    [th.start() for th in ths]
    [th.join() for th in ths]
    assert errors == []
    assert sorted(r[1] for r in hasil) == [False, True]
    assert len({r[0]["job_id"] for r in hasil}) == 1
    assert s1.usage(t["tenant_id"])["jobs_used"] == 1


def test_kuota_job_tidak_jebol_saat_paralel(tmp_path):
    path = str(tmp_path / "kuota.db")
    seed = Store(path)
    t = seed.create_tenant(plan="pro", limits={"jobs_per_month": 3, "tokens_per_month": 10_000_000,
                                               "storage_gb": 1})
    stores = [Store(path) for _ in range(6)]
    bar = threading.Barrier(6)
    ok, quota = [], []

    def mk(i, st):
        bar.wait()
        try:
            st.create_job(t["tenant_id"], "recon", PACK, "artifact://a/1",
                          {"tokens": 1000, "seconds": 60}, f"paralel-{i:04d}")
            ok.append(i)
        except ControlPlaneError as exc:
            quota.append(exc.code)

    ths = [threading.Thread(target=mk, args=(i, st)) for i, st in enumerate(stores)]
    [th.start() for th in ths]
    [th.join() for th in ths]
    assert len(ok) == 3 and quota == ["quota_jobs_exceeded"] * 3
    assert seed.billing.verify_chain(t["tenant_id"])["ok"] is True


# ------------------------------------------------------------------ HTTP
@pytest.fixture()
def server():
    httpd = serve(Store(":memory:"), ADMIN, "127.0.0.1", 0, WKEY)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


def _raw(base, method, path, raw=None, headers=None):
    req = urllib.request.Request(base + path, data=raw, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read()), dict(r.headers)
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read() or b"{}"), dict(exc.headers)


def _tenant_http(base):
    _, t, _ = _raw(base, "POST", "/v1/tenants", json.dumps({"plan": "pro"}).encode(), {"X-Admin-Key": ADMIN})
    return t


def test_h01_rute_finish_tenant_dicabut(server):
    t = _tenant_http(server)
    body = {"type": "recon", "pack": PACK, "target_ref": "artifact://a/1",
            "budget": {"tokens": 5000, "seconds": 600}, "idempotency_key": "http-h01-01"}
    _, job, _ = _raw(server, "POST", "/v1/jobs", json.dumps(body).encode(), {"X-API-Key": t["api_key"]})
    _raw(server, "POST", "/v1/worker/claim", json.dumps({"worker_id": "worker-h01"}).encode(), {"X-Worker-Key": WKEY})
    code, payload, _ = _raw(server, "POST", f"/v1/jobs/{job['job']['job_id']}/finish",
                            json.dumps({"status": "failed", "tokens_used": 0}).encode(), {"X-API-Key": t["api_key"]})
    assert code == 410 and payload["error"]["code"] == "endpoint_removed"
    _, j, _ = _raw(server, "GET", f"/v1/jobs/{job['job']['job_id']}", None, {"X-API-Key": t["api_key"]})
    assert j["job"]["status"] == "running"


@pytest.mark.parametrize("raw,path,hdr_kind", [
    (b"[1,2]", "/v1/jobs", "tenant"),
    (b'"teks"', "/v1/jobs", "tenant"),
    (json.dumps({"type": "recon", "pack": [1], "budget": {}}).encode(), "/v1/jobs", "tenant"),
    (json.dumps({"type": "recon", "pack": PACK, "budget": [5000]}).encode(), "/v1/jobs", "tenant"),
    (json.dumps({"worker_id": "wwww", "lease_seconds": "abc"}).encode(), "/v1/worker/claim", "worker"),
    (json.dumps({"worker_id": "wwww", "lease_seconds": 10 ** 9}).encode(), "/v1/worker/claim", "worker"),
    (json.dumps({"worker_id": "wwww", "lease_seconds": 1.5}).encode(), "/v1/worker/claim", "worker"),
])
def test_h18_h22_input_cacat_400_bukan_500(server, raw, path, hdr_kind):
    t = _tenant_http(server)
    hdr = {"X-API-Key": t["api_key"]} if hdr_kind == "tenant" else {"X-Worker-Key": WKEY}
    code, payload, _ = _raw(server, "POST", path, raw, hdr)
    assert code == 400, payload


def test_h21_content_length_cacat_400(server):
    import http.client
    host, port = server.split("//")[1].split(":")
    conn = http.client.HTTPConnection(host, int(port), timeout=5)
    conn.putrequest("POST", "/v1/jobs")
    conn.putheader("Content-Length", "abc")
    conn.endheaders()
    resp = conn.getresponse()
    assert resp.status == 400 and json.loads(resp.read())["error"]["code"] == "invalid_content_length"
    conn.close()


def test_h26_kunci_non_ascii_401_bukan_500(server):
    for hdr in ({"X-Admin-Key": "kunci\u00e9"}, {"X-Worker-Key": "\u00fc" * 30}):
        path = "/v1/admin/revenue" if "X-Admin-Key" in hdr else "/v1/worker/claim"
        method = "GET" if "X-Admin-Key" in hdr else "POST"
        code, _, _ = _raw(server, method, path, b"{}" if method == "POST" else None,
                          {k: v.encode("latin-1").decode("latin-1") for k, v in hdr.items()})
        assert code == 401


def test_respons_tidak_di_cache_dan_nosniff(server):
    code, _, headers = _raw(server, "GET", "/healthz")
    assert code == 200
    assert headers.get("Cache-Control") == "no-store" and headers.get("X-Content-Type-Options") == "nosniff"


def test_invoice_hanya_bisa_diterbitkan_admin(server):
    t = _tenant_http(server)
    start, end = _closed_period()
    code, _, _ = _raw(server, "POST", "/v1/invoices", json.dumps({"period_start": start, "period_end": end}).encode(),
                      {"X-API-Key": t["api_key"]})
    assert code == 404  # rute tenant untuk menerbitkan sudah tidak ada
    body = {"tenant_id": t["tenant"]["tenant_id"], "period_start": start, "period_end": end}
    code, inv, _ = _raw(server, "POST", "/v1/admin/invoices", json.dumps(body).encode(), {"X-Admin-Key": ADMIN})
    assert code == 201 and inv["invoice"]["jobs"] == 0
    code, again, _ = _raw(server, "POST", "/v1/admin/invoices", json.dumps(body).encode(), {"X-Admin-Key": ADMIN})
    assert code == 200 and again["invoice"]["replayed"] is True
