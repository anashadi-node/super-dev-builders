# Third-Party Notices

SDB sendiri berlisensi **BUSL-1.1** (`LICENSE`). Berkas ini mencatat komponen pihak ketiga yang dipakai,
diuji, atau ditolak beserta lisensinya. Sumber kebenaran: `registry/skills.yaml` → `third_party`.

## Komponen yang terpasang / dipakai

| Repo | Lisensi | Pin | Status | Catatan kewajiban |
|---|---|---|---|---|
| `morluto/rea` (`rea-agents@6.8.0`) | MIT | `160d821ac9` | INSTALLED (CLI, `~/.hermes/tools/rea-6.8.0`) | sertakan teks MIT + copyright saat redistribusi |
| `trailofbits/skills` | **CC-BY-SA-4.0** | `82fe822625` | INSTALLED (sebagian skill) | **atribusi + share-alike**; karya turunan wajib CC-BY-SA-4.0; **tidak boleh** dilisensikan ulang sebagai BUSL |
| `microsoft/playwright` | Apache-2.0 | `7ad3fba1aa` | IN_USE (uji browser) | sertakan NOTICE Apache-2.0 |

## Komponen yang dinilai tetapi tidak dipasang

| Repo | Lisensi | Status | Alasan ringkas |
|---|---|---|---|
| `obra/superpowers` | MIT | REJECTED_BLUEPRINT | dilarang dokumen acuan; kapabilitas sudah tertutup skill native |
| `getsentry/skills` | Apache-2.0 | REJECTED_COVERED | tumpang tindih dengan skill kami |
| `getsentry/sentry-for-ai` | MIT | BELUM_TERPASANG | butuh akun/telemetri vendor |
| `github/github-mcp-server` | MIT | BELUM_TERPASANG | belum perlu |
| `upstash/context7` | MIT | BELUM_TERPASANG | — |
| `apify/crawlee` | Apache-2.0 | BELUM_TERPASANG | — |
| `dequelabs/axe-core` | MPL-2.0 | BELUM_TERPASANG | — |
| `GoogleChrome/lighthouse` | Apache-2.0 | BELUM_TERPASANG | — |
| `garris/BackstopJS` | MIT | DEFER | digantikan verifikasi visual sendiri |
| `MobSF/...` | GPL-3.0 | QUARANTINE | GPL-3.0 tidak kompatibel dengan distribusi proprietary |
| `skylot/jadx`, `iBotPeaches/Apktool`, `NationalSecurityAgency/ghidra` | Apache-2.0 | QUARANTINE | belum diadopsi (butuh approval terpisah) |
| `anthropics/skills` | none_declared | REJECTED_LICENSE | tanpa lisensi = hak cipta penuh; dilarang dipasang |

## Aturan pemisahan lisensi (wajib)

1. **CC-BY-SA tidak boleh masuk paket berbayar sebagai konten milik SDB.** Paket yang memuatnya harus
   menandai `"license": "CC-BY-SA-4.0"` per skill, menyertakan atribusi, dan tidak mengklaim BUSL atas bagian itu.
2. Setiap manifest paket (`platform/packs/*.json`) memuat `license` per skill; verifier menolak paket `proprietary`
   yang berisi skill CC-BY-SA atau `none_declared`.
3. Distribusi ulang `rea-agents` harus menyertakan teks MIT + copyright `morluto`.
4. Jika GPL-3.0 dipertimbangkan, keputusan harus tercatat di `docs/adr/` dan tidak boleh digabung ke distribusi
   proprietary tanpa review hukum.

## Verifikasi

```bash
/usr/bin/python3 - <<'PY'
import yaml
reg = yaml.safe_load(open("registry/skills.yaml"))
bad = [e["repo"] for e in reg["third_party"] if e["status"] == "INSTALLED" and not e.get("license")]
print("terpasang tanpa lisensi:", bad)
PY
```
