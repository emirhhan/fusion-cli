"""`--exclude-dynamic-system-prompt-sections` (#301)."""

from __future__ import annotations

from types import SimpleNamespace

from typer.testing import CliRunner

from fusion_cli.cli import app as app_module
from fusion_cli.cli import print_run
from fusion_cli.engines.agent import dynamic_sections, loop
from fusion_cli.engines.agent.loop import run_agent

from .fakes import ScriptedProvider, model_result
from .test_system_prompt_layers import _deps

runner = CliRunner()
_BELLEK = "BELLEK KONUMU: /home/kisi/.fusion/memory"


def _texts(messages, role: str) -> str:
    return "\n".join(str(m.content) for m in messages if m.role == role)


async def _run(monkeypatch, tmp_path, *, exclude: bool, system_prompt: str | None = None):
    provider = ScriptedProvider([model_result("Tamam.")])
    monkeypatch.setattr(loop, "build_provider", lambda _spec, **_kwargs: provider)
    monkeypatch.setattr(loop, "memory_prompt_block", lambda _deps: _BELLEK)
    with dynamic_sections.excluded(exclude):
        await run_agent(
            "Merhaba", _deps(tmp_path, "nvidia_nim/ornek-model"), system_prompt=system_prompt
        )
    return provider.seen_messages[0]


async def test_bayrak_bellek_konumunu_ilk_kullanici_mesajina_tasir(monkeypatch, tmp_path):
    messages = await _run(monkeypatch, tmp_path, exclude=True)
    assert _BELLEK not in _texts(messages, "system")
    assert _BELLEK in _texts(messages, "user")
    assert messages[-1].content == "Merhaba"


async def test_bayraksiz_bellek_sistem_isteminde_kalir(monkeypatch, tmp_path):
    messages = await _run(monkeypatch, tmp_path, exclude=False)
    assert _BELLEK in _texts(messages, "system")
    assert _BELLEK not in _texts(messages, "user")


async def test_system_prompt_verilince_bayrak_yok_sayilir(monkeypatch, tmp_path):
    messages = await _run(monkeypatch, tmp_path, exclude=True, system_prompt="ÖZEL İSTEM")
    assert _BELLEK in _texts(messages, "system")


def test_p_bayragi_artik_etkisiz_uyarisi_vermez_ve_kosuya_iletir(monkeypatch):
    seen: list[bool] = []

    async def _fake(task, config, **kwargs):
        seen.append(dynamic_sections.active())
        return SimpleNamespace(
            final_text="t",
            ok=True,
            stop_reason=None,
            model_calls_made=1,
            hit_step_limit=False,
            messages=[],
        )

    monkeypatch.setattr(print_run, "run_agent_task", _fake)
    result = runner.invoke(app_module.app, ["-p", "x", "--exclude-dynamic-system-prompt-sections"])
    assert result.exit_code == 0, result.output
    assert seen == [True]
    assert "exclude-dynamic" not in result.output
    assert dynamic_sections.active() is False
