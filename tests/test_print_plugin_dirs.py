"""`fusion -p --plugin-dir` oturumluk eklenti listesini kurar (#301, eklenti alanı #401)."""

from __future__ import annotations

import os
from types import SimpleNamespace

from typer.testing import CliRunner

from fusion_cli.cli import app as app_module
from fusion_cli.cli import print_run
from fusion_cli.cli.print_plugin_dirs import PLUGIN_DIRS_ENV

runner = CliRunner()


def test_plugin_dir_ortam_listesine_eklenir_ve_etkisiz_uyarisi_yok(monkeypatch, tmp_path):
    monkeypatch.setenv(PLUGIN_DIRS_ENV, "")
    first, second = tmp_path / "a", tmp_path / "b"
    first.mkdir()
    second.mkdir()
    seen: list[str] = []

    async def _fake(task, config, **kwargs):
        seen.append(os.environ.get(PLUGIN_DIRS_ENV, ""))
        return SimpleNamespace(
            final_text="tamam",
            ok=True,
            stop_reason=None,
            model_calls_made=1,
            hit_step_limit=False,
            messages=[],
        )

    monkeypatch.setattr(print_run, "run_agent_task", _fake)
    args = ["-p", "--plugin-dir", str(first), "--plugin-dir", str(second)]
    args += ["--plugin-dir", str(first), "x"]
    result = runner.invoke(app_module.app, args)
    assert result.exit_code == 0, result.output
    assert "etkisiz" not in result.output
    assert seen == [os.pathsep.join([str(first.resolve()), str(second.resolve())])]


def test_plugin_dir_tek_yol_alir_sonraki_konumsal_istemdir():
    from fusion_cli.cli.print_argv import expand_variadic

    assert expand_variadic(["--plugin-dir", "a", "sorgu"]) == ["--plugin-dir", "a", "sorgu"]
