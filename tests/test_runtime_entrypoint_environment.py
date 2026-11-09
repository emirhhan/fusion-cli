"""Frozen startup must not redirect a user's installed browser cache."""

from __future__ import annotations

import os
import runpy
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

import pytest

ENTRYPOINT = Path(__file__).resolve().parents[1] / "desktop_build/runtime/entrypoint.py"


@pytest.fixture(autouse=True)
def isolated_dotenv_candidates(monkeypatch):
    from fusion_cli.config import loader

    monkeypatch.setattr(loader, "env_file_candidates", lambda: [])
    monkeypatch.setattr(loader, "_DOTENV_KEYS", frozenset())


def _run_entrypoint(
    monkeypatch: pytest.MonkeyPatch, *, prepare_cli: Callable[[], None] | None = None
) -> list[str | None]:
    observed: list[str | None] = []
    app = ModuleType("fusion_cli.cli.app")

    def main() -> None:
        if prepare_cli is not None:
            prepare_cli()
        observed.append(os.environ.get("PLAYWRIGHT_BROWSERS_PATH"))

    app.main = main
    monkeypatch.setitem(sys.modules, "fusion_cli.cli.app", app)
    runpy.run_path(str(ENTRYPOINT), run_name="__main__")
    return observed


def test_frozen_startup_uses_normal_playwright_cache_before_cli_runs(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.delenv("PLAYWRIGHT_BROWSERS_PATH", raising=False)

    assert _run_entrypoint(monkeypatch) == [""]


@pytest.mark.parametrize("configured", ["0", "/owned/browser-cache", ""])
def test_frozen_startup_preserves_explicit_browser_cache(monkeypatch, configured):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", configured)

    assert _run_entrypoint(monkeypatch) == [configured]


def test_unfrozen_entrypoint_retains_playwright_default(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.delenv("PLAYWRIGHT_BROWSERS_PATH", raising=False)

    assert _run_entrypoint(monkeypatch) == [None]


def test_bootstrap_default_allows_user_dotenv_browser_cache(monkeypatch, tmp_path):
    from fusion_cli.config import loader

    dotenv = tmp_path / ".env"
    dotenv.write_text("PLAYWRIGHT_BROWSERS_PATH=/user/configured-cache\n", encoding="utf-8")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.delenv("PLAYWRIGHT_BROWSERS_PATH", raising=False)
    monkeypatch.setattr(loader, "env_file_candidates", lambda: [dotenv])
    monkeypatch.setattr(loader, "_apply_stored_secrets", lambda: None)
    monkeypatch.setattr(loader, "_DOTENV_KEYS", frozenset())

    assert _run_entrypoint(monkeypatch, prepare_cli=loader.load_environment) == [
        "/user/configured-cache"
    ]


def test_frozen_startup_selects_bundled_tokenizers_before_cli(monkeypatch, tmp_path):
    bundle = tmp_path / "fusion-tokenizer-cache"
    bundle.mkdir()
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    monkeypatch.delenv("TIKTOKEN_CACHE_DIR", raising=False)
    monkeypatch.delenv("DATA_GYM_CACHE_DIR", raising=False)
    observed = []
    _run_entrypoint(
        monkeypatch, prepare_cli=lambda: observed.append(os.environ.get("TIKTOKEN_CACHE_DIR"))
    )
    assert observed == [str(bundle)]


@pytest.mark.parametrize("name", ["TIKTOKEN_CACHE_DIR", "DATA_GYM_CACHE_DIR"])
@pytest.mark.parametrize("value", ["", "/explicit/cache"])
def test_frozen_tokenizers_preserve_explicit_cache_and_empty_optout(
    monkeypatch, tmp_path, name, value
):
    (tmp_path / "fusion-tokenizer-cache").mkdir()
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    monkeypatch.delenv("TIKTOKEN_CACHE_DIR", raising=False)
    monkeypatch.delenv("DATA_GYM_CACHE_DIR", raising=False)
    monkeypatch.setenv(name, value)
    observed = []
    _run_entrypoint(monkeypatch, prepare_cli=lambda: observed.append(dict(os.environ)))
    assert observed[0][name] == value
    if name == "DATA_GYM_CACHE_DIR":
        assert "TIKTOKEN_CACHE_DIR" not in observed[0]


def test_source_entrypoint_does_not_select_bundled_tokenizers(monkeypatch, tmp_path):
    (tmp_path / "fusion-tokenizer-cache").mkdir()
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    monkeypatch.delenv("TIKTOKEN_CACHE_DIR", raising=False)
    monkeypatch.delenv("DATA_GYM_CACHE_DIR", raising=False)
    observed = []
    _run_entrypoint(
        monkeypatch, prepare_cli=lambda: observed.append(os.environ.get("TIKTOKEN_CACHE_DIR"))
    )
    assert observed == [None]


@pytest.mark.parametrize("name", ["TIKTOKEN_CACHE_DIR", "DATA_GYM_CACHE_DIR"])
def test_frozen_tokenizer_default_allows_user_dotenv_cache(monkeypatch, tmp_path, name):
    from fusion_cli.config import loader

    (tmp_path / "fusion-tokenizer-cache").mkdir()
    dotenv = tmp_path / ".env"
    dotenv.write_text(
        f"{name}=/user/tokenizer-cache\nBOOTSTRAP_UNRELATED_CANARY=yes\n", encoding="utf-8"
    )
    monkeypatch.delenv("BOOTSTRAP_UNRELATED_CANARY", raising=False)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    monkeypatch.delenv("TIKTOKEN_CACHE_DIR", raising=False)
    monkeypatch.delenv("DATA_GYM_CACHE_DIR", raising=False)
    monkeypatch.setattr(loader, "env_file_candidates", lambda: [dotenv])
    monkeypatch.setattr(loader, "_DOTENV_KEYS", frozenset())
    secret_reads = []
    monkeypatch.setattr(loader, "_apply_stored_secrets", lambda: secret_reads.append(True))
    observed = []

    def cli():
        assert "BOOTSTRAP_UNRELATED_CANARY" not in os.environ
        assert secret_reads == []  # bootstrap must not read stored credentials
        loader.load_environment()
        observed.append(dict(os.environ))

    _run_entrypoint(monkeypatch, prepare_cli=cli)
    assert observed[0][name] == "/user/tokenizer-cache"
    if name == "DATA_GYM_CACHE_DIR":
        assert "TIKTOKEN_CACHE_DIR" not in observed[0]
    assert secret_reads == [True]  # only normal loader phase owns secret reads


@pytest.mark.parametrize("name", ["TIKTOKEN_CACHE_DIR", "DATA_GYM_CACHE_DIR"])
def test_frozen_tokenizer_process_cache_wins_over_dotenv(monkeypatch, tmp_path, name):
    from fusion_cli.config import loader

    (tmp_path / "fusion-tokenizer-cache").mkdir()
    dotenv = tmp_path / ".env"
    dotenv.write_text(f"{name}=/dotenv/cache\n", encoding="utf-8")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    monkeypatch.delenv("TIKTOKEN_CACHE_DIR", raising=False)
    monkeypatch.delenv("DATA_GYM_CACHE_DIR", raising=False)
    monkeypatch.setenv(name, "/process/cache")
    monkeypatch.setattr(loader, "env_file_candidates", lambda: [dotenv])
    monkeypatch.setattr(loader, "_DOTENV_KEYS", frozenset())
    monkeypatch.setattr(loader, "_apply_stored_secrets", lambda: None)
    observed = []
    _run_entrypoint(
        monkeypatch,
        prepare_cli=lambda: (loader.load_environment(), observed.append(dict(os.environ))),
    )
    assert observed[0][name] == "/process/cache"


@pytest.mark.parametrize("name", ["TIKTOKEN_CACHE_DIR", "DATA_GYM_CACHE_DIR"])
def test_frozen_empty_process_cache_optout_survives_conflicting_dotenv(monkeypatch, tmp_path, name):
    from fusion_cli.config import loader

    dotenv = tmp_path / ".env"
    dotenv.write_text(f"{name}=/dotenv/cache\n", encoding="utf-8")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setenv(name, "")
    monkeypatch.setattr(loader, "env_file_candidates", lambda: [dotenv])
    monkeypatch.setattr(loader, "_apply_stored_secrets", lambda: None)
    _run_entrypoint(monkeypatch, prepare_cli=loader.load_environment)
    assert os.environ[name] == ""


def test_frozen_cache_variables_retain_tiktoken_priority_across_sources(monkeypatch, tmp_path):
    from fusion_cli.config import loader

    dotenv = tmp_path / ".env"
    dotenv.write_text("TIKTOKEN_CACHE_DIR=/dotenv/high-priority-cache\n", encoding="utf-8")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.delenv("TIKTOKEN_CACHE_DIR", raising=False)
    monkeypatch.setenv("DATA_GYM_CACHE_DIR", "/process/lower-priority-cache")
    monkeypatch.setattr(loader, "env_file_candidates", lambda: [dotenv])
    monkeypatch.setattr(loader, "_apply_stored_secrets", lambda: None)
    _run_entrypoint(monkeypatch, prepare_cli=loader.load_environment)
    assert os.environ["TIKTOKEN_CACHE_DIR"] == "/dotenv/high-priority-cache"
    assert os.environ["DATA_GYM_CACHE_DIR"] == "/process/lower-priority-cache"
