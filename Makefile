# Super Dev Builders Ecosystem — task runner
# Interpreter: hormati PY_SYS bila diset; jika tidak, pakai python3 dari PATH.
# JANGAN hardcode /usr/bin/python3 — tidak portabel: di runner CI, setup-python
# menaruh Python di path lain dan /usr/bin/python3 tidak punya pytest.
PY_SYS ?= $(shell command -v python3 || command -v python)

.PHONY: help check lint drift doctor inventory test gate-init lint-registry release-check skills-list install-main clean-pyc

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

# skill terpasang (main + profil) vs sumber repo; exit 1 bila MISSING/DIFF
drift:
	$(PY_SYS) scripts/doctor.py --drift-only

# gerbang lokal sebelum commit: lint + registry + test + drift
check: lint lint-registry test drift

gate-init:
	@echo "gunakan: $(PY_SYS) scripts/init_target.py <slug> && $(PY_SYS) scripts/gate_check.py --target <slug>"

lint-registry:
	$(PY_SYS) scripts/registry_lint.py

release-check:
	@slug=$$(python3 -c "import sys,os;runs='runs';c=[(os.path.getmtime(os.path.join(runs,d)),d) for d in (os.listdir(runs) if os.path.isdir(runs) else [])];print(max(c)[1] if c else '')" 2>/dev/null); \
	if [ -z "$$slug" ]; then echo "Tidak ada run di runs/"; exit 1; fi; \
	echo "release gate untuk: runs/$$slug"; \
	$(PY_SYS) scripts/release_check.py --project runs/$$slug

skills-list:
	$(PY_SYS) scripts/install_skills.py --list

install-main:
	$(PY_SYS) scripts/install_skills.py --main --dry-run

clean-pyc:
	find . -name "__pycache__" -type d -prune -exec rm -rf {} +
