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

.PHONY: help check lint drift doctor inventory test gate-init lint-registry release-check skills-list install-main workflow install-dry-run clean-pyc

help:
	@grep -E "^[a-z-]+:" Makefile | sed "s/:.*//" | column -c 80

doctor:
	$(PY_SYS) scripts/doctor.py

inventory:
	$(PY_SYS) scripts/inventory_ecosystem.py --out reports/inventory_after.json

test:
	$(PY_SYS) -m pytest tests skills -q

lint:
	ruff check scripts tests skills

# skill terpasang (main + profil) vs sumber repo; exit 1 bila MISSING/DIFF.
# Drift hanya bermakna bila Host punya Hermes. Di runner CI (~/.hermes tidak ada)
# target ini DILEWATI dengan pesan eksplisit — bukan gagal, bukan lulus diam-diam.
drift:
	@if [ -d "$$HOME/.hermes/skills" ]; then $(PY_SYS) scripts/doctor.py --drift-only; \
	else echo "SKIP drift — tanpa $$HOME/.hermes/skills (mis. runner CI)"; fi

# gerbang lokal sebelum commit: lint + registry + test + drift
check: lint lint-registry test drift

gate-init:
	@echo "gunakan: $(PY_SYS) scripts/init_target.py <slug> && $(PY_SYS) scripts/gate_check.py --target <slug>"

lint-registry:
	$(PY_SYS) scripts/registry_lint.py

release-check:
	@slug=$$($(PY_SYS) -c "import os;runs='runs';c=[(os.path.getmtime(os.path.join(runs,d)),d) for d in (os.listdir(runs) if os.path.isdir(runs) else [])];print(max(c)[1] if c else '')" 2>/dev/null); \
	if [ -z "$$slug" ]; then echo "Tidak ada run di runs/"; exit 1; fi; \
	echo "release gate untuk: runs/$$slug"; \
	$(PY_SYS) scripts/release_check.py --project runs/$$slug

skills-list:
	$(PY_SYS) scripts/install_skills.py --list

# runner 16 tahap (TARGET=<slug>); tanpa TARGET pakai run terbaru di runs/
workflow:
	@slug="$(TARGET)"; \
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
	find . -name "__pycache__" -type d -prune -exec rm -rf {} +
