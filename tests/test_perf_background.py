"""Performans: ders çıkarımı gibi tur-sonrası işler cevabı BLOKLAMAMALI.

`run_agent_task` verilen `background`'ı motora iletmezse ders çıkarımı (bir model
çağrısı) tur bitişini bekletir ve kullanıcı bir sonraki mesajı yazamaz — gözlemlenen
"ekstra gecikme". Bu test, background'ın deps'e geçtiğini kilitler.
"""

from __future__ import annotations

import fusion_cli.cli.session as session
from fusion_cli.cli.session import run_agent_task
from fusion_cli.core.concurrency import BackgroundTasks
from fusion_cli.engines.agent.loop import AgentOutcome

from .fakes import make_config


class _NoPrompter:
    async def confirm(self, request):
        return False

    async def ask(self, question):
        return ""


async def test_run_agent_task_backgroundi_motora_iletir(monkeypatch):
    yakalanan = {}

    async def _sahte_run_agent(task, deps, **kwargs):
        yakalanan["background"] = deps.background
        return AgentOutcome(final_text="tamam", messages=[])

    monkeypatch.setattr(session, "run_agent", _sahte_run_agent)
    tasks = BackgroundTasks()

    await run_agent_task(
        "görev",
        make_config(),
        sinks=(),
        prompter_factory=lambda _drain: _NoPrompter(),
        interactive=False,
        background=tasks,
    )

    assert yakalanan["background"] is tasks


async def test_background_verilmezse_none_gecer(monkeypatch):
    """Yedek: background verilmezse eski davranış (bloklayan) korunur, ama None açıkça geçer."""
    yakalanan = {}

    async def _sahte_run_agent(task, deps, **kwargs):
        yakalanan["background"] = deps.background
        return AgentOutcome(final_text="x", messages=[])

    monkeypatch.setattr(session, "run_agent", _sahte_run_agent)

    await run_agent_task(
        "görev",
        make_config(),
        sinks=(),
        prompter_factory=lambda _drain: _NoPrompter(),
        interactive=False,
    )

    assert yakalanan["background"] is None
