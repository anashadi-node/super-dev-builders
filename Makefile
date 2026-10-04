# Super Dev Builders Ecosystem — task runner
PY_SYS := /usr/bin/python3

.PHONY: help doctor inventory test gate-init lint-registry release-check skills-list install-main clean-pyc

help:
	@grep -E "^[a-z-]+:" Makefile | sed "s/:.*//" | column -c 80

doctor:
	$(PY_SYS) scripts/doctor.py

inventory:
	$(PY_SYS) scripts/inventory_ecosystem.py --out reports/inventory_after.json

test:
	$(PY_SYS) -m pytest tests -q

gate-init:
	@echo "gunakan: $(PY_SYS) scripts/init_target.py <slug> && $(PY_SYS) scripts/gate_check.py --target <slug>"

lint-registry:
	$(PY_SYS) scripts/registry_lint.py

release-check:
	$(PY_SYS) scripts/release_check.py --project .

skills-list:
	$(PY_SYS) scripts/install_skills.py --list

install-main:
	$(PY_SYS) scripts/install_skills.py --main --dry-run

clean-pyc:
	find . -name "__pycache__" -type d -prune -exec rm -rf {} +
