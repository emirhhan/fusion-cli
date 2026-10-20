"""Seçilmiş motorun açık host gereksinimi ve özgün kabul koşulları."""

import argparse
from dataclasses import replace
from types import SimpleNamespace

import pytest

from .test_driver_browser import _apis


def test_requirement_only_uses_same_process_selected_host(tmp_path):
    from evals.driver_browser import bind_browser

    _, host, entry, proof, _ = _apis(tmp_path)
    result = bind_browser(
        None,
        proof,
        observer=None,
        host=host,
        entry=entry,
        process_id=123,
        require_remotion_kit=True,
    )
    assert result.require_remotion_kit is True
    assert not hasattr(result, "remotion_browser")


@pytest.mark.parametrize("fault", ["pid", "source", "unsupported"])
def test_requirement_rejects_wrong_authority_before_factory(tmp_path, fault):
    from evals.driver_browser import bind_browser

    _, host, entry, proof, _ = _apis(tmp_path)
    if fault == "pid":
        proof = replace(proof, pid=99)
    elif fault == "source":
        host.__file__ = str(tmp_path / "other.py")
    else:
        host.AppHostDependencies = lambda: None
    with pytest.raises(ValueError):
        bind_browser(
            None,
            proof,
            observer=None,
            host=host,
            entry=entry,
            process_id=123,
            require_remotion_kit=True,
        )


def test_requirement_without_selected_engine_rejected():
    from evals.driver_engine import selected_command

    with pytest.raises(ValueError):
        selected_command(argparse.Namespace(log=False, require_remotion_kit=True))


def test_runner_host_options_keep_original_timeout_and_config(tmp_path):
    from evals.kabul.runner import Job, RunnerOptions, _driver_command

    options = RunnerOptions(
        1,
        0,
        tmp_path / "config.yaml",
        tmp_path / "engine",
        tmp_path / "manifest.json",
        require_remotion_kit=True,
    )
    job = Job(SimpleNamespace(timeout_s=5400, needs_chrome=False), 1, tmp_path / "work")
    argv = _driver_command(job, job.workdir, "TASK", options)
    assert argv[argv.index("--sure") + 1] == "5400"
    assert "--require-remotion-kit" in argv
    assert options.config == tmp_path / "config.yaml"


def test_runner_browser_requires_complete_pair_and_selected_engine(tmp_path):
    from evals.kabul.runner import RunnerOptions

    with pytest.raises(ValueError):
        RunnerOptions(1, 0, None, remotion_browser_executable=tmp_path / "chrome")
    with pytest.raises(ValueError):
        RunnerOptions(1, 0, None, require_remotion_kit=True)


async def test_runner_config_environment_and_timeout_remain_original(tmp_path, monkeypatch):
    from evals.kabul import runner

    captured = []

    class Process:
        async def communicate(self):
            return b"{}", b""

    async def create(*argv, **kwargs):
        captured.append((argv, kwargs))
        return Process()

    monkeypatch.setattr(runner.asyncio, "create_subprocess_exec", create)
    monkeypatch.setattr(runner, "_inherited_env", lambda: {"ORIGINAL": "unchanged"})
    options = runner.RunnerOptions(1, 0, tmp_path / "config.yaml")
    job = runner.Job(SimpleNamespace(timeout_s=5400, needs_chrome=False), 1, tmp_path)
    await runner._drive(job, tmp_path, "TASK", options)
    assert captured[0][1]["env"] == {
        "ORIGINAL": "unchanged",
        "FUSION_CONFIG": str(tmp_path / "config.yaml"),
    }
    argv = captured[0][0]
    assert argv[argv.index("--sure") + 1] == "5400"


async def test_browser_and_requirement_both_reach_selected_host(tmp_path):
    from evals.driver_browser import HostBrowserSelection, bind_browser

    observer, host, entry, proof, calls = _apis(tmp_path)
    executable = tmp_path / "chrome"
    executable.write_text("existing")
    executable.chmod(0o755)
    choice = HostBrowserSelection(executable, "chrome-for-testing")
    bound = bind_browser(
        choice,
        proof,
        observer=observer,
        host=host,
        entry=entry,
        process_id=123,
        require_remotion_kit=True,
    )
    assert bound.require_remotion_kit is True
    assert await bound.remotion_transport("request") == "observation"
    assert calls == [("request", (executable, "chrome-for-testing"))]


def test_bootstrap_requirement_only_binds_verified_host_without_observer_import(
    tmp_path, monkeypatch
):
    import importlib

    from evals import driver_engine, engine_launcher

    _, host, entry, proof, _ = _apis(tmp_path)
    proof = replace(proof, pid=driver_engine.os.getpid())
    captured = []

    def imported(name):
        if name == "fusion_cli.cli.app_host":
            return host
        pytest.fail("Gereksinim-only observer veya model import etmemeli")

    def launch(root, manifest, path, **kwargs):
        captured.append(kwargs["host_dependencies_factory"](proof, entry))

    monkeypatch.setattr(importlib, "import_module", imported)
    monkeypatch.setattr(engine_launcher, "launch", launch)
    driver_engine.bootstrap(str(tmp_path), "manifest", "proof", False, require_remotion_kit=True)
    assert captured[0].require_remotion_kit is True
