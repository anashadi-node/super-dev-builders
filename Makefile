# Super Dev Builders Ecosystem — task runner
#
# Interpreter: repo punya .venv lokal (di luar git, ter-ignore). Utamakan itu, lalu
# python3 dari PATH (di runner CI = Python setup-python yang sudah dipasangi
# dependensi uji). JANGAN hardcode /usr/bin/python3 — tidak portabel: di runner
# setup-python menaruh Python di path lain dan /usr/bin/python3 tidak punya pytest.
#
# Catatan kejujuran: percobaan perbaikan pertama hanya memakai `command -v python3`.
# Di workstation ini PATH menaruh Python Hermes lebih dulu dan Python itu TIDAK punya
# pytest -> `make test` gagal lokal. Resolusi karena itu dibuat sadar-kapabilitas:
# dipilih interpreter yang benar-benar bisa `import pytest`.
PY_SYS ?= $(shell \
  if [ -x .venv/bin/python ]; then echo .venv/bin/python; \
  elif python3 -c "import pytest" 2>/dev/null; then echo python3; \
  elif /usr/bin/python3 -c "import pytest" 2>/dev/null; then echo /usr/bin/python3; \
  else echo python3; fi)

# Dokumen butuh modul `markdown` (docs-only). Interpreter uji (.venv) tidak memilikinya dengan
# sengaja — paket runtime tetap minim — jadi dicari yang benar-benar bisa `import markdown`.
PY_DOC ?= $(shell \
  if python3 -c "import markdown" 2>/dev/null; then echo python3; \
  elif /usr/bin/python3 -c "import markdown" 2>/dev/null; then echo /usr/bin/python3; \
  else echo python3; fi)

# TARGET lewat lingkungan (bukan interpolasi make ke shell): nilai ber-kutip/`;`/`$(...)` tetap data.
export TARGET

.PHONY: help check lint drift doctor inventory test gate-init lint-registry release-check skills-list install-main workflow install-dry-run clean-pyc docs-tutorial docs-lint mutation did did-providers did-bench pr-merge

help:
	@grep -E "^[a-z-]+:" Makefile | sed "s/:.*//" | column -c 80

doctor:
	$(PY_SYS) scripts/doctor.py

inventory:
	$(PY_SYS) scripts/inventory_ecosystem.py --out reports/inventory_after.json

# Uji integrasi ikut dijalankan: sebelumnya 57 uji di integrations/ hanya lulus
# kalau seseorang ingat menjalankannya manual (audit 2026-11-05, temuan VF2).
test:
	$(PY_SYS) -m pytest tests skills integrations -q

lint:
	ruff check sdb_platform scripts tests skills dashboard

# skill terpasang (main + profil) vs sumber repo; exit 1 bila MISSING/DIFF.
# Drift hanya bermakna bila Host punya Hermes. Di runner CI (~/.hermes tidak ada)
# target ini DILEWATI dengan pesan eksplisit — bukan gagal, bukan lulus diam-diam.
drift:
	@if [ -d "$$HOME/.hermes/skills" ]; then $(PY_SYS) scripts/doctor.py --drift-only; \
	else echo "SKIP drift — tanpa $$HOME/.hermes/skills (mis. runner CI)"; fi

# gerbang lokal sebelum commit: lint + registry + test + drift + higiene artefak + pack + dokumen
# docs-lint (ADR-0008) menegakkan apa yang dulu hanya prosa di docs/INDEX.md: setiap dokumen
# terindeks, tiap rujukan indeks hidup, tidak ada PDF terlacak, HTML generate wajib berdaftar,
# klaim jumlah skill di README sama dengan registry. Tanpa ini aturan dokumen tidak pernah bisa gagal.
check: lint lint-registry test drift hygiene packs docs-lint

# Manifest paket per divisi (ADR-0003): hash + lisensi harus cocok dengan registry & SKILL.md.
packs:
	$(PY_SYS) scripts/pack_build.py verify

# Worker Fase 2b: kerjakan satu job dari antrean lokal.
worker:
	SDB_ALLOW_ECHO_EXECUTOR=1 $(PY_SYS) -m sdb_platform.runtime.worker --db data/control.db --once --executor echo

