"""Seçilmiş kaynak modüllerinde yalnız host tarayıcı seçimi bağlanır."""

from pathlib import Path
from types import SimpleNamespace

import pytest
from evals.driver_browser import HostBrowserSelection, bind_browser
from evals.engine_proof import ImportedEngineProof


def _apis(tmp_path):
    calls = []

    async def observe(request, *, browser):
        calls.append((request, browser))
        return "observation"

    observer = SimpleNamespace(
        __file__=str(tmp_path / "src/fusion_cli/tools/remotion_observe.py"),
        ExistingBrowser=lambda executable, mode: (executable, mode),
        observe_frame=observe,
    )
    host = SimpleNamespace(
        __file__=str(tmp_path / "src/fusion_cli/cli/app_host.py"),
        AppHostDependencies=lambda **kwargs: SimpleNamespace(**kwargs),
    )
    entry = SimpleNamespace(
        __file__=str(tmp_path / "src/fusion_cli/cli/app.py"),
        main=lambda *, host_dependencies=None: None,
    )
    proof = ImportedEngineProof(
        123,
        str(tmp_path / "src/fusion_cli/__init__.py"),
        entry.__file__,
        str(tmp_path),
        "a" * 64,
        "b" * 40,
    )
    return observer, host, entry, proof, calls


async def test_host_selection_binds_only_selected_module_transport(tmp_path):
    observer, host, entry, proof, calls = _apis(tmp_path)
    executable = tmp_path / "chrome"
    executable.write_text("existing")
    executable.chmod(0o755)
    choice = HostBrowserSelection(executable, "chrome-for-testing")
    binding = bind_browser(choice, proof, observer=observer, host=host, entry=entry, process_id=123)
    request = object()
    assert await binding.remotion_transport(request) == "observation"
    assert calls == [(request, (executable, "chrome-for-testing"))]


def test_absent_choice_is_noop_without_inspecting_modules():
    assert bind_browser(None, None, observer=None, host=None, entry=None, process_id=123) is None


@pytest.mark.parametrize(
    "case", ["missing", "directory", "relative", "mode", "not_executable", "secret"]
)
def test_invalid_host_selection_rejected_without_fallback(tmp_path, case):
    executable = tmp_path / (".env-chrome" if case == "secret" else "chrome")
    if case == "directory":
        executable.mkdir()
    elif case != "missing":
        executable.write_text("existing")
        executable.chmod(0o644 if case == "not_executable" else 0o755)
    if case == "relative":
        executable = Path("chrome")
    with pytest.raises(ValueError):
        HostBrowserSelection(executable, "invalid" if case == "mode" else "chrome-for-testing")


@pytest.mark.parametrize(
    "case",
    [
        "pid",
        "observer_source",
        "host_source",
        "entry_source",
        "entry_api",
        "observer_api",
        "host_api",
    ],
)
def test_selected_source_or_unsupported_api_is_explicit_error(tmp_path, case):
    observer, host, entry, proof, calls = _apis(tmp_path)
    executable = tmp_path / "chrome"
    executable.write_text("existing")
    executable.chmod(0o755)
    if case.endswith("_source"):
        {"observer_source": observer, "host_source": host, "entry_source": entry}[
            case
        ].__file__ = str(tmp_path / "outside.py")
    elif case == "entry_api":
        entry.main = lambda: None
    elif case == "observer_api":
        observer.observe_frame = lambda request: None
    elif case == "host_api":
        host.AppHostDependencies = lambda: None
    with pytest.raises(ValueError, match=r"desteklenmiyor|kaynak|süreç"):
        bind_browser(
            HostBrowserSelection(executable, "chrome-for-testing"),
            proof,
            observer=observer,
            host=host,
            entry=entry,
            process_id=999 if case == "pid" else 123,
        )
    assert calls == []


def test_reference_missing_factory_is_explicitly_unsupported(tmp_path):
    observer, host, entry, proof, calls = _apis(tmp_path)
    del observer.ExistingBrowser
    executable = tmp_path / "chrome"
    executable.write_text("existing")
    executable.chmod(0o755)
    with pytest.raises(ValueError, match="desteklenmiyor"):
        bind_browser(
            HostBrowserSelection(executable, "headless-shell"),
            proof,
            observer=observer,
            host=host,
            entry=entry,
            process_id=123,
        )
    assert calls == []
