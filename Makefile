PY=.venv/bin

setup:
	python3 -m venv .venv && $(PY)/pip install -q -e ".[dev]"

data:
	$(PY)/ledgerly-generate --seed 42 --out data

report:
	$(PY)/cockpit build --db data/ledgerly.duckdb --out report

test:
	$(PY)/pytest -q

all: data report test

.PHONY: setup data report test all
