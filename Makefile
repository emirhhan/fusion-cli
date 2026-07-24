# Kalite kapısı — CLAUDE.md: her faz sonunda `make check` temiz olmadan commit atılmaz.
# Araçlar .venv varsa oradan, yoksa PATH'ten çalışır; böylece CI de aynı kapıyı kullanır.
.PHONY: setup venv install format lint type test check clean eval

VENV_BIN := $(if $(wildcard .venv/bin/python),.venv/bin/,)
PY       := $(VENV_BIN)python
RUFF     := $(VENV_BIN)ruff
MYPY     := $(VENV_BIN)mypy
PYTEST   := $(VENV_BIN)pytest

# Tek adımlık kurulum: uygun Python'u bulur, .venv kurar, .env'i hazırlar.
setup:
	./setup.sh --dev

venv:
	./setup.sh

install:
	$(PY) -m pip install --quiet --upgrade pip
	$(PY) -m pip install --quiet -e ".[dev]"

format:
	$(RUFF) format src tests evals prompt_opt

lint:
	$(RUFF) format --check src tests evals prompt_opt
	$(RUFF) check src tests evals prompt_opt

type:
	$(MYPY)

test:
	$(PYTEST)

check: lint type test

# Değerlendirme seti: başlangıç görevlerini koştur, raporu eval-report.json'a yaz.
# GERÇEK model çağrısı yapar (ağ + anahtar gerekir). İki raporu karşılaştırmak için:
#   $(PY) -m evals compare eski.json yeni.json
eval:
	$(PY) -m evals run evals/suite/starter.yaml --out eval-report.json

clean:
	rm -rf .venv .pytest_cache .ruff_cache .mypy_cache src/*.egg-info
