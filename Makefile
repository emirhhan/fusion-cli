# Kalite kapısı — CLAUDE.md: her faz sonunda `make check` temiz olmadan commit atılmaz.
# Araçlar .venv varsa oradan, yoksa PATH'ten çalışır; böylece CI de aynı kapıyı kullanır.
.PHONY: setup venv install format lint type test deadlock check clean eval app-check app-visual runtime-bundle app-package

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
	$(RUFF) format src tests evals prompt_opt desktop_build

lint:
	$(RUFF) format --check src tests evals prompt_opt desktop_build
	$(RUFF) check src tests evals prompt_opt desktop_build

type:
	$(MYPY)

test:
	$(PYTEST)

# Kilitlenme ağı — kapıların ETKİLEŞİMİNİ koruyan paketler.
#
# Ayrı bir hedef olarak durur çünkü `test` içinde eriyip gitmemeli: bugüne kadarki
# kilitlenmelerin hepsi tek tek doğru yazılmış kapıların birbirini engellemesinden
# doğdu ve birim testler bu sınıfı GÖREMEZ. Bir dosya yanlışlıkla silinir ya da
# yeniden adlandırılırsa `deadlock` hedefi "no tests ran" ile kırılır; `test`
# hedefinde bu sessizce kaybolurdu.
DEADLOCK_SUITES := tests/test_deadlock_property.py tests/test_gate_matrix.py \
                   tests/test_web_build_runs.py tests/test_eval_criteria_sound.py

deadlock:
	$(PYTEST) $(DEADLOCK_SUITES)

check: lint type test deadlock

app-check:
	cd app && npm ci && npm run check

app-visual:
	cd app && npm ci && npx playwright install chromium && npm run test:visual

runtime-bundle:
	$(PY) -m pip install -e ".[desktop,mcp,gateway]"
	cd app && npm run runtime:build && npm run runtime:smoke

app-package:
	$(PY) -m pip install -e ".[desktop,mcp,gateway]"
	cd app && npm run bundle:mac
	$(PY) desktop_build/macos/smoke_app_bundle.py app/src-tauri/target/release/bundle/macos/Fusion.app

# Değerlendirme seti: başlangıç görevlerini koştur, raporu eval-report.json'a yaz.
# GERÇEK model çağrısı yapar (ağ + anahtar gerekir). İki raporu karşılaştırmak için:
#   $(PY) -m evals compare eski.json yeni.json
eval:
	$(PY) -m evals run evals/suite/starter.yaml --out eval-report.json

clean:
	rm -rf .venv .pytest_cache .ruff_cache .mypy_cache src/*.egg-info
