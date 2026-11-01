"""`--betas` (#301): Anthropic API isteklerine `anthropic-beta` başlığı."""

from __future__ import annotations

from types import SimpleNamespace

from typer.testing import CliRunner

from fusion_cli.cli import app as app_module
from fusion_cli.cli import print_run
from fusion_cli.providers import beta_headers
from fusion_cli.providers.litellm_provider import LiteLlmProvider

from .fakes import request

runner = CliRunner()


def test_anthropic_modeline_beta_basligi_eklenir():
    provider = LiteLlmProvider("anthropic/claude-sonnet-4-5", role="agent")
    with beta_headers.enabled(("interleaved-thinking-2025-05-14", "context-1m")):
        kwargs = provider._call_kwargs(request(), stream=False)
    assert kwargs["extra_headers"] == {
        "anthropic-beta": "interleaved-thinking-2025-05-14,context-1m"
    }


def test_baska_saglayiciya_ve_bayraksiz_baslik_gitmez():
    other = LiteLlmProvider("nvidia_nim/ornek-model", role="agent")
    with beta_headers.enabled(("x",)):
        assert "extra_headers" not in other._call_kwargs(request(), stream=False)
    claude = LiteLlmProvider("anthropic/claude-sonnet-4-5", role="agent")
    assert "extra_headers" not in claude._call_kwargs(request(), stream=False)


def test_degerler_virgul_ve_tekrarla_ayrilir():
    assert beta_headers.parse(["a,b", "b", "c d"]) == ("a", "b", "c", "d")


def test_p_betas_kosu_boyunca_etkin_ve_etkisiz_uyarisi_yok(monkeypatch):
    seen: list[tuple[str, ...]] = []

    async def _fake(task, config, **kwargs):
        seen.append(beta_headers.current())
        return SimpleNamespace(
            final_text="t",
            ok=True,
            stop_reason=None,
            model_calls_made=1,
            hit_step_limit=False,
            messages=[],
        )

    monkeypatch.setattr(print_run, "run_agent_task", _fake)
    result = runner.invoke(app_module.app, ["-p", "x", "--betas", "interleaved-thinking"])
    assert result.exit_code == 0, result.output
    assert seen == [("interleaved-thinking",)]
    assert "--betas" not in result.output
    assert beta_headers.current() == ()
