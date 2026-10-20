"""Başarısız kabuk çağrısı, değişiklik olmadan sınırsız tekrar edilemez."""

from __future__ import annotations

import pytest

from fusion_cli.core.budget import BudgetStop
from fusion_cli.core.events import ToolExecuted
from fusion_cli.engines.agent.loop import run_agent

from .fakes import RecordingSink, ScriptedProvider, model_result, tool_call
from .test_agent_loop import _deps, _kur


@pytest.mark.parametrize("alias", ["run_shell", "bash"])
async def test_ayni_basarisiz_kabuk_cagrisi_sinirli_kesilir(monkeypatch, tmp_path, alias):
    root = tmp_path / "project "
    root.mkdir()
    command = f"cd {root.as_posix().rstrip()} && pwd"
    provider = ScriptedProvider(
        [model_result(tool_calls=[tool_call(alias, command=command)]) for _ in range(9)]
        + [model_result("Dizin bulunamadı; işlem yapılamadı.")]
    )
    _kur(monkeypatch, provider)
    sink = RecordingSink()
    result = await run_agent(
        "Projedeki dizini incele",
        _deps(root, sink, runtime={"agent_max_steps": 20}),
    )
    assert result.stop_reason == BudgetStop.REPEATED_CALL.value
    assert not result.ok
    assert result.model_calls_made <= 5
    assert "aynı" in result.final_text.lower()
    assert len([event for event in sink.events if isinstance(event, ToolExecuted)]) <= 5


async def test_bosluklu_kokte_goreli_kabuk_cagrisi_calisir(monkeypatch, tmp_path):
    root = tmp_path / "project "
    root.mkdir()
    _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(
                    tool_calls=[tool_call("run_shell", command="pwd && printf 'verified\\n'")]
                ),
                model_result("Proje dizini araçla doğrulandı; değişiklik gerekmedi."),
            ]
        ),
    )
    sink = RecordingSink()
    result = await run_agent("Proje dizinini göster", _deps(root, sink))
    assert any(
        message.role == "tool" and str(root) in message.content for message in result.messages
    )
    assert result.stop_reason is None


async def test_basarili_kabuk_onkosulu_duzeltince_ayni_komut_yeniden_calisir(monkeypatch, tmp_path):
    command = "test -d ready"
    _kur(
        monkeypatch,
        ScriptedProvider(
            [
                *[
                    model_result(tool_calls=[tool_call("run_shell", command=command)])
                    for _ in range(4)
                ],
                model_result(tool_calls=[tool_call("run_shell", command="mkdir ready")]),
                model_result(tool_calls=[tool_call("run_shell", command=command)]),
                model_result("Önkoşul düzeltildi ve kontrol başarıyla tamamlandı."),
            ]
        ),
    )
    result = await run_agent(
        "Eksik ready klasörünü oluştur ve kontrol et", _deps(tmp_path, RecordingSink())
    )
    assert result.stop_reason is None, [
        (use.arguments, use.ok, use.output[:180]) for use in result.tool_uses
    ]
    assert any(
        use.name == "run_shell" and use.arguments.get("command") == command and use.ok
        for use in result.tool_uses
    )


async def test_tekrar_durusundan_sonra_ayni_yanittaki_mutasyon_atlanir(monkeypatch, tmp_path):
    def failed(name="run_shell"):
        return tool_call(name, command="test -d missing")

    _kur(
        monkeypatch,
        ScriptedProvider(
            [
                *[
                    model_result(tool_calls=[failed("run_shell" if index % 2 else "bash")])
                    for index in range(4)
                ],
                model_result(
                    tool_calls=[
                        failed(),
                        tool_call("write_file", path="should-not-exist.txt", content="x"),
                    ]
                ),
                model_result("Bitti."),
            ]
        ),
    )
    result = await run_agent(
        "Dosyayı oluştur ve dizini kontrol et", _deps(tmp_path, RecordingSink())
    )
    assert result.stop_reason == BudgetStop.REPEATED_CALL.value
    assert not (tmp_path / "should-not-exist.txt").exists()
    assert any(
        message.role == "tool" and message.name == "write_file" and message.ok is False
        for message in result.messages
    )