# Control plane lokal (Fase 2). Butuh SDB_ADMIN_KEY >= 24 karakter.
control-plane:
	@test -n "$$SDB_ADMIN_KEY" || (echo "set SDB_ADMIN_KEY dulu (>=24 char)"; exit 2)
	$(PY_SYS) -m sdb_platform.control_plane.app --db data/control.db --port 8088

# Aturan penempatan (docs/PETA_STRUKTUR.md §4): tidak ada artefak besar/PII baru di git.
# Baseline di platform/hygiene-baseline.json mencatat utang lama sebagai WARN.
# Dokumen tutorial: HTML dilacak, PDF hasil build tidak (melewati gerbang 512 KB di repo_hygiene).
docs-tutorial:
	$(PY_DOC) scripts/build_tutorial.py docs/TUTORIAL_PENGGUNAAN.md
	$(PY_DOC) scripts/build_tutorial.py docs/TUTORIAL_PRIBADI.md \
	  --title "Panduan Pribadi SDB — PC Ini & Telegram" \
	  --desc "Panduan pemakaian pribadi SDB: Command Deck lokal, shortcut desktop, control plane, dan bot Telegram read-only." \
	  --kicker "Super Dev Builders · Panduan Pribadi"
	$(PY_DOC) scripts/build_tutorial.py docs/WORKFLOW_SKENARIO.md \
	  --title "Workflow SDB — Semua Skenario" \
	  --desc "Alur kerja SDB untuk clone/reverse engineering, PRD jadi, chat ide, game, mobile, CLI, data, refactor, audit, dan operasional." \
	  --kicker "Super Dev Builders · Workflow Skenario"

docs-lint:
	$(PY_SYS) scripts/docs_lint.py

# Uji mutasi (temuan T-09/T-13 audit 2026-11-05): sengaja merusak satu baris logika
# gerbang, jalankan suite, lalu pulihkan. Mutan yang SINTAS = baris tanpa penjaga.
# Tidak masuk `make check`: 10 mutan x suite penuh terlalu lambat untuk tiap commit.
# Skor wajib 100% (10/10). Lihat docs/AUDIT_VALIDASI_SDB_20261105.md §9.
mutation:
	$(PY_SYS) tools/mutation_gate.py --run --fast

hygiene:
	$(PY_SYS) scripts/repo_hygiene.py

gate-init:
	@echo "gunakan: $(PY_SYS) scripts/init_target.py <slug> && $(PY_SYS) scripts/gate_check.py <slug>"

lint-registry:
	$(PY_SYS) scripts/registry_lint.py

# Pindai rahasia dengan allowlist berjustifikasi (.gitleaks.toml).
# Gitleaks opsional: target ini di-skip bila biner tidak ada (mis. runner CI).
secrets:
	@command -v gitleaks >/dev/null 2>&1 || { echo "SKIP secrets - gitleaks tidak terpasang"; exit 0; }
	gitleaks detect --config .gitleaks.toml --no-banner --redact --log-opts="--all"

# Kontrol kompensasi: pindai ULANG TANPA allowlist untuk mengaudit berkas yang
# dikecualikan .gitleaks.toml. Memakai konfigurasi netral di state/ karena
# gitleaks otomatis memuat .gitleaks.toml dari akar repo.
# Keluaran normal = 40 temuan lama (37 SHA-1 + 3 fixture). Yang dicari: temuan BARU.
secrets-raw:
	@command -v gitleaks >/dev/null 2>&1 || { echo "SKIP secrets-raw - gitleaks tidak terpasang"; exit 0; }
	@mkdir -p state
	@printf '%s\n' '[extend]' 'useDefault = true' > state/gitleaks-nofilter.toml
	@gitleaks detect --config state/gitleaks-nofilter.toml --no-banner --redact --log-opts="--all" --report-format json --report-path state/gitleaks-raw.json >/dev/null 2>&1 || true
	@$(PY_SYS) -c "import json;d=json.load(open('state/gitleaks-raw.json'));print('temuan tanpa allowlist:',len(d));[print('  ',x['RuleID'],x['File']) for x in d]"

