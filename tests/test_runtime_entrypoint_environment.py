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
