"""Sohbet kipi: Fusion sohbette dosya yazmaz ve plan motoruna girmez.

Ölçüldü (17 Eylül denetimi): sohbet kipinde "bana bir kampanya planı yap"
isteği plan motoruna girip diske `KAMPANYA_PLANI.md` yazdı; planın kendisi
sohbette hiç görünmedi. Claude'da sohbet turu dosya oluşturmaz.
"""

from __future__ import annotations

from pathlib import Path

from fusion_cli.engines.agent.chat_mode import chat_execution, chat_tool_names
from fusion_cli.engines.agent.execution_policy import ExecutionPolicy


def test_sohbet_kipinde_degistirme_kapali() -> None:
    politika = ExecutionPolicy(is_web=True, allow_mutation=True, complex_task=True)

    sohbet = chat_execution(politika)

    assert sohbet.allow_mutation is False
    assert sohbet.complex_task is False
    assert sohbet.required_effect is None
    assert sohbet.requires_tool_evidence is False
    assert "sohbet" in sohbet.mutation_block_reason.lower()


def test_sohbet_kipinde_yalniz_okuyan_araclar_sunulur() -> None:
    from fusion_cli.tools import build_registry

    registry = build_registry()
    izinli = chat_tool_names(registry)

    assert "read_file" in izinli
    assert "web_search" in izinli
    assert "git" in izinli  # salt-okunur git; commit/push ayrı araçta
    assert "write_file" not in izinli
    assert "run_shell" not in izinli
    assert "edit_file" not in izinli
    assert "download_file" not in izinli


async def test_sohbet_turu_dosya_yazmaz(tmp_path: Path, monkeypatch) -> None:
    """Model yazmayı denese bile sohbet turunda dosya oluşmaz."""
    from fusion_cli.engines.agent.loop import run_agent

    from .agent_harness import install_provider, web_deps
    from .fakes import RecordingSink, ScriptedProvider, model_result, tool_call

    sink = RecordingSink()
    deps = web_deps(tmp_path, sink)
    install_provider(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(
                    "Planı dosyaya yazıyorum.",
                    tool_calls=(
                        tool_call("write_file", path="kampanya.md", content="plan"),
                    ),
                ),
                model_result("Kampanya planı: hedef kitle, bütçe, takvim."),
            ]
        ),
    )

    sonuc = await run_agent("bana bir kampanya planı yap", deps, chat_mode=True)

    assert not (tmp_path / "kampanya.md").exists()
    assert sonuc.final_text


async def test_masaustu_sohbet_kipinde_chat_mode_gecer(tmp_path: Path, monkeypatch) -> None:
    """Masaüstü 'sohbet' kipinde turu sohbet turu olarak başlatmalı."""
    from fusion_cli.cli import session as cli_session

    yakalanan: dict[str, object] = {}

    async def sahte_run_agent(task: str, deps: object, **kwargs: object) -> object:
        yakalanan.update(kwargs)

        from fusion_cli.engines.agent.loop import AgentOutcome

        return AgentOutcome(final_text="cevap", messages=[], ok=True)

    monkeypatch.setattr(cli_session, "run_agent", sahte_run_agent)
    await cli_session._run_agent_with_mcp(
        "merhaba",
        deps=None,
        config=_bos_config(),
        bus=_SessizVeriyolu(),
        history=None,
        mode=cli_session.ApprovalMode.AUTO,
        extra_system="",
        system_prompt=None,
        chat_mode=True,
    )

    assert yakalanan["chat_mode"] is True


def _bos_config():
    from .fakes import make_config

    return make_config()


class _SessizVeriyolu:
    def publish(self, _event: object) -> None:
        return None