# Divisi Investigasi (DID, tahap 01C). Tiga perintah sengaja dipisah agar
# pemakaian harian jelas: bukti alat, gerbang mutu, lalu skor terhadap label.
did-providers:
	$(PY_SYS) scripts/provider_snapshot.py

# validate: gagal (exit 1) bila handoff melanggar kontrak — jangan cuma "kelihatan rapi".
did:
	@slug="$${TARGET:-}"; \
	if [ -z "$$slug" ]; then echo "pakai: make did TARGET=<slug>"; exit 2; fi; \
	$(PY_SYS) scripts/did_validate.py validate --target "$$slug" --render

# bench: butuh handoff + label independen; skor ditulis ke reports/<slug>/did-bench.json.
did-bench:
	@slug="$${TARGET:-}"; \
	if [ -z "$$slug" ] || [ -z "$${TRUTH:-}" ]; then \
		echo "pakai: make did-bench TARGET=<slug> TRUTH=benchmarks/<slug>/ground_truth.json"; exit 2; fi; \
	mkdir -p "reports/$$slug"; \
	$(PY_SYS) scripts/did_validate.py bench --handoff "runs/$$slug/did/handoff.json" --truth "$$TRUTH" \
		--json-out "reports/$$slug/did-bench.json"; \
	cat "reports/$$slug/did-bench.json"

# pr-merge: jalur merge yang benar — CI wajib hijau, squash, branch dihapus.
pr-merge:
	@num="$${PR:-}"; \
	if [ -z "$$num" ]; then echo "pakai: make pr-merge PR=<nomor>"; exit 2; fi; \
	ok=0; tries=0; \
	while [ "$$ok" = "0" ] && [ "$$tries" -lt 40 ]; do \
		tries=$$((tries + 1)); \
		if gh pr checks "$$num" --watch --interval 20; then ok=1; continue; fi; \
		msg=$$(gh pr checks "$$num" 2>&1 || true); \
		case "$$msg" in \
			*"no checks reported"*) echo "CI belum mulai (percobaan $$tries) — tunggu 15 dtk"; sleep 15 ;; \
			*) echo "$$msg"; exit 1 ;; \
		esac; \
	done; \
	[ "$$ok" = "1" ] || { echo "CI tidak pernah muncul setelah $$tries percobaan"; exit 1; }; \
	gh pr merge "$$num" --squash --admin --delete-branch

release-check:
	@slug="$${TARGET:-}"; \
	if [ -z "$$slug" ]; then slug=$$($(PY_SYS) -c "import os;runs='runs';c=[(os.path.getmtime(os.path.join(runs,d)),d) for d in (os.listdir(runs) if os.path.isdir(runs) else [])];print(max(c)[1] if c else '')" 2>/dev/null); fi; \
	if [ -z "$$slug" ]; then echo "Tidak ada run di runs/ — pakai: make release-check TARGET=<slug>"; exit 1; fi; \
	echo "release gate untuk: runs/$$slug"; \
	$(PY_SYS) scripts/release_check.py "$$slug"

skills-list:
	$(PY_SYS) scripts/install_skills.py --list

# runner 18 tahap (TARGET=<slug>); daftar tunggal di workflows/stages.yaml
workflow:
	@slug="$${TARGET:-}"; \
	if [ -z "$$slug" ]; then slug=$$($(PY_SYS) -c "import os;r='runs';c=[(os.path.getmtime(os.path.join(r,d)),d) for d in (os.listdir(r) if os.path.isdir(r) else [])];print(max(c)[1] if c else '')" 2>/dev/null); fi; \
	if [ -z "$$slug" ]; then echo "Tidak ada run di runs/ — pakai: make workflow TARGET=<slug>"; exit 1; fi; \
	$(PY_SYS) scripts/workflow_run.py "$$slug"

# rencana pemasangan ke host (TIDAK mengubah apa pun)
install-dry-run:
	@echo "Prasyarat: jalankan dari root repo; detail di GETTING_STARTED.md"
	./install.sh --dry-run

install-main:
	$(PY_SYS) scripts/install_skills.py --main --dry-run

clean-pyc:
	find . -path ./.venv -prune -o -path ./node_modules -prune -o -name "__pycache__" -type d -prune -exec rm -r -- {} +
