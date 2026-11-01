"""Üretilen depo haritasındaki tanım adları sır taşımaz."""

from __future__ import annotations

import pytest

from fusion_cli.engines.agent.loop import run_agent

from .fakes import RecordingSink, ScriptedProvider, model_result
from .test_agent_loop import TAM_CEVAP, _deps, _kur


@pytest.mark.parametrize("source_kind", ["definition", "docstring", "comment"])
async def test_gercek_provider_isteginde_harita_sirri_maskelenir(
    tmp_path, monkeypatch, source_kind
):
    secret = "ghp_" + "Z" * 36
    source = f"def {secret}():\n    pass\n"
    if source_kind == "docstring":
        source = '"""\n' + source + '"""\ndef safe(): pass\n'
    elif source_kind == "comment":
        source = f"# {secret}\ndef safe(): pass\n"
    (tmp_path / "app.py").write_text(source)
    sink = RecordingSink()
    provider = _kur(monkeypatch, ScriptedProvider([model_result(TAM_CEVAP)]))
    deps = _deps(tmp_path, sink, runtime={"repo_map_chars": 4000})
    await run_agent("app.py dosyasını incele", deps)
    assert provider.seen_messages
    text = "\n".join(message.content for message in provider.seen_messages[0])
    assert "app.py" in text
    assert secret not in text
